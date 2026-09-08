"""
alert_engine.py — Core real-time alert processing pipeline for Component 4.

Processes each incoming ANPR detection through:
  1. Blacklist matching (exact + fuzzy via Levenshtein edit distance)
  2. Anomaly detection (loitering, wrong-way, speed anomaly, restricted zone)
  3. Deduplication / rate limiting
  4. Alert persistence + notification dispatch

All anomaly rules are explicit and explainable — no ML black boxes.
All thresholds are configurable via alert_config (DB-backed).
"""

import json
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, BlacklistRecord, AlertRecord
from matcher import normalize_plate, levenshtein
from camera_graph import CAMERAS, camera_distance_km, implied_speed_kmph
from alert_config import alert_config
from alert_notifier import alert_dispatcher


# ─── Blacklist Cache ───────────────────────────────────────────────────────────

class BlacklistCache:
    """
    In-memory cache of active blacklist entries for O(1) exact-match lookups.
    Fuzzy matching iterates the cache only when OCR confidence is low.
    """

    def __init__(self):
        self._cache: Dict[str, Dict] = {}  # normalized_plate → {plate, reason, priority}
        self._lock = threading.RLock()
        self._loaded = False

    def load(self) -> None:
        """Load all active blacklist entries from database."""
        session = SessionLocal()
        try:
            records = session.query(BlacklistRecord).filter_by(is_active=True).all()
            with self._lock:
                self._cache = {
                    r.normalized_plate: {
                        "plate_number": r.plate_number,
                        "normalized_plate": r.normalized_plate,
                        "reason": r.reason,
                        "priority": r.priority,
                    }
                    for r in records
                }
                self._loaded = True
            print(f"[BlacklistCache] Loaded {len(self._cache)} active blacklist entries")
        except Exception as e:
            print(f"[BlacklistCache] Failed to load: {e}")
        finally:
            session.close()

    def refresh(self) -> None:
        """Reload cache from database (called after CRUD operations)."""
        self.load()

    def exact_match(self, normalized: str) -> Optional[Dict]:
        """O(1) lookup by normalized plate. Returns blacklist entry or None."""
        if not self._loaded:
            self.load()
        with self._lock:
            return self._cache.get(normalized)

    def fuzzy_match(self, normalized: str, max_distance: int = 2) -> Optional[Tuple[Dict, int]]:
        """
        Find closest blacklist entry within edit distance threshold.
        Returns (entry, edit_distance) or None.
        Only called when OCR confidence is below threshold.
        """
        if not self._loaded:
            self.load()
        best_entry = None
        best_dist = max_distance + 1

        with self._lock:
            for bl_normalized, entry in self._cache.items():
                dist = levenshtein(normalized, bl_normalized)
                if dist <= max_distance and dist < best_dist and dist > 0:
                    best_dist = dist
                    best_entry = entry

        return (best_entry, best_dist) if best_entry else None

    @property
    def size(self) -> int:
        return len(self._cache)


# ─── Anomaly State Tracker ────────────────────────────────────────────────────

class AnomalyStateTracker:
    """
    Maintains sliding-window state for anomaly detection across detections.
    Thread-safe for concurrent detection processing.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Loitering: plate → camera_id → deque of timestamps
        self._loitering_window: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        # Route tracking: plate → deque of (camera_id, timestamp) for wrong-way detection
        self._route_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        # Speed tracking: plate → (last_camera_id, last_timestamp) for speed anomaly
        self._last_sighting: Dict[str, Tuple[str, datetime]] = {}

    def record_sighting(self, plate: str, camera_id: str, timestamp: datetime) -> None:
        """Record a vehicle sighting for anomaly state tracking."""
        normalized = normalize_plate(plate)
        with self._lock:
            # Loitering window
            self._loitering_window[normalized][camera_id].append(timestamp)
            # Route history
            self._route_history[normalized].append((camera_id, timestamp))
            # Last sighting
            self._last_sighting[normalized] = (camera_id, timestamp)

    def check_loitering(self, plate: str, camera_id: str, timestamp: datetime) -> Optional[Dict]:
        """
        Check if vehicle is loitering: >= N detections at the same camera within T minutes.
        Returns trigger details dict if loitering detected, else None.
        """
        normalized = normalize_plate(plate)
        count_threshold = alert_config.get_int("loitering_count_threshold", 3)
        window_minutes = alert_config.get_int("loitering_window_minutes", 10)
        cutoff = timestamp - timedelta(minutes=window_minutes)

        with self._lock:
            timestamps = self._loitering_window[normalized][camera_id]
            # Prune old entries
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            recent_count = len(timestamps)

        if recent_count >= count_threshold:
            return {
                "rule": "LOITERING",
                "description": f"Vehicle detected {recent_count} times at {camera_id} within {window_minutes} minutes",
                "detection_count": recent_count,
                "window_minutes": window_minutes,
                "threshold": count_threshold,
                "camera_id": camera_id,
            }
        return None

    def check_wrong_way(self, plate: str, camera_id: str, timestamp: datetime) -> Optional[Dict]:
        """
        Check for A→B→A backtracking pattern within time window.
        Returns trigger details dict if wrong-way detected, else None.
        """
        normalized = normalize_plate(plate)
        window_minutes = alert_config.get_int("wrong_way_window_minutes", 15)
        cutoff = timestamp - timedelta(minutes=window_minutes)

        with self._lock:
            history = list(self._route_history[normalized])

        # Need at least 3 sightings to detect A→B→A
        recent = [(cam, ts) for cam, ts in history if ts >= cutoff]
        if len(recent) < 3:
            return None

        # Check last 3 cameras for A→B→A pattern
        last_three_cams = [cam for cam, _ in recent[-3:]]
        if (last_three_cams[0] == last_three_cams[2] and
                last_three_cams[0] != last_three_cams[1]):
            return {
                "rule": "WRONG_WAY",
                "description": (
                    f"Backtracking detected: {last_three_cams[0]} → "
                    f"{last_three_cams[1]} → {last_three_cams[2]} "
                    f"within {window_minutes} minutes"
                ),
                "camera_sequence": last_three_cams,
                "window_minutes": window_minutes,
                "timestamps": [ts.isoformat() for _, ts in recent[-3:]],
            }
        return None

    def check_speed_anomaly(self, plate: str, camera_id: str, timestamp: datetime) -> Optional[Dict]:
        """
        Check if implied speed between consecutive camera sightings exceeds
        a physically implausible threshold.
        Returns trigger details dict if speed anomaly detected, else None.
        """
        normalized = normalize_plate(plate)
        speed_threshold = alert_config.get_float("speed_anomaly_threshold_kmph", 150.0)

        with self._lock:
            prev = self._last_sighting.get(normalized)

        if prev is None:
            return None

        prev_camera, prev_ts = prev
        if prev_camera == camera_id:
            return None  # Same camera, not a speed check

        delta_seconds = (timestamp - prev_ts).total_seconds()
        if delta_seconds <= 0:
            return None

        speed = implied_speed_kmph(prev_camera, camera_id, delta_seconds)
        if speed is None:
            return None

        distance = camera_distance_km(prev_camera, camera_id)

        if speed > speed_threshold:
            return {
                "rule": "SPEED_ANOMALY",
                "description": (
                    f"Implied speed {speed:.0f} km/h between {prev_camera} and {camera_id} "
                    f"exceeds {speed_threshold:.0f} km/h threshold — "
                    f"possible plate cloning or OCR error"
                ),
                "from_camera": prev_camera,
                "to_camera": camera_id,
                "distance_km": round(distance, 2) if distance else 0,
                "time_seconds": round(delta_seconds, 1),
                "implied_speed_kmph": round(speed, 1),
                "threshold_kmph": speed_threshold,
            }
        return None


# ─── Alert Engine ──────────────────────────────────────────────────────────────

class AlertEngine:
    """
    Core alert processing pipeline.
    Each incoming detection passes through blacklist matching, anomaly detection,
    deduplication, and notification dispatch.
    """

    def __init__(self):
        self.blacklist_cache = BlacklistCache()
        self.anomaly_tracker = AnomalyStateTracker()
        self._dedup_cache: Dict[str, datetime] = {}  # dedup_key → last_alert_time
        self._dedup_lock = threading.RLock()
        self._stats = {
            "detections_processed": 0,
            "alerts_generated": 0,
            "alerts_suppressed": 0,
            "blacklist_hits": 0,
            "possible_matches": 0,
            "loitering_alerts": 0,
            "wrong_way_alerts": 0,
            "speed_anomaly_alerts": 0,
            "restricted_zone_alerts": 0,
        }

    def initialize(self) -> None:
        """Load caches and prepare engine for processing."""
        self.blacklist_cache.load()
        print(f"[AlertEngine] Initialized. Blacklist: {self.blacklist_cache.size} entries")

    def process_detection(self, detection: Dict) -> List[Dict]:
        """
        Process a single ANPR detection through the full alert pipeline.

        Args:
            detection: Dict with keys: plate_number (or plate_raw), camera_id,
                       timestamp, confidence, and optionally lat, lon, camera_name

        Returns:
            List of generated alert dicts (may be empty, or multiple for a single detection)
        """
        self._stats["detections_processed"] += 1

        # Normalize input
        plate_raw = detection.get("plate_raw") or detection.get("plate", "")
        camera_id = detection.get("camera_id", "")
        confidence = float(detection.get("confidence", 0.0))
        timestamp_str = detection.get("timestamp", "")
        camera_name = detection.get("camera_name", "")

        # Parse timestamp
        try:
            if isinstance(timestamp_str, datetime):
                timestamp = timestamp_str
            else:
                timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            timestamp = datetime.now(timezone.utc)

        # Get camera location info
        cam_info = CAMERAS.get(camera_id, {})
        if not camera_name:
            camera_name = cam_info.get("name", camera_id)
        lat = detection.get("lat") or cam_info.get("lat", 28.6139)
        lon = detection.get("lon") or cam_info.get("lon", 77.2090)

        normalized = normalize_plate(plate_raw)
        generated_alerts = []

        # ── 1. Blacklist Matching ──────────────────────────────────────────

        bl_exact = self.blacklist_cache.exact_match(normalized)
        low_confidence_threshold = alert_config.get_float("fuzzy_match_confidence_threshold", 0.85)
        is_low_confidence = confidence < low_confidence_threshold

        if bl_exact and not is_low_confidence:
            # High-confidence exact/canonical match -> BLACKLIST_HIT
            alert = self._create_alert(
                alert_type="BLACKLIST_HIT",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority=bl_exact["priority"],
                trigger_details={
                    "rule": "BLACKLIST_HIT",
                    "description": f"Exact match against blacklisted plate {bl_exact['plate_number']}",
                    "blacklisted_plate": bl_exact["plate_number"],
                    "reason": bl_exact["reason"],
                    "match_type": "exact",
                    "normalized_plate": normalized,
                },
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["blacklist_hits"] += 1

        elif bl_exact and is_low_confidence:
            # Low-confidence match (needs human verification) -> POSSIBLE_MATCH
            raw_dist = levenshtein(
                plate_raw.upper().replace("-", "").replace(" ", ""),
                bl_exact["plate_number"].upper().replace("-", "").replace(" ", "")
            )
            alert = self._create_alert(
                alert_type="POSSIBLE_MATCH",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority="MEDIUM",
                trigger_details={
                    "rule": "POSSIBLE_MATCH",
                    "description": (
                        f"Possible match — OCR read '{plate_raw}' matched blacklisted plate "
                        f"'{bl_exact['plate_number']}' with low confidence ({confidence:.0%}). "
                        f"Needs manual verification."
                    ),
                    "blacklisted_plate": bl_exact["plate_number"],
                    "reason": bl_exact["reason"],
                    "match_type": "low_confidence_canonical",
                    "edit_distance": raw_dist,
                    "ocr_confidence": confidence,
                    "normalized_detection": normalized,
                    "normalized_blacklist": bl_exact["normalized_plate"],
                },
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["possible_matches"] += 1

        elif is_low_confidence:
            # Fuzzy match for non-canonical near-matches (e.g. DL01AB1239 vs DL01AB1234)
            max_edit = alert_config.get_int("fuzzy_match_max_edit_distance", 2)
            fuzzy_result = self.blacklist_cache.fuzzy_match(normalized, max_edit)
            if fuzzy_result:
                entry, edit_dist = fuzzy_result
                alert = self._create_alert(
                    alert_type="POSSIBLE_MATCH",
                    plate=plate_raw,
                    camera_id=camera_id,
                    location_name=camera_name,
                    lat=lat, lon=lon,
                    timestamp=timestamp,
                    confidence=confidence,
                    priority="MEDIUM",  # Always MEDIUM — needs human review
                    trigger_details={
                        "rule": "POSSIBLE_MATCH",
                        "description": (
                            f"Possible match — OCR read '{plate_raw}' is {edit_dist} edit(s) "
                            f"from blacklisted plate '{entry['plate_number']}'. "
                            f"OCR confidence {confidence:.0%} is below threshold. Needs manual review."
                        ),
                        "blacklisted_plate": entry["plate_number"],
                        "reason": entry["reason"],
                        "match_type": "fuzzy",
                        "edit_distance": edit_dist,
                        "ocr_confidence": confidence,
                        "normalized_detection": normalized,
                        "normalized_blacklist": entry["normalized_plate"],
                    },
                )
                if alert:
                    generated_alerts.append(alert)
                    self._stats["possible_matches"] += 1

        # ── 2. Anomaly Detection ───────────────────────────────────────────

        # Record the sighting BEFORE anomaly checks (order matters for speed check)
        # Speed check needs the PREVIOUS sighting, so check first, then record
        speed_result = self.anomaly_tracker.check_speed_anomaly(plate_raw, camera_id, timestamp)
        if speed_result:
            alert = self._create_alert(
                alert_type="SPEED_ANOMALY",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority="HIGH",
                trigger_details=speed_result,
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["speed_anomaly_alerts"] += 1

        # Now record the sighting for future anomaly checks
        self.anomaly_tracker.record_sighting(plate_raw, camera_id, timestamp)

        # Loitering check (same camera, repeated detections)
        loitering_result = self.anomaly_tracker.check_loitering(plate_raw, camera_id, timestamp)
        if loitering_result:
            alert = self._create_alert(
                alert_type="LOITERING",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority="MEDIUM",
                trigger_details=loitering_result,
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["loitering_alerts"] += 1

        # Wrong-way / backtracking check
        wrong_way_result = self.anomaly_tracker.check_wrong_way(plate_raw, camera_id, timestamp)
        if wrong_way_result:
            alert = self._create_alert(
                alert_type="WRONG_WAY",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority="HIGH",
                trigger_details=wrong_way_result,
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["wrong_way_alerts"] += 1

        # Restricted zone check
        restricted_result = self._check_restricted_zone(camera_id, timestamp)
        if restricted_result:
            alert = self._create_alert(
                alert_type="RESTRICTED_ZONE",
                plate=plate_raw,
                camera_id=camera_id,
                location_name=camera_name,
                lat=lat, lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority="HIGH",
                trigger_details=restricted_result,
            )
            if alert:
                generated_alerts.append(alert)
                self._stats["restricted_zone_alerts"] += 1

        return generated_alerts

    def _check_restricted_zone(self, camera_id: str, timestamp: datetime) -> Optional[Dict]:
        """
        Check if detection is in a restricted zone during restricted hours.
        Zones are configurable via the admin panel.
        """
        restricted_zones = alert_config.get_json("restricted_zones", [])
        if not restricted_zones:
            return None

        current_hour = timestamp.hour
        for zone in restricted_zones:
            if zone.get("camera_id") == camera_id:
                start_hour = zone.get("start_hour", 0)
                end_hour = zone.get("end_hour", 0)
                reason = zone.get("reason", "Restricted access zone")

                # Handle overnight ranges (e.g., 22 to 6)
                if start_hour <= end_hour:
                    in_restricted_hours = start_hour <= current_hour < end_hour
                else:
                    in_restricted_hours = current_hour >= start_hour or current_hour < end_hour

                if in_restricted_hours:
                    return {
                        "rule": "RESTRICTED_ZONE",
                        "description": (
                            f"Vehicle detected at {camera_id} during restricted hours "
                            f"({start_hour:02d}:00 - {end_hour:02d}:00): {reason}"
                        ),
                        "camera_id": camera_id,
                        "current_hour": current_hour,
                        "restricted_start": start_hour,
                        "restricted_end": end_hour,
                        "zone_reason": reason,
                    }
        return None

    def _create_alert(
        self,
        alert_type: str,
        plate: str,
        camera_id: str,
        location_name: str,
        lat: float,
        lon: float,
        timestamp: datetime,
        confidence: float,
        priority: str,
        trigger_details: Dict,
    ) -> Optional[Dict]:
        """
        Create and persist an alert, with deduplication check.
        Returns the alert dict if created, None if suppressed as duplicate.
        """
        # ── Deduplication Check ────────────────────────────────────────────
        dedup_window = alert_config.get_int("dedup_window_minutes", 5)
        normalized = normalize_plate(plate)

        # Dedup key = plate + alert_type
        dedup_key = f"{normalized}:{alert_type}"

        with self._dedup_lock:
            last_alert_time = self._dedup_cache.get(dedup_key)
            if last_alert_time:
                cutoff = timestamp - timedelta(minutes=dedup_window)
                if last_alert_time > cutoff:
                    self._stats["alerts_suppressed"] += 1
                    return None  # Suppress duplicate
            self._dedup_cache[dedup_key] = timestamp

        # ── Build trajectory deep link ─────────────────────────────────────
        trajectory_link = f"/trajectory?plate={plate}"

        # ── Create alert record ────────────────────────────────────────────
        alert_id = str(uuid.uuid4())
        alert_data = {
            "id": alert_id,
            "alert_type": alert_type,
            "plate_number": plate,
            "camera_id": camera_id,
            "location_name": location_name,
            "lat": lat,
            "lon": lon,
            "timestamp": timestamp.isoformat(),
            "confidence": round(confidence, 4),
            "priority": priority,
            "status": "NEW",
            "trigger_details": trigger_details,
            "trajectory_link": trajectory_link,
            "dedup_key": dedup_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # ── Persist to database ────────────────────────────────────────────
        session = SessionLocal()
        try:
            record = AlertRecord(
                id=alert_id,
                alert_type=alert_type,
                plate_number=plate,
                camera_id=camera_id,
                location_name=location_name,
                lat=lat,
                lon=lon,
                timestamp=timestamp,
                confidence=confidence,
                priority=priority,
                status="NEW",
                trigger_details=json.dumps(trigger_details),
                trajectory_link=trajectory_link,
                dedup_key=dedup_key,
            )
            session.add(record)
            session.commit()
            self._stats["alerts_generated"] += 1
        except Exception as e:
            session.rollback()
            print(f"[AlertEngine] Failed to persist alert: {e}")
            return None
        finally:
            session.close()

        # ── Dispatch notifications ─────────────────────────────────────────
        config_dict = {k: v["value"] for k, v in alert_config.get_all().items()}
        alert_dispatcher.dispatch(alert_data, config_dict)

        return alert_data

    def process_detection_batch(self, detections: List[Dict]) -> List[Dict]:
        """
        Process a batch of detections through the alert pipeline.
        Returns all generated alerts.
        """
        all_alerts = []
        for det in detections:
            alerts = self.process_detection(det)
            all_alerts.extend(alerts)
        return all_alerts

    def get_stats(self) -> Dict:
        """Return engine processing statistics."""
        return dict(self._stats)

    def reset_anomaly_state(self) -> None:
        """Clear all anomaly tracking state (useful for testing)."""
        self.anomaly_tracker = AnomalyStateTracker()
        with self._dedup_lock:
            self._dedup_cache.clear()


# ─── Global Engine Singleton ──────────────────────────────────────────────────

alert_engine = AlertEngine()
