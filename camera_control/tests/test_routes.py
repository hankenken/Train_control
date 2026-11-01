import math
import unittest

from camera_control.routes import RouteManager


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.manager = RouteManager({"lanes": [
            {"id": "upper", "mode": "time", "time_threshold_s": 2},
            {"id": "lower", "mode": "led", "led_interval_s": 2},
        ]})

    def event(self, lane, gate, timestamp, track="train-1", **extra):
        return self.manager.ingest({"lane": lane, "track_id": track,
                                    "gate": gate, "timestamp": timestamp, **extra})

    def lane(self, lane="upper", now=100):
        return next(v for v in self.manager.status(now)["lanes"] if v["id"] == lane)

    def test_no_request_before_b_or_from_led_polling(self):
        self.assertTrue(self.event("lower", "A", 1)["accepted"])
        self.assertEqual(self.lane("lower", 1)["led_route"], "straight")
        self.assertEqual(self.lane("lower", 3)["led_route"], "curve")
        self.assertEqual(self.lane("lower", 5)["led_route"], "straight")
        self.assertIsNone(self.lane("lower")["last_requested_route"])
        self.assertEqual(self.manager.status(100)["requests"], [])

    def test_time_threshold_and_release_preserve_last_route(self):
        self.event("upper", "A", 1)
        r = self.event("upper", "B", 2)
        self.assertEqual(r["decision"]["route"], "straight")
        self.assertEqual(self.lane()["state"], "locked")
        self.assertTrue(self.manager.release("upper", True, 3)["accepted"])
        self.assertEqual(self.lane()["last_requested_route"], "straight")
        self.event("upper", "A", 4)
        self.assertEqual(self.lane()["last_requested_route"], "straight")
        r = self.event("upper", "B", 6)
        self.assertEqual(r["decision"]["route"], "curve")
        self.assertEqual(len(self.manager.status(100)["requests"]), 2)

    def test_led_uses_capture_time_even_after_ui_polled_later(self):
        self.event("lower", "A", 10)
        self.assertEqual(self.lane("lower", 14.5)["led_route"], "straight")
        # B was captured earlier, during the curve interval.
        r = self.event("lower", "B", 12.5)
        self.assertEqual(r["decision"]["route"], "curve")
        self.assertEqual(r["decision"]["timestamp"], 12.5)
        self.assertTrue(r["decision"]["simulated"])
        self.assertFalse(r["decision"]["hardware_outputs_enabled"])

    def test_mismatched_train_blocks_instead_of_selecting(self):
        self.event("upper", "A", 10, track="first")
        r = self.event("upper", "B", 11, track="second")
        self.assertFalse(r["accepted"])
        self.assertEqual(self.lane()["state"], "uncertain")
        self.assertFalse(self.event("upper", "B", 12, track="first")["accepted"])
        self.assertEqual(self.manager.status(100)["requests"], [])

    def test_ambiguity_and_track_loss_do_not_clear_or_drive(self):
        self.event("upper", "A", 10)
        r = self.manager.mark_uncertain("upper", "camera_offline", 11)
        self.assertTrue(r["accepted"])
        self.assertFalse(self.event("upper", "B", 12)["accepted"])
        self.assertFalse(self.manager.release("upper", False, 13)["accepted"])
        self.assertEqual(self.lane()["state"], "uncertain")
        self.assertTrue(self.manager.release("upper", True, 14)["accepted"])
        self.assertEqual(self.lane()["state"], "idle")
        self.assertEqual(self.manager.status(100)["requests"], [])

    def test_ambiguous_b_after_a_does_not_request(self):
        self.event("lower", "A", 1)
        self.assertFalse(self.event("lower", "B", 2, ambiguous=True)["accepted"])
        self.assertEqual(self.lane("lower")["state"], "uncertain")
        self.assertIsNone(self.lane("lower")["last_requested_route"])

    def test_stale_and_duplicate_events_do_not_repeat_or_rearm(self):
        self.event("upper", "A", 10)
        self.assertFalse(self.event("upper", "A", 10)["accepted"])
        self.assertFalse(self.event("upper", "B", 9)["accepted"])
        self.assertTrue(self.event("upper", "B", 11)["accepted"])
        self.assertFalse(self.event("upper", "B", 11)["accepted"])
        self.assertFalse(self.event("upper", "A", 12)["accepted"])
        self.assertEqual(len(self.manager.status(100)["requests"]), 1)
        self.manager.release("upper", True, 13)
        self.assertFalse(self.event("upper", "A", 12.5)["accepted"])
        self.assertEqual(self.lane()["state"], "idle")

    def test_b_without_a_and_reordered_a_do_not_arm(self):
        self.assertFalse(self.event("upper", "B", 10)["accepted"])
        self.assertFalse(self.event("upper", "A", 9)["accepted"])
        self.assertEqual(self.lane()["state"], "idle")

    def test_lane_locks_are_independent(self):
        self.event("upper", "A", 1)
        self.event("lower", "A", 1)
        self.event("upper", "B", 2)
        self.assertEqual(self.lane("lower")["state"], "waiting")
        self.assertEqual(self.event("lower", "B", 3)["decision"]["route"], "curve")

    def test_release_does_not_auto_restore_or_repeat_request(self):
        self.event("upper", "A", 1)
        self.event("upper", "B", 2)
        before = self.manager.status(3)["requests"]
        self.assertFalse(self.manager.release("upper", 1, 3)["accepted"])
        self.assertTrue(self.manager.release("upper", True, 3)["accepted"])
        self.assertEqual(self.manager.status(4)["requests"], before)
        self.assertEqual(self.lane()["last_requested_route"], "straight")

    def test_invalid_event_data_never_changes_state(self):
        cases = [None, {}, {"lane": "other"}]
        base = {"lane": "upper", "track_id": "T", "gate": "A", "timestamp": 1}
        for key, values in [("timestamp", [math.nan, math.inf, -1, True, "1"]),
                            ("gate", ["C", None]), ("track_id", [None, [], True]),
                            ("ambiguous", [1, "true"])]:
            cases.extend({**base, key: value} for value in values)
        for case in cases:
            with self.subTest(event=case):
                self.assertFalse(self.manager.ingest(case)["accepted"])
        self.assertEqual(self.lane()["state"], "idle")
        self.assertEqual(self.manager.status(100)["requests"], [])

    def test_status_and_decision_are_copies(self):
        self.event("upper", "A", 1)
        result = self.event("upper", "B", 2)
        result["decision"]["route"] = "bad"
        snapshot = self.manager.status(3)
        snapshot["requests"][0]["route"] = "bad"
        snapshot["lanes"][0]["state"] = "idle"
        self.assertEqual(self.lane()["state"], "locked")
        self.assertEqual(self.manager.status(4)["requests"][0]["route"], "straight")

    def test_config_rejects_duplicate_lanes_invalid_timing_and_too_many(self):
        for config in [{}, {"lanes": []}, {"lanes": [{"id": "x", "mode": "bad"}]},
                       {"lanes": [{"id": "x", "mode": "time", "time_threshold_s": 0}]},
                       {"lanes": [{"id": "x", "mode": "led", "led_interval_s": math.nan}]},
                       {"lanes": [{"id": "x", "mode": "time"}] * 2},
                       {"lanes": [{"id": str(i), "mode": "time"} for i in range(5)]}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                RouteManager(config)


if __name__ == "__main__":
    unittest.main()
