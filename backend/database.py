"""
database.py — Database persistence for Component 2 (Trajectory Reconstruction Engine).

Stores:
- cameras: Static camera locations with GPS coordinates and zone metadata.
- detections: Historical ANPR sighting events with plate_number, timestamp, camera_id,
  confidence, lat, lon.
Supports PostgreSQL with transparent SQLite fallback (backend/trajectory_data.db).
"""

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import json
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

sys.path.insert(0, os.path.dirname(__file__))
from camera_graph import CAMERAS

Base = declarative_base()


class CameraRecord(Base):
    """Static camera metadata table."""
    __tablename__ = "cameras"

    camera_id = Column(String(32), primary_key=True)
    name = Column(String(128), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    zone = Column(String(64), nullable=False)
    speed_limit_kmph = Column(Float, default=60.0)

    detections = relationship("DetectionRecord", back_populates="camera")

    def to_dict(self) -> Dict:
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "zone": self.zone,
            "speed_limit_kmph": self.speed_limit_kmph,
        }


class DetectionRecord(Base):
    """Historical ANPR plate sighting records."""
    __tablename__ = "detections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plate_number = Column(String(32), nullable=False, index=True)
    raw_plate = Column(String(32), nullable=True)
    camera_id = Column(String(32), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.90)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    vehicle_type = Column(String(32), default="Car")
    is_simulated = Column(Boolean, default=True)

    camera = relationship("CameraRecord", back_populates="detections")

    __table_args__ = (
        Index("idx_plate_timestamp", "plate_number", "timestamp"),
        Index("idx_camera_timestamp", "camera_id", "timestamp"),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "plate_number": self.plate_number,
            "raw_plate": self.raw_plate or self.plate_number,
            "camera_id": self.camera_id,
            "camera_name": self.camera.name if self.camera else self.camera_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": round(self.confidence, 4),
            "lat": self.lat,
            "lon": self.lon,
            "vehicle_type": self.vehicle_type,
        }


# ─── Component 3: Road Segments & Pre-Aggregated Summary Tables ───────────────

class RoadSegmentRecord(Base):
    """Road segment representing a monitored traffic corridor between camera nodes."""
    __tablename__ = "road_segments"

    segment_id = Column(String(32), primary_key=True)
    name = Column(String(128), nullable=False)
    from_camera_id = Column(String(32), ForeignKey("cameras.camera_id"), nullable=False)
    to_camera_id = Column(String(32), ForeignKey("cameras.camera_id"), nullable=False)
    distance_km = Column(Float, nullable=False)
    speed_limit_kmph = Column(Float, default=60.0)
    zone = Column(String(64), nullable=False)
    geometry_json = Column(Text, nullable=False)  # JSON array of [lat, lon] coordinates

    def to_dict(self) -> Dict:
        return {
            "segment_id": self.segment_id,
            "name": self.name,
            "from_camera_id": self.from_camera_id,
            "to_camera_id": self.to_camera_id,
            "distance_km": self.distance_km,
            "speed_limit_kmph": self.speed_limit_kmph,
            "zone": self.zone,
            "coordinates": json.loads(self.geometry_json) if self.geometry_json else [],
        }


class HourlyTrafficSummaryRecord(Base):
    """Pre-aggregated hourly traffic rollup for high-performance dashboard queries."""
    __tablename__ = "hourly_traffic_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_str = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    hour = Column(Integer, nullable=False, index=True)          # 0 - 23
    camera_id = Column(String(32), ForeignKey("cameras.camera_id"), nullable=False, index=True)
    segment_id = Column(String(32), nullable=True, index=True)
    vehicle_count = Column(Integer, default=0)
    avg_speed_kmph = Column(Float, default=45.0)
    congestion_index = Column(Float, default=0.2)             # 0.0 (empty) to 1.0 (gridlock)
    camera_status = Column(String(32), default="ONLINE")      # "ONLINE", "OFFLINE", "DEGRADED"
    is_offline = Column(Boolean, default=False)               # Explicit flag: distinguishes offline from 0 traffic

    __table_args__ = (
        Index("idx_hourly_date_hour", "date_str", "hour"),
        Index("idx_hourly_camera_date", "camera_id", "date_str"),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "date": self.date_str,
            "hour": self.hour,
            "camera_id": self.camera_id,
            "segment_id": self.segment_id,
            "vehicle_count": self.vehicle_count,
            "avg_speed_kmph": round(self.avg_speed_kmph, 1),
            "congestion_index": round(self.congestion_index, 2),
            "camera_status": self.camera_status,
            "is_offline": self.is_offline,
        }


class DailyCorridorSummaryRecord(Base):
    """Pre-aggregated daily summary for long-term urban planning and bottleneck analysis."""
    __tablename__ = "daily_corridor_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date_str = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    segment_id = Column(String(32), nullable=False, index=True)
    total_volume = Column(Integer, default=0)
    avg_speed_kmph = Column(Float, default=40.0)
    peak_hour = Column(Integer, default=9)
    peak_volume = Column(Integer, default=0)
    congestion_level = Column(String(32), default="MODERATE")  # "LOW", "MODERATE", "HEAVY", "SEVERE"
    uptime_pct = Column(Float, default=100.0)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "date": self.date_str,
            "segment_id": self.segment_id,
            "total_volume": self.total_volume,
            "avg_speed_kmph": round(self.avg_speed_kmph, 1),
            "peak_hour": self.peak_hour,
            "peak_volume": self.peak_volume,
            "congestion_level": self.congestion_level,
            "uptime_pct": round(self.uptime_pct, 1),
        }


# ─── Component 4: Alert System Database Models ────────────────────────────────

class BlacklistRecord(Base):
    """Blacklisted vehicle plates for real-time alert matching."""
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plate_number = Column(String(32), nullable=False, unique=True, index=True)
    normalized_plate = Column(String(32), nullable=False, index=True)
    reason = Column(String(256), nullable=False)
    priority = Column(String(16), nullable=False, default="HIGH")  # CRITICAL, HIGH, MEDIUM, LOW
    date_added = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    added_by = Column(String(128), nullable=False, default="system")
    is_active = Column(Boolean, default=True, index=True)

    __table_args__ = (
        Index("idx_blacklist_active_plate", "is_active", "normalized_plate"),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "plate_number": self.plate_number,
            "normalized_plate": self.normalized_plate,
            "reason": self.reason,
            "priority": self.priority,
            "date_added": self.date_added.isoformat() if self.date_added else None,
            "added_by": self.added_by,
            "is_active": self.is_active,
        }


class AlertRecord(Base):
    """Persisted alert events generated by the alert engine."""
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_type = Column(String(32), nullable=False, index=True)
    # BLACKLIST_HIT, POSSIBLE_MATCH, LOITERING, WRONG_WAY, SPEED_ANOMALY, RESTRICTED_ZONE
    plate_number = Column(String(32), nullable=False, index=True)
    camera_id = Column(String(32), nullable=False)
    location_name = Column(String(128), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    priority = Column(String(16), nullable=False, default="MEDIUM", index=True)
    # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(String(16), nullable=False, default="NEW", index=True)
    # NEW, UNDER_REVIEW, CONFIRMED, DISMISSED
    trigger_details = Column(Text, nullable=False, default="{}")  # JSON
    trajectory_link = Column(String(512), nullable=True)
    dedup_key = Column(String(128), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    audit_entries = relationship("AlertAuditRecord", back_populates="alert", order_by="AlertAuditRecord.reviewed_at")

    __table_args__ = (
        Index("idx_alert_status_timestamp", "status", "timestamp"),
        Index("idx_alert_type_timestamp", "alert_type", "timestamp"),
        Index("idx_alert_plate_timestamp", "plate_number", "timestamp"),
    )

    def to_dict(self, include_audit: bool = False) -> Dict:
        result = {
            "id": self.id,
            "alert_type": self.alert_type,
            "plate_number": self.plate_number,
            "camera_id": self.camera_id,
            "location_name": self.location_name,
            "lat": self.lat,
            "lon": self.lon,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": round(self.confidence, 4),
            "priority": self.priority,
            "status": self.status,
            "trigger_details": json.loads(self.trigger_details) if self.trigger_details else {},
            "trajectory_link": self.trajectory_link,
            "dedup_key": self.dedup_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_audit and self.audit_entries:
            result["audit_trail"] = [a.to_dict() for a in self.audit_entries]
        return result


class AlertAuditRecord(Base):
    """Immutable audit trail for alert status changes — legal accountability requirement."""
    __tablename__ = "alert_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(36), ForeignKey("alerts.id"), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # STATUS_CHANGE, NOTE_ADDED, ESCALATED
    old_status = Column(String(16), nullable=True)
    new_status = Column(String(16), nullable=True)
    reviewed_by = Column(String(128), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text, nullable=True)

    alert = relationship("AlertRecord", back_populates="audit_entries")

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "action": self.action,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "notes": self.notes,
        }


class AnomalyConfigRecord(Base):
    """Configurable anomaly detection thresholds and system settings."""
    __tablename__ = "anomaly_config"

    config_key = Column(String(64), primary_key=True)
    config_value = Column(Text, nullable=False)
    description = Column(String(256), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_by = Column(String(128), nullable=False, default="system")

    def to_dict(self) -> Dict:
        return {
            "config_key": self.config_key,
            "config_value": self.config_value,
            "description": self.description,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }


# ─── Authentication & RBAC Models ─────────────────────────────────────────────

class UserRecord(Base):
    """User account with Role-Based Access Control (RBAC)."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(64), nullable=False, unique=True, index=True)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(32), nullable=False, default="Traffic Police", index=True)  # Admin, Traffic Police, City Planner
    full_name = Column(String(128), nullable=False, default="")
    email = Column(String(128), nullable=True)
    department = Column(String(128), nullable=True)
    badge_id = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)

    @property
    def password_hash(self) -> str:
        return self.hashed_password

    @password_hash.setter
    def password_hash(self, value: str):
        self.hashed_password = value

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "full_name": self.full_name,
            "email": self.email,
            "department": self.department,
            "badge_id": self.badge_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class AuthAuditRecord(Base):
    """Immutable audit trail for user authentication, plate searches, and enforcement queries."""
    __tablename__ = "auth_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=True, index=True)
    username = Column(String(64), nullable=False, index=True)
    role = Column(String(32), nullable=True)
    action = Column(String(64), nullable=False, index=True)
    # LOGIN_SUCCESS, LOGIN_FAILED, PLATE_SEARCH, TRAJECTORY_QUERY, VAULT_ACCESS, ALERT_STATUS_CHANGE, CONFIG_UPDATE, VIDEO_PROCESSED
    resource = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False, default="SUCCESS")
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
    details = Column(JSON, nullable=True)  # Structured audit metadata
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("idx_auth_audit_action_ts", "action", "timestamp"),
        Index("idx_auth_audit_user_ts", "username", "timestamp"),
    )

    def to_dict(self) -> Dict:
        det = {}
        if self.details:
            try:
                det = json.loads(self.details) if isinstance(self.details, str) else self.details
            except Exception:
                det = {"raw": str(self.details)}
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "action": self.action,
            "resource": self.resource,
            "status": self.status,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": det,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ─── Engine & Session Setup ──────────────────────────────────────────────────

def get_database_url() -> str:
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    db_path = os.path.join(os.path.dirname(__file__), "trajectory_data.db")
    return f"sqlite:///{db_path}"


DATABASE_URL = get_database_url()
is_sqlite = DATABASE_URL.startswith("sqlite")

try:
    if is_sqlite:
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        with engine.connect() as conn:
            pass
except Exception as e:
    # Fallback to local SQLite if Postgres connection fails
    db_path = os.path.join(os.path.dirname(__file__), "trajectory_data.db")
    DATABASE_URL = f"sqlite:///{db_path}"
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ─── SQLite Auto-Migration Helper ─────────────────────────────────────────────

def _ensure_sqlite_columns():
    """Ensure missing columns in existing SQLite tables are migrated without data loss."""
    if not is_sqlite:
        return
    with engine.connect() as conn:
        # Check users table
        try:
            res = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            existing_cols = {row[1] for row in res}
            if "email" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(128)"))
            if "department" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN department VARCHAR(128)"))
            if "badge_id" not in existing_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN badge_id VARCHAR(64)"))
            conn.commit()
        except Exception as e:
            print(f"[Database Migration] Users table check: {e}")

        # Check auth_audit_log table
        try:
            res = conn.execute(text("PRAGMA table_info(auth_audit_log)")).fetchall()
            existing_cols = {row[1] for row in res}
            if "status" not in existing_cols:
                conn.execute(text("ALTER TABLE auth_audit_log ADD COLUMN status VARCHAR(32) DEFAULT 'SUCCESS'"))
            if "user_agent" not in existing_cols:
                conn.execute(text("ALTER TABLE auth_audit_log ADD COLUMN user_agent VARCHAR(256)"))
            conn.commit()
        except Exception as e:
            print(f"[Database Migration] Auth audit table check: {e}")


_ensure_sqlite_columns()


# ─── Pre-seed Static Cameras and Realistic Historical Trips ───────────────────

def init_seed_data():
    """Ensure static cameras and rich test trajectories exist in database."""
    session = SessionLocal()
    try:
        # 1. Seed Cameras
        for cam_id, cam_info in CAMERAS.items():
            existing = session.query(CameraRecord).filter_by(camera_id=cam_id).first()
            if not existing:
                cam = CameraRecord(
                    camera_id=cam_id,
                    name=cam_info["name"],
                    lat=cam_info["lat"],
                    lon=cam_info["lon"],
                    zone=cam_info["zone"],
                    speed_limit_kmph=60.0,
                )
                session.add(cam)
        session.commit()

        # 2. Check if detections exist
        det_count = session.query(DetectionRecord).count()
        if det_count < 20:
            print("[Database] Pre-seeding historical multi-camera vehicle trajectories...")
            now = datetime.now(timezone.utc)
            base_time = now - timedelta(hours=4)

            # Scenario 1: DL01AB1234 — Normal journey with a 45-min GAP and camera bursts (for deduplication test)
            route_1 = [
                # Hop 1: Connaught Place (CAM_01) - 3 rapid burst frames
                ("CAM_01", base_time, 0.96),
                ("CAM_01", base_time + timedelta(seconds=2), 0.98), # burst frame
                ("CAM_01", base_time + timedelta(seconds=5), 0.92), # burst frame
                
                # Hop 2: India Gate (CAM_02) - 8 mins later (2.5 km -> ~18.7 km/h normal city traffic)
                ("CAM_02", base_time + timedelta(minutes=8), 0.94),
                ("CAM_02", base_time + timedelta(minutes=8, seconds=3), 0.97), # burst frame
                
                # Hop 3: Lajpat Nagar (CAM_03) - 14 mins later (5.2 km -> ~22.3 km/h)
                ("CAM_03", base_time + timedelta(minutes=22), 0.89),

                # GAP INTENTIONAL: 45 min delay before appearing at Saket (CAM_05)
                # (Driver parked or traversed unmonitored arterial streets)
                ("CAM_05", base_time + timedelta(minutes=67), 0.91),

                # Hop 4: Hauz Khas (CAM_06) - 10 mins later (3.1 km)
                ("CAM_06", base_time + timedelta(minutes=77), 0.95),

                # Hop 5: Dhaula Kuan (CAM_07) - 16 mins later (7.4 km)
                ("CAM_07", base_time + timedelta(minutes=93), 0.86),
            ]

            for cam_id, ts, conf in route_1:
                cam = CAMERAS[cam_id]
                rec = DetectionRecord(
                    plate_number="DL01AB1234",
                    raw_plate="DL01AB1234" if conf > 0.90 else "DLO1AB1234",
                    camera_id=cam_id,
                    timestamp=ts,
                    confidence=conf,
                    lat=cam["lat"],
                    lon=cam["lon"],
                    vehicle_type="Car",
                )
                session.add(rec)

            # Scenario 2: MH12XY5678 — Wanted vehicle cross-Delhi transit with speed anomaly GAP
            route_2 = [
                ("CAM_08", base_time + timedelta(minutes=10), 0.95),
                ("CAM_08", base_time + timedelta(minutes=10, seconds=4), 0.99),
                ("CAM_09", base_time + timedelta(minutes=24), 0.91),
                # Speed anomaly gap: 4 mins later across town at CAM_03 (implied speed > 120 km/h)
                ("CAM_03", base_time + timedelta(minutes=28), 0.84),
                ("CAM_04", base_time + timedelta(minutes=42), 0.93),
            ]
            for cam_id, ts, conf in route_2:
                cam = CAMERAS[cam_id]
                rec = DetectionRecord(
                    plate_number="MH12XY5678",
                    raw_plate="MH12XY5678",
                    camera_id=cam_id,
                    timestamp=ts,
                    confidence=conf,
                    lat=cam["lat"],
                    lon=cam["lon"],
                    vehicle_type="SUV",
                )
                session.add(rec)

            # Scenario 3: UP32CD9999 — Clean 4-stop delivery route
            route_3 = [
                ("CAM_01", base_time + timedelta(minutes=5), 0.97),
                ("CAM_02", base_time + timedelta(minutes=15), 0.96),
                ("CAM_03", base_time + timedelta(minutes=30), 0.94),
                ("CAM_04", base_time + timedelta(minutes=45), 0.92),
            ]
            for cam_id, ts, conf in route_3:
                cam = CAMERAS[cam_id]
                rec = DetectionRecord(
                    plate_number="UP32CD9999",
                    raw_plate="UP32CD9999",
                    camera_id=cam_id,
                    timestamp=ts,
                    confidence=conf,
                    lat=cam["lat"],
                    lon=cam["lon"],
                    vehicle_type="Truck",
                )
                session.add(rec)

            session.commit()
            print("[Database] Seed trajectories generated successfully.")

        # 3. Seed Road Segments (Component 3)
        segment_count = session.query(RoadSegmentRecord).count()
        if segment_count < 8:
            print("[Database] Seeding Delhi NCR arterial road corridors...")
            road_segments_def = [
                {
                    "segment_id": "SEG_01",
                    "name": "Connaught Place — India Gate Corridor",
                    "from_camera_id": "CAM_01",
                    "to_camera_id": "CAM_02",
                    "distance_km": 2.42,
                    "speed_limit_kmph": 50.0,
                    "zone": "Central Delhi",
                    "coords": [[28.6329, 77.2197], [28.6250, 77.2250], [28.6129, 77.2295]],
                },
                {
                    "segment_id": "SEG_02",
                    "name": "India Gate — Lajpat Nagar Arterial",
                    "from_camera_id": "CAM_02",
                    "to_camera_id": "CAM_03",
                    "distance_km": 5.20,
                    "speed_limit_kmph": 60.0,
                    "zone": "Central Delhi",
                    "coords": [[28.6129, 77.2295], [28.5900, 77.2350], [28.5677, 77.2433]],
                },
                {
                    "segment_id": "SEG_03",
                    "name": "Lajpat Nagar — Nehru Place Ring Road",
                    "from_camera_id": "CAM_03",
                    "to_camera_id": "CAM_04",
                    "distance_km": 2.51,
                    "speed_limit_kmph": 50.0,
                    "zone": "South Delhi",
                    "coords": [[28.5677, 77.2433], [28.5580, 77.2480], [28.5491, 77.2518]],
                },
                {
                    "segment_id": "SEG_04",
                    "name": "Nehru Place — Saket Press Enclave Corridor",
                    "from_camera_id": "CAM_04",
                    "to_camera_id": "CAM_05",
                    "distance_km": 5.87,
                    "speed_limit_kmph": 50.0,
                    "zone": "South Delhi",
                    "coords": [[28.5491, 77.2518], [28.5350, 77.2300], [28.5244, 77.2090]],
                },
                {
                    "segment_id": "SEG_05",
                    "name": "Connaught Place — Dwarka Sector 10 (NH48)",
                    "from_camera_id": "CAM_01",
                    "to_camera_id": "CAM_06",
                    "distance_km": 18.50,
                    "speed_limit_kmph": 70.0,
                    "zone": "West Delhi",
                    "coords": [[28.6329, 77.2197], [28.6000, 77.1200], [28.5823, 77.0517]],
                },
                {
                    "segment_id": "SEG_06",
                    "name": "Connaught Place — Rohini Outer Ring Corridor",
                    "from_camera_id": "CAM_01",
                    "to_camera_id": "CAM_07",
                    "distance_km": 14.40,
                    "speed_limit_kmph": 60.0,
                    "zone": "North Delhi",
                    "coords": [[28.6329, 77.2197], [28.6700, 77.1600], [28.7041, 77.1025]],
                },
                {
                    "segment_id": "SEG_07",
                    "name": "Connaught Place — Shahdara Vikas Marg Corridor",
                    "from_camera_id": "CAM_01",
                    "to_camera_id": "CAM_08",
                    "distance_km": 9.20,
                    "speed_limit_kmph": 60.0,
                    "zone": "East Delhi",
                    "coords": [[28.6329, 77.2197], [28.6450, 77.2600], [28.6692, 77.2994]],
                },
                {
                    "segment_id": "SEG_08",
                    "name": "Dwarka — Gurugram Sohna Road Express Corridor",
                    "from_camera_id": "CAM_06",
                    "to_camera_id": "CAM_09",
                    "distance_km": 22.00,
                    "speed_limit_kmph": 80.0,
                    "zone": "Gurugram",
                    "coords": [[28.5823, 77.0517], [28.4900, 77.0800], [28.4089, 77.0425]],
                },
            ]

            for sdef in road_segments_def:
                seg_rec = RoadSegmentRecord(
                    segment_id=sdef["segment_id"],
                    name=sdef["name"],
                    from_camera_id=sdef["from_camera_id"],
                    to_camera_id=sdef["to_camera_id"],
                    distance_km=sdef["distance_km"],
                    speed_limit_kmph=sdef["speed_limit_kmph"],
                    zone=sdef["zone"],
                    geometry_json=json.dumps(sdef["coords"]),
                )
                session.add(seg_rec)
            session.commit()

        # 4. Pre-Aggregate Hourly & Daily Traffic Summaries (Component 3 Rollups)
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        last_week_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        hourly_count = session.query(HourlyTrafficSummaryRecord).filter_by(date_str=today_str).count()
        if hourly_count < 100:
            print("[Database] Generating pre-aggregated hourly traffic rollups for Today & Prior Period...")
            camera_list = list(CAMERAS.keys())
            corridor_ids = ["SEG_01", "SEG_02", "SEG_03", "SEG_04", "SEG_05", "SEG_06", "SEG_07", "SEG_08"]

            # Generate 24 hours of pre-aggregated data for both dates
            for d_idx, date_val in enumerate([today_str, last_week_str]):
                # Prior period has slight variation (e.g. 8% lower volume)
                vol_factor = 1.0 if d_idx == 0 else 0.92

                for hr in range(24):
                    # Peak hour multipliers: Morning (8-10), Evening (17-20)
                    if 8 <= hr <= 10:
                        hour_mult = 2.4
                        base_spd = 24.0
                        congestion_idx = 0.85
                    elif 17 <= hr <= 20:
                        hour_mult = 2.8
                        base_spd = 21.0
                        congestion_idx = 0.92
                    elif 0 <= hr <= 5:
                        hour_mult = 0.35
                        base_spd = 58.0
                        congestion_idx = 0.08
                    else:
                        hour_mult = 1.2
                        base_spd = 42.0
                        congestion_idx = 0.42

                    # Rollup for each camera station
                    for cam_id in camera_list:
                        is_cam_offline = False
                        status_str = "ONLINE"
                        seg_id = f"SEG_0{((camera_list.index(cam_id) % 8) + 1)}"

                        # Explicit scenario: CAM_08 (Shahdara Flyover) experienced an offline hardware failure today between 13:00 and 17:00
                        if d_idx == 0 and cam_id == "CAM_08" and (13 <= hr <= 17):
                            is_cam_offline = True
                            status_str = "OFFLINE"
                            veh_count = 0
                            spd_val = 0.0
                            c_idx = 0.0
                        else:
                            veh_count = int(850 * hour_mult * vol_factor) + ((hr * 13) % 70)
                            spd_val = max(15.0, base_spd + ((hr * 7) % 10) - 5.0)
                            c_idx = congestion_idx

                        summary_rec = HourlyTrafficSummaryRecord(
                            date_str=date_val,
                            hour=hr,
                            camera_id=cam_id,
                            segment_id=seg_id,
                            vehicle_count=veh_count,
                            avg_speed_kmph=spd_val,
                            congestion_index=c_idx,
                            camera_status=status_str,
                            is_offline=is_cam_offline,
                        )
                        session.add(summary_rec)

            # Generate Daily Corridor Summaries
            for d_idx, date_val in enumerate([today_str, last_week_str]):
                vol_factor = 1.0 if d_idx == 0 else 0.92
                for seg_id in corridor_ids:
                    seg_vol = int(18500 * vol_factor) + (int(seg_id[-1]) * 850)
                    corridor_rec = DailyCorridorSummaryRecord(
                        date_str=date_val,
                        segment_id=seg_id,
                        total_volume=seg_vol,
                        avg_speed_kmph=36.5 if seg_id in ["SEG_01", "SEG_02", "SEG_03"] else 52.0,
                        peak_hour=18,
                        peak_volume=int(seg_vol * 0.12),
                        congestion_level="HEAVY" if seg_id in ["SEG_01", "SEG_02", "SEG_07"] else "MODERATE",
                        uptime_pct=83.3 if (d_idx == 0 and seg_id == "SEG_07") else 100.0,
                    )
                    session.add(corridor_rec)

            session.commit()
            print("[Database] Component 3 pre-aggregated summaries seeded successfully.")

        # 5. Seed Blacklist (Component 4) — migrate hardcoded wanted plates
        blacklist_count = session.query(BlacklistRecord).count()
        if blacklist_count < 5:
            print("[Database] Seeding blacklist with wanted vehicle plates...")
            from matcher import normalize_plate
            blacklist_entries = [
                {"plate": "DL01AB1234", "reason": "Reported stolen — FIR #2026/DL/4521", "priority": "CRITICAL"},
                {"plate": "MH12XY5678", "reason": "Wanted in connection with armed robbery — Case #MH/CR/8891", "priority": "CRITICAL"},
                {"plate": "UP32CD9999", "reason": "Suspected vehicle used in hit-and-run — FIR #2026/UP/1102", "priority": "HIGH"},
                {"plate": "KA05EF2222", "reason": "Outstanding traffic violations — 12 unpaid challans", "priority": "MEDIUM"},
                {"plate": "RJ14GH7777", "reason": "Registration expired — impounded vehicle escaped", "priority": "HIGH"},
            ]
            for entry in blacklist_entries:
                rec = BlacklistRecord(
                    plate_number=entry["plate"],
                    normalized_plate=normalize_plate(entry["plate"]),
                    reason=entry["reason"],
                    priority=entry["priority"],
                    added_by="system_seed",
                    is_active=True,
                )
                session.add(rec)
            session.commit()
            print("[Database] Blacklist seeded with 5 wanted plates.")

        # 6. Seed Anomaly Configuration Defaults (Component 4)
        config_count = session.query(AnomalyConfigRecord).count()
        if config_count < 5:
            print("[Database] Seeding anomaly detection configuration defaults...")
            default_configs = [
                ("loitering_count_threshold", "3", "Minimum detections at same camera to trigger loitering alert"),
                ("loitering_window_minutes", "10", "Time window in minutes for loitering detection"),
                ("speed_anomaly_threshold_kmph", "150", "Implied speed above this value triggers speed anomaly alert"),
                ("wrong_way_window_minutes", "15", "Time window to detect A→B→A backtracking pattern"),
                ("dedup_window_minutes", "5", "Suppress duplicate alerts within this window"),
                ("fuzzy_match_confidence_threshold", "0.85", "OCR confidence below this triggers fuzzy blacklist matching"),
                ("fuzzy_match_max_edit_distance", "2", "Maximum Levenshtein distance for fuzzy blacklist match"),
                ("restricted_zones", "[]", "JSON array of {camera_id, start_hour, end_hour, reason}"),
                ("email_enabled", "false", "Enable email notifications for HIGH/CRITICAL alerts"),
                ("sms_enabled", "false", "Enable SMS notifications via Twilio for CRITICAL alerts"),
                ("smtp_host", "", "SMTP server hostname"),
                ("smtp_port", "587", "SMTP server port"),
                ("smtp_user", "", "SMTP authentication username"),
                ("smtp_password", "", "SMTP authentication password"),
                ("twilio_sid", "", "Twilio Account SID"),
                ("twilio_token", "", "Twilio Auth Token"),
                ("twilio_from", "", "Twilio sender phone number"),
                ("notification_recipients", "[]", "JSON array of {name, email, phone, priority_filter}"),
            ]
            for key, value, desc in default_configs:
                rec = AnomalyConfigRecord(
                    config_key=key,
                    config_value=value,
                    description=desc,
                    updated_by="system_seed",
                )
                session.add(rec)
            session.commit()
            print("[Database] Anomaly configuration defaults seeded successfully.")

        # 7. Seed Default RBAC User Accounts
        user_count = session.query(UserRecord).count()
        if user_count < 3:
            print("[Database] Seeding default RBAC user accounts...")
            from auth import get_password_hash
            default_users = [
                {
                    "username": "admin",
                    "password": "Admin@123",
                    "role": "Admin",
                    "full_name": "Chief Administrator Verma",
                    "badge_id": "HQ-ADMIN-01",
                },
                {
                    "username": "police_sharma",
                    "password": "Police@123",
                    "role": "Traffic Police",
                    "full_name": "Inspector R. K. Sharma",
                    "badge_id": "DL-TP-4091",
                },
                {
                    "username": "planner_verma",
                    "password": "Planner@123",
                    "role": "City Planner",
                    "full_name": "Urban Traffic Analyst Priya Verma",
                    "badge_id": "DDA-PLAN-88",
                },
            ]
            for u in default_users:
                existing = session.query(UserRecord).filter_by(username=u["username"]).first()
                if not existing:
                    user_rec = UserRecord(
                        username=u["username"],
                        hashed_password=get_password_hash(u["password"]),
                        role=u["role"],
                        full_name=u["full_name"],
                        badge_id=u["badge_id"],
                        is_active=True,
                    )
                    session.add(user_rec)
            session.commit()
            print("[Database] Default RBAC users seeded successfully (admin, police_sharma, planner_verma).")

    except Exception as e:
        session.rollback()
        print(f"[Database] Seed initialization warning: {e}")
    finally:
        session.close()


init_seed_data()

