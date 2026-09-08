"""
queue_publisher.py — Message Queue Producer Interface (RabbitMQ & Kafka).

Publishes real-time plate recognition events to downstream consumers
(Trajectory Reconstruction Engine and Flagged Vehicle Alert Engine).
Decouples inference ingestion from analytics processing.
"""

import json
import os
import sys
import threading
from typing import Dict, List, Optional
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings


class QueuePublisher:
    """Asynchronous Message Queue Publisher with Resilient Memory Buffer."""

    def __init__(self):
        self.queue_type = settings.QUEUE_TYPE
        self.topic = settings.QUEUE_TOPIC
        self.rabbitmq_url = settings.RABBITMQ_URL
        self.kafka_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.buffer = deque(maxlen=settings.QUEUE_FALLBACK_BUFFER_SIZE)
        self.is_connected = False
        self._lock = threading.Lock()
        self._init_connection()

    def _init_connection(self):
        """Attempt connection to configured broker."""
        if self.queue_type == "rabbitmq":
            try:
                # Test with pika if installed
                import pika
                params = pika.URLParameters(self.rabbitmq_url)
                params.socket_timeout = 2.0
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                channel.exchange_declare(exchange=self.topic, exchange_type="fanout", durable=True)
                connection.close()
                self.is_connected = True
                print(f"[QueuePublisher] Connected to RabbitMQ at {self.rabbitmq_url}")
            except Exception as e:
                print(f"[QueuePublisher] RabbitMQ offline ({e}). Running in resilient buffered mode.")
                self.is_connected = False
        elif self.queue_type == "kafka":
            try:
                from kafka import KafkaProducer
                self.producer = KafkaProducer(
                    bootstrap_servers=self.kafka_servers.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    request_timeout_ms=2000,
                )
                self.is_connected = True
                print(f"[QueuePublisher] Connected to Kafka at {self.kafka_servers}")
            except Exception as e:
                print(f"[QueuePublisher] Kafka offline ({e}). Running in resilient buffered mode.")
                self.is_connected = False

    def publish_detection(self, detection: Dict) -> bool:
        """
        Publish an ANPR detection event.

        Payload schema:
        {
            "event_type": "ANPR_DETECTION",
            "detection_id": str,
            "camera_id": str,
            "timestamp": str (ISO-8601),
            "plate": str,
            "confidence": float,
            "bbox": [x1, y1, x2, y2],
            "needs_review": bool,
            "review_reasons": list[str]
        }
        """
        event = {
            "event_type": "ANPR_DETECTION",
            "camera_id": detection.get("camera_id"),
            "timestamp": detection.get("timestamp"),
            "plate": detection.get("plate"),
            "raw_plate": detection.get("raw_plate"),
            "confidence": detection.get("confidence"),
            "bbox": detection.get("bbox"),
            "needs_review": detection.get("needs_review", False),
            "review_reasons": detection.get("review_reasons", []),
            "latency_ms": detection.get("latency_ms"),
        }

        with self._lock:
            self.buffer.append(event)

        # If live broker is connected, publish over socket
        if self.is_connected:
            try:
                if self.queue_type == "rabbitmq":
                    import pika
                    params = pika.URLParameters(self.rabbitmq_url)
                    connection = pika.BlockingConnection(params)
                    channel = connection.channel()
                    channel.basic_publish(
                        exchange=self.topic,
                        routing_key="",
                        body=json.dumps(event),
                        properties=pika.BasicProperties(delivery_mode=2),
                    )
                    connection.close()
                    return True
                elif self.queue_type == "kafka":
                    self.producer.send(self.topic, event)
                    return True
            except Exception as e:
                print(f"[QueuePublisher] Broker send failed: {e}. Event safely kept in local buffer.")
                self.is_connected = False
                return False

        return True  # Safely buffered

    def get_buffered_events(self, limit: int = 50) -> List[Dict]:
        """Inspect recent published/buffered queue events."""
        with self._lock:
            return list(self.buffer)[-limit:]


publisher = QueuePublisher()
