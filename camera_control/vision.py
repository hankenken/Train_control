"""Fixed-background, lane-constrained train detection with conservative tracking.

Images are uint8 BGR or grayscale arrays. Backgrounds are installed explicitly
with ``set_background`` only when the operator knows the scene is empty; they
are never updated from normal frames, so a stationary tram remains detectable.
OpenCV accelerates image operations when installed. The NumPy fallback exists
for deterministic offline tests and small images, not a real-time guarantee.

This module does not clear routes, operate GPIO, identify individual liveries,
or merge identities across cameras. Lost/ambiguous observations emit warnings,
never inferred gate crossings or inferred train clearance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:  # Offline test environments need only NumPy.
    cv2 = None


Point = tuple[float, float]
VisionResult = dict[str, Any]


def _point(value: Any) -> Point:
    if len(value) != 2:
        raise ValueError("points must have two coordinates")
    point = (float(value[0]), float(value[1]))
    if not all(math.isfinite(v) for v in point):
        raise ValueError("coordinates must be finite")
    return point


@dataclass(frozen=True)
class LaneSpec:
    id: str
    camera: str
    polygon: tuple[Point, ...]
    gate_a: tuple[Point, Point]
    gate_b: tuple[Point, Point]
    direction: Point

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "LaneSpec":
        polygon = tuple(_point(p) for p in value["polygon"])
        if len(polygon) < 3:
            raise ValueError("lane polygons require at least three points")
        signed_area = sum(
            p[0] * q[1] - q[0] * p[1]
            for p, q in zip(polygon, polygon[1:] + polygon[:1])
        )
        if abs(signed_area) < 1e-6:
            raise ValueError("lane polygon has zero area")
        direction = _point(value["direction"])
        length = math.hypot(*direction)
        if length < 1e-9:
            raise ValueError("lane direction must be nonzero")
        gates = []
        for name in ("gate_a", "gate_b"):
            if len(value[name]) != 2:
                raise ValueError("each gate must be a finite line segment")
            gate = tuple(_point(p) for p in value[name])
            if math.dist(*gate) < 1e-9:
                raise ValueError("gates must have positive length")
            gates.append(gate)
        return cls(
            str(value["id"]), str(value["camera"]), polygon,
            gates[0], gates[1],
            (direction[0] / length, direction[1] / length),
        )


@dataclass
class _Track:
    id: int
    lane: str
    camera: str
    center: Point
    last_seen: float
    area: int
    visible: bool = True
    ambiguous: bool = False
    associable: bool = True
    fired: set[str] = field(default_factory=set)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "camera": self.camera, "lane": self.lane,
            "center": list(self.center), "visible": self.visible,
            "ambiguous": self.ambiguous, "last_seen": self.last_seen,
        }


@dataclass(frozen=True)
class _Detection:
    center: Point
    area: int
    ambiguous: bool


def _gray(image: np.ndarray) -> np.ndarray:
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError("images must be uint8 NumPy arrays")
    if image.ndim == 2 and image.shape[0] and image.shape[1]:
        return image.copy()
    if image.ndim == 3 and image.shape[2] == 3 and image.shape[0] and image.shape[1]:
        if cv2 is not None:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # BGR convention, rounded consistently enough for threshold detection.
        a = image.astype(np.uint16)
        return ((29 * a[..., 0] + 150 * a[..., 1] + 77 * a[..., 2] + 128) >> 8).astype(np.uint8)
    raise ValueError("images must have shape HxW or HxWx3")


def _polygon_mask(shape: tuple[int, int], polygon: tuple[Point, ...]) -> np.ndarray:
    if cv2 is not None:
        mask = np.zeros(shape, dtype=np.uint8)
        cv2.fillPoly(mask, [np.rint(polygon).astype(np.int32)], 1)
        return mask.astype(bool)
    # Pixel-centre ray casting, including polygon boundaries.
    y, x = np.indices(shape, dtype=np.float64)
    inside = np.zeros(shape, dtype=bool)
    boundary = np.zeros(shape, dtype=bool)
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = q[0] - p[0], q[1] - p[1]
        cross = (x - p[0]) * dy - (y - p[1]) * dx
        boundary |= ((np.abs(cross) < 1e-7)
                     & (x >= min(p[0], q[0])) & (x <= max(p[0], q[0]))
                     & (y >= min(p[1], q[1])) & (y <= max(p[1], q[1])))
        if abs(dy) > 1e-12:
            intersection = dx * (y - p[1]) / dy + p[0]
            inside ^= ((p[1] > y) != (q[1] > y)) & (x < intersection)
    return inside | boundary


def _morphology(mask: np.ndarray, kernel_size: int) -> np.ndarray:
    if kernel_size <= 1:
        return mask
    if cv2 is not None:
        a = mask.astype(np.uint8)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        a = cv2.morphologyEx(a, cv2.MORPH_OPEN, kernel)
        return cv2.morphologyEx(a, cv2.MORPH_CLOSE, kernel).astype(bool)

    def operation(a: np.ndarray, erode: bool) -> np.ndarray:
        radius = kernel_size // 2
        pad = np.pad(a, radius, constant_values=False)
        result = np.ones_like(a) if erode else np.zeros_like(a)
        for yy in range(kernel_size):
            for xx in range(kernel_size):
                view = pad[yy:yy + a.shape[0], xx:xx + a.shape[1]]
                if erode:
                    result &= view
                else:
                    result |= view
        return result

    opened = operation(operation(mask, True), False)
    return operation(operation(opened, False), True)


def _components(mask: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return eight-connected component pixel coordinates in the cropped ROI."""
    if cv2 is not None:
        count, labels, _, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        return [np.nonzero(labels == label) for label in range(1, count)]
    remaining = set(zip(*np.nonzero(mask)))
    result = []
    while remaining:
        seed = remaining.pop()
        stack = [seed]
        coordinates = [seed]
        while stack:
            y, x = stack.pop()
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if (yy, xx) in remaining:
                        remaining.remove((yy, xx))
                        stack.append((yy, xx))
                        coordinates.append((yy, xx))
        result.append((np.array([p[0] for p in coordinates]),
                       np.array([p[1] for p in coordinates])))
    return result


def _crossing_fraction(start: Point, end: Point, gate: tuple[Point, Point]) -> float | None:
    """Finite-segment intersection; exclude a trajectory beginning on the gate."""
    a, b = gate
    rx, ry = end[0] - start[0], end[1] - start[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-9:
        return None
    qx, qy = a[0] - start[0], a[1] - start[1]
    fraction = (qx * sy - qy * sx) / denominator
    gate_fraction = (qx * ry - qy * rx) / denominator
    if 1e-9 < fraction <= 1 + 1e-9 and -1e-9 <= gate_fraction <= 1 + 1e-9:
        return min(fraction, 1.0)
    return None


class VisionEngine:
    def __init__(
        self, lanes: list[dict[str, Any] | LaneSpec], *, threshold: int = 24,
        min_area: int = 20, max_area: int | None = None,
        max_match_distance: float = 80.0, lost_timeout: float = 1.0,
        max_tracks: int = 4, morph_kernel: int = 3,
    ) -> None:
        self.lanes = [p if isinstance(p, LaneSpec) else LaneSpec.from_dict(p) for p in lanes]
        if len({p.id for p in self.lanes}) != len(self.lanes):
            raise ValueError("lane IDs must be globally unique")
        if not 0 <= threshold <= 255 or min_area < 1:
            raise ValueError("invalid detection threshold or minimum area")
        if max_area is not None and max_area < min_area:
            raise ValueError("maximum area must not be smaller than minimum area")
        if max_match_distance <= 0 or lost_timeout <= 0 or max_tracks < 1:
            raise ValueError("tracking limits must be positive")
        if morph_kernel < 1 or morph_kernel % 2 == 0:
            raise ValueError("morphology kernel must be a positive odd integer")
        self.threshold, self.min_area, self.max_area = threshold, min_area, max_area
        self.max_match_distance, self.lost_timeout = float(max_match_distance), float(lost_timeout)
        self.max_tracks, self.morph_kernel = max_tracks, morph_kernel
        self._backgrounds: dict[str, np.ndarray] = {}
        self._masks: dict[str, dict[str, np.ndarray]] = {}
        self._overlap: dict[str, np.ndarray] = {}
        self._regions: dict[str, dict[str, tuple[int, int, int, int]]] = {}
        self._tracks: dict[int, _Track] = {}
        self._last_time: dict[str, float] = {}
        self._next_id = 1

    def set_background(self, camera_id: str, image: np.ndarray) -> None:
        """Operator-only empty-scene calibration. Clears that camera's tracks."""
        camera_id = str(camera_id)
        gray = _gray(image)
        lanes = [p for p in self.lanes if p.camera == camera_id]
        if not lanes:
            raise ValueError("camera has no configured lanes")
        masks = {p.id: _polygon_mask(gray.shape, p.polygon) for p in lanes}
        if any(not mask.any() for mask in masks.values()):
            raise ValueError("lane polygon lies outside the calibrated image")
        self._backgrounds[camera_id] = gray
        self._masks[camera_id] = masks
        regions = {}
        for lane_id, mask in masks.items():
            ys, xs = np.nonzero(mask)
            regions[lane_id] = (int(xs.min()), int(xs.max() + 1),
                                int(ys.min()), int(ys.max() + 1))
        self._regions[camera_id] = regions
        self._overlap[camera_id] = np.sum(list(masks.values()), axis=0) > 1
        self._tracks = {i: t for i, t in self._tracks.items() if t.camera != camera_id}
        self._last_time.pop(camera_id, None)

    def reset_tracks(self, camera_id: str | None = None) -> None:
        """Explicit operator reset, not evidence that a train or route has cleared."""
        if camera_id is None:
            self._tracks.clear()
            self._last_time.clear()
        else:
            camera_id = str(camera_id)
            self._tracks = {i: t for i, t in self._tracks.items() if t.camera != camera_id}
            self._last_time.pop(camera_id, None)

    def _detections(self, camera: str, gray: np.ndarray, lane: LaneSpec) -> list[_Detection]:
        mask = self._masks[camera][lane.id]
        x0, x1, y0, y1 = self._regions[camera][lane.id]
        foreground = (np.abs(gray[y0:y1, x0:x1].astype(np.int16)
                             - self._backgrounds[camera][y0:y1, x0:x1].astype(np.int16)) > self.threshold)
        foreground &= mask[y0:y1, x0:x1]
        foreground = _morphology(foreground, self.morph_kernel)
        foreground &= mask[y0:y1, x0:x1]
        overlap = self._overlap[camera][y0:y1, x0:x1]
        result = []
        for ys, xs in _components(foreground):
            area = len(xs)
            if area >= self.min_area:
                result.append(_Detection(
                    (float(xs.mean() + x0), float(ys.mean() + y0)), area,
                    bool(overlap[ys, xs].any()) or (self.max_area is not None and area > self.max_area),
                ))
        return sorted(result, key=lambda d: (d.center[0], d.center[1]))

    def process(self, camera_id: str, image: np.ndarray, timestamp: float) -> VisionResult:
        camera = str(camera_id)
        warnings: list[str] = []
        events: list[dict[str, Any]] = []

        def result() -> dict[str, Any]:
            return {
                "camera": camera, "timestamp": timestamp,
                "calibrated": camera in self._backgrounds,
                "tracks": [t.public() for t in sorted(self._tracks.values(), key=lambda t: t.id)
                           if t.camera == camera],
                "events": events, "warnings": list(dict.fromkeys(warnings)),
            }

        if camera not in self._backgrounds:
            warnings.append("background_not_set:" + camera)
            return result()
        if not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            warnings.append("invalid_timestamp:" + camera)
            return result()
        if camera in self._last_time and timestamp <= self._last_time[camera]:
            warnings.append("nonmonotonic_timestamp:" + camera)
            return result()
        try:
            gray = _gray(image)
        except ValueError:
            warnings.append("invalid_image:" + camera)
            return result()
        if gray.shape != self._backgrounds[camera].shape:
            warnings.append("image_shape_changed:" + camera)
            return result()
        self._last_time[camera] = float(timestamp)
        # Expiry is internal bookkeeping, never a train-clear event.
        expired = [i for i, t in self._tracks.items()
                   if t.camera == camera and timestamp - t.last_seen > self.lost_timeout]
        for track_id in expired:
            warnings.append("track_expired:" + str(track_id))
            del self._tracks[track_id]
        lanes = [p for p in self.lanes if p.camera == camera]
        detections = {p.id: self._detections(camera, gray, p) for p in lanes}
        other_visible = sum(t.visible and t.associable for t in self._tracks.values() if t.camera != camera)
        if sum(map(len, detections.values())) + other_visible > self.max_tracks:
            warnings.append("max_tracks_exceeded:" + camera)
            for t in self._tracks.values():
                if t.camera == camera:
                    t.visible, t.ambiguous, t.associable = False, True, False
            return result()
        for lane in lanes:
            current = detections[lane.id]
            previous = [t for t in self._tracks.values() if t.camera == camera and t.lane == lane.id]
            active = [t for t in previous if t.associable]
            invalid_detections = {j for j, d in enumerate(current) if d.ambiguous}
            if invalid_detections:
                warnings.append("ambiguous_foreground:" + lane.id)
            candidates = {(i, j) for i, t in enumerate(active) for j, d in enumerate(current)
                          if math.dist(t.center, d.center) <= self.max_match_distance}
            bad_tracks = {i for i in range(len(active))
                          if sum(a == i for a, _ in candidates) > 1}
            invalid_detections |= {j for j in range(len(current))
                                   if sum(b == j for _, b in candidates) > 1}
            # Propagate ambiguity through the association graph rather than
            # guessing the nearest identity during a merge or split.
            while True:
                new_bad = bad_tracks | {i for i, j in candidates if j in invalid_detections}
                new_invalid = invalid_detections | {j for i, j in candidates if i in new_bad}
                if new_bad == bad_tracks and new_invalid == invalid_detections:
                    break
                bad_tracks, invalid_detections = new_bad, new_invalid
            if bad_tracks:
                warnings.append("identity_ambiguous:" + lane.id)
            lane_uncertain = (
                any(not t.associable for t in previous)
                or bool(bad_tracks) or bool(invalid_detections)
                or any(sum(a == i and j not in invalid_detections for a, j in candidates) != 1
                       for i in range(len(active)))
            )
            if lane_uncertain:
                warnings.append("lane_identity_unresolved:" + lane.id)
            matched = set()
            for i, track in enumerate(active):
                matches = [j for a, j in candidates if a == i and j not in invalid_detections]
                if i in bad_tracks or len(matches) != 1:
                    track.visible, track.ambiguous, track.associable = False, True, False
                    warnings.append("track_lost:" + str(track.id))
                    continue
                j = matches[0]
                detection = current[j]
                matched.add(j)
                old_center, old_time = track.center, track.last_seen
                delta = (detection.center[0] - old_center[0], detection.center[1] - old_center[1])
                forward = delta[0] * lane.direction[0] + delta[1] * lane.direction[1] > 1e-7
                # A frame interval beyond timeout cannot produce a crossing:
                # that track has already expired above and gets a new ID.
                if forward and not lane_uncertain:
                    for gate_name, gate in (("A", lane.gate_a), ("B", lane.gate_b)):
                        fraction = _crossing_fraction(old_center, detection.center, gate)
                        if fraction is not None and gate_name not in track.fired:
                            events.append({"camera": camera, "lane": lane.id,
                                           "track_id": track.id, "gate": gate_name,
                                           "timestamp": old_time + fraction * (timestamp - old_time)})
                            track.fired.add(gate_name)
                track.center, track.last_seen, track.area = detection.center, float(timestamp), detection.area
                track.visible, track.ambiguous = True, lane_uncertain
            uncertain = lane_uncertain
            for j, detection in enumerate(current):
                if j in matched or j in invalid_detections:
                    continue
                if uncertain:
                    warnings.append("lane_identity_unresolved:" + lane.id)
                    continue
                track = _Track(self._next_id, lane.id, camera, detection.center, float(timestamp), detection.area)
                self._tracks[track.id] = track
                self._next_id += 1
        events.sort(key=lambda e: (e["timestamp"], e["track_id"], e["gate"]))
        return result()
