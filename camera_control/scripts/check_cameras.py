#!/usr/bin/env python3
"""Inventory two Pi cameras and sensor modes; never operate GPIO or save images."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path


def model_name() -> str:
    for path in (Path('/proc/device-tree/model'), Path('/sys/firmware/devicetree/base/model')):
        if path.is_file():
            return path.read_bytes().replace(b'\0', b'').decode('utf-8', errors='replace')
    return ''


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def inventory(capture_test: bool = False) -> tuple[dict, int]:
    model = model_name()
    if not model.startswith('Raspberry Pi 5') or platform.machine() != 'aarch64':
        return {'ok': False, 'error': 'Raspberry Pi 5 with a 64-bit OS is required. No cameras were opened.', 'model': model or 'unknown'}, 2
    # Import only after checking the platform: this file can be invoked on a PC
    # to report the unsupported platform without requiring Picamera2.
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        return {'ok': False, 'error': f'Picamera2 is unavailable: {exc}. Run setup_pi.sh in Raspberry Pi OS.'}, 2
    try:
        camera_info = Picamera2.global_camera_info()
    except Exception as exc:
        return {'ok': False, 'error': f'Camera enumeration failed: {exc}'}, 1
    report = {'ok': False, 'model': model, 'detected_count': len(camera_info), 'cameras': [], 'capture_test': 'not requested', 'notes': [
        'Mode fps values are sensor-mode limits, not a guaranteed two-camera processing rate.',
        'A 640x360 output size alone does not guarantee the full sensor field of view.',
        'No images are saved and no GPIO is used.',
    ]}
    errors = False
    for index, info in enumerate(camera_info):
        item = {'index': index, 'info': json_safe(info)}
        camera = None
        try:
            camera = Picamera2(index)
            properties = camera.camera_properties
            full_crop = properties.get('ScalerCropMaximum')
            item['properties'] = json_safe(properties)
            item['modes'] = []
            for mode in camera.sensor_modes:
                crop = mode.get('crop_limits')
                item['modes'].append({
                    'size': json_safe(mode.get('size')),
                    'format': str(mode.get('format')),
                    'bit_depth': mode.get('bit_depth'),
                    'sensor_mode_fps': mode.get('fps'),
                    'crop_limits': json_safe(crop),
                    'full_field_of_view_by_crop': tuple(crop) == tuple(full_crop) if crop is not None and full_crop is not None else None,
                })
        except Exception as exc:
            item['error'] = str(exc)
            errors = True
        finally:
            if camera is not None:
                try:
                    camera.close()
                except Exception as exc:
                    item['close_error'] = str(exc)
                    errors = True
        report['cameras'].append(item)
    if capture_test and len(camera_info) >= 2 and not errors:
        opened = []
        started = []
        try:
            for index in range(2):
                camera = Picamera2(index)
                opened.append(camera)
                camera.configure(camera.create_video_configuration(main={'size': (640, 360), 'format': 'RGB888'}, controls={'FrameRate': 10}))
            for camera in opened:
                camera.start()
                started.append(camera)
            frames = [camera.capture_array() for camera in opened]
            report['capture_test'] = {'requested_fps': 10, 'frames': [{'camera_index': i, 'shape': list(frame.shape), 'dtype': str(frame.dtype)} for i, frame in enumerate(frames)], 'timing_or_full_fov_verified': False}
        except Exception as exc:
            errors = True
            report['capture_test'] = {'error': str(exc)}
        finally:
            for camera in reversed(started):
                try:
                    camera.stop()
                except Exception:
                    errors = True
            for camera in reversed(opened):
                try:
                    camera.close()
                except Exception:
                    errors = True
    elif capture_test:
        report['capture_test'] = 'skipped: two cameras without inventory errors are required'
    report['ok'] = len(camera_info) >= 2 and not errors
    if len(camera_info) < 2:
        report['notes'].append('Two cameras are required; check both CSI cables with Pi power disconnected before reconnecting.')
    return report, 0 if report['ok'] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-test', action='store_true', help='Start both cameras at a requested 640x360/10fps, capture one frame each, then close. No files are saved.')
    args = parser.parse_args()
    report, code = inventory(args.capture_test)
    print(json.dumps(json_safe(report), ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
