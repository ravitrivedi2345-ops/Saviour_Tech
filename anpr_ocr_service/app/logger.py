"""
logger.py — Structured Inference & Audit Logger for Active Learning and Retraining.

Logs every single prediction (input metadata, bounding box, raw characters,
validated plate, confidence, latency) to structured JSON Lines logs.
This provides the dataset corpus for the active learning retraining pipeline.
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings


class InferenceLogger:
    """Writes structured JSONL audit logs for retraining pipelines."""

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = log_dir or settings.AUDIT_LOG_DIR
        os.makedirs(self.log_dir, exist_ok=True)

    def log_inference(
        self,
        image: Optional[np.ndarray],
        detection: Dict,
        camera_id: str,
        image_name: Optional[str] = None,
    ):
        """Append an inference audit record."""
        # Calculate image hash for provenance
        img_hash = None
        if image is not None:
            img_hash = hashlib.sha256(image.tobytes()[:2048]).hexdigest()[:16]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = os.path.join(self.log_dir, f"inferences_{today}.jsonl")

        record = {
            "timestamp": detection.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "camera_id": camera_id,
            "image_hash": img_hash,
            "image_name": image_name,
            "bbox": detection.get("bbox"),
            "raw_plate": detection.get("raw_plate"),
            "validated_plate": detection.get("plate"),
            "confidence": detection.get("confidence"),
            "is_format_valid": detection.get("is_format_valid"),
            "needs_review": detection.get("needs_review"),
            "review_reasons": detection.get("review_reasons"),
            "latency_ms": detection.get("latency_ms"),
            "stage_latencies": detection.get("stage_latencies"),
        }

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[InferenceLogger] Failed to write log: {e}")


audit_logger = InferenceLogger()
