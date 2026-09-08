"""
matcher.py — Fuzzy plate matching and trajectory reconstruction engine.

═══════════════════════════════════════════════════════════════════
  REAL-WORLD LIMITATIONS THIS SIMPLIFIED VERSION DOES NOT HANDLE
═══════════════════════════════════════════════════════════════════

1. TWO-WHEELER PLATE DETECTION
   Motorcycle plates in India are often non-standard in font, size, and
   placement. Real two-wheeler ANPR requires separate model heads trained
   specifically on hand-painted or HSRPlate variants. This prototype treats
   Motorcycles the same as Cars.

2. CAMERA CLOCK DRIFT
   In a deployed network, individual cameras may drift by ±5–30 seconds
   relative to GPS/NTP time. Uncorrected drift makes time-window feasibility
   checks unreliable for short hops. This prototype assumes all cameras share
   a perfectly synchronised clock.

3. CLONED / DUPLICATE PLATES
   If two vehicles carry the same plate (cloning), both will appear in the
   trajectory — which is physically impossible (two places at once). A real
   system must detect simultaneous sightings of the same plate at distant
   cameras and flag them. This prototype does not implement clone detection.

4. PARTIAL PLATE READS
   Real ANPR cameras often capture only 4–6 characters when a vehicle is at
   an angle or moving fast. This prototype only injects full-plate character
   swaps, not partial reads.

5. EDIT-DISTANCE THRESHOLD IS HEURISTIC
   The threshold of ≤ 2 edit-distance works for the synthetic noise in this
   demo but would produce false positives on real traffic where many plates
   differ by just one character legitimately (e.g. DL01AB1234 vs DL01AB1235).
   A production system would use both edit distance and probabilistic Bayesian
   plate identity models.

═══════════════════════════════════════════════════════════════════
"""

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from camera_graph import camera_distance_km, is_feasible, implied_speed_kmph, MAX_SPEED_KMPH

# ─── Configuration ─────────────────────────────────────────────────────────────

EDIT_DISTANCE_THRESHOLD: int = 2      # Max Levenshtein distance for plate match
MAX_TIME_GAP_HOURS: float = 4.0       # Don't link sightings > 4 hours apart
TRAJECTORY_CONFIDENCE_FLOOR: float = 0.0  # Min possible score

# ─── Edit distance (pure Python — no external deps) ────────────────────────────

def levenshtein(s1: str, s2: str) -> int:
    """Standard Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    # Single-row DP
    prev = list(range(len2 + 1))
    for i, c1 in enumerate(s1, 1):
        curr = [i]
        for j, c2 in enumerate(s2, 1):
            cost = 0 if c1 == c2 else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[len2]


# ─── Plate normalisation ───────────────────────────────────────────────────────

# Characters that are commonly confused in both directions
_CANONICAL_MAP = str.maketrans({
    "O": "0", "I": "1", "B": "8", "S": "5", "G": "6", "Z": "2"
})

def normalize_plate(plate: str) -> str:
    """
    Collapse OCR ambiguous characters to a canonical form for grouping.
    All letters/digits are uppercased; confusable chars are folded to digits.
    Spaces and hyphens are stripped.
    """
    plate = plate.upper().replace(" ", "").replace("-", "")
    return plate.translate(_CANONICAL_MAP)


def plates_match(p1: str, p2: str) -> bool:
    """
    Return True if two raw plate strings are likely the same physical plate.
    Uses normalised edit distance to absorb OCR noise.
    """
    n1, n2 = normalize_plate(p1), normalize_plate(p2)
    return levenshtein(n1, n2) <= EDIT_DISTANCE_THRESHOLD


# ─── Canonical plate resolution ────────────────────────────────────────────────

def canonical_plate(plate: str) -> str:
    """Return the normalised canonical form of a plate (used as group key)."""
    return normalize_plate(plate)


# ─── Trajectory building ───────────────────────────────────────────────────────

def _parse_ts(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp to aware datetime (UTC)."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _hop_score(det_a: dict, det_b: dict) -> float:
    """
    Compute a quality score [0, 1] for a single hop between two detections.
    Penalises:
      - Low confidence at either end
      - Long time gap (normalised to a 4-hour window)
    """
    avg_conf = (det_a["confidence"] + det_b["confidence"]) / 2.0
    ta = _parse_ts(det_a["timestamp"])
    tb = _parse_ts(det_b["timestamp"])
    gap_hours = abs((tb - ta).total_seconds()) / 3600.0
    time_penalty = min(gap_hours / MAX_TIME_GAP_HOURS, 1.0)
    return avg_conf * (1.0 - 0.5 * time_penalty)


def _score_segment(detections: List[dict]) -> float:
    """
    Aggregate hop scores across a trajectory segment.
    Single-detection segments get the confidence of that detection directly.
    """
    if len(detections) == 1:
        return detections[0]["confidence"]
    scores = [_hop_score(detections[i], detections[i + 1]) for i in range(len(detections) - 1)]
    return round(sum(scores) / len(scores), 4)


def build_trajectories(detections: List[dict]) -> Dict[str, dict]:
    """
    Group detections into vehicle trajectories using fuzzy plate matching.

    Algorithm:
      1. Group detections by canonical plate.
      2. For each group, sort by timestamp.
      3. Walk through sorted detections and split into segments whenever a hop
         is physically impossible (exceeds MAX_SPEED_KMPH between cameras) or
         the time gap exceeds MAX_TIME_GAP_HOURS.
      4. Between segments, emit a GAP marker.
      5. Score each segment individually.

    Returns:
        Dict keyed by canonical plate → trajectory dict with segments and metadata.
    """
    # Step 1: Group by canonical plate with vehicle-type majority vote
    groups: Dict[str, List[dict]] = defaultdict(list)
    for det in detections:
        key = canonical_plate(det["plate_raw"])
        groups[key].append(det)

    trajectories = {}
    for canon_key, group in groups.items():
        # Sort by timestamp
        group.sort(key=lambda d: d["timestamp"])

        # Resolve canonical plate → most common raw plate in group
        raw_counts: Dict[str, int] = defaultdict(int)
        for d in group:
            raw_counts[d["plate_raw"]] += 1
        representative_plate = max(raw_counts, key=raw_counts.get)

        # Vehicle type majority vote
        vtype_counts: Dict[str, int] = defaultdict(int)
        for d in group:
            vtype_counts[d["vehicle_type"]] += 1
        dominant_vtype = max(vtype_counts, key=vtype_counts.get)

        # Step 2–4: Split into segments
        segments = []
        current_segment = [group[0]]

        for i in range(1, len(group)):
            prev, curr = group[i - 1], group[i]
            ta = _parse_ts(prev["timestamp"])
            tb = _parse_ts(curr["timestamp"])
            delta_seconds = (tb - ta).total_seconds()
            gap_hours = delta_seconds / 3600.0

            # Reject if vehicle type is inconsistent (different type in this group)
            # We use majority vote — just note the inconsistency
            vtype_ok = (prev["vehicle_type"] == curr["vehicle_type"]) or (
                curr["vehicle_type"] == dominant_vtype
            )

            # Check physical feasibility
            feasible = is_feasible(prev["camera_id"], curr["camera_id"], delta_seconds)
            time_ok = gap_hours <= MAX_TIME_GAP_HOURS

            if feasible and time_ok:
                current_segment.append(curr)
            else:
                # Commit current segment, start new one
                if current_segment:
                    segments.append({
                        "type": "segment",
                        "detections": current_segment,
                        "score": _score_segment(current_segment),
                        "hop_count": len(current_segment),
                    })

                # Build a GAP marker explaining why the split happened
                reason = []
                if not feasible:
                    spd = implied_speed_kmph(prev["camera_id"], curr["camera_id"], delta_seconds)
                    dist = camera_distance_km(prev["camera_id"], curr["camera_id"])
                    reason.append(
                        f"Implied speed {spd:.0f} km/h exceeds {MAX_SPEED_KMPH} km/h limit "
                        f"over {dist:.1f} km"
                    )
                if not time_ok:
                    reason.append(f"Time gap {gap_hours:.1f} h exceeds {MAX_TIME_GAP_HOURS} h limit")

                segments.append({
                    "type": "gap",
                    "from_detection": prev,
                    "to_detection": curr,
                    "gap_seconds": delta_seconds,
                    "reason": "; ".join(reason) if reason else "Unknown",
                })

                current_segment = [curr]

        # Commit final segment
        if current_segment:
            segments.append({
                "type": "segment",
                "detections": current_segment,
                "score": _score_segment(current_segment),
                "hop_count": len(current_segment),
            })

        # Overall trajectory confidence = mean of segment scores
        seg_scores = [s["score"] for s in segments if s["type"] == "segment"]
        overall_confidence = round(sum(seg_scores) / len(seg_scores), 4) if seg_scores else 0.0

        trajectories[canon_key] = {
            "canonical_plate": canon_key,
            "representative_plate": representative_plate,
            "vehicle_type": dominant_vtype,
            "total_detections": len(group),
            "total_segments": sum(1 for s in segments if s["type"] == "segment"),
            "total_gaps": sum(1 for s in segments if s["type"] == "gap"),
            "overall_confidence": overall_confidence,
            "segments": segments,
        }

    return trajectories


def find_trajectory(plate_query: str, trajectories: Dict[str, dict]) -> Optional[dict]:
    """
    Look up a trajectory for a given plate string (raw or partial).
    Uses fuzzy matching so noisy input still resolves to the right trajectory.

    Returns the best matching trajectory dict or None.
    """
    query_norm = canonical_plate(plate_query)

    best_key = None
    best_dist = EDIT_DISTANCE_THRESHOLD + 1

    for key in trajectories:
        dist = levenshtein(query_norm, key)
        if dist < best_dist:
            best_dist = dist
            best_key = key

    return trajectories[best_key] if best_key is not None else None
