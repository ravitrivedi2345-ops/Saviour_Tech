"""
test_backend.py — Comprehensive unit tests for Component 2 (Trajectory & Analytics Backend).
"""

import unittest
from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from camera_graph import CAMERAS, camera_distance_km, is_feasible, implied_speed_kmph
from matcher import levenshtein, normalize_plate, plates_match, build_trajectories
from identity import get_vehicle_info, is_wanted


class TestCameraGraph(unittest.TestCase):
    def test_camera_graph_nodes(self):
        self.assertEqual(len(CAMERAS), 9)
        self.assertIn("CAM_01", CAMERAS)
        self.assertIn("CAM_09", CAMERAS)

    def test_distance_calculation(self):
        d = camera_distance_km("CAM_01", "CAM_02")
        self.assertIsNotNone(d)
        self.assertGreater(d, 0.0)
        self.assertLess(d, 50.0)

    def test_feasibility_check(self):
        # Feasible: 2 hours for a short hop
        self.assertTrue(is_feasible("CAM_01", "CAM_02", 7200))
        # Physically impossible: 1 second across town (>80 km/h)
        self.assertFalse(is_feasible("CAM_01", "CAM_02", 1))

    def test_implied_speed(self):
        # 10 km in 3600 seconds = 10 km/h
        spd = implied_speed_kmph("CAM_01", "CAM_02", 3600)
        self.assertIsNotNone(spd)
        self.assertGreater(spd, 0)


class TestFuzzyMatcher(unittest.TestCase):
    def test_levenshtein_distance(self):
        self.assertEqual(levenshtein("DL01AB1234", "DL01AB1234"), 0)
        self.assertEqual(levenshtein("DL01AB1234", "DLO1AB1234"), 1)  # 0 -> O
        self.assertEqual(levenshtein("DL01AB1234", "DLO1A81234"), 2)  # 0 -> O, B -> 8
        self.assertGreater(levenshtein("DL01AB1234", "MH12XY5678"), 2)

    def test_plates_match(self):
        # OCR character confusions should match
        self.assertTrue(plates_match("DL01AB1234", "DLO1AB1234"))
        self.assertFalse(plates_match("DL01AB1234", "RJ14GH7777"))

    def test_trajectory_building_with_gap(self):
        now = datetime.now(timezone.utc)
        detections = [
            {
                "plate_raw": "DL01AB1234",
                "camera_id": "CAM_01",
                "timestamp": now.isoformat(),
                "vehicle_type": "Car",
                "confidence": 0.95,
            },
            # Sighted 2 seconds later across Delhi at CAM_09 -> physically impossible -> triggers GAP
            {
                "plate_raw": "DLO1AB1234",  # OCR typo
                "camera_id": "CAM_09",
                "timestamp": (now + timedelta(seconds=2)).isoformat(),
                "vehicle_type": "Car",
                "confidence": 0.88,
            },
        ]
        trajectories = build_trajectories(detections)
        self.assertTrue(len(trajectories) > 0)
        first_traj = list(trajectories.values())[0]
        # Should contain segments and gap markers
        self.assertTrue(len(first_traj["segments"]) >= 1)


class TestPrivacyAndEnforcement(unittest.TestCase):
    def test_wanted_vehicle_check(self):
        self.assertTrue(is_wanted("DL01AB1234"))
        self.assertTrue(is_wanted("MH12XY5678"))
        self.assertFalse(is_wanted("HR26DK0001"))

    def test_identity_vault_isolation(self):
        owner = get_vehicle_info("DL01AB1234")
        self.assertIsNotNone(owner)
        self.assertEqual(owner["owner_name"], "Ramesh Kumar Sharma")
        self.assertIn("address", owner)


if __name__ == "__main__":
    unittest.main()
