"""Route selection from capture-timestamped virtual gates.

This module simulates requests. It never reads GPIO or drives a point.
Callers must supply one shared monotonic time base for events and manual actions.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import threading
from typing import Any


def _timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _positive(value: Any, label: str) -> float:
    number = _timestamp(value)
    if number is None or number == 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _track(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _result(accepted: bool, reason: str, decision: dict | None = None) -> dict:
    return {"accepted": accepted, "reason": reason,
            "decision": dict(decision) if decision else None}


@dataclass
class _Lane:
    id: str
    mode: str
    time_threshold_s: float
    led_interval_s: float
    state: str = "idle"
    track_id: str | None = None
    a_timestamp: float | None = None
    last_event_timestamp: float | None = None
    last_requested_route: str | None = None
    uncertainty_reason: str | None = None


class RouteManager:
    """Up to four independent A/B selectors with explicit manual release.

    ``config['lanes']`` is a non-empty list of dicts with ``id`` and ``mode``
    (``time`` or ``led``). Both timing parameters default to 2 seconds.
    State changes are protected by an internal lock. Returned dicts are copies.
    """

    def __init__(self, config: dict):
        if not isinstance(config, dict):
            raise ValueError("config must be a dict")
        specs = config.get("lanes")
        if not isinstance(specs, list) or not 1 <= len(specs) <= 4:
            raise ValueError("lanes must contain between one and four lanes")
        self._lanes: dict[str, _Lane] = {}
        for spec in specs:
            if not isinstance(spec, dict):
                raise ValueError("each lane must be a dict")
            lane_id = spec.get("id")
            if not isinstance(lane_id, str) or not lane_id.strip():
                raise ValueError("lane id must be a non-empty string")
            if lane_id in self._lanes:
                raise ValueError("lane ids must be unique")
            mode = spec.get("mode")
            if mode not in ("time", "led"):
                raise ValueError("lane mode must be time or led")
            self._lanes[lane_id] = _Lane(
                id=lane_id, mode=mode,
                time_threshold_s=_positive(spec.get("time_threshold_s", 2),
                                           "time_threshold_s"),
                led_interval_s=_positive(spec.get("led_interval_s", 2),
                                         "led_interval_s"),
            )
        self._lock = threading.RLock()
        self._requests: deque[dict] = deque(maxlen=256)
        self._request_number = 0

    @staticmethod
    def _led_route(lane: _Lane, timestamp: float) -> str | None:
        if lane.a_timestamp is None or timestamp < lane.a_timestamp:
            return None
        elapsed = timestamp - lane.a_timestamp
        # fmod avoids overflowing an integer when given widely separated times.
        phase = math.fmod(elapsed, 2 * lane.led_interval_s)
        return "straight" if phase < lane.led_interval_s else "curve"

    @staticmethod
    def _set_uncertain(lane: _Lane, reason: str) -> None:
        lane.state = "uncertain"
        if lane.uncertainty_reason is None:
            lane.uncertainty_reason = reason

    def ingest(self, event: dict) -> dict:
        """Consume one gate observation; only matching B after A can request.

        ``track_id`` accepts a string or integer (normalized to a string).
        Reordered/equal timestamps are rejected per lane. Once a valid event is
        observed its capture timestamp advances the ordering watermark, even if
        it cannot arm or release a route. A different train while waiting makes
        the identity uncertain and requires manual clearance confirmation.
        """
        if not isinstance(event, dict):
            return _result(False, "invalid_event")
        with self._lock:
            lane_id = event.get("lane")
            if not isinstance(lane_id, str) or lane_id not in self._lanes:
                return _result(False, "unknown_lane")
            lane = self._lanes[lane_id]
            gate = event.get("gate")
            if gate not in ("A", "B"):
                return _result(False, "invalid_gate")
            track_id = _track(event.get("track_id"))
            if track_id is None:
                return _result(False, "invalid_track_id")
            timestamp = _timestamp(event.get("timestamp"))
            if timestamp is None:
                return _result(False, "invalid_timestamp")
            ambiguous = event.get("ambiguous", False)
            if not isinstance(ambiguous, bool):
                return _result(False, "invalid_ambiguous_flag")
            if (lane.last_event_timestamp is not None
                    and timestamp <= lane.last_event_timestamp):
                return _result(False, "stale_or_duplicate_event")
            lane.last_event_timestamp = timestamp
            if ambiguous:
                self._set_uncertain(lane, "ambiguous_detection")
                return _result(False, "ambiguous_detection")
            if lane.state == "uncertain":
                return _result(False, "lane_uncertain")
            if lane.state == "locked":
                return _result(False, "route_locked")
            if lane.state == "idle":
                if gate != "A":
                    return _result(False, "b_without_a")
                lane.state = "waiting"
                lane.track_id = track_id
                lane.a_timestamp = timestamp
                return _result(True, "armed")
            # Waiting for B for the train bound at A.
            if track_id != lane.track_id:
                self._set_uncertain(lane, "track_mismatch")
                return _result(False, "track_mismatch")
            if gate == "A":
                return _result(False, "already_armed")
            assert lane.a_timestamp is not None
            elapsed = timestamp - lane.a_timestamp
            route = ("straight" if elapsed < lane.time_threshold_s else "curve"
                     ) if lane.mode == "time" else self._led_route(lane, timestamp)
            assert route in ("straight", "curve")
            self._request_number += 1
            decision = {
                "event": "route_requested", "request_id": self._request_number,
                "lane": lane.id, "track_id": lane.track_id,
                "timestamp": timestamp, "a_timestamp": lane.a_timestamp,
                "elapsed_s": elapsed, "route": route, "mode": lane.mode,
                "simulated": True, "hardware_outputs_enabled": False,
            }
            lane.state = "locked"
            lane.last_requested_route = route
            self._requests.append(decision)
            return _result(True, "route_requested", decision)

    def mark_uncertain(self, lane: str, reason: str, now: float) -> dict:
        """Block a lane after track loss, camera outage or ambiguous identity."""
        with self._lock:
            if not isinstance(lane, str) or lane not in self._lanes:
                return _result(False, "unknown_lane")
            timestamp = _timestamp(now)
            if timestamp is None:
                return _result(False, "invalid_timestamp")
            if not isinstance(reason, str) or not reason.strip():
                return _result(False, "invalid_reason")
            state = self._lanes[lane]
            if (state.last_event_timestamp is not None
                    and timestamp < state.last_event_timestamp):
                return _result(False, "stale_uncertainty")
            state.last_event_timestamp = timestamp
            self._set_uncertain(state, reason.strip())
            return _result(True, "lane_uncertain")

    def release(self, lane: str, confirm_clear: bool, now: float) -> dict:
        """Clear only the software lock after operator-confirmed full passage.

        This neither changes the previous requested route nor drives a point.
        A new A must be captured after this manual action to arm another train.
        """
        with self._lock:
            if not isinstance(lane, str) or lane not in self._lanes:
                return _result(False, "unknown_lane")
            timestamp = _timestamp(now)
            if timestamp is None:
                return _result(False, "invalid_timestamp")
            if confirm_clear is not True:
                return _result(False, "clear_confirmation_required")
            state = self._lanes[lane]
            if (state.last_event_timestamp is not None
                    and timestamp < state.last_event_timestamp):
                return _result(False, "stale_release")
            state.state = "idle"
            state.track_id = None
            state.a_timestamp = None
            state.uncertainty_reason = None
            state.last_event_timestamp = timestamp
            return _result(True, "released")

    def status(self, now: float) -> dict:
        """Return copied state. Polling the LED indication never requests output."""
        timestamp = _timestamp(now)
        if timestamp is None:
            raise ValueError("now must be a non-negative finite timestamp")
        with self._lock:
            lanes = []
            for lane in self._lanes.values():
                lanes.append({
                    "id": lane.id, "mode": lane.mode, "state": lane.state,
                    "track_id": lane.track_id, "a_timestamp": lane.a_timestamp,
                    "last_event_timestamp": lane.last_event_timestamp,
                    "last_requested_route": lane.last_requested_route,
                    "led_route": self._led_route(lane, timestamp)
                    if lane.state == "waiting" and lane.mode == "led" else None,
                    "uncertainty_reason": lane.uncertainty_reason,
                    "time_threshold_s": lane.time_threshold_s,
                    "led_interval_s": lane.led_interval_s,
                })
            return {"lanes": lanes, "requests": [dict(r) for r in self._requests],
                    "hardware_outputs_enabled": False}
