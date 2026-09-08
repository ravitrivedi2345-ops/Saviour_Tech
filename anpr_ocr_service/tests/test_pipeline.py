"""
test_pipeline.py — Unit and integration tests for ANPR OCR Service.
"""

import os
import sys
import unittest
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings
from app.validator import PlateValidator
from app.detector import PlateDetector
from app.recognizer import PlateRecognizer
from app.pipeline import ANPRPipeline
from app.database import save_detection, query_detections
from app.queue_publisher import publisher


class TestANPROCRService(unittest.TestCase):

    def setUp(self):
        self.validator = PlateValidator(threshold=0.85)
        self.pipeline = ANPRPipeline(confidence_threshold=0.85)

    def test_validator_clean_plate(self):
        """Test clean valid Indian plate passes with no review flag."""
        res = self.validator.validate("DL01AB1234", confidence=0.92)
        self.assertEqual(res["plate"], "DL01AB1234")
        self.assertTrue(res["is_format_valid"])
        self.assertFalse(res["needs_review"])
        self.assertEqual(len(res["review_reasons"]), 0)

    def test_validator_confidence_threshold_flag(self):
        """Test confidence below 0.85 triggers needs_review flag."""
        res = self.validator.validate("DL01AB1234", confidence=0.74)
        self.assertEqual(res["plate"], "DL01AB1234")
        self.assertTrue(res["needs_review"])
        self.assertTrue(any("below review threshold" in r for r in res["review_reasons"]))

    def test_validator_character_confusion_rectification(self):
        """Test slot-based heuristic rectifies 0/O and 8/B swaps."""
        # DLO1A81234 has 'O' in district slot 1, and '8' in series slot 2
        res = self.validator.validate("DLO1A81234", confidence=0.90)
        # Should be corrected to DL01AB1234
        self.assertEqual(res["plate"], "DL01AB1234")
        self.assertTrue(res["is_format_valid"])

    def test_validator_invalid_format_flagged(self):
        """Test completely invalid plate text is flagged for review."""
        res = self.validator.validate("INVALID_123", confidence=0.90)
        self.assertFalse(res["is_format_valid"])
        self.assertTrue(res["needs_review"])

    def test_ctc_decoder(self):
        """Test CTC greedy decoding logic."""
        rec = PlateRecognizer()
        # Synthetic log probs: length 5, vocab 37
        T = 5
        V = 37
        log_probs = np.zeros((T, V))
        # Path: Blank(0), D(14), D(14), Blank(0), L(22)
        log_probs[0, 0] = 10.0
        log_probs[1, 14] = 10.0
        log_probs[2, 14] = 10.0
        log_probs[3, 0] = 10.0
        log_probs[4, 22] = 10.0

        text, conf = rec.ctc_decode(log_probs)
        self.assertEqual(text, "DL")

    def test_pipeline_synthetic_frame(self):
        """Test end-to-end pipeline processing on a generated test frame."""
        # Create dummy frame with high-contrast text patch
        frame = np.full((300, 400, 3), 40, dtype=np.uint8)
        plate_patch = np.full((50, 180, 3), 250, dtype=np.uint8)
        cv2.putText(plate_patch, "MH12XY5678", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        frame[120:170, 110:290] = plate_patch

        results = self.pipeline.process_frame(
            frame, 
            camera_id="TEST_CAM_01",
            metadata_hint="MH12XY5678"
        )
        self.assertGreater(len(results), 0)
        det = results[0]
        self.assertEqual(det["camera_id"], "TEST_CAM_01")
        self.assertIn("bbox", det)
        self.assertIn("confidence", det)
        self.assertIn("latency_ms", det)
        self.assertIn("stage_latencies", det)

    def test_database_persistence_and_query(self):
        """Test saving and querying detection records."""
        sample_det = {
            "camera_id": "CAM_DB_TEST",
            "timestamp": "2026-09-07T12:30:00+00:00",
            "plate": "UP32CD9999",
            "raw_plate": "UP32CD9999",
            "confidence": 0.95,
            "bbox": [100, 200, 300, 250],
            "is_format_valid": True,
            "needs_review": False,
            "review_reasons": [],
            "latency_ms": 14.5,
        }
        rec = save_detection(sample_det)
        self.assertIsNotNone(rec.id)

        queried = query_detections(camera_id="CAM_DB_TEST", limit=10)
        self.assertGreater(len(queried), 0)
        self.assertEqual(queried[0]["plate_number"], "UP32CD9999")

    def test_queue_publisher_buffering(self):
        """Test queue publisher buffers event without raising exception."""
        sample_det = {
            "camera_id": "CAM_QUEUE_TEST",
            "timestamp": "2026-09-07T12:30:00Z",
            "plate": "RJ14GH7777",
            "confidence": 0.88,
            "bbox": [50, 100, 150, 140],
        }
        success = publisher.publish_detection(sample_det)
        self.assertTrue(success)
        buffered = publisher.get_buffered_events(limit=5)
        self.assertGreater(len(buffered), 0)
        self.assertEqual(buffered[-1]["plate"], "RJ14GH7777")


if __name__ == "__main__":
    unittest.main()
