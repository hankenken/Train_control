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
        self._first_timestamp = None

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
            if self._first_timestamp is None:
                self._first_timestamp = timestamp
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
        rate = ((self.frames-1)/(f.timestamp-self._first_timestamp)
                if f and self.frames>1 and f.timestamp>self._first_timestamp else None)
        return {'id': self.id, 'name': self.config.get('name', self.id),
                'frames': self.frames, 'last_timestamp': f.timestamp if f else None,
                'timestamp_kind': f.timestamp_kind if f else None,
                'error': self.error, 'observed_read_fps': round(rate,2) if rate is not None else None,
                'capture_info': dict(self.capture_info)}


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


class USBSource(LatestSource):
    """UVC capture for LattePanda/Windows. Times are host-read, not exposure times.

    The latest-frame slot bounds our own queue only. Driver/USB buffering and
    inter-camera synchronization must be measured separately on real devices.
    """
    def run(self):
        import cv2
        device = self.config.get('device')
        if isinstance(device, bool) or not isinstance(device, int) or device < 0:
            raise ValueError('USBカメラのdeviceは0以上の整数で指定してください')
        backend = self.config.get('backend', 'dshow')
        apis = {'dshow': cv2.CAP_DSHOW, 'msmf': cv2.CAP_MSMF, 'auto': cv2.CAP_ANY}
        if backend not in apis:
            raise ValueError('backendはdshow、msmf、autoのいずれかです')
        width, height = self.config.get('capture_size', [1920, 1080])
        low = tuple(self.config.get('processing_size', [1280, 720]))
        fps = float(self.config.get('fps', 15))
        fourcc = self.config.get('fourcc', 'MJPG')
        if not isinstance(fourcc, str) or len(fourcc) != 4:
            raise ValueError('fourccはMJPGなどの4文字です')
        self.capture = cv2.VideoCapture(device, apis[backend])
        if not self.capture.isOpened():
            raise RuntimeError(f'USBカメラ{device}を開けません。機器番号・権限・使用中アプリを確認してください')
        accepted = {}
        # Some UVC devices choose supported resolutions according to codec.
        for name, prop, value in [
                ('fourcc', cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc)),
                ('width', cv2.CAP_PROP_FRAME_WIDTH, width),
                ('height', cv2.CAP_PROP_FRAME_HEIGHT, height),
                ('fps', cv2.CAP_PROP_FPS, fps),
                ('buffer_size', cv2.CAP_PROP_BUFFERSIZE, 1)]:
            accepted[name] = bool(self.capture.set(prop, value))
        properties = self.config.get('properties', {})
        property_ids = {'autofocus': cv2.CAP_PROP_AUTOFOCUS,
                        'focus': cv2.CAP_PROP_FOCUS,
                        'auto_exposure': cv2.CAP_PROP_AUTO_EXPOSURE,
                        'exposure': cv2.CAP_PROP_EXPOSURE,
                        'auto_wb': cv2.CAP_PROP_AUTO_WB,
                        'wb_temperature': cv2.CAP_PROP_WB_TEMPERATURE}
        for name, value in properties.items():
            if name not in property_ids or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('不明または無効なカメラ設定: '+name)
            # Units vary by camera/backend. No guessed exposure conversion.
            accepted[name] = bool(self.capture.set(property_ids[name], value))
        def reported(prop):
            value = float(self.capture.get(prop))
            return value if math.isfinite(value) else None
        code = reported(cv2.CAP_PROP_FOURCC)
        codec = ''.join(chr((int(code) >> (8*i)) & 255) for i in range(4)) if code is not None else None
        if codec is not None:
            codec = ''.join(c if 32 <= ord(c) < 127 else '?' for c in codec)
        self.capture_info = {
            'device_index': device, 'backend_requested': backend,
            'requested_size': [width, height], 'processing_size': list(low),
            'fps_target': fps, 'fourcc_requested': fourcc,
            'reported_size': [reported(cv2.CAP_PROP_FRAME_WIDTH), reported(cv2.CAP_PROP_FRAME_HEIGHT)],
            'reported_fps': reported(cv2.CAP_PROP_FPS), 'reported_fourcc': codec,
            'property_set_accepted': accepted, 'driver_buffering_verified': False,
            'timestamp_note': 'host_read_complete。露光時刻ではなく、USB内部遅延と2台の同期は未測定。',
            'note': '機器番号は再接続で変わる場合があります。各画像の担当範囲を確認してください'}
        while not self._stop.is_set():
            ok, image = self.capture.read()
            timestamp = clock()
            if not ok or image is None or not isinstance(image, np.ndarray) or image.size == 0:
                raise RuntimeError('USBカメラの取得が停止しました。接続を確認してアプリを再起動してください')
            if image.dtype != np.uint8 or image.ndim not in (2, 3):
                raise RuntimeError('USBカメラの画像形式を解釈できません')
            actual_height, actual_width = image.shape[:2]
            self.capture_info['actual_frame_size'] = [actual_width, actual_height]
            if (actual_width, actual_height) != (width, height):
                raise RuntimeError(f'要求{width}x{height}に対し実画像は{actual_width}x{actual_height}です。対応モードを確認し設定を修正してください')
            if abs(actual_width/actual_height-low[0]/low[1]) > .01:
                raise RuntimeError('撮影サイズと画像処理サイズの縦横比を合わせてください')
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            if (actual_width, actual_height) != low:
                gray = cv2.resize(gray, low, interpolation=cv2.INTER_AREA)
            self.publish(gray, timestamp, 'host_read_complete')
            # Drain camera/driver frames continuously; do not accumulate a queue.

    def close(self):
        if hasattr(self, 'capture'):
            self.capture.release()
