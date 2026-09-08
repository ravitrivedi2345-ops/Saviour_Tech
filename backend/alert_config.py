"""
alert_config.py — Centralized configuration manager for Component 4 anomaly thresholds.

Loads configurable thresholds from the AnomalyConfigRecord table,
merges with hardcoded defaults, and provides an in-memory cache with
invalidation on update.
"""

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, AnomalyConfigRecord


# ─── Default Configuration Values ──────────────────────────────────────────────

DEFAULT_CONFIG: Dict[str, str] = {
    "loitering_count_threshold": "3",
    "loitering_window_minutes": "10",
    "speed_anomaly_threshold_kmph": "150",
    "wrong_way_window_minutes": "15",
    "dedup_window_minutes": "5",
    "fuzzy_match_confidence_threshold": "0.85",
    "fuzzy_match_max_edit_distance": "2",
    "restricted_zones": "[]",
    "email_enabled": "false",
    "sms_enabled": "false",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "twilio_sid": "",
    "twilio_token": "",
    "twilio_from": "",
    "notification_recipients": "[]",
}


class AlertConfigManager:
    """Thread-safe configuration manager with in-memory cache."""

    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._loaded = False

    def _load_from_db(self) -> None:
        """Load all config values from database into cache."""
        session = SessionLocal()
        try:
            records = session.query(AnomalyConfigRecord).all()
            with self._lock:
                self._cache = {r.config_key: r.config_value for r in records}
                self._loaded = True
        except Exception as e:
            print(f"[AlertConfig] Failed to load from DB: {e}. Using defaults.")
            with self._lock:
                self._cache = dict(DEFAULT_CONFIG)
                self._loaded = True
        finally:
            session.close()

    def _ensure_loaded(self) -> None:
        """Lazy-load config on first access."""
        if not self._loaded:
            self._load_from_db()

    def get(self, key: str, default: Optional[str] = None) -> str:
        """Get a config value by key, falling back to defaults."""
        self._ensure_loaded()
        with self._lock:
            return self._cache.get(key, DEFAULT_CONFIG.get(key, default or ""))

    def get_int(self, key: str, default: int = 0) -> int:
        """Get a config value as integer."""
        try:
            return int(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a config value as float."""
        try:
            return float(self.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a config value as boolean."""
        val = self.get(key, str(default)).lower()
        return val in ("true", "1", "yes", "on")

    def get_json(self, key: str, default: Any = None) -> Any:
        """Get a config value parsed as JSON."""
        try:
            return json.loads(self.get(key, "[]"))
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else []

    def get_all(self) -> Dict[str, Dict[str, str]]:
        """Get all config values with descriptions."""
        self._ensure_loaded()
        session = SessionLocal()
        try:
            records = session.query(AnomalyConfigRecord).all()
            result = {}
            for r in records:
                result[r.config_key] = {
                    "value": r.config_value,
                    "description": r.description or "",
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    "updated_by": r.updated_by,
                }
            # Include defaults not in DB
            for key, val in DEFAULT_CONFIG.items():
                if key not in result:
                    result[key] = {
                        "value": val,
                        "description": "",
                        "updated_at": None,
                        "updated_by": "default",
                    }
            return result
        except Exception as e:
            print(f"[AlertConfig] Error fetching all configs: {e}")
            return {k: {"value": v, "description": "", "updated_at": None, "updated_by": "default"}
                    for k, v in DEFAULT_CONFIG.items()}
        finally:
            session.close()

    def update(self, key: str, value: str, updated_by: str = "admin") -> bool:
        """Update a config value in both DB and cache."""
        session = SessionLocal()
        try:
            record = session.query(AnomalyConfigRecord).filter_by(config_key=key).first()
            if record:
                record.config_value = value
                record.updated_at = datetime.now(timezone.utc)
                record.updated_by = updated_by
            else:
                record = AnomalyConfigRecord(
                    config_key=key,
                    config_value=value,
                    description=DEFAULT_CONFIG.get(key, ""),
                    updated_by=updated_by,
                )
                session.add(record)
            session.commit()

            # Invalidate cache
            with self._lock:
                self._cache[key] = value

            print(f"[AlertConfig] Updated '{key}' = '{value}' by {updated_by}")
            return True
        except Exception as e:
            session.rollback()
            print(f"[AlertConfig] Failed to update '{key}': {e}")
            return False
        finally:
            session.close()

    def update_batch(self, updates: Dict[str, str], updated_by: str = "admin") -> int:
        """Update multiple config values at once. Returns count of successful updates."""
        count = 0
        for key, value in updates.items():
            if self.update(key, value, updated_by):
                count += 1
        return count

    def invalidate_cache(self) -> None:
        """Force reload from database on next access."""
        with self._lock:
            self._loaded = False
            self._cache.clear()


# ─── Global singleton ─────────────────────────────────────────────────────────

alert_config = AlertConfigManager()
