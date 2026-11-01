"""Offline synthetic image tests; these do not validate physical cameras."""
import unittest

import numpy as np

from camera_control.vision import LaneSpec, VisionEngine


def lane(name="up_outer", camera="cam0", x0=2, x1=117, direction=(0, 1)):
    return {
        "id": name, "camera": camera,
        "polygon": [[x0, 2], [x1, 2], [x1, 117], [x0, 117]],
        "gate_a": [[x0 + 2, 40], [x1 - 2, 40]],
        "gate_b": [[x0 + 2, 70], [x1 - 2, 70]],
        "direction": list(direction),
    }


def frame(*centres, width=120, height=120):
    result = np.zeros((height, width), dtype=np.uint8)
    for x, y in centres:
        result[y - 5:y + 6, x - 5:x + 6] = 180
    return result


class VisionTests(unittest.TestCase):
    def engine(self, lanes=None, **kwargs):
        engine = VisionEngine(lanes or [lane()], **kwargs)
        engine.set_background("cam0", frame())
        return engine

    def test_requires_explicit_empty_background(self):
        engine = VisionEngine([lane()])
        a = engine.process("cam0", frame((50, 20)), 0.0)
        b = engine.process("cam0", frame((50, 90)), 0.2)
        self.assertFalse(a["calibrated"])
        self.assertEqual(a["tracks"], [])
        self.assertEqual(b["events"], [])
        self.assertIn("background_not_set:cam0", b["warnings"])

    def test_stationary_train_persists_with_same_identity(self):
        engine = self.engine()
        initial = engine.process("cam0", frame((50, 25)), 0.0)
        track_id = initial["tracks"][0]["id"]
        for n in range(1, 51):
            result = engine.process("cam0", frame((50, 25)), n * 0.1)
            self.assertEqual(result["tracks"][0]["id"], track_id)
            self.assertTrue(result["tracks"][0]["visible"])
            self.assertFalse(result["tracks"][0]["ambiguous"])
            self.assertEqual(result["events"], [])

    def test_crosses_thin_gates_between_frames_with_interpolated_time(self):
        engine = self.engine(max_match_distance=90)
        engine.process("cam0", frame((50, 20)), 0.0)
        result = engine.process("cam0", frame((50, 80)), 0.6)
        self.assertEqual([e["gate"] for e in result["events"]], ["A", "B"])
        self.assertAlmostEqual(result["events"][0]["timestamp"], 0.2)
        self.assertAlmostEqual(result["events"][1]["timestamp"], 0.5)
        self.assertEqual(result["events"][0]["track_id"], result["events"][1]["track_id"])

    def test_wrong_direction_does_not_select_route(self):
        engine = self.engine(max_match_distance=90)
        engine.process("cam0", frame((50, 80)), 0.0)
        result = engine.process("cam0", frame((50, 20)), 0.6)
        self.assertEqual(result["events"], [])

    def test_gate_occurs_once_per_track_even_if_reversing(self):
        engine = self.engine(max_match_distance=90)
        engine.process("cam0", frame((50, 20)), 0.0)
        self.assertEqual(len(engine.process("cam0", frame((50, 80)), 0.3)["events"]), 2)
        self.assertEqual(engine.process("cam0", frame((50, 20)), 0.5)["events"], [])
        self.assertEqual(engine.process("cam0", frame((50, 80)), 0.8)["events"], [])

    def test_crossing_infinite_extension_is_not_crossing_finite_gate(self):
        spec = lane()
        spec["gate_a"] = [[10, 40], [30, 40]]
        spec["gate_b"] = [[10, 70], [30, 70]]
        engine = self.engine([spec], max_match_distance=90)
        engine.process("cam0", frame((80, 20)), 0.0)
        self.assertEqual(engine.process("cam0", frame((80, 80)), 0.5)["events"], [])

    def test_merged_detections_do_not_guess_identity_or_emit_gate(self):
        engine = self.engine(max_match_distance=80)
        first = engine.process("cam0", frame((30, 20), (70, 20)), 0.0)
        self.assertEqual(len(first["tracks"]), 2)
        # A broad foreground blob contains both possible identities, beyond A.
        merged = frame()
        merged[45:56, 25:76] = 180
        result = engine.process("cam0", merged, 0.4)
        self.assertEqual(result["events"], [])
        self.assertIn("identity_ambiguous:up_outer", result["warnings"])
        self.assertTrue(all(t["ambiguous"] for t in result["tracks"]))
        self.assertTrue(all(not t["visible"] for t in result["tracks"]))

    def test_one_missing_identity_suppresses_other_gates_in_same_lane(self):
        engine = self.engine(max_match_distance=35)
        engine.process("cam0", frame((25, 25), (90, 25)), 0.0)
        result = engine.process("cam0", frame((25, 50)), 0.3)
        self.assertEqual(result["events"], [])
        self.assertTrue(any(w.startswith("track_lost:") for w in result["warnings"]))

    def test_loss_and_reappearance_never_infer_clear_or_reuse_id(self):
        engine = self.engine(lost_timeout=1.0)
        first = engine.process("cam0", frame((50, 20)), 0.0)
        old_id = first["tracks"][0]["id"]
        lost = engine.process("cam0", frame(), 0.1)
        self.assertFalse(lost["tracks"][0]["visible"])
        self.assertEqual(lost["events"], [])
        uncertain = engine.process("cam0", frame((50, 80)), 0.2)
        self.assertEqual(uncertain["events"], [])
        self.assertEqual([t["id"] for t in uncertain["tracks"]], [old_id])
        after_timeout = engine.process("cam0", frame((50, 80)), 1.2)
        self.assertEqual(after_timeout["events"], [])
        self.assertNotEqual(after_timeout["tracks"][0]["id"], old_id)
        self.assertIn("track_expired:" + str(old_id), after_timeout["warnings"])

    def test_overlapping_projected_lanes_are_ambiguous(self):
        engine = self.engine([lane("left", x1=72), lane("right", x0=48)])
        result = engine.process("cam0", frame((60, 30)), 0.0)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["tracks"], [])
        self.assertIn("ambiguous_foreground:left", result["warnings"])
        self.assertIn("ambiguous_foreground:right", result["warnings"])

    def test_four_disjoint_lanes_preserve_four_stopped_trains(self):
        specs = [lane(str(i), x0=i * 70 + 2, x1=i * 70 + 67) for i in range(4)]
        engine = VisionEngine(specs, max_tracks=4)
        engine.set_background("cam0", frame(width=282))
        image = frame(*[(i * 70 + 30, 25) for i in range(4)], width=282)
        a = engine.process("cam0", image, 0.0)
        b = engine.process("cam0", image, 0.5)
        self.assertEqual(len(a["tracks"]), 4)
        self.assertEqual([t["id"] for t in a["tracks"]], [t["id"] for t in b["tracks"]])
        self.assertEqual(b["events"], [])

    def test_camera_timestamps_and_calibration_are_independent(self):
        engine = VisionEngine([lane("a", "cam0"), lane("b", "cam1")])
        engine.set_background("cam0", frame())
        engine.set_background("cam1", frame())
        a = engine.process("cam0", frame((50, 20)), 10.0)
        b = engine.process("cam1", frame((50, 20)), 1.0)
        self.assertNotEqual(a["tracks"][0]["id"], b["tracks"][0]["id"])
        self.assertEqual(b["warnings"], [])
        engine.set_background("cam0", frame())
        self.assertEqual(len(engine.process("cam1", frame((50, 20)), 1.1)["tracks"]), 1)

    def test_invalid_or_out_of_order_frames_do_not_create_events(self):
        engine = self.engine()
        engine.process("cam0", frame((50, 20)), 1.0)
        bad_time = engine.process("cam0", frame((50, 80)), 0.5)
        self.assertEqual(bad_time["events"], [])
        self.assertIn("nonmonotonic_timestamp:cam0", bad_time["warnings"])
        bad_shape = engine.process("cam0", np.zeros((60, 60), np.uint8), 1.2)
        self.assertEqual(bad_shape["events"], [])
        self.assertIn("image_shape_changed:cam0", bad_shape["warnings"])

    def test_too_many_detections_pause_without_events(self):
        engine = self.engine(max_tracks=1)
        result = engine.process("cam0", frame((25, 20), (90, 20)), 0.0)
        self.assertIn("max_tracks_exceeded:cam0", result["warnings"])
        self.assertEqual(result["events"], [])

    def test_bgr_input_and_configuration_validation(self):
        engine = self.engine()
        image = np.repeat(frame((50, 25))[..., None], 3, axis=2)
        self.assertTrue(engine.process("cam0", image, 0.0)["tracks"][0]["visible"])
        with self.assertRaises(ValueError):
            VisionEngine([lane(direction=(0, 0))])
        with self.assertRaises(ValueError):
            VisionEngine([lane(), lane()])
        with self.assertRaises(ValueError):
            LaneSpec.from_dict({**lane(), "gate_a": [[1, 2], [1, 2]]})


if __name__ == "__main__":
    unittest.main()
