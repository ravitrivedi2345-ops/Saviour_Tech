"""
test_trajectory_engine.py — Unit tests for Component 2 (Trajectory Reconstruction Engine).
"""

import unittest
from datetime import datetime, timezone, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, DetectionRecord, CameraRecord, init_seed_data
from trajectory_engine import (
    reconstruct_trajectory,
    generate_trajectory_csv,
    generate_trajectory_dossier_html,
    haversine_km,
    format_duration,
)


class TestTrajectoryEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure seed data exists
        init_seed_data()

    def test_haversine_distance(self):
        # Connaught Place (28.6329, 77.2197) to India Gate (28.6129, 77.2295) is approx 2.4-2.6 km
        d = haversine_km(28.6329, 77.2197, 28.6129, 77.2295)
        self.assertGreater(d, 2.0)
        self.assertLess(d, 3.2)

    def test_format_duration(self):
        self.assertEqual(format_duration(45), "45s")
        self.assertEqual(format_duration(125), "2m 5s")
        self.assertEqual(format_duration(3665), "1h 1m")

    def test_query_existing_trajectory(self):
        res = reconstruct_trajectory("DL01AB1234")
        self.assertTrue(res["found"])
        self.assertEqual(res["plate_number"], "DL01AB1234")
        self.assertGreater(res["total_waypoints"], 0)
        self.assertIsNotNone(res["summary"])
        self.assertGreater(res["summary"]["total_distance_km"], 0.0)

    def test_burst_deduplication(self):
        # DL01AB1234 has 3 rapid burst frames at CAM_01 in seed data
        # With deduplication=True, CAM_01 should appear exactly ONCE at the start
        res_dedup = reconstruct_trajectory("DL01AB1234", deduplicate=True)
        res_no_dedup = reconstruct_trajectory("DL01AB1234", deduplicate=False)

        self.assertLess(res_dedup["total_waypoints"], res_no_dedup["total_waypoints"])
        first_wp = res_dedup["waypoints"][0]
        self.assertEqual(first_wp["camera_id"], "CAM_01")
        self.assertGreaterEqual(first_wp.get("burst_count", 1), 2)

    def test_explicit_gap_detection(self):
        # DL01AB1234 has an intentional 45-min gap between CAM_03 and CAM_05
        res = reconstruct_trajectory("DL01AB1234", gap_time_threshold_minutes=30.0)
        self.assertGreater(res["summary"]["gap_count"], 0)
        
        # Check that segments list contains at least one gap segment
        gap_segments = [s for s in res["segments"] if s["type"] == "gap"]
        self.assertGreater(len(gap_segments), 0)
        first_gap = gap_segments[0]
        self.assertIn("Coverage Gap", first_gap["reason"])
        self.assertGreater(first_gap["distance_km"], 0)

    def test_confidence_filtering(self):
        # Higher confidence filter should return fewer or equal points
        res_all = reconstruct_trajectory("DL01AB1234", min_confidence=0.0)
        res_strict = reconstruct_trajectory("DL01AB1234", min_confidence=0.95)
        self.assertLessEqual(res_strict["total_waypoints"], res_all["total_waypoints"])

    def test_empty_state_for_unknown_plate(self):
        res = reconstruct_trajectory("XX99ZZ9999")
        self.assertFalse(res["found"])
        self.assertEqual(res["total_waypoints"], 0)
        self.assertEqual(len(res["waypoints"]), 0)
        self.assertEqual(len(res["segments"]), 0)
        self.assertIsNone(res["summary"])

    def test_csv_export(self):
        res = reconstruct_trajectory("DL01AB1234")
        csv_str = generate_trajectory_csv(res)
        self.assertIn("# ANPR TRAJECTORY RECONSTRUCTION REPORT", csv_str)
        self.assertIn("DL01AB1234", csv_str)
        self.assertIn("Sequence,Timestamp (UTC),Camera ID", csv_str)
        self.assertIn("CAM_01", csv_str)

    def test_html_dossier_export(self):
        res = reconstruct_trajectory("DL01AB1234")
        html_str = generate_trajectory_dossier_html(res)
        self.assertIn("DELHI POLICE TRAFFIC", html_str)
        self.assertIn("DL01AB1234", html_str)
        self.assertIn("CHRONOLOGICAL WAYPOINT AUDIT LOG", html_str)
        self.assertIn("window.print()", html_str)


if __name__ == "__main__":
    unittest.main()
