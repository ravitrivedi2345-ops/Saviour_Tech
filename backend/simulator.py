"""
simulator.py — Simulated ANPR detection generator for the prototype.

Produces fake detection events in the format a real ANPR camera would emit:
  • Plate text (Indian format, with deliberate OCR noise in ~15% of reads)
  • Camera ID (from the camera_graph node set)
  • Timestamp (UTC ISO-8601)
  • Vehicle type
  • Confidence score [0.60, 0.99]

OCR noise table (intentional substitutions that real systems must handle):
    0 ↔ O     1 ↔ I     8 ↔ B     5 ↔ S     6 ↔ G     2 ↔ Z
"""

import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from camera_graph import CAMERA_IDS, CAMERAS

# ─── Plate pool ────────────────────────────────────────────────────────────────
# A representative pool of "real" plates that will recur across cameras to form
# trajectories. A few are in the wanted list (see analytics.py).

PLATE_POOL: List[str] = [
    # Wanted plates (deliberately included so alerts fire)
    "DL01AB1234",
    "MH12XY5678",
    "UP32CD9999",
    "KA05EF2222",
    "RJ14GH7777",
    # Normal vehicles
    "DL02BC2345",
    "DL03CD3456",
    "DL04DE4567",
    "DL05EF5678",
    "DL07GH7890",
    "DL08HI8901",
    "DL09IJ9012",
    "MH01JK0123",
    "MH02KL1234",
    "MH03LM2345",
    "UP14MN3456",
    "UP16NO4567",
    "UP32PQ5678",
    "HR26QR6789",
    "HR26RS7890",
    "PB10ST8901",
    "GJ01TU9012",
    "TN09UV0123",
    "KA04VW1234",
    "WB20WX2345",
    "RJ01XY3456",
    "AP39YZ4567",
    "MP09ZA5678",
    "BR01AB6789",
]

VEHICLE_TYPES: List[str] = ["Car", "Motorcycle", "Truck", "Auto-Rickshaw", "Bus"]

# Camera weighting: high-congestion cameras get 3× more detections
_CAM_WEIGHTS = {
    cam_id: (3 if CAMERAS[cam_id]["typical_congestion"] == "high" else 1)
    for cam_id in CAMERA_IDS
}

# ─── OCR noise engine ──────────────────────────────────────────────────────────

# Bidirectional substitution map (both directions are equally likely mistakes)
OCR_NOISE_MAP: Dict[str, str] = {
    "0": "O", "O": "0",
    "1": "I", "I": "1",
    "8": "B", "B": "8",
    "5": "S", "S": "5",
    "6": "G", "G": "6",
    "2": "Z", "Z": "2",
}

NOISE_RATE: float = 0.15  # 15% of detections get at least one character swapped


def inject_ocr_noise(plate: str) -> str:
    """
    Return a noisy version of a plate string by randomly substituting one or
    two characters using the OCR confusion table. Probability is NOISE_RATE.
    """
    if random.random() > NOISE_RATE:
        return plate  # clean read

    chars = list(plate)
    # Find positions that are substitutable
    substitutable = [i for i, c in enumerate(chars) if c in OCR_NOISE_MAP]
    if not substitutable:
        return plate

    # Swap 1 character (occasionally 2)
    n_swaps = random.choices([1, 2], weights=[0.75, 0.25])[0]
    positions = random.sample(substitutable, k=min(n_swaps, len(substitutable)))
    for pos in positions:
        chars[pos] = OCR_NOISE_MAP[chars[pos]]

    return "".join(chars)


# ─── Detection generator ───────────────────────────────────────────────────────

def _random_plate() -> str:
    """Pick a plate from the pool, biased toward repeats to build trajectories."""
    # 70% chance to pick a pool plate (creates real trajectories)
    # 30% chance to generate a random one-off plate
    if random.random() < 0.70:
        return random.choice(PLATE_POOL)
    state = random.choice(["DL", "MH", "UP", "HR", "RJ", "KA", "GJ", "PB", "WB"])
    dist = f"{random.randint(1, 39):02d}"
    series = "".join(random.choices(string.ascii_uppercase, k=2))
    number = f"{random.randint(1000, 9999)}"
    return f"{state}{dist}{series}{number}"


def generate_detections(
    count: int = 200,
    start_time: Optional[datetime] = None,
    window_minutes: int = 60,
) -> List[Dict]:
    """
    Generate `count` simulated ANPR detection events spread over `window_minutes`.

    Returns a list of detection dicts, each with:
        id, plate_raw, plate_clean, camera_id, timestamp, vehicle_type,
        confidence, ocr_noisy (bool)
    """
    if start_time is None:
        # Default to 1 hour before "now" so the window makes sense
        start_time = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    cam_ids = list(_CAM_WEIGHTS.keys())
    cam_weights = list(_CAM_WEIGHTS.values())

    detections = []
    for _ in range(count):
        clean_plate = _random_plate()
        raw_plate = inject_ocr_noise(clean_plate)
        noisy = raw_plate != clean_plate

        # Pick camera with weighting
        cam_id = random.choices(cam_ids, weights=cam_weights, k=1)[0]

        # Random timestamp within the window
        offset_seconds = random.uniform(0, window_minutes * 60)
        ts = start_time + timedelta(seconds=offset_seconds)

        # Confidence: lower when plate is noisy
        if noisy:
            confidence = round(random.uniform(0.60, 0.78), 3)
        else:
            confidence = round(random.uniform(0.75, 0.99), 3)

        detections.append({
            "id": str(uuid.uuid4()),
            "plate_raw": raw_plate,
            "plate_clean": clean_plate,  # ground-truth (not available in real system)
            "camera_id": cam_id,
            "camera_name": CAMERAS[cam_id]["name"],
            "timestamp": ts.isoformat(),
            "vehicle_type": random.choice(VEHICLE_TYPES),
            "confidence": confidence,
            "ocr_noisy": noisy,
        })

    # Sort chronologically
    detections.sort(key=lambda d: d["timestamp"])
    return detections
