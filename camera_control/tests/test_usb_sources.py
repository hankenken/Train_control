"""UVC source tests with a mocked driver; no USB devices or Windows required."""
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from camera_control.sources import USBSource


class FakeCapture:
    def __init__(self, frames=(), opened=True, set_failures=(), reported=None):
        self._frames = iter(frames)
        self.opened = opened
        self.set_failures = set(set_failures)
        self.settings = []
        self.release_calls = 0
        self.read_calls = 0
        self.reported = {
            cv2.CAP_PROP_FRAME_WIDTH: 160,
            cv2.CAP_PROP_FRAME_HEIGHT: 90,
            cv2.CAP_PROP_FPS: 15,
            cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
        }
        self.reported.update(reported or {})

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.settings.append((prop, value))
        return prop not in self.set_failures

    def get(self, prop):
        return self.reported.get(prop, 0)

    def read(self):
        self.read_calls += 1
        return next(self._frames, (False, None))

    def release(self):
        self.release_calls += 1


def config(**overrides):
    return {"id": "cam0", "device": 0, "backend": "dshow",
            "capture_size": [160, 90], "processing_size": [80, 45],
            "fps": 15, "fourcc": "MJPG", **overrides}


def image(value=80):
    return np.full((90, 160, 3), value, np.uint8)


def stop_after(source, count):
    publish = source.publish

    def bounded(*args):
        publish(*args)
        if source.frames >= count:
            source._stop.set()

    source.publish = bounded


class USBSourceTests(unittest.TestCase):
    def test_dshow_negotiation_host_read_time_and_processing_frame(self):
        source = USBSource(config())
        cap = FakeCapture([(True, image())])
        stop_after(source, 1)
        timeline = []
        read = cap.read

        def observed_read():
            timeline.append("read")
            return read()

        def after_read_clock():
            timeline.append("clock")
            return 123.5

        cap.read = observed_read
        with patch("cv2.VideoCapture", return_value=cap) as constructor, \
                patch("camera_control.sources.clock", side_effect=after_read_clock):
            source._run()
        constructor.assert_called_once_with(0, cv2.CAP_DSHOW)
        self.assertIsNone(source.error)
        self.assertEqual(timeline, ["read", "clock"])
        self.assertEqual(cap.settings[:5], [
            (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
            (cv2.CAP_PROP_FRAME_WIDTH, 160),
            (cv2.CAP_PROP_FRAME_HEIGHT, 90),
            (cv2.CAP_PROP_FPS, 15.0),
            (cv2.CAP_PROP_BUFFERSIZE, 1),
        ])
        frame = source.latest()
        self.assertEqual(frame.image.shape, (45, 80))
        self.assertEqual(frame.image.dtype, np.uint8)
        self.assertEqual(int(frame.image[0, 0]), 80)
        self.assertEqual(frame.timestamp, 123.5)
        self.assertEqual(frame.timestamp_kind, "host_read_complete")
        self.assertFalse(source.capture_info["driver_buffering_verified"])
        self.assertIn("露光時刻ではなく", source.capture_info["timestamp_note"])
        self.assertEqual(cap.release_calls, 1)

    def test_msmf_and_auto_backend_selection(self):
        for backend, api in [("msmf", cv2.CAP_MSMF), ("auto", cv2.CAP_ANY)]:
            with self.subTest(backend=backend):
                source = USBSource(config(backend=backend, device=1))
                cap = FakeCapture([(True, image())])
                stop_after(source, 1)
                with patch("cv2.VideoCapture", return_value=cap) as constructor:
                    source._run()
                constructor.assert_called_once_with(1, api)
                self.assertIsNone(source.error)
                self.assertEqual(cap.release_calls, 1)

    def test_two_configured_cameras_have_independent_latest_slots(self):
        first = USBSource(config(id="cam0", device=0))
        second = USBSource(config(id="cam1", device=1))
        caps = [FakeCapture([(True, image(50))]),
                FakeCapture([(True, image(200))])]
        stop_after(first, 1)
        stop_after(second, 1)
        with patch("cv2.VideoCapture", side_effect=caps) as constructor:
            first._run()
            second._run()
        self.assertEqual([c.args[0] for c in constructor.call_args_list], [0, 1])
        self.assertEqual(int(first.latest().image[0, 0]), 50)
        self.assertEqual(int(second.latest().image[0, 0]), 200)
        self.assertEqual([c.release_calls for c in caps], [1, 1])

    def test_latest_frame_replaces_older_frames_without_queueing(self):
        source = USBSource(config())
        cap = FakeCapture([(True, image(v)) for v in (10, 40, 90)])
        stop_after(source, 3)
        with patch("cv2.VideoCapture", return_value=cap), \
                patch("camera_control.sources.clock", side_effect=[1., 2., 3.]):
            source._run()
        self.assertIsNone(source.error)
        self.assertEqual(source.frames, 3)
        self.assertEqual(source.latest().sequence, 3)
        self.assertEqual(source.latest().timestamp, 3.)
        self.assertEqual(int(source.latest().image[0, 0]), 90)
        self.assertEqual(cap.read_calls, 3)

    def test_camera_drop_retains_last_frame_and_reports_error_not_empty_scene(self):
        source = USBSource(config())
        cap = FakeCapture([(True, image(130)), (False, None)])
        with patch("cv2.VideoCapture", return_value=cap), \
                patch("camera_control.sources.clock", side_effect=[10., 11.]):
            source._run()
        self.assertIsNotNone(source.error)
        self.assertEqual(source.frames, 1)
        self.assertEqual(source.latest().timestamp, 10.)
        self.assertEqual(int(source.latest().image[0, 0]), 130)
        self.assertEqual(cap.release_calls, 1)

    def test_camera_open_failure_releases_capture_and_publishes_nothing(self):
        source = USBSource(config())
        cap = FakeCapture(opened=False)
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNotNone(source.error)
        self.assertIsNone(source.latest())
        self.assertEqual(cap.read_calls, 0)
        self.assertEqual(cap.release_calls, 1)

    def test_actual_frame_size_mismatch_is_not_silently_resized_for_calibration(self):
        source = USBSource(config())
        cap = FakeCapture([(True, np.zeros((180, 320, 3), np.uint8))])
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNotNone(source.error)
        self.assertIn("320x180", source.error)
        self.assertEqual(source.capture_info["actual_frame_size"], [320, 180])
        self.assertIsNone(source.latest())
        self.assertEqual(cap.release_calls, 1)

    def test_aspect_ratio_mismatch_does_not_distort_gate_geometry(self):
        source = USBSource(config(processing_size=[80, 80]))
        cap = FakeCapture([(True, image())])
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNotNone(source.error)
        self.assertIsNone(source.latest())
        self.assertEqual(cap.release_calls, 1)

    def test_bad_driver_frames_never_publish_a_clear_frame(self):
        for frame in [None, "not-an-array", np.array([], np.uint8),
                      np.zeros((90, 160, 3), np.float32),
                      np.zeros((160,), np.uint8)]:
            with self.subTest(frame_type=type(frame).__name__):
                source = USBSource(config())
                cap = FakeCapture([(True, frame)])
                with patch("cv2.VideoCapture", return_value=cap):
                    source._run()
                self.assertIsNotNone(source.error)
                self.assertEqual(source.frames, 0)
                self.assertIsNone(source.latest())
                self.assertEqual(cap.release_calls, 1)

    def test_invalid_device_backend_or_codec_does_not_open_a_camera(self):
        bad = [{"device": -1}, {"device": True}, {"device": "0"},
               {"backend": "unknown"}, {"fourcc": "bad"}]
        for fields in bad:
            with self.subTest(fields=fields):
                source = USBSource(config(**fields))
                with patch("cv2.VideoCapture") as constructor:
                    source._run()
                constructor.assert_not_called()
                self.assertIsNotNone(source.error)
                self.assertIsNone(source.latest())

    def test_unsupported_property_fails_and_releases_opened_device(self):
        source = USBSource(config(properties={"invented_control": 10}))
        cap = FakeCapture()
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNotNone(source.error)
        self.assertEqual(cap.release_calls, 1)
        self.assertEqual(cap.read_calls, 0)

    def test_ignored_buffer_setting_and_missing_reported_fps_are_not_verified(self):
        source = USBSource(config())
        cap = FakeCapture([(True, image())],
                          set_failures=[cv2.CAP_PROP_BUFFERSIZE],
                          reported={cv2.CAP_PROP_FPS: float("nan")})
        stop_after(source, 1)
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNone(source.error)
        info = source.capture_info
        self.assertFalse(info["property_set_accepted"]["buffer_size"])
        self.assertFalse(info["driver_buffering_verified"])
        self.assertIsNone(info["reported_fps"])
        self.assertEqual(info["fps_target"], 15)

    def test_manual_properties_keep_backend_native_units(self):
        source = USBSource(config(properties={"auto_exposure": 0.25,
                                               "exposure": -6.0,
                                               "autofocus": 0}))
        cap = FakeCapture([(True, image())])
        stop_after(source, 1)
        with patch("cv2.VideoCapture", return_value=cap):
            source._run()
        self.assertIsNone(source.error)
        self.assertIn((cv2.CAP_PROP_AUTO_EXPOSURE, 0.25), cap.settings)
        self.assertIn((cv2.CAP_PROP_EXPOSURE, -6.0), cap.settings)
        self.assertIn((cv2.CAP_PROP_AUTOFOCUS, 0), cap.settings)


if __name__ == "__main__":
    unittest.main()
