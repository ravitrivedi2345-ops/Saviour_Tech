"""
Live Traffic WebSocket Broadcaster and Simulation Feed for City-Wide ANPR Nodes
"""

import asyncio
import json
import logging
import random
import time
from typing import Dict, List, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger("live_traffic")

# Delhi NCR Camera Nodes Reference
CAMERA_NODES = [
    {"camera_id": "CAM-01", "name": "AIIMS Flyover - Ring Road North", "lat": 28.5672, "lng": 77.2100, "corridor": "Ring Road"},
    {"camera_id": "CAM-02", "name": "Lajpat Nagar Central - Ring Road East", "lat": 28.5700, "lng": 77.2400, "corridor": "Ring Road"},
    {"camera_id": "CAM-03", "name": "Ashram Chowk Junction - Ring Road South-East", "lat": 28.5720, "lng": 77.2600, "corridor": "Ring Road"},
    {"camera_id": "CAM-04", "name": "Dhaula Kuan Interchange - NH-48", "lat": 28.5921, "lng": 77.1610, "corridor": "NH-48"},
    {"camera_id": "CAM-05", "name": "Mahipalpur Bypass - NH-48 Airport Corridor", "lat": 28.5480, "lng": 77.1200, "corridor": "NH-48"},
    {"camera_id": "CAM-06", "name": "Gurugram Border Toll Plaza - NH-48", "lat": 28.5020, "lng": 77.0850, "corridor": "NH-48"},
    {"camera_id": "CAM-07", "name": "Barapullah Elevated Entry - Sarai Kale Khan", "lat": 28.5880, "lng": 77.2550, "corridor": "Barapullah"},
    {"camera_id": "CAM-08", "name": "Barapullah Midpoint - INA Market Exit", "lat": 28.5750, "lng": 77.2150, "corridor": "Barapullah"},
    {"camera_id": "CAM-09", "name": "Outer Ring Road - Munirka Flyover", "lat": 28.5550, "lng": 77.1730, "corridor": "Outer Ring Road"},
    {"camera_id": "CAM-10", "name": "Outer Ring Road - IIT Flyover", "lat": 28.5440, "lng": 77.1920, "corridor": "Outer Ring Road"},
    {"camera_id": "CAM-11", "name": "Outer Ring Road - Nehru Place Terminal", "lat": 28.5485, "lng": 77.2510, "corridor": "Outer Ring Road"},
    {"camera_id": "CAM-12", "name": "Mathura Road - Nizamuddin Dargah", "lat": 28.5895, "lng": 77.2450, "corridor": "Mathura Road"},
    {"camera_id": "CAM-13", "name": "Mathura Road - Apollo Hospital Sarita Vihar", "lat": 28.5380, "lng": 77.2880, "corridor": "Mathura Road"},
    {"camera_id": "CAM-14", "name": "Mathura Road - Badarpur Border Flyover", "lat": 28.4980, "lng": 77.3020, "corridor": "Mathura Road"},
]

SAMPLE_PLATES = [
    "DL01AB1234", "DL03CD5678", "DL08EF9012", "HR26DK8899", "HR51AU3321",
    "UP16BZ4455", "UP14CW7788", "DL04JK1122", "DL09LM3344", "HR29PQ5566",
    "DL10ST7788", "DL12XY9900", "UP32GH1212", "DL05QR6543", "HR10ZZ9999"
]

SAMPLE_VEHICLE_TYPES = ["Car / Sedan", "SUV", "Two-Wheeler", "Commercial Auto", "Light Truck"]


class LiveTrafficManager:
    """Manages active WebSocket connections and broadcasts real-time traffic updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._simulation_task: Optional[asyncio.Task] = None
        self.camera_stats: Dict[str, dict] = {
            cam["camera_id"]: {
                "detections_last_min": random.randint(15, 65),
                "avg_speed_kmh": round(random.uniform(32.0, 78.0), 1),
                "congestion_level": "Moderate",
                "congestion_score": 0.45,  # 0.0 (free) to 1.0 (jammed)
                "status": "Online"
            }
            for cam in CAMERA_NODES
        }

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Live traffic client connected. Total clients: {len(self.active_connections)}")
        
        # Send initial camera state snapshot immediately on connection
        initial_payload = {
            "type": "SNAPSHOT",
            "timestamp": time.time(),
            "camera_nodes": CAMERA_NODES,
            "camera_stats": self.camera_stats
        }
        await websocket.send_text(json.dumps(initial_payload))

        # Ensure background simulator is running
        if self._simulation_task is None or self._simulation_task.done():
            self._simulation_task = asyncio.create_task(self._simulation_loop())

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Live traffic client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead_connections = set()
        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception:
                dead_connections.add(conn)
        for dead in dead_connections:
            self.active_connections.discard(dead)

    async def broadcast_detection(self, detection: dict):
        """Broadcasts an external/real OCR detection event to all live map clients."""
        await self.broadcast({
            "type": "LIVE_DETECTION",
            "timestamp": time.time(),
            "detection": detection
        })

    async def _simulation_loop(self):
        """Simulates periodic realistic live traffic detections and congestion updates across Delhi nodes."""
        logger.info("Starting live traffic background simulation loop...")
        tick = 0
        while True:
            try:
                await asyncio.sleep(2.5)  # Emit a detection event every 2.5 seconds
                if not self.active_connections:
                    await asyncio.sleep(2.0)
                    continue

                tick += 1
                cam = random.choice(CAMERA_NODES)
                cam_id = cam["camera_id"]
                speed = round(random.uniform(25.0, 85.0), 1)
                plate = random.choice(SAMPLE_PLATES)
                confidence = round(random.uniform(0.88, 0.99), 3)
                v_type = random.choice(SAMPLE_VEHICLE_TYPES)

                # Update camera node stats
                stat = self.camera_stats.setdefault(cam_id, {
                    "detections_last_min": 20,
                    "avg_speed_kmh": 50.0,
                    "congestion_level": "Low",
                    "congestion_score": 0.2,
                    "status": "Online"
                })
                stat["detections_last_min"] = max(5, stat["detections_last_min"] + random.choice([-1, 0, 1, 2]))
                stat["avg_speed_kmh"] = round(stat["avg_speed_kmh"] * 0.9 + speed * 0.1, 1)

                # Congestion score calculation based on speed & flow
                if stat["avg_speed_kmh"] < 30:
                    stat["congestion_level"] = "Heavy"
                    stat["congestion_score"] = min(1.0, round(0.7 + (30 - stat["avg_speed_kmh"]) / 100, 2))
                elif stat["avg_speed_kmh"] < 50:
                    stat["congestion_level"] = "Moderate"
                    stat["congestion_score"] = round(0.4 + (50 - stat["avg_speed_kmh"]) / 100, 2)
                else:
                    stat["congestion_level"] = "Low"
                    stat["congestion_score"] = max(0.1, round(0.15 + (85 - stat["avg_speed_kmh"]) / 200, 2))

                detection_event = {
                    "type": "LIVE_DETECTION",
                    "timestamp": time.time(),
                    "detection": {
                        "camera_id": cam_id,
                        "camera_name": cam["name"],
                        "corridor": cam["corridor"],
                        "lat": cam["lat"],
                        "lng": cam["lng"],
                        "plate_number": plate,
                        "confidence": confidence,
                        "speed_kmh": speed,
                        "vehicle_type": v_type,
                        "is_flagged": random.random() < 0.12  # Occasionally simulate flagged vehicles
                    }
                }
                await self.broadcast(detection_event)

                # Every 4 ticks (10s), broadcast full heatmap / congestion matrix update
                if tick % 4 == 0:
                    heatmap_data = [
                        {
                            "camera_id": c["camera_id"],
                            "lat": c["lat"],
                            "lng": c["lng"],
                            "intensity": self.camera_stats[c["camera_id"]]["congestion_score"],
                            "congestion_level": self.camera_stats[c["camera_id"]]["congestion_level"],
                            "avg_speed_kmh": self.camera_stats[c["camera_id"]]["avg_speed_kmh"],
                            "detections_last_min": self.camera_stats[c["camera_id"]]["detections_last_min"]
                        }
                        for c in CAMERA_NODES
                    ]
                    await self.broadcast({
                        "type": "CONGESTION_HEATMAP_UPDATE",
                        "timestamp": time.time(),
                        "heatmap": heatmap_data,
                        "camera_stats": self.camera_stats
                    })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in live traffic simulation loop: {e}")
                await asyncio.sleep(2.0)


# Global singleton manager
live_traffic_manager = LiveTrafficManager()
