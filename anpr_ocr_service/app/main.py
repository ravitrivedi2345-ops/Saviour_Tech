"""
main.py — FastAPI Application for Standalone High-Precision ANPR OCR Service.

Component 1 of City Traffic Monitoring Platform.
Provides REST endpoints for single-frame detection, batch processing, video scanning,
database querying, and metrics inspection.
"""

import base64
import io
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import settings
from app.pipeline import ANPRPipeline
from app.database import save_detection, query_detections
from app.queue_publisher import publisher
from app.logger import audit_logger

app = FastAPI(
    title="ANPR High-Precision OCR Service",
    description="Component 1: Two-stage plate detection (YOLOv8) and character recognition (CRNN).",
    version=settings.SERVICE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline instance
pipeline = ANPRPipeline()

# In-memory metrics tracking
metrics_store = {
    "total_inferences": 0,
    "total_plates_detected": 0,
    "review_flagged_count": 0,
    "latencies_ms": [],
    "start_time": time.time(),
}


# ─── Pydantic Schemas ──────────────────────────────────────────────────────────

class Base64ImageRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image string")
    camera_id: str = Field(default="CAM_01", description="Camera sensor identifier")
    timestamp: Optional[str] = Field(default=None, description="ISO-8601 sighting timestamp")
    metadata_hint: Optional[str] = Field(default=None, description="Optional ground truth hint for testing")


class DetectionResponse(BaseModel):
    plate: str
    raw_plate: str
    confidence: float
    timestamp: str
    camera_id: str
    bbox: List[int]
    is_format_valid: bool
    needs_review: bool
    review_reasons: List[str]
    latency_ms: float
    stage_latencies: Dict[str, float]


class PipelineResponse(BaseModel):
    status: str
    camera_id: str
    timestamp: str
    plate_count: int
    detections: List[DetectionResponse]
    total_latency_ms: float


# ─── Helpers ───────────────────────────────────────────────────────────────────

def decode_image_bytes(file_bytes: bytes) -> np.ndarray:
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image encoding. Could not decode frame.")
    return img


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def health_check():
    """Verify hardware acceleration and subsystem connectivity."""
    has_cuda = False
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except ImportError:
        pass

    uptime_seconds = round(time.time() - metrics_store["start_time"], 1)

    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "device_configured": settings.DEVICE,
        "cuda_available": has_cuda,
        "inference_engine": "CUDA" if has_cuda else "CPU (Fallback)",
        "queue_broker": settings.QUEUE_TYPE,
        "queue_connected": publisher.is_connected,
        "uptime_seconds": uptime_seconds,
    }


@app.post("/api/v1/detect/image", response_model=PipelineResponse)
async def detect_image(
    file: Optional[UploadFile] = File(None),
    camera_id: str = Form("CAM_01"),
    timestamp: Optional[str] = Form(None),
    metadata_hint: Optional[str] = Form(None),
):
    """
    Process a single frame uploaded as multipart/form-data.
    Executes YOLOv8 detection + CRNN recognition + format validation,
    persists in PostgreSQL, and pushes event to RabbitMQ/Kafka queue.
    """
    if file is None:
        raise HTTPException(status_code=400, detail="File must be provided.")

    file_bytes = await file.read()
    image = decode_image_bytes(file_bytes)

    t_start = time.perf_counter()
    ts = timestamp or datetime.now(timezone.utc).isoformat()

    detections = pipeline.process_frame(
        image=image,
        camera_id=camera_id,
        timestamp=ts,
        metadata_hint=metadata_hint,
    )

    total_latency = (time.perf_counter() - t_start) * 1000.0

    # Persist and publish each detection
    for det in detections:
        # Save to database
        try:
            save_detection(det, image_uri=file.filename)
        except Exception as e:
            print(f"[API] DB Save warning: {e}")

        # Publish to event queue
        publisher.publish_detection(det)

        # Audit log for retraining
        audit_logger.log_inference(image, det, camera_id=camera_id, image_name=file.filename)

        # Update metrics
        metrics_store["total_plates_detected"] += 1
        if det.get("needs_review"):
            metrics_store["review_flagged_count"] += 1

    metrics_store["total_inferences"] += 1
    metrics_store["latencies_ms"].append(total_latency)
    if len(metrics_store["latencies_ms"]) > 1000:
        metrics_store["latencies_ms"].pop(0)

    return {
        "status": "success",
        "camera_id": camera_id,
        "timestamp": ts,
        "plate_count": len(detections),
        "detections": detections,
        "total_latency_ms": round(total_latency, 2),
    }


@app.post("/api/v1/detect/base64", response_model=PipelineResponse)
def detect_base64(payload: Base64ImageRequest):
    """Process a single frame provided as a base64 string."""
    try:
        img_data = base64.b64decode(payload.image_base64)
        image = decode_image_bytes(img_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to decode base64: {e}")

    t_start = time.perf_counter()
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()

    detections = pipeline.process_frame(
        image=image,
        camera_id=payload.camera_id,
        timestamp=ts,
        metadata_hint=payload.metadata_hint,
    )

    total_latency = (time.perf_counter() - t_start) * 1000.0

    for det in detections:
        try:
            save_detection(det)
        except Exception as e:
            print(f"[API] DB Save warning: {e}")
        publisher.publish_detection(det)
        audit_logger.log_inference(image, det, camera_id=payload.camera_id)
        metrics_store["total_plates_detected"] += 1
        if det.get("needs_review"):
            metrics_store["review_flagged_count"] += 1

    metrics_store["total_inferences"] += 1
    metrics_store["latencies_ms"].append(total_latency)

    return {
        "status": "success",
        "camera_id": payload.camera_id,
        "timestamp": ts,
        "plate_count": len(detections),
        "detections": detections,
        "total_latency_ms": round(total_latency, 2),
    }


@app.post("/api/v1/detect/batch")
async def detect_batch(
    files: List[UploadFile] = File(...),
    camera_ids: Optional[str] = Form(None),
):
    """
    Batch process multiple frames concurrently (e.g. 20 concurrent camera feeds).
    camera_ids: comma-separated list of camera IDs matching file count.
    """
    cams = camera_ids.split(",") if camera_ids else ["CAM_BATCH"] * len(files)
    results = []
    t_start = time.perf_counter()

    for idx, f in enumerate(files):
        cid = cams[idx].strip() if idx < len(cams) else "CAM_BATCH"
        file_bytes = await f.read()
        image = decode_image_bytes(file_bytes)
        dets = pipeline.process_frame(image=image, camera_id=cid)
        for d in dets:
            save_detection(d)
            publisher.publish_detection(d)
        results.append({"filename": f.filename, "camera_id": cid, "detections": dets})

    total_time = (time.perf_counter() - t_start) * 1000.0
    fps = (len(files) / (total_time / 1000.0)) if total_time > 0 else 0.0

    return {
        "batch_size": len(files),
        "total_latency_ms": round(total_time, 2),
        "throughput_fps": round(fps, 1),
        "results": results,
    }


@app.get("/api/v1/detections")
def get_detections(
    camera_id: Optional[str] = Query(None, description="Filter by camera sensor"),
    plate_number: Optional[str] = Query(None, description="Search plate number substring"),
    needs_review: Optional[bool] = Query(None, description="Filter items flagged for review"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query indexed plate detections stored in database."""
    records = query_detections(
        camera_id=camera_id,
        plate_number=plate_number,
        needs_review=needs_review,
        limit=limit,
    )
    return {"count": len(records), "detections": records}


@app.get("/api/v1/queue/events")
def get_queue_events(limit: int = Query(20, ge=1, le=100)):
    """Inspect recent published detection messages buffered for downstream consumer."""
    events = publisher.get_buffered_events(limit=limit)
    return {"count": len(events), "events": events}


@app.get("/api/v1/metrics")
def get_metrics():
    """Operational metrics: inference throughput, review rates, and latency stats."""
    latencies = metrics_store["latencies_ms"]
    avg_latency = float(np.mean(latencies)) if latencies else 0.0
    p95_latency = float(np.percentile(latencies, 95)) if latencies else 0.0

    tot_plates = metrics_store["total_plates_detected"]
    review_pct = (metrics_store["review_flagged_count"] / tot_plates * 100) if tot_plates > 0 else 0.0

    return {
        "total_inferences": metrics_store["total_inferences"],
        "total_plates_detected": tot_plates,
        "review_flagged_count": metrics_store["review_flagged_count"],
        "review_rate_percentage": round(review_pct, 2),
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "target_concurrency": settings.MAX_CONCURRENT_STREAMS,
        "target_stream_fps": settings.TARGET_STREAM_FPS,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
