"""
test_alert_system.py — Comprehensive test suite for Component 4 Alert System.

Covers 10 scenarios:
  1. Blacklist exact match
  2. Blacklist fuzzy match (low OCR confidence, edit distance <= 2)
  3. No false positive (edit distance > 2 or high confidence)
  4. Loitering detection (>= N sightings at same camera within T minutes)
  5. Wrong-way / backtracking detection (A -> B -> A pattern)
  6. Implausible speed anomaly (inter-camera velocity > 150 km/h)
  7. Restricted zone violation (configured camera during restricted hours)
  8. Time-bucketed alert deduplication
  9. Alert status workflow and audit logging
  10. Blacklist CRUD & cache invalidation
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Add backend directory to path
sys.path.insert(0, os.path.dirname(__file__))

from database import (
    SessionLocal,
    Base,
    engine,
    BlacklistRecord,
    AlertRecord,
    AlertAuditRecord,
    AnomalyConfigRecord,
    init_seed_data,
)
from matcher import normalize_plate
from alert_config import alert_config
from alert_engine import alert_engine


# ─── 1. Blacklist Exact Match ──────────────────────────────────────────────────

def test_blacklist_exact_match():
    """Exact match of blacklisted plate generates BLACKLIST_HIT alert immediately."""
    alert_engine.blacklist_cache.refresh()
    norm = normalize_plate("DL01AB1234")
    session = SessionLocal()
    bl = session.query(BlacklistRecord).filter_by(normalized_plate=norm).first()
    if not bl:
        bl = BlacklistRecord(
            plate_number="DL-01-AB-1234",
            normalized_plate=norm,
            reason="Stolen vehicle test",
            priority="CRITICAL",
            added_by="test",
            is_active=True,
        )
        session.add(bl)
        session.commit()
    session.close()
    alert_engine.blacklist_cache.refresh()

    detection = {
        "plate_raw": "DL-01-AB-1234",
        "camera_id": "CAM_01",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.95,
    }

    alerts = alert_engine.process_detection(detection)
    assert len(alerts) >= 1
    hit = next((a for a in alerts if a["alert_type"] == "BLACKLIST_HIT"), None)
    assert hit is not None
    assert hit["plate_number"] == "DL-01-AB-1234"
    assert hit["priority"] in ("CRITICAL", "HIGH")
    assert hit["trigger_details"]["match_type"] == "exact"


# ─── 2. Blacklist Fuzzy Match ──────────────────────────────────────────────────

def test_blacklist_fuzzy_match():
    """Low-confidence OCR read near blacklisted plate generates POSSIBLE_MATCH alert."""
    alert_engine.blacklist_cache.refresh()

    # DLO1AB1234 has 'O' instead of '0' (edit distance 1 from DL01AB1234)
    # OCR confidence is 0.72 (< 0.85 threshold)
    detection = {
        "plate_raw": "DLO1AB1234",
        "camera_id": "CAM_02",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.72,
    }

    alerts = alert_engine.process_detection(detection)
    possible_match = next((a for a in alerts if a["alert_type"] == "POSSIBLE_MATCH"), None)
    assert possible_match is not None
    assert possible_match["priority"] == "MEDIUM"
    assert possible_match["trigger_details"]["match_type"] in ("fuzzy", "low_confidence_canonical")
    assert possible_match["trigger_details"]["edit_distance"] <= 2


# ─── 3. No False Positive ──────────────────────────────────────────────────────

def test_no_false_positive():
    """Detection with high confidence or large edit distance generates NO blacklist alert."""
    # Completely clean plate with high confidence
    detection = {
        "plate_raw": "MH12XY9999",
        "camera_id": "CAM_03",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.98,
    }

    alerts = alert_engine.process_detection(detection)
    bl_alerts = [a for a in alerts if a["alert_type"] in ("BLACKLIST_HIT", "POSSIBLE_MATCH")]
    assert len(bl_alerts) == 0


# ─── 4. Loitering Detection ───────────────────────────────────────────────────

def test_loitering_detection():
    """Vehicle seen >= 3 times at the same camera within 10 min triggers LOITERING alert."""
    plate = "UP16ZZ1111"
    base_time = datetime.now(timezone.utc) - timedelta(minutes=5)

    # 1st sighting: no alert
    a1 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_04", "timestamp": (base_time + timedelta(minutes=1)).isoformat(), "confidence": 0.95
    })
    assert not any(a["alert_type"] == "LOITERING" for a in a1)

    # 2nd sighting: no alert
    a2 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_04", "timestamp": (base_time + timedelta(minutes=2)).isoformat(), "confidence": 0.95
    })
    assert not any(a["alert_type"] == "LOITERING" for a in a2)

    # 3rd sighting: triggers LOITERING
    a3 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_04", "timestamp": (base_time + timedelta(minutes=3)).isoformat(), "confidence": 0.95
    })
    loitering = next((a for a in a3 if a["alert_type"] == "LOITERING"), None)
    assert loitering is not None
    assert loitering["trigger_details"]["rule"] == "LOITERING"
    assert loitering["trigger_details"]["detection_count"] >= 3


# ─── 5. Wrong-Way / Backtracking Detection ─────────────────────────────────────

def test_wrong_way_detection():
    """A -> B -> A pattern within 15 minutes triggers WRONG_WAY alert."""
    plate = "HR26WW2222"
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Sighting 1: CAM_01
    alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_01", "timestamp": (base_time + timedelta(minutes=1)).isoformat(), "confidence": 0.9
    })

    # Sighting 2: CAM_02
    alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_02", "timestamp": (base_time + timedelta(minutes=3)).isoformat(), "confidence": 0.9
    })

    # Sighting 3: Back to CAM_01 within window
    a3 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_01", "timestamp": (base_time + timedelta(minutes=5)).isoformat(), "confidence": 0.9
    })

    wrong_way = next((a for a in a3 if a["alert_type"] == "WRONG_WAY"), None)
    assert wrong_way is not None
    assert wrong_way["trigger_details"]["camera_sequence"] == ["CAM_01", "CAM_02", "CAM_01"]


# ─── 6. Implausible Speed Anomaly ─────────────────────────────────────────────

def test_speed_anomaly_detection():
    """Implied speed > 150 km/h between two cameras triggers SPEED_ANOMALY alert."""
    plate = "DL08SS3333"
    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    # CAM_01 (Connaught Place)
    alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_01", "timestamp": base_time.isoformat(), "confidence": 0.95
    })

    # CAM_09 (Cyber City Gurugram, ~28 km away) sighted only 2 minutes later
    # Speed = 28 km / (2/60 h) = 840 km/h -> physically impossible
    a2 = alert_engine.process_detection({
        "plate_raw": plate,
        "camera_id": "CAM_09",
        "timestamp": (base_time + timedelta(minutes=2)).isoformat(),
        "confidence": 0.95,
    })

    speed_alert = next((a for a in a2 if a["alert_type"] == "SPEED_ANOMALY"), None)
    assert speed_alert is not None
    assert speed_alert["trigger_details"]["implied_speed_kmph"] > 150.0
    assert speed_alert["priority"] == "HIGH"


# ─── 7. Restricted Zone Detection ─────────────────────────────────────────────

def test_restricted_zone_detection():
    """Detection in a configured restricted zone during active hours triggers RESTRICTED_ZONE alert."""
    # Configure CAM_05 as restricted 24/7 for testing
    import json
    test_zones = json.dumps([{
        "camera_id": "CAM_05",
        "start_hour": 0,
        "end_hour": 24,
        "reason": "Test Security Zone Alpha",
    }])
    alert_config.update("restricted_zones", test_zones, "test_suite")

    detection = {
        "plate_raw": "KA01RZ4444",
        "camera_id": "CAM_05",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.92,
    }

    alerts = alert_engine.process_detection(detection)
    rz_alert = next((a for a in alerts if a["alert_type"] == "RESTRICTED_ZONE"), None)
    assert rz_alert is not None
    assert rz_alert["trigger_details"]["zone_reason"] == "Test Security Zone Alpha"

    # Reset restricted zones
    alert_config.update("restricted_zones", "[]", "test_suite")


# ─── 8. Alert Deduplication ───────────────────────────────────────────────────

def test_alert_deduplication():
    """Rapid repeated detections for the same plate and alert type are deduplicated."""
    plate = "DL01AB1234"  # Known blacklisted plate
    now = datetime.now(timezone.utc)

    # First hit -> alert generated
    a1 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_01", "timestamp": now.isoformat(), "confidence": 0.95
    })
    hit1 = [a for a in a1 if a["alert_type"] == "BLACKLIST_HIT"]
    assert len(hit1) == 1

    # Second hit within 1 minute -> suppressed as duplicate
    a2 = alert_engine.process_detection({
        "plate_raw": plate, "camera_id": "CAM_01", "timestamp": (now + timedelta(seconds=30)).isoformat(), "confidence": 0.95
    })
    hit2 = [a for a in a2 if a["alert_type"] == "BLACKLIST_HIT"]
    assert len(hit2) == 0

    stats = alert_engine.get_stats()
    assert stats["alerts_suppressed"] >= 1


# ─── 9. Alert Status Workflow & Audit Log ─────────────────────────────────────

def test_alert_status_workflow_and_audit():
    """Alert status transition creates legal audit log entries."""
    session = SessionLocal()

    # Create a fresh test alert
    alert = AlertRecord(
        alert_type="BLACKLIST_HIT",
        plate_number="DL01AB1234",
        camera_id="CAM_01",
        location_name="Connaught Place Outer Circle",
        lat=28.6315,
        lon=77.2167,
        timestamp=datetime.now(timezone.utc),
        confidence=0.95,
        priority="CRITICAL",
        status="NEW",
        trigger_details="{}",
    )
    session.add(alert)
    session.commit()
    alert_id = alert.id

    # Transition 1: NEW -> UNDER_REVIEW
    alert.status = "UNDER_REVIEW"
    audit1 = AlertAuditRecord(
        alert_id=alert_id,
        action="STATUS_CHANGE",
        old_status="NEW",
        new_status="UNDER_REVIEW",
        reviewed_by="officer_sharma",
        notes="Dispatched unit to intercept",
    )
    session.add(audit1)
    session.commit()

    # Transition 2: UNDER_REVIEW -> CONFIRMED
    alert.status = "CONFIRMED"
    audit2 = AlertAuditRecord(
        alert_id=alert_id,
        action="STATUS_CHANGE",
        old_status="UNDER_REVIEW",
        new_status="CONFIRMED",
        reviewed_by="inspector_singh",
        notes="Vehicle intercepted and impounded",
    )
    session.add(audit2)
    session.commit()

    # Verify audit trail
    audits = session.query(AlertAuditRecord).filter_by(alert_id=alert_id).order_by(AlertAuditRecord.reviewed_at).all()
    assert len(audits) == 2
    assert audits[0].old_status == "NEW" and audits[0].new_status == "UNDER_REVIEW"
    assert audits[1].old_status == "UNDER_REVIEW" and audits[1].new_status == "CONFIRMED"
    assert audits[1].reviewed_by == "inspector_singh"

    # Test to_dict with audit
    alert_dict = alert.to_dict(include_audit=True)
    assert len(alert_dict["audit_trail"]) == 2

    session.close()


# ─── 10. Blacklist CRUD & Cache Invalidation ──────────────────────────────────

def test_blacklist_crud_cache():
    """Blacklist CRUD updates persistent DB and refreshes in-memory cache."""
    session = SessionLocal()
    test_plate = "DL99XX0000"
    norm_plate = normalize_plate(test_plate)

    # Clean up any leftover test record
    session.query(BlacklistRecord).filter_by(normalized_plate=norm_plate).delete()
    session.commit()

    # 1. Add plate
    rec = BlacklistRecord(
        plate_number=test_plate,
        normalized_plate=norm_plate,
        reason="Test Warrant Issued",
        priority="HIGH",
        added_by="test_admin",
        is_active=True,
    )
    session.add(rec)
    session.commit()
    session.close()

    # Refresh cache
    alert_engine.blacklist_cache.refresh()
    match = alert_engine.blacklist_cache.exact_match(norm_plate)
    assert match is not None
    assert match["reason"] == "Test Warrant Issued"

    # 2. Deactivate (soft delete)
    session = SessionLocal()
    rec = session.query(BlacklistRecord).filter_by(normalized_plate=norm_plate).first()
    rec.is_active = False
    session.commit()
    session.close()

    alert_engine.blacklist_cache.refresh()
    assert alert_engine.blacklist_cache.exact_match(norm_plate) is None


# ─── Standalone Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("1. Blacklist exact match", test_blacklist_exact_match),
        ("2. Blacklist fuzzy match", test_blacklist_fuzzy_match),
        ("3. No false positive", test_no_false_positive),
        ("4. Loitering detection", test_loitering_detection),
        ("5. Wrong-way detection", test_wrong_way_detection),
        ("6. Speed anomaly", test_speed_anomaly_detection),
        ("7. Restricted zone", test_restricted_zone_detection),
        ("8. Alert deduplication", test_alert_deduplication),
        ("9. Status workflow & audit", test_alert_status_workflow_and_audit),
        ("10. Blacklist CRUD & cache", test_blacklist_crud_cache),
    ]

    print("\n" + "=" * 60)
    print(" COMPONENT 4 — ALERT SYSTEM TEST SUITE")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, test_fn in tests:
        # Fixture setup
        init_seed_data()
        alert_engine.initialize()
        alert_engine.reset_anomaly_state()

        try:
            test_fn()
            print(f"  [PASS]  {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL]  {name} — Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f" RESULTS: {passed} passed, {failed} failed (Total {len(tests)})")
    print("=" * 60 + "\n")

    sys.exit(0 if failed == 0 else 1)
