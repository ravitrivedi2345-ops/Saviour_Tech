"""
analytics.py — Urban traffic analytics layer.

Computes congestion proxies, inter-camera speeds, and real-time alerts
from a batch of ANPR detections. This module operates on trajectory/detection
data only — it does NOT import identity.py, preserving the planner-view
access boundary.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from camera_graph import (
    CAMERAS,
    camera_distance_km,
    implied_speed_kmph,
    CAMERA_IDS,
)
from matcher import canonical_plate, plates_match

# ─── Wanted plate list (hardcoded for prototype) ───────────────────────────────
# In production this would be fetched from a secured enforcement database.
# The canonical (normalised) form is stored to match against noisy reads.

WANTED_PLATES_RAW: List[str] = [
    "DL01AB1234",
    "MH12XY5678",
    "UP32CD9999",
    "KA05EF2222",
    "RJ14GH7777",
]

WANTED_PLATES_CANONICAL = {canonical_plate(p): p for p in WANTED_PLATES_RAW}


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ts(ts_str: str) -> datetime:
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ─── Congestion analytics ──────────────────────────────────────────────────────

def congestion_by_camera(detections: List[dict]) -> Dict[str, dict]:
    """
    Compute per-camera, per-hour vehicle counts as a basic congestion proxy.

    Returns a dict keyed by camera_id:
        {
          "camera_name": str,
          "zone": str,
          "total": int,
          "by_hour": {hour_str: count},   # hour_str = "HH:00"
          "peak_hour": str,
          "peak_count": int,
        }
    """
    # camera_id → hour_string → count
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for det in detections:
        ts = _parse_ts(det["timestamp"])
        hour_str = f"{ts.hour:02d}:00"
        counts[det["camera_id"]][hour_str] += 1

    result = {}
    for cam_id in CAMERA_IDS:
        cam_info = CAMERAS[cam_id]
        by_hour = dict(counts.get(cam_id, {}))
        total = sum(by_hour.values())
        if by_hour:
            peak_hour = max(by_hour, key=by_hour.get)
            peak_count = by_hour[peak_hour]
        else:
            peak_hour = "—"
            peak_count = 0

        result[cam_id] = {
            "camera_name": cam_info["name"],
            "zone": cam_info["zone"],
            "total": total,
            "by_hour": dict(sorted(by_hour.items())),
            "peak_hour": peak_hour,
            "peak_count": peak_count,
        }

    return result


# ─── Inter-camera speed analytics ─────────────────────────────────────────────

def avg_speed_between_cameras(detections: List[dict]) -> Dict[str, dict]:
    """
    Estimate average implied speed for each adjacent camera pair seen in the data.

    Groups detections by canonical plate, sorts by time, then for consecutive
    sightings at different cameras computes the implied speed.

    Only feasible hops (speed ≤ 150 km/h — relaxed for analytics purposes) are
    included to filter out obvious data errors.

    Returns dict keyed by "CAM_X→CAM_Y":
        {"cam_a": str, "cam_b": str, "avg_speed_kmph": float,
         "sample_count": int, "distance_km": float}
    """
    MAX_PLAUSIBLE_SPEED = 150.0  # km/h — relaxed upper bound for analytics

    # plate → sorted detections
    plate_detections: Dict[str, List[dict]] = defaultdict(list)
    for det in detections:
        key = canonical_plate(det["plate_raw"])
        plate_detections[key].append(det)

    hop_speeds: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    for plate_key, dets in plate_detections.items():
        dets_sorted = sorted(dets, key=lambda d: d["timestamp"])
        for i in range(len(dets_sorted) - 1):
            a, b = dets_sorted[i], dets_sorted[i + 1]
            if a["camera_id"] == b["camera_id"]:
                continue  # same camera, skip
            ta = _parse_ts(a["timestamp"])
            tb = _parse_ts(b["timestamp"])
            delta = (tb - ta).total_seconds()
            if delta <= 0:
                continue
            speed = implied_speed_kmph(a["camera_id"], b["camera_id"], delta)
            if speed is not None and 0 < speed <= MAX_PLAUSIBLE_SPEED:
                hop_speeds[(a["camera_id"], b["camera_id"])].append(speed)

    result = {}
    for (cam_a, cam_b), speeds in hop_speeds.items():
        dist = camera_distance_km(cam_a, cam_b) or 0.0
        key = f"{cam_a}→{cam_b}"
        result[key] = {
            "cam_a": cam_a,
            "cam_a_name": CAMERAS[cam_a]["name"],
            "cam_b": cam_b,
            "cam_b_name": CAMERAS[cam_b]["name"],
            "avg_speed_kmph": round(sum(speeds) / len(speeds), 1),
            "sample_count": len(speeds),
            "distance_km": round(dist, 2),
        }

    return result


# ─── Alert engine ──────────────────────────────────────────────────────────────

def check_alerts(detections: List[dict]) -> List[dict]:
    """
    Scan detections for wanted plate matches (fuzzy).

    Returns a list of alert dicts, one per matching detection:
        {
          "detection_id": str,
          "plate_raw": str,
          "matched_wanted_plate": str,
          "camera_id": str,
          "camera_name": str,
          "timestamp": str,
          "vehicle_type": str,
          "confidence": float,
          "severity": "HIGH" | "MEDIUM",
        }

    Severity is HIGH if confidence ≥ 0.85 (clean read), MEDIUM otherwise.
    """
    alerts = []
    for det in detections:
        raw = det["plate_raw"]
        canon = canonical_plate(raw)

        for wanted_canon, wanted_raw in WANTED_PLATES_CANONICAL.items():
            if plates_match(raw, wanted_raw):
                severity = "HIGH" if det["confidence"] >= 0.85 else "MEDIUM"
                alerts.append({
                    "detection_id": det["id"],
                    "plate_raw": raw,
                    "matched_wanted_plate": wanted_raw,
                    "camera_id": det["camera_id"],
                    "camera_name": det["camera_name"],
                    "timestamp": det["timestamp"],
                    "vehicle_type": det["vehicle_type"],
                    "confidence": det["confidence"],
                    "severity": severity,
                })
                break  # one alert per detection

    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts


# ─── Summary stats ─────────────────────────────────────────────────────────────

def batch_summary(detections: List[dict]) -> dict:
    """Quick summary stats for a detection batch."""
    if not detections:
        return {"total": 0, "unique_plates": 0, "noisy_reads": 0, "cameras_active": 0}

    unique_plates = len({canonical_plate(d["plate_raw"]) for d in detections})
    noisy = sum(1 for d in detections if d.get("ocr_noisy", False))
    cameras_active = len({d["camera_id"] for d in detections})

    return {
        "total": len(detections),
        "unique_plates": unique_plates,
        "noisy_reads": noisy,
        "noise_pct": round(noisy / len(detections) * 100, 1),
        "cameras_active": cameras_active,
        "time_range_start": detections[0]["timestamp"],
        "time_range_end": detections[-1]["timestamp"],
    }
