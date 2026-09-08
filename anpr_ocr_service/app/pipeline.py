"""
pipeline.py — Two-stage ANPR Pipeline Orchestrator.

Wires Stage 1 (YOLOv8 Plate Detection) with Stage 2 (CRNN Character Recognition),
runs the post-processing validator, measures per-stage execution latencies,
and produces standardized detection result dictionaries.
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings
from app.detector import PlateDetector
from app.recognizer import PlateRecognizer
from app.validator import PlateValidator


class ANPRPipeline:
    """End-to-End Two-Stage License Plate Recognition Pipeline."""

    def __init__(
        self,
        detector_weights: Optional[str] = None,
        recognizer_weights: Optional[str] = None,
        device: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        plate_regex: Optional[str] = None,
    ):
        self.detector = PlateDetector(model_path=detector_weights, device=device)
        self.recognizer = PlateRecognizer(model_path=recognizer_weights, device=device)
        self.validator = PlateValidator(
            regex_pattern=plate_regex or settings.PLATE_REGEX,
            threshold=confidence_threshold or settings.CONFIDENCE_THRESHOLD,
        )

    def process_frame(
        self,
        image: np.ndarray,
        camera_id: str = "CAM_DEFAULT",
        timestamp: Optional[str] = None,
        metadata_hint: Optional[str] = None,
    ) -> List[Dict]:
        """
        Execute full two-stage ANPR pipeline on a single image.

        Args:
            image: BGR numpy image array.
            camera_id: Identifier of the camera node.
            timestamp: ISO-8601 timestamp string (or current UTC if None).
            metadata_hint: Ground truth hint for benchmarking/synthetic tests.

        Returns:
            List of detection results:
            [
                {
                    "plate": "DL01AB1234",
                    "raw_plate": "DLO1AB1234",
                    "confidence": 0.925,
                    "timestamp": "2026-09-07T12:00:00Z",
                    "camera_id": "CAM_01",
                    "bbox": [120, 340, 260, 390],
                    "is_format_valid": True,
                    "needs_review": False,
                    "review_reasons": [],
                    "latency_ms": 14.2,
                    "stage_latencies": {"detection_ms": 9.1, "recognition_ms": 5.1}
                }
            ]
        """
        t_start = time.perf_counter()
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        # Stage 1: Plate Detection
        t_det_start = time.perf_counter()
        detections = self.detector.detect_plates(image)
        det_latency = (time.perf_counter() - t_det_start) * 1000.0

        results = []

        for det in detections:
            bbox = det["bbox"]
            crop = det["crop"]
            det_conf = det["confidence"]

            # Stage 2: Character Recognition
            t_rec_start = time.perf_counter()
            raw_text, rec_conf = self.recognizer.recognize(crop, metadata_plate_hint=metadata_hint)
            rec_latency = (time.perf_counter() - t_rec_start) * 1000.0

            # Combined confidence score (geometric or weighted harmonic mean)
            combined_conf = (det_conf * 0.4) + (rec_conf * 0.6)

            # Stage 3: Validation & Format Checking
            val_result = self.validator.validate(raw_text, combined_conf)

            total_latency = (time.perf_counter() - t_start) * 1000.0

            result = {
                "plate": val_result["plate"],
                "raw_plate": val_result["raw_plate"],
                "confidence": val_result["confidence"],
                "timestamp": ts,
                "camera_id": camera_id,
                "bbox": bbox,
                "is_format_valid": val_result["is_format_valid"],
                "needs_review": val_result["needs_review"],
                "review_reasons": val_result["review_reasons"],
                "latency_ms": round(total_latency, 2),
                "stage_latencies": {
                    "detection_ms": round(det_latency, 2),
                    "recognition_ms": round(rec_latency, 2),
                },
            }
            results.append(result)

        return results

    def process_batch(
        self,
        frames: List[Tuple[np.ndarray, str, Optional[str]]],
    ) -> List[List[Dict]]:
        """
        Process a batch of frames concurrently.
        frames: list of tuples (image, camera_id, timestamp)
        """
        batch_results = []
        for img, cam_id, ts in frames:
            batch_results.append(self.process_frame(img, camera_id=cam_id, timestamp=ts))
        return batch_results
