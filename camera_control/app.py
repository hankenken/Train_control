"""Local camera/vision prototype for LattePanda Windows and legacy Pi. No GPIO or physical-output implementation."""
from __future__ import annotations
import argparse
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import copy
import json
import math
import threading
import time

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool, StrictInt, StrictFloat, ConfigDict

from .routes import RouteManager
from .sources import DemoSource, ReplaySource, PiSource, USBSource, clock
from .vision import VisionEngine
from .calibration import build_calibration

ROOT = Path(__file__).resolve().parent


def read_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    if config.get('outputs_enabled') is not False:
        raise ValueError('この試作ではoutputs_enabled:falseが必須です。実出力機能はありません。')
    cameras = config.get('cameras', [])
    if not 1 <= len(cameras) <= 2:
        raise ValueError('カメラは1〜2台で指定してください')
    ids = [c['id'] for c in cameras]
    if len(set(ids)) != len(ids):
        raise ValueError('camera idが重複しています')
    route_ids = {l['id'] for l in config['routes']['lanes']}
    for lane in config.get('vision', {}).get('lanes', []):
        if lane['camera'] not in ids or lane['id'] not in route_ids:
            raise ValueError('検知レーンのcamera/idが設定と一致しません')
    for camera in cameras:
        fps = camera.get('fps', 15)
        if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not math.isfinite(fps) or not 1 <= fps <= 60:
            raise ValueError('fpsは1〜60で指定してください')
        if 'path' in camera:
            camera['path'] = str((path.parent/camera['path']).resolve())
    for name, minimum, maximum in [('preview_fps',1,10),('stale_frame_s',.1,10)]:
        value=config.get(name,4 if name=='preview_fps' else .75)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:
            raise ValueError(f'{name}は{minimum}〜{maximum}で指定してください')
    indices=[c['index'] for c in cameras if 'index' in c]
    if len(indices)!=len(set(indices)):
        raise ValueError('camera indexが重複しています')
    devices=[c['device'] for c in cameras if 'device' in c]
    if any(isinstance(d,bool) or not isinstance(d,int) or d<0 for d in devices) or len(devices)!=len(set(devices)):
        raise ValueError('USB deviceは重複しない0以上の整数で指定してください')
    for c in cameras:
        if 'device' not in c:continue
        for key,default in [('capture_size',[1920,1080]),('processing_size',[1280,720])]:
            size=c.get(key,default)
            if not isinstance(size,list) or len(size)!=2 or any(isinstance(n,bool) or not isinstance(n,int) or n<=0 for n in size):
                raise ValueError(key+'は正の整数2個で指定してください')
        if c.get('backend','dshow') not in ('dshow','msmf','auto'):
            raise ValueError('不明なUSB backendです')
    return config


class Runtime:
    def __init__(self, config, mode='demo', log_path=None):
        if config.get('outputs_enabled') is not False:
            raise ValueError('実機出力を有効化する設定はありません')
        self.config = copy.deepcopy(config)
        self.mode = mode
        if mode not in ('demo', 'pi', 'replay', 'usb'):
            raise ValueError('不明な実行モードです')
        self.manager = RouteManager(config['routes'])
        opts = dict(config.get('vision', {}))
        lanes = opts.pop('lanes', [])
        self.engine = VisionEngine(lanes, **opts)
        self.vision_lanes = lanes
        self.sources = {}
        epoch = clock()
        for c in config['cameras']:
            cls = {'demo': DemoSource, 'pi': PiSource, 'replay': ReplaySource, 'usb': USBSource}[mode]
            self.sources[c['id']] = cls(c, epoch) if mode == 'demo' else cls(c)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.running = False
        self.paused = False
        self.backgrounds = {}
        self.tracks = {}
        self.warnings = {}
        self.jpeg = {}
        self.preview_times = {}
        self.processed = {}
        self.metrics = {}
        self.events = deque(maxlen=100)
        self.log_path = Path(log_path).resolve() if log_path else None
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == 'demo':
            for ident in self.sources:
                self.set_background_image(ident, DemoSource.empty_image())

    def record(self, entry):
        self.events.appendleft(entry)
        if self.log_path:
            try:
                with self.log_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, ensure_ascii=False)+'\n')
            except OSError as exc:
                self.warnings['log'] = [f'ログを書き込めません: {exc}']

    def start(self):
        self.running = True
        for source in self.sources.values():
            source.start()
        self.thread = threading.Thread(target=self._run, name='vision', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        for source in self.sources.values():
            source.stop()
        self.running = False

    def set_background_image(self, camera, image):
        with self.lock:
            self.engine.set_background(camera, image)
            self.backgrounds[camera] = image.copy()
            self.tracks[camera] = []

    def capture_background(self, camera):
        if camera not in self.sources:
            raise KeyError(camera)
        source = self.sources[camera]
        frame = source.latest()
        if frame is None or source.error or clock()-frame.timestamp > self.config.get('stale_frame_s', .75):
            raise ValueError('最新の正常な映像がありません')
        with self.lock:
            self.hold_active(camera, '背景を再登録しました。通過状態を確認してください')
            self.set_background_image(camera, frame.image)
            self.record({'kind': 'background_set', 'camera': camera, 'timestamp': clock()})
        return {'accepted': True, 'camera': camera}

    def hold_active(self, camera, reason):
        owned = {l['id'] for l in self.vision_lanes if l['camera'] == camera}
        for lane in self.manager.status(clock())['lanes']:
            if lane['id'] in owned and lane['state'] in ('waiting', 'locked'):
                self.manager.mark_uncertain(lane['id'], reason, clock())

    def pause(self, paused):
        with self.lock:
            if paused != self.paused:
                for camera in self.sources:
                    self.hold_active(camera, '一時停止／再開により追跡の連続性がありません')
                # Never form a trajectory across the unprocessed pause interval.
                for camera, image in self.backgrounds.items():
                    self.engine.set_background(camera, image)
                    self.tracks[camera] = []
                self.paused = paused
                self.record({'kind': 'pause', 'paused': paused, 'timestamp': clock()})
        return {'accepted': True, 'paused': self.paused}

    def release(self, lane, confirm_clear):
        with self.lock:
            result = self.manager.release(lane, confirm_clear, clock())
            if result['accepted']:
                self.engine.reset_lane(lane)
                self.record({'kind': 'manual_release', 'lane': lane, 'timestamp': clock()})
            return result

    def apply_calibration(self, value):
        camera=value['camera']
        if camera not in self.sources: raise ValueError('不明なカメラです')
        frame=self.sources[camera].latest()
        if frame is None or self.sources[camera].error or clock()-frame.timestamp>self.config.get('stale_frame_s',.75):
            raise ValueError('最新の正常なカメラ映像を取得してから設定してください')
        with self.lock:
            proposed=build_calibration(self.config,value,[frame.image.shape[1],frame.image.shape[0]])
            opts=copy.deepcopy(proposed['vision']);lanes=opts.pop('lanes',[])
            engine=VisionEngine(lanes,**opts)
            affected={camera}|{l['camera'] for l in self.vision_lanes if l['id']==value['lane']}
            backgrounds={c:im for c,im in self.backgrounds.items() if c not in affected and any(l['camera']==c for l in lanes)}
            for c,im in backgrounds.items(): engine.set_background(c,im)
            self.manager.update_settings(proposed['routes']) # Atomic validation before mutation.
            self.engine,self.config,self.vision_lanes=engine,proposed,lanes
            self.backgrounds=backgrounds; self.tracks={};self.warnings={};self.preview_times={}
            for c,source in self.sources.items():
                latest=source.latest()
                if latest:self.processed[c]=latest.sequence
            self.record({'kind':'calibration_set','camera':camera,'lane':value['lane'],'timestamp':clock()})
            return {'accepted':True,'background_required':True,'lane':next(l for l in lanes if l['id']==value['lane'])}

    def process_frame(self, camera, frame):
        started = clock()
        with self.lock:
            result = self.engine.process(camera, frame.image, frame.timestamp)
            self.tracks[camera] = result['tracks']
            self.warnings[camera] = result['warnings']
            # Bind A/B decisions to the timestamp calculated from capture frames.
            for event in result['events']:
                outcome = self.manager.ingest(event)
                self.record({'kind': 'gate', **event, 'accepted': outcome['accepted'],
                             'reason': outcome['reason']})
                if outcome.get('decision'):
                    self.record({'kind': 'decision', **outcome['decision']})
            # Missing/ambiguous identity never means that a route is clear.
            tracks_by_id = {str(t['id']): t for t in result['tracks']}
            owned = {l['id'] for l in self.vision_lanes if l['camera'] == camera}
            for lane in self.manager.status(clock())['lanes']:
                if lane['id'] not in owned or lane['state'] not in ('waiting', 'locked'):
                    continue
                track = tracks_by_id.get(str(lane['track_id']))
                if not track or not track['visible'] or track['ambiguous']:
                    self.manager.mark_uncertain(lane['id'], '車両を見失ったか識別が不明瞭です', clock())
            self.metrics[camera] = {'processing_ms': round((clock()-started)*1000, 2),
                                    'capture_age_ms': round(max(0, clock()-frame.timestamp)*1000, 2)}
            self.make_preview(camera, frame)

    def make_preview(self, camera, frame):
        now = clock()
        if now-self.preview_times.get(camera, 0) < 1/self.config.get('preview_fps', 4):
            return
        import cv2
        image = frame.image
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            image = image.copy()
        for lane in self.vision_lanes:
            if lane['camera'] != camera:
                continue
            cv2.polylines(image, [np.array(lane['polygon'], dtype=np.int32)], True, (100, 160, 100), 1)
            for key, color in [('gate_a', (0, 220, 255)), ('gate_b', (255, 160, 0))]:
                a, b = lane[key]
                cv2.line(image, tuple(map(int, a)), tuple(map(int, b)), color, 2)
                cv2.putText(image, key[-1].upper(), tuple(map(int, a)), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        for track in self.tracks.get(camera, []):
            p = tuple(map(int, track['center']))
            color = (0, 0, 255) if track['ambiguous'] else (0, 255, 0)
            cv2.circle(image, p, 7, color, 2)
            if track.get('bbox'):
                x0,y0,x1,y1=track['bbox'];cv2.rectangle(image,(x0,y0),(x1,y1),color,2)
            cv2.putText(image, str(track['id']), (p[0]+8, p[1]), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        h, w = image.shape[:2]
        preview = cv2.resize(image, (640, max(1, round(h*640/w))))
        ok, encoded = cv2.imencode('.jpg', preview, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            self.jpeg[camera] = encoded.tobytes()
            self.preview_times[camera] = now

    def _run(self):
        try:
            while not self.stop_event.is_set():
                for camera, source in self.sources.items():
                    frame = source.latest()
                    with self.lock:
                        stale = frame is None or clock()-frame.timestamp > self.config.get('stale_frame_s', .75)
                        if source.error or stale:
                            self.hold_active(camera, 'カメラの停止または映像遅延')
                            self.warnings[camera] = [source.error or '映像を待っています／映像が古くなっています']
                        if frame is None or frame.sequence == self.processed.get(camera):
                            continue
                        self.processed[camera] = frame.sequence
                        if self.paused or stale or source.error:
                            self.make_preview(camera, frame)
                            continue
                    self.process_frame(camera, frame)
                self.stop_event.wait(.01)
        except Exception as exc:
            with self.lock:
                self.warnings['runtime'] = [f'{type(exc).__name__}: {exc}']
                for camera in self.sources:
                    self.hold_active(camera, '画像処理が停止しました')
        finally:
            self.running = False

    def status(self):
        with self.lock:
            routes = self.manager.status(clock())
            for lane in routes['lanes']:
                lane.update(phase=lane['state'], indication=lane['led_route'],
                            reason=lane['uncertainty_reason'], route=lane['last_requested_route'])
            cameras = []
            for source in self.sources.values():
                info = source.status()
                info['calibrated'] = source.id in self.backgrounds
                info['metrics'] = self.metrics.get(source.id, {})
                frame=source.latest()
                info['frame_size']=[frame.image.shape[1],frame.image.shape[0]] if frame else None
                info['lanes_configured']=sum(l['camera']==source.id for l in self.vision_lanes)
                cameras.append(info)
            warnings = [w for ws in self.warnings.values() for w in ws]
            if self.mode == 'usb':
                for camera in cameras:
                    info=camera['capture_info']
                    reported=info.get('reported_fourcc')
                    if reported and reported!=info.get('fourcc_requested'):
                        warnings.append(camera['id']+'：要求した動画形式と実際の報告形式が異なります（'+reported+'）。USB帯域と遅延を確認してください。')
                warnings.append('USB映像の時刻は読取り完了時刻です。撮影時刻・内部遅延・2台の同期は未測定です。')
            if not self.vision_lanes:
                warnings.append('検出範囲が未設定です。カメラの「検出範囲・A/Bを設定」から登録してください。')
            return {'mode': self.mode, 'running': self.running, 'paused': self.paused,
                    'outputs_enabled': False, 'clock_now': clock(), 'cameras': cameras, 'routes': routes,
                    'tracks': [copy.deepcopy(t) for ts in self.tracks.values() for t in ts],
                    'events': list(self.events), 'warnings': warnings,
                    'layout_note': self.config.get('layout_note', '')}


class ReleaseRequest(BaseModel):
    confirm_clear: StrictBool


class PauseRequest(BaseModel):
    paused: StrictBool


class CalibrationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    camera: str
    lane: str
    roi: list[list[StrictFloat]]
    a: list[StrictFloat]
    b: list[StrictFloat]
    mode: str
    time_threshold_s: StrictFloat=2.0
    led_interval_s: StrictFloat=2.0
    threshold: StrictInt=25
    min_area: StrictInt=30
    max_match_distance: StrictInt=80


def create_app(config=None, mode='demo', log_path=None):
    if config is None:
        config = read_config(ROOT/'config/demo.json')
    runtime = Runtime(config, mode, log_path)

    @asynccontextmanager
    async def lifespan(app):
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(title='Nゲージ カメラ検証', lifespan=lifespan)
    app.state.runtime = runtime
    app.mount('/static', StaticFiles(directory=ROOT/'web'), name='static')

    @app.get('/')
    def index():
        return FileResponse(ROOT/'web/index.html')

    @app.get('/api/status')
    def status():
        return runtime.status()

    @app.get('/api/config')
    def get_config():
        return copy.deepcopy(runtime.config)

    @app.get('/api/config/download')
    def download_config():
        with runtime.lock:
            data=json.dumps(runtime.config,ensure_ascii=False,indent=2)+'\n'
        return Response(data,media_type='application/json',headers={'Content-Disposition':'attachment; filename="camera-test.local.json"'})

    @app.post('/api/calibration')
    def calibration(request: CalibrationRequest):
        try:return runtime.apply_calibration(request.model_dump())
        except ValueError as exc:raise HTTPException(409,str(exc))

    @app.get('/api/snapshot/{camera}.jpg')
    def snapshot(camera: str):
        if camera not in runtime.sources:raise HTTPException(404,'不明なカメラです')
        source=runtime.sources[camera];frame=source.latest()
        if frame is None or source.error or clock()-frame.timestamp>runtime.config.get('stale_frame_s',.75):
            raise HTTPException(409,'最新の正常な映像がありません')
        import cv2
        ok,data=cv2.imencode('.jpg',frame.image)
        if not ok:raise HTTPException(409,'画像を作成できません')
        return Response(data.tobytes(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})

    @app.post('/api/background/{camera}')
    def background(camera: str):
        try:
            return runtime.capture_background(camera)
        except KeyError:
            raise HTTPException(404, '不明なカメラです')
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post('/api/release/{lane}')
    def release(lane: str, request: ReleaseRequest):
        result = runtime.release(lane, request.confirm_clear)
        if not result['accepted']:
            raise HTTPException(409, result['reason'])
        return result

    @app.post('/api/pause')
    def pause(request: PauseRequest):
        return runtime.pause(request.paused)

    @app.get('/api/preview/{camera}.mjpg')
    def preview(camera: str):
        if camera not in runtime.sources:
            raise HTTPException(404, '不明なカメラです')
        def chunks():
            while runtime.running:
                with runtime.lock:
                    data = runtime.jpeg.get(camera)
                if data:
                    yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+data+b'\r\n'
                time.sleep(1/runtime.config.get('preview_fps', 4))
        return StreamingResponse(chunks(), media_type='multipart/x-mixed-replace; boundary=frame')

    return app


def main():
    parser = argparse.ArgumentParser(description='Camera control prototype (no physical outputs)')
    parser.add_argument('--mode', choices=['demo', 'pi', 'replay', 'usb'], default='demo')
    parser.add_argument('--config')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--log', help='JSONL event log path; optional')
    args = parser.parse_args()
    config_path = args.config or str(ROOT/'config'/({'demo':'demo.json','pi':'pi5.example.json','replay':'replay.example.json','usb':'lattepanda.example.json'}[args.mode]))
    try:
        config = read_config(config_path)
        if args.mode == 'pi':
            model = Path('/proc/device-tree/model')
            if not model.exists() or 'Raspberry Pi 5' not in model.read_text():
                parser.error('piモードはRaspberry Pi 5実機で検証してください。デモは--mode demoです。')
        app = create_app(config, args.mode, args.log)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
