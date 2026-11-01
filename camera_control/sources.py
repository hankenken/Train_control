"""Latest-frame sources. Pi imports are lazy so demo/replay require no hardware."""
from __future__ import annotations
from dataclasses import dataclass
import threading
import time
import math
import numpy as np


def clock() -> float:
    # libcamera SensorTimestamp is a boot-time timestamp on Raspberry Pi.
    if hasattr(time, 'CLOCK_BOOTTIME'):
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    return time.monotonic()


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    timestamp: float
    sequence: int
    timestamp_kind: str


class LatestSource:
    def __init__(self, config):
        self.config = config
        self.id = config['id']
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._frame = None
        self.error = None
        self.frames = 0
        self.capture_info = {}

    def start(self):
        self._thread = threading.Thread(target=self._run, name='capture-'+self.id, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.run()
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
        finally:
            self.close()

    def run(self):
        raise NotImplementedError

    def close(self):
        pass

    def publish(self, image, timestamp, kind):
        if not math.isfinite(timestamp):
            raise ValueError('Invalid capture timestamp')
        # Consumers never share a driver-owned request buffer.
        with self._lock:
            self.frames += 1
            self._frame = Frame(image.copy(), timestamp, self.frames, kind)

    def latest(self):
        with self._lock:
            return self._frame

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def status(self):
        f = self.latest()
        return {'id': self.id, 'name': self.config.get('name', self.id),
                'frames': self.frames, 'last_timestamp': f.timestamp if f else None,
                'timestamp_kind': f.timestamp_kind if f else None,
                'error': self.error, 'capture_info': self.capture_info}


class DemoSource(LatestSource):
    """Two synthetic lanes, including stopped objects. Never moves real trains."""
    def __init__(self, config, epoch=None):
        super().__init__(config)
        self.epoch = epoch if epoch is not None else clock()

    @staticmethod
    def empty_image():
        image = np.full((360, 640, 3), 32, np.uint8)
        for y in (100, 260):
            image[y-20:y-17, 10:630] = 80
            image[y+17:y+20, 10:630] = 80
        return image

    def image_at(self, elapsed):
        image = self.empty_image()
        for i, y in enumerate((100, 260)):
            t = (elapsed - i*0.45) % 30
            if t < 1 or t > 14:
                continue
            if t < 4:
                x = 55 + (t-1)*75
            elif t < 6:
                x = 280
            else:
                x = 280+(t-6)*60
            if x > 675:
                continue
            x = int(x)
            left, right = max(0, x-32), min(640, x+32)
            if right > left:
                image[y-12:y+13, left:right] = (190, 210, 230)
        return image

    def run(self):
        fps = float(self.config.get('fps', 15))
        while not self._stop.is_set():
            now = clock()
            self.publish(self.image_at(now-self.epoch), now, 'synthetic_boottime')
            self._stop.wait(1/fps)


class ReplaySource(LatestSource):
    def run(self):
        import cv2
        self.capture = cv2.VideoCapture(self.config['path'])
        if not self.capture.isOpened():
            raise RuntimeError('録画ファイルを開けません')
        fps = self.capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0:
            fps = float(self.config.get('fps', 15))
        start = clock(); number = 0
        while not self._stop.is_set():
            ok, image = self.capture.read()
            if not ok:
                self.error = '録画の終端です。見失いを通過完了として扱いません。'
                break
            media_t = number/fps
            due = start+media_t
            if self._stop.wait(max(0, due-clock())):
                break
            target = self.config.get('processing_size', [640, 360])
            image = cv2.resize(image, tuple(target))
            self.publish(image, due, 'replay_fps_timeline')
            number += 1

    def close(self):
        if hasattr(self, 'capture'):
            self.capture.release()


class PiSource(LatestSource):
    """Two independent Picamera2 instances, each with a bounded latest-frame slot."""
    def run(self):
        from picamera2 import Picamera2
        self.camera = Picamera2(int(self.config['index']))
        main = tuple(self.config.get('main_size', [1920, 1080]))
        low = tuple(self.config.get('processing_size', [1280, 720]))
        fps = float(self.config.get('fps', 15))
        modes = self.camera.sensor_modes
        usable = [m for m in modes if m['size'][0] >= main[0] and m['size'][1] >= main[1]
                  and m.get('fps', fps) >= fps]
        if not usable:
            raise RuntimeError('指定解像度・fpsに対応するセンサモードがありません')
        # Preserve maximum available crop area, then choose its smallest viable mode.
        def crop_area(m):
            c = m.get('crop_limits', (0, 0, *m['size']))
            return c[2]*c[3]
        maximum = max(map(crop_area, usable))
        selected = min((m for m in usable if crop_area(m) == maximum),
                       key=lambda m: m['size'][0]*m['size'][1])
        controls = {'FrameRate': fps}
        controls.update(self.config.get('controls', {}))
        configuration = self.camera.create_video_configuration(
            main={'size': main, 'format': 'RGB888'},
            lores={'size': low, 'format': 'YUV420'},
            sensor={'output_size': selected['size'], 'bit_depth': selected['bit_depth']},
            controls=controls, buffer_count=4)
        self.camera.configure(configuration)
        self.capture_info = {'sensor_size': list(selected['size']),
                             'crop_limits': list(selected.get('crop_limits', [])),
                             'processing_size': list(low), 'fps_target': fps,
                             'note': '実際の画角・ピント・露出・遅延を確認してください'}
        self.camera.start()
        while not self._stop.is_set():
            request = self.camera.capture_request()
            try:
                metadata = request.get_metadata()
                yuv = request.make_array('lores')
                # Only the luminance plane is used; no full-resolution JPEG encoding.
                gray = yuv[:low[1], :low[0]].copy()
                ts = metadata.get('SensorTimestamp')
                if ts is None:
                    raise RuntimeError('SensorTimestampがありません。時刻の確認が必要です')
                timestamp = float(ts)/1e9
                if abs(clock()-timestamp) > 5:
                    raise RuntimeError('撮影時刻とホスト時刻の基準が一致しません')
                self.publish(gray, timestamp, 'libcamera_SensorTimestamp')
            finally:
                request.release()

    def close(self):
        if hasattr(self, 'camera'):
            try:
                self.camera.stop()
            finally:
                self.camera.close()
