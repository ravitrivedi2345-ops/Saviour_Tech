"""
test_city_analytics.py — Unit tests for Component 3 (City Traffic Analytics Engine).
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import init_seed_data
from city_analytics import (
    get_traffic_heatmap,
    get_segment_speeds,
    get_route_density,
    get_comparative_trends,
    export_city_analytics_csv,
    export_city_analytics_report_html,
    cache,
)


class TestCityAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_seed_data()
        cache.clear()

    def test_heatmap_query_and_offline_distinction(self):
        # Query heatmap for today
        res = get_traffic_heatmap()
        self.assertIn("points", res)
        self.assertEqual(res["total_cameras"], 9)
        self.assertGreater(res["total_city_volume"], 0)

        # Check offline sensor distinction:
        # CAM_08 (Shahdara Flyover) should be marked OFFLINE in afternoon hours, NOT zero traffic
        res_afternoon = get_traffic_heatmap(hour_range="13-17")
        cam_08_point = next((p for p in res_afternoon["points"] if p["camera_id"] == "CAM_08"), None)
        self.assertIsNotNone(cam_08_point)
        self.assertTrue(cam_08_point["is_offline"])
        self.assertEqual(cam_08_point["camera_status"], "OFFLINE")
        self.assertIn("Data Incomplete", cam_08_point["status_label"])

    def test_segment_speeds(self):
        res = get_segment_speeds()
        self.assertIn("corridors", res)
        self.assertGreaterEqual(len(res["corridors"]), 8)

        seg_01 = next((c for c in res["corridors"] if c["segment_id"] == "SEG_01"), None)
        self.assertIsNotNone(seg_01)
        self.assertGreater(seg_01["avg_speed_kmph"], 0)
        self.assertEqual(seg_01["speed_limit_kmph"], 50.0)
        self.assertIn(seg_01["speed_status"], ["FREE_FLOW", "MODERATE", "CONGESTED"])

    def test_route_density_rankings(self):
        res = get_route_density()
        self.assertIn("corridors", res)
        self.assertGreaterEqual(len(res["corridors"]), 8)

        # Verify sorted by volume descending
        volumes = [c["total_volume"] for c in res["corridors"]]
        self.assertEqual(volumes, sorted(volumes, reverse=True))
        self.assertIsNotNone(res["busiest_corridor"])

    def test_comparative_trends(self):
        res = get_comparative_trends(compare="today_vs_last_week", metric="volume")
        self.assertEqual(len(res["hours"]), 24)
        self.assertEqual(len(res["current_period"]["data"]), 24)
        self.assertEqual(len(res["prior_period"]["data"]), 24)
        self.assertGreater(res["current_period"]["total"], 0)
        self.assertGreater(res["prior_period"]["total"], 0)
        self.assertIn("08:00 - 11:00", res["commute_rush_hours"]["morning"])

    def test_analytics_csv_export(self):
        hm = get_traffic_heatmap()
        sp = get_segment_speeds()
        dn = get_route_density()
        csv_out = export_city_analytics_csv(hm, sp, dn)

        self.assertIn("CITY TRAFFIC ANALYTICS AGGREGATED REPORT", csv_out)
        self.assertIn("CAMERA NODE TRAFFIC VOLUMES", csv_out)
        self.assertIn("ROAD CORRIDOR AVERAGE SPEEDS", csv_out)
        self.assertIn("CAM_01", csv_out)
        self.assertIn("SEG_01", csv_out)

    def test_analytics_html_dossier(self):
        hm = get_traffic_heatmap()
        sp = get_segment_speeds()
        dn = get_route_density()
        tr = get_comparative_trends()
        html_out = export_city_analytics_report_html(hm, sp, dn, tr)

        self.assertIn("DELHI INTEGRATED TRAFFIC MANAGEMENT CENTER", html_out)
        self.assertIn("City-Wide Traffic Analytics", html_out)
        self.assertIn("window.print()", html_out)


if __name__ == "__main__":
    unittest.main()
