"""
config.py — Configuration settings for High-Precision ANPR OCR Service.

Handles configurable confidence thresholds, plate format regex patterns,
database DSNs, message queue endpoints, and GPU/CPU inference device targets.
"""

import os
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service identity
    SERVICE_NAME: str = "anpr-ocr-service"
    SERVICE_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # Hardware & Inference Execution
    DEVICE: str = "auto"  # 'auto', 'cuda', or 'cpu'
    GPU_BATCH_SIZE: int = 16
    MAX_CONCURRENT_STREAMS: int = 20
    TARGET_STREAM_FPS: float = 15.0

    # Detection & Recognition Confidence Thresholds
    CONFIDENCE_THRESHOLD: float = 0.85  # Detections below 85% flagged as needs_review
    DETECTION_IOU_THRESHOLD: float = 0.45
    DETECTION_CONF_THRESHOLD: float = 0.50

    # Plate Format Rules (Configurable for any country/state standard)
    # Default: Indian Standard (e.g. DL01AB1234, MH12XY5678, KA05EF2222)
    # Format: 2-letter State Code + 1-2 digit RTO + 1-3 letter Series + 4 digit number
    PLATE_REGEX: str = r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$"
    COUNTRY_CODE: str = "IN"

    # Database Persistence (PostgreSQL with automatic SQLite fallback for local testing)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://anpr_user:anpr_secret@localhost:5432/anpr_db"
    )
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./anpr_local.db"
    USE_SQLITE_FALLBACK: bool = True

    # Message Queue Interface (RabbitMQ or Kafka)
    QUEUE_TYPE: str = "rabbitmq"  # 'rabbitmq' or 'kafka'
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    QUEUE_TOPIC: str = "anpr.detections"
    QUEUE_FALLBACK_BUFFER_SIZE: int = 1000

    # Retraining & Audit Logging
    AUDIT_LOG_DIR: str = "./logs/inferences"
    LOG_RAW_IMAGES: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
