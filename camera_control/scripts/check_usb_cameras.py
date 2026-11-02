#!/usr/bin/env python3
"""Inspect Windows USB-camera candidates only when explicitly requested.

No camera is opened by default. --probe opens each selected candidate in turn.
--capture-test requires two different indices and briefly opens both cameras.
Windows indices do not provide verified, persistent physical camera identity.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import struct
import sys
import time


def parse_indices(value: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in value.split(',')]
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Use comma-separated indices such as 0,1.') from exc
    if not values or any(index < 0 or index > 31 for index in values) or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError('Indices must be distinct integers from 0 to 31.')
    return values


def parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = (int(item) for item in value.lower().split('x'))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError('Use WIDTHxHEIGHT, for example 1920x1080.') from exc
    if width < 1 or height < 1 or width > 8192 or height > 8192:
        raise argparse.ArgumentTypeError('Width and height must be between 1 and 8192.')
    return width, height


def safe_number(value):
    number = float(value)
    return round(number, 4) if math.isfinite(number) else None


def fourcc_name(value) -> str | None:
    number = int(value) if math.isfinite(float(value)) else 0
    if number <= 0:
        return None
    return ''.join(chr((number >> (8 * i)) & 0xFF) for i in range(4)).strip('\x00')


def configure(camera, cv2, args) -> dict:
    width, height = args.capture_size
    # Backend property setters are requests. Actual frame size is checked below.
    setters = {
        'fourcc': bool(camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))),
        'width': bool(camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)),
        'height': bool(camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)),
        'fps': bool(camera.set(cv2.CAP_PROP_FPS, args.fps)),
    }
    return {
        'property_requests_accepted': setters,
        'reported_width': safe_number(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
        'reported_height': safe_number(camera.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        'reported_fps': safe_number(camera.get(cv2.CAP_PROP_FPS)),
        'reported_fourcc': fourcc_name(camera.get(cv2.CAP_PROP_FOURCC)),
    }


def inspect(args) -> tuple[dict, int]:
    report = {
        'platform': platform.platform(),
        'process_bits': struct.calcsize('P') * 8,
        'backend': args.backend,
        'physical_camera_identity_verified': False,
        'requested': {'capture_size': list(args.capture_size), 'fps': args.fps, 'fourcc': args.fourcc},
        'cameras': [],
        'notes': [
            'DirectShow/Media Foundation indices may change after reconnecting or rebooting. Verify each physical camera manually.',
            'Reported fps and FOURCC are backend properties, not measured throughput or a guarantee of the sensor field of view.',
            'Frame times are host monotonic read-completion times, NOT sensor exposure timestamps.',
            'No images are saved. No GPIO, Arduino, firmware, or serial device is used.',
        ],
    }
    if platform.system() != 'Windows' or struct.calcsize('P') * 8 != 64:
        report.update(ok=False, error='Windows x64 is required. No cameras were opened.')
        return report, 2
    if not args.probe and not args.capture_test:
        report.update(ok=True, action='none', opened_cameras=0, next_step='Use --probe --indices 0,1,2 to explicitly inspect candidates, then --capture-test --devices 0,1 after verifying identity.')
        return report, 0
    try:
        import cv2
    except ImportError as exc:
        report.update(ok=False, error=f'OpenCV is unavailable: {exc}. Run setup_windows.ps1 first.')
        return report, 2
    api = cv2.CAP_DSHOW if args.backend == 'dshow' else cv2.CAP_MSMF
    if args.probe:
        for index in args.indices:
            item = {'index': index, 'opened': False}
            camera = None
            try:
                camera = cv2.VideoCapture(index, api)
                item['opened'] = bool(camera.isOpened())
                if item['opened']:
                    item.update(configure(camera, cv2, args))
                    item['backend_name'] = camera.getBackendName()
            except Exception as exc:
                item['error'] = str(exc)
            finally:
                if camera is not None:
                    try:
                        camera.release()
                    except Exception as exc:
                        item['release_error'] = str(exc)
            report['cameras'].append(item)
        report['action'] = 'probe'
        report['opened_cameras'] = sum(item['opened'] for item in report['cameras'])
        report['ok'] = report['opened_cameras'] >= 2 and not any(item.get('error') or item.get('release_error') for item in report['cameras'])
        return report, 0 if report['ok'] else 1

    # Keeping both handles open reveals conflicts hidden by sequential probing.
    opened = []
    completed = False
    try:
        for index in args.devices:
            item = {'index': index, 'opened': False}
            report['cameras'].append(item)
            camera = cv2.VideoCapture(index, api)
            opened.append(camera)
            item['opened'] = bool(camera.isOpened())
            if not item['opened']:
                raise RuntimeError(f'Camera index {index} could not be opened using {args.backend}.')
            item.update(configure(camera, cv2, args))
            item['backend_name'] = camera.getBackendName()
            item['frames'] = []
        for sequence in range(args.frames):
            for camera, item in zip(opened, report['cameras']):
                read_started = time.monotonic()
                success, frame = camera.read()
                read_finished = time.monotonic()
                if not success or frame is None or frame.size == 0:
                    raise RuntimeError(f'No frame received from camera index {item["index"]}.')
                height, width = frame.shape[:2]
                item['frames'].append({
                    'sequence': sequence,
                    'actual_size': [int(width), int(height)],
                    'host_read_completed_monotonic_s': round(read_finished, 6),
                    'read_duration_ms': round((read_finished - read_started) * 1000, 3),
                    'timestamp_kind': 'host_read_completion_not_exposure',
                })
        completed = True
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        release_errors = []
        for camera in reversed(opened):
            try:
                camera.release()
            except Exception as exc:
                release_errors.append(str(exc))
    if release_errors:
        completed = False
        report['release_errors'] = release_errors
    report.update(action='capture_test', ok=completed, handles_released=not release_errors, measured_fps=None, sensor_field_of_view_verified=False)
    if completed:
        report['requested_size_received'] = all(
            entry['actual_size'] == list(args.capture_size)
            for item in report['cameras'] for entry in item['frames']
        )
        if not report['requested_size_received']:
            report['notes'].append('At least one frame differs from the requested size. Review the camera format before configuring A/B coordinates.')
    return report, 0 if completed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--probe', action='store_true', help='Explicitly open each candidate index to report negotiated properties; the camera light may turn on.')
    action.add_argument('--capture-test', action='store_true', help='Explicitly open both selected cameras and read a few frames, then release them.')
    parser.add_argument('--indices', type=parse_indices, default=[0, 1, 2, 3, 4], help='Candidate indices for --probe only; default 0,1,2,3,4.')
    parser.add_argument('--devices', type=parse_indices, help='Two manually selected distinct indices required for --capture-test, for example 0,1.')
    parser.add_argument('--backend', choices=('dshow', 'msmf'), default='dshow')
    parser.add_argument('--capture-size', type=parse_size, default=(1920, 1080))
    parser.add_argument('--fps', type=float, default=15.0)
    parser.add_argument('--fourcc', default='MJPG')
    parser.add_argument('--frames', type=int, default=3, help='Frames per camera for --capture-test; default 3, maximum 30.')
    args = parser.parse_args()
    if args.capture_test and (args.devices is None or len(args.devices) != 2):
        parser.error('--capture-test requires --devices with exactly two distinct indices.')
    if not math.isfinite(args.fps) or args.fps <= 0 or args.fps > 240:
        parser.error('--fps must be greater than zero and at most 240.')
    if len(args.fourcc) != 4 or not args.fourcc.isascii():
        parser.error('--fourcc must contain exactly four ASCII characters, such as MJPG.')
    if not 1 <= args.frames <= 30:
        parser.error('--frames must be between 1 and 30.')
    report, code = inspect(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
