"""
queue_consumer.py — Message Queue Consumer for Component 4 Alert Engine.

Consumes ANPR detection events from RabbitMQ or Kafka (published by the OCR
service via queue_publisher.py) and feeds them into the alert engine pipeline.

When no broker is available, operates in "simulation bridge" mode where
detections from /simulate are fed directly into the alert engine in-process.
"""

import json
import os
import threading
import time
from typing import Callable, Dict, Optional

import sys
sys.path.insert(0, os.path.dirname(__file__))


class QueueConsumer:
    """
    Background message queue consumer with resilient fallback.
    Runs as a daemon thread started on FastAPI startup.
    """

    def __init__(self, on_detection: Callable[[Dict], None]):
        """
        Args:
            on_detection: Callback function invoked for each received detection.
                          Expected signature: fn(detection_dict) -> None
        """
        self.on_detection = on_detection
        self.queue_type = os.getenv("QUEUE_TYPE", "rabbitmq")
        self.rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.queue_topic = os.getenv("QUEUE_TOPIC", "anpr.detections")
        self.consumer_group = os.getenv("CONSUMER_GROUP", "alert-engine-group")
        self.is_connected = False
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background consumer thread."""
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._consumer_loop,
            daemon=True,
            name="alert-queue-consumer",
        )
        self._thread.start()
        print("[QueueConsumer] Background consumer thread started")

    def stop(self) -> None:
        """Stop the consumer thread gracefully."""
        self._stop_event.set()
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        print("[QueueConsumer] Consumer thread stopped")

    def _consumer_loop(self) -> None:
        """Main consumer loop — attempts broker connection, retries on failure."""
        self.is_running = True

        while not self._stop_event.is_set():
            if self.queue_type == "rabbitmq":
                self._consume_rabbitmq()
            elif self.queue_type == "kafka":
                self._consume_kafka()

            if self._stop_event.is_set():
                break

            # Retry delay on connection failure
            print("[QueueConsumer] Broker connection lost. Retrying in 10s...")
            print("[QueueConsumer] Detections can still be processed via /simulate bridge mode.")
            self._stop_event.wait(timeout=10.0)

        self.is_running = False

    def _consume_rabbitmq(self) -> None:
        """Connect to RabbitMQ and consume detection events."""
        try:
            import pika

            params = pika.URLParameters(self.rabbitmq_url)
            params.socket_timeout = 5.0
            params.heartbeat = 30

            connection = pika.BlockingConnection(params)
            channel = connection.channel()

            # Declare the exchange (must match the publisher's declaration)
            channel.exchange_declare(
                exchange=self.queue_topic,
                exchange_type="fanout",
                durable=True,
            )

            # Create an exclusive queue for this consumer
            result = channel.queue_declare(queue="", exclusive=True)
            queue_name = result.method.queue
            channel.queue_bind(exchange=self.queue_topic, queue=queue_name)

            self.is_connected = True
            print(f"[QueueConsumer] Connected to RabbitMQ. Consuming from '{self.queue_topic}'")

            def callback(ch, method, properties, body):
                try:
                    detection = json.loads(body)
                    if detection.get("event_type") == "ANPR_DETECTION":
                        self.on_detection(detection)
                except Exception as e:
                    print(f"[QueueConsumer] Error processing message: {e}")

            channel.basic_consume(
                queue=queue_name,
                on_message_callback=callback,
                auto_ack=True,
            )

            # Blocking consume with periodic stop checks
            while not self._stop_event.is_set():
                connection.process_data_events(time_limit=1)

            connection.close()

        except ImportError:
            print("[QueueConsumer] pika not installed — RabbitMQ consumer unavailable")
            print("[QueueConsumer] Running in simulation bridge mode only")
            self._stop_event.wait()  # Block until stop signal
        except Exception as e:
            self.is_connected = False
            print(f"[QueueConsumer] RabbitMQ error: {e}")

    def _consume_kafka(self) -> None:
        """Connect to Kafka and consume detection events."""
        try:
            from kafka import KafkaConsumer

            consumer = KafkaConsumer(
                self.queue_topic,
                bootstrap_servers=self.kafka_servers.split(","),
                group_id=self.consumer_group,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                consumer_timeout_ms=1000,
            )

            self.is_connected = True
            print(f"[QueueConsumer] Connected to Kafka. Consuming '{self.queue_topic}'")

            while not self._stop_event.is_set():
                records = consumer.poll(timeout_ms=1000)
                for tp, messages in records.items():
                    for msg in messages:
                        try:
                            detection = msg.value
                            if detection.get("event_type") == "ANPR_DETECTION":
                                self.on_detection(detection)
                        except Exception as e:
                            print(f"[QueueConsumer] Error processing Kafka message: {e}")

            consumer.close()

        except ImportError:
            print("[QueueConsumer] kafka-python not installed — Kafka consumer unavailable")
            print("[QueueConsumer] Running in simulation bridge mode only")
            self._stop_event.wait()
        except Exception as e:
            self.is_connected = False
            print(f"[QueueConsumer] Kafka error: {e}")

    @property
    def status(self) -> Dict:
        """Return current consumer status."""
        return {
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "queue_type": self.queue_type,
            "topic": self.queue_topic,
            "mode": "broker" if self.is_connected else "simulation_bridge",
        }
