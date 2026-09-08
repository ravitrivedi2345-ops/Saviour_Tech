"""
database.py — Database persistence for ANPR detections.

Schema stores all plate sightings with B-tree indexes on:
- plate_number
- timestamp
- camera_id
- needs_review
And composite index on (camera_id, timestamp) for rapid trajectory corridor queries.
Supports PostgreSQL, with automatic SQLite fallback for standalone local tests.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings

Base = declarative_base()


class DetectionRecord(Base):
    """Stores full ANPR plate recognition event."""

    __tablename__ = "anpr_detections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    camera_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    plate_number = Column(String(32), nullable=False, index=True)
    raw_plate = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False)
    
    # Bounding box coordinates
    bbox_x1 = Column(Integer, nullable=False)
    bbox_y1 = Column(Integer, nullable=False)
    bbox_x2 = Column(Integer, nullable=False)
    bbox_y2 = Column(Integer, nullable=False)

    is_format_valid = Column(Boolean, default=True)
    needs_review = Column(Boolean, default=False, index=True)
    review_reasons = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)
    image_uri = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Composite indexes for high-throughput temporal and spatial lookups
    __table_args__ = (
        Index("idx_cam_timestamp", "camera_id", "timestamp"),
        Index("idx_plate_timestamp", "plate_number", "timestamp"),
        Index("idx_review_queue", "needs_review", "timestamp"),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "plate_number": self.plate_number,
            "raw_plate": self.raw_plate,
            "confidence": self.confidence,
            "bbox": [self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2],
            "is_format_valid": self.is_format_valid,
            "needs_review": self.needs_review,
            "review_reasons": self.review_reasons.split("; ") if self.review_reasons else [],
            "latency_ms": self.latency_ms,
            "image_uri": self.image_uri,
        }


# Database Engine setup with resilient fallback
def init_db():
    db_url = settings.DATABASE_URL
    # For sync SQLAlchemy engine conversion if asyncpg URL passed
    if db_url.startswith("postgresql+asyncpg://"):
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    else:
        sync_url = db_url

    try:
        engine = create_engine(sync_url, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            pass
        print(f"[Database] Connected to PostgreSQL at {sync_url.split('@')[-1]}")
    except Exception as e:
        print(f"[Database] PostgreSQL connection failed ({e}). Falling back to SQLite.")
        sqlite_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "anpr_local.db")
        sync_url = f"sqlite:///{sqlite_path}"
        engine = create_engine(sync_url, connect_args={"check_same_thread": False})

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, session_factory


engine, SessionLocal = init_db()


def save_detection(detection: Dict, image_uri: Optional[str] = None) -> DetectionRecord:
    """Save a single detection dictionary to database."""
    session = SessionLocal()
    try:
        ts = detection.get("timestamp")
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            dt = ts or datetime.now(timezone.utc)

        bbox = detection.get("bbox", [0, 0, 0, 0])
        reasons = detection.get("review_reasons", [])
        reasons_str = "; ".join(reasons) if isinstance(reasons, list) else str(reasons)

        rec = DetectionRecord(
            camera_id=detection.get("camera_id", "UNKNOWN"),
            timestamp=dt,
            plate_number=detection.get("plate", ""),
            raw_plate=detection.get("raw_plate", ""),
            confidence=float(detection.get("confidence", 0.0)),
            bbox_x1=int(bbox[0]),
            bbox_y1=int(bbox[1]),
            bbox_x2=int(bbox[2]),
            bbox_y2=int(bbox[3]),
            is_format_valid=detection.get("is_format_valid", True),
            needs_review=detection.get("needs_review", False),
            review_reasons=reasons_str,
            latency_ms=detection.get("latency_ms"),
            image_uri=image_uri,
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        return rec
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def query_detections(
    camera_id: Optional[str] = None,
    plate_number: Optional[str] = None,
    needs_review: Optional[bool] = None,
    limit: int = 100,
) -> List[Dict]:
    """Query detections with filtering."""
    session = SessionLocal()
    try:
        q = session.query(DetectionRecord)
        if camera_id:
            q = q.filter(DetectionRecord.camera_id == camera_id)
        if plate_number:
            q = q.filter(DetectionRecord.plate_number.like(f"%{plate_number}%"))
        if needs_review is not None:
            q = q.filter(DetectionRecord.needs_review == needs_review)

        q = q.order_by(DetectionRecord.timestamp.desc()).limit(limit)
        return [r.to_dict() for r in q.all()]
    finally:
        session.close()
