"""
main.py — FastAPI application for the ANPR Trajectory Tracking prototype.

Endpoints:
    POST /simulate?count=N           Generate N fake detections & run pipeline
    GET  /trajectory/{plate}         Reconstructed trajectory for a plate
    GET  /analytics/congestion       Per-camera hourly vehicle counts
    GET  /analytics/speeds           Inter-camera average speeds
    GET  /alerts                     Flagged-vehicle matches
    GET  /detections                 Raw detection list (last batch)
    GET  /summary                    Batch summary stats

Access-control note:
    The /identity/{plate} endpoint is separated and marked as enforcement-only.
    It imports identity.py — no other endpoint does.
"""

import sys
import os

# Allow running as `python main.py` from the backend/ directory
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import json
import asyncio

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, Form, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from simulator import generate_detections
from matcher import build_trajectories, find_trajectory, normalize_plate
from analytics import (
    congestion_by_camera,
    avg_speed_between_cameras,
    check_alerts,
    batch_summary,
)
from fastapi.responses import Response, HTMLResponse
from trajectory_engine import (
    reconstruct_trajectory,
    generate_trajectory_csv,
    generate_trajectory_dossier_html,
)
from city_analytics import (
    get_traffic_heatmap,
    get_segment_speeds,
    get_route_density,
    get_comparative_trends,
    export_city_analytics_csv,
    export_city_analytics_report_html,
)
from database import (
    SessionLocal,
    DetectionRecord,
    CameraRecord,
    RoadSegmentRecord,
    BlacklistRecord,
    AlertRecord,
    AlertAuditRecord,
    AnomalyConfigRecord,
    UserRecord,
    AuthAuditRecord,
)
from camera_graph import CAMERAS, CAMERA_IDS
from alert_config import alert_config
from alert_notifier import ws_manager
from alert_engine import alert_engine
from queue_consumer import QueueConsumer

# New extensions
from auth import (
    get_current_user,
    get_optional_user,
    require_roles,
    create_access_token,
    create_refresh_token,
    decode_token,
    authenticate_user,
    log_auth_audit,
    User,
)
from live_traffic import live_traffic_manager
from video_processor import video_processor
from routing_engine import get_curved_route_geometry, DELHI_NCR_CORRIDORS

# ─── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="City-Wide ANPR Trajectory Engine & Alert System",
    description="Multi-camera ANPR trajectory tracking, city analytics, real-time alert engine, RBAC auth, live map feed, and video ANPR lab",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Prototype/Demo — restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Request Models ───────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AlertStatusUpdateRequest(BaseModel):
    status: str  # NEW, UNDER_REVIEW, CONFIRMED, DISMISSED
    reviewed_by: str = "operator"
    notes: Optional[str] = None


class BlacklistCreateRequest(BaseModel):
    plate_number: str
    reason: str
    priority: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    added_by: str = "operator"


class BlacklistUpdateRequest(BaseModel):
    reason: Optional[str] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None


class ConfigBatchUpdateRequest(BaseModel):
    updates: Dict[str, str]
    updated_by: str = "admin"


# ─── Queue Consumer Background Worker ──────────────────────────────────────────

queue_consumer = QueueConsumer(on_detection=alert_engine.process_detection)


@app.on_event("startup")
def on_startup():
    """Initialize alert engine cache and start background queue consumer."""
    alert_engine.initialize()
    queue_consumer.start()
    print("[Main] Alert engine & queue consumer initialized successfully.")


@app.on_event("shutdown")
def on_shutdown():
    """Stop background workers gracefully."""
    queue_consumer.stop()
    print("[Main] Background workers stopped.")


# ─── In-memory state ───────────────────────────────────────────────────────────

_state = {
    "detections": [],
    "trajectories": {},
    "congestion": {},
    "speeds": {},
    "alerts": [],
    "summary": {},
    "last_simulated": None,
}


# ─── Authentication & RBAC Endpoints ──────────────────────────────────────────

@app.post("/auth/login", summary="User login with JWT generation")
def login(req: LoginRequest, request: Request):
    """Authenticate user with username/password and return access & refresh tokens."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    user = authenticate_user(req.username, req.password)
    if not user:
        log_auth_audit(
            user_id=None,
            username=req.username,
            action="LOGIN_FAILED",
            resource="/auth/login",
            status="FAILURE",
            ip_address=client_ip,
            user_agent=user_agent,
            details={"reason": "Invalid credentials"}
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    access_token = create_access_token(data={"sub": user.username, "role": user.role, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.username, "role": user.role, "user_id": user.id})
    
    log_auth_audit(
        user_id=user.id,
        username=user.username,
        action="LOGIN_SUCCESS",
        resource="/auth/login",
        status="SUCCESS",
        ip_address=client_ip,
        user_agent=user_agent,
        details={"role": user.role}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in_minutes": 30,
        "user": user.to_dict()
    }


@app.post("/auth/refresh", summary="Refresh expired access token")
def refresh_token(req: RefreshTokenRequest, request: Request):
    """Generate a new access token using a valid refresh token."""
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    username = payload.get("sub")
    role = payload.get("role")
    user_id = payload.get("user_id")
    
    new_access_token = create_access_token(data={"sub": username, "role": role, "user_id": user_id})
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in_minutes": 30
    }


@app.get("/auth/me", summary="Get current authenticated user profile")
def get_me(current_user: User = Depends(get_current_user)):
    return {"user": current_user.to_dict()}


@app.post("/auth/logout", summary="Logout and log audit event")
def logout(request: Request, current_user: Optional[User] = Depends(get_optional_user)):
    if current_user:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        log_auth_audit(
            user_id=current_user.id,
            username=current_user.username,
            action="LOGOUT",
            resource="/auth/logout",
            status="SUCCESS",
            ip_address=client_ip,
            user_agent=user_agent
        )
    return {"status": "ok", "message": "Logged out successfully"}


@app.get("/auth/audit-logs", summary="Get audit logs (Admin only)")
def get_audit_logs(
    action: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: User = Depends(require_roles(["Admin"]))
):
    """Retrieve audit trail of login attempts, plate search queries, and administrative events."""
    session = SessionLocal()
    try:
        query = session.query(AuthAuditRecord)
        if action:
            query = query.filter(AuthAuditRecord.action == action.upper())
        if username:
            query = query.filter(AuthAuditRecord.username.ilike(f"%{username.strip()}%"))
        records = query.order_by(AuthAuditRecord.timestamp.desc()).limit(limit).all()
        return {"audit_logs": [r.to_dict() for r in records], "total": len(records)}
    finally:
        session.close()


# ─── Video Upload with ML-Based Plate Detection Endpoints ─────────────────────

@app.post("/video/upload", summary="Upload video for frame-by-frame ANPR inference")
async def upload_video(
    file: UploadFile = File(...),
    camera_id: str = Form("CAM-01"),
    current_user: Optional[User] = Depends(get_optional_user)
):
    """
    Accepts video file (MP4, AVI, MOV, MKV), validates minimum duration >= 10.0 seconds,
    and dispatches asynchronous frame-by-frame ANPR OCR inference.
    """
    allowed_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format '{ext}'. Allowed formats: {', '.join(allowed_exts)}"
        )

    # Save uploaded file to temp path
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_file_path = temp_file.name

    # Validate video duration >= 10.0 seconds
    is_valid, duration_or_err, fps, total_frames = video_processor.validate_video_duration(temp_file_path, min_duration_sec=10.0)
    if not is_valid:
        try:
            os.remove(temp_file_path)
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"Video rejected: {duration_or_err}. Minimum required duration is 10.0 seconds."
        )

    # Create background task
    task = video_processor.create_task(
        filename=file.filename or "uploaded_video.mp4",
        duration_sec=float(duration_or_err),
        fps=float(fps),
        total_frames=int(total_frames),
        camera_id=camera_id
    )

    # Launch asynchronous background inference worker
    asyncio.create_task(
        video_processor.process_video_task(
            task_id=task.task_id,
            video_path=temp_file_path,
            camera_id=camera_id
        )
    )

    return {
        "status": "ACCEPTED",
        "task_id": task.task_id,
        "filename": file.filename,
        "duration_seconds": round(float(duration_or_err), 2),
        "fps": round(float(fps), 1),
        "total_frames": int(total_frames),
        "camera_id": camera_id,
        "message": "Video accepted. Processing asynchronously with live progress feedback stream."
    }


@app.get("/video/status/{task_id}", summary="Get video processing task status and results")
def get_video_status(task_id: str):
    task = video_processor.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Video task not found")
    return task.to_dict()


@app.get("/video/tasks", summary="List recent video processing tasks")
def get_video_tasks():
    return {"tasks": video_processor.list_tasks()}


@app.websocket("/ws/video-process/{task_id}")
async def websocket_video_process(websocket: WebSocket, task_id: str):
    """
    Live streaming WebSocket feed for video frame-by-frame progress,
    detected plates, bounding boxes, and crop thumbnails.
    """
    await websocket.accept()
    video_processor.connect_ws(task_id, websocket)
    try:
        task = video_processor.get_task(task_id)
        if task:
            await websocket.send_text(json.dumps({
                "type": "INITIAL_STATE",
                "task": task.to_dict()
            }))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "PONG"}))
    except WebSocketDisconnect:
        video_processor.disconnect_ws(task_id, websocket)
    except Exception:
        video_processor.disconnect_ws(task_id, websocket)


# ─── Live Traffic WebSocket & Road Routing Endpoints ─────────────────────────

@app.websocket("/ws/live-traffic")
async def websocket_live_traffic_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket feed broadcasting live ANPR detections,
    pulsing camera node statuses, and dynamic congestion heatmaps.
    """
    await live_traffic_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "PONG", "timestamp": datetime.now(timezone.utc).isoformat()}))
    except WebSocketDisconnect:
        live_traffic_manager.disconnect(websocket)
    except Exception:
        live_traffic_manager.disconnect(websocket)


@app.get("/routing/corridor-path", summary="Get realistic road network geometry between camera stations")
def get_corridor_path(
    start_cam: Optional[str] = Query(default=None),
    end_cam: Optional[str] = Query(default=None),
    origin_lat: Optional[float] = Query(default=None),
    origin_lng: Optional[float] = Query(default=None),
    dest_lat: Optional[float] = Query(default=None),
    dest_lng: Optional[float] = Query(default=None),
):
    """
    Returns high-resolution road-snapped coordinates along Indian road corridors (OSM/OSRM)
    instead of straight Euclidean lines.
    """
    if start_cam:
        start_cam = start_cam.replace("-", "_")
    if end_cam:
        end_cam = end_cam.replace("-", "_")

    if start_cam and end_cam:
        c1 = CAMERAS.get(start_cam)
        c2 = CAMERAS.get(end_cam)
        if c1 and c2:
            origin_lat, origin_lng = c1["lat"], c1["lon"]
            dest_lat, dest_lng = c2["lat"], c2["lon"]

    if origin_lat is None or origin_lng is None or dest_lat is None or dest_lng is None:
        raise HTTPException(status_code=400, detail="Must provide start_cam/end_cam or coordinate pairs")

    geometry = get_curved_route_geometry(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        start_cam=start_cam,
        end_cam=end_cam,
    )
    return {
        "start_cam": start_cam,
        "end_cam": end_cam,
        "coordinates": geometry,
        "point_count": len(geometry),
    }


# ─── WebSocket Endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket feed for new ANPR alerts.
    Clients connect to receive live JSON alert events instantly as detections are processed.
    """
    await websocket.accept()
    ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "event": "CONNECTED",
            "message": "Connected to real-time ANPR alert stream",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_clients": ws_manager.connection_count,
        }))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({
                    "event": "PONG",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        ws_manager.disconnect(websocket)
        print(f"[WebSocket] Disconnected with error: {e}")


# ─── Simulation Route ──────────────────────────────────────────────────────────

@app.post("/simulate")
def simulate(count: int = Query(default=200, ge=10, le=2000)):
    """
    Generate a fresh batch of ANPR detections, run the full pipeline,
    feed into the real-time alert engine, and store results.
    """
    detections = generate_detections(count=count)
    trajectories = build_trajectories(detections)
    congestion = congestion_by_camera(detections)
    speeds = avg_speed_between_cameras(detections)
    summary = batch_summary(detections)

    # Process detections through Component 4 Alert Engine
    generated_alerts = alert_engine.process_detection_batch(detections)

    # Legacy alerts check for backward compatibility
    legacy_alerts = check_alerts(detections)

    _state["detections"] = detections
    _state["trajectories"] = trajectories
    _state["congestion"] = congestion
    _state["speeds"] = speeds
    _state["alerts"] = generated_alerts if generated_alerts else legacy_alerts
    _state["summary"] = summary
    _state["last_simulated"] = datetime.now(timezone.utc).isoformat()

    # Persist simulation records to database
    session = SessionLocal()
    try:
        for det in detections:
            cam = CAMERAS.get(det["camera_id"], {"lat": 28.6139, "lon": 77.2090})
            rec = DetectionRecord(
                plate_number=det["plate_raw"],
                raw_plate=det["plate_raw"],
                camera_id=det["camera_id"],
                timestamp=datetime.fromisoformat(det["timestamp"]),
                confidence=det["confidence"],
                lat=cam["lat"],
                lon=cam["lon"],
                vehicle_type=det.get("vehicle_type", "Car"),
            )
            session.add(rec)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Simulate DB sync error]: {e}")
    finally:
        session.close()

    return {
        "status": "ok",
        "summary": summary,
        "alert_count": len(generated_alerts),
        "alerts_generated": len(generated_alerts),
        "trajectory_count": len(trajectories),
        "last_simulated": _state["last_simulated"],
    }


@app.get("/detections")
def get_detections(limit: int = Query(default=100, ge=1, le=2000)):
    """Return the most recent detections (newest first)."""
    dets = sorted(
        _state["detections"], key=lambda d: d["timestamp"], reverse=True
    )
    return {"detections": dets[:limit], "total": len(_state["detections"])}


# ─── Component 2: Trajectory Reconstruction Engine ──────────────────────────

@app.get(
    "/trajectory",
    summary="Reconstruct historical vehicle trajectory",
    description="Query vehicle sightings with chronological ordering, burst deduplication, speed calculation, and explicit coverage gap detection."
)
def get_reconstructed_trajectory(
    request: Request,
    plate: str = Query(..., description="Target license plate number (e.g. DL01AB1234)"),
    start: Optional[str] = Query(default=None, description="Start date/time in ISO-8601 format"),
    end: Optional[str] = Query(default=None, description="End date/time in ISO-8601 format"),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
    limit: int = Query(default=50, ge=1, le=500, description="Waypoints per page"),
    gap_threshold_min: float = Query(default=30.0, ge=1.0, description="Time gap threshold in minutes"),
    deduplicate: bool = Query(default=True, description="Collapse multi-frame reads from the same camera pass"),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Component 2 Core Query Endpoint:
    Returns chronological waypoints with GPS coordinates, distance, speed,
    continuous vs gap polylines, and summary metrics.
    Logs plate search query in audit trail.
    """
    clean_plate = plate.strip().upper()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Audit log every plate search query with user ID and timestamp
    log_auth_audit(
        user_id=current_user.id if current_user else None,
        username=current_user.username if current_user else "anonymous_operator",
        action="PLATE_SEARCH",
        resource=f"/trajectory?plate={clean_plate}",
        status="SUCCESS",
        ip_address=client_ip,
        user_agent=user_agent,
        details={"plate_number": clean_plate, "user_role": current_user.role if current_user else "Public/Operator"}
    )

    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    result = reconstruct_trajectory(
        plate=clean_plate,
        start=start_dt,
        end=end_dt,
        min_confidence=min_confidence,
        page=page,
        limit=limit,
        deduplicate=deduplicate,
        gap_time_threshold_minutes=gap_threshold_min,
    )
    return result


@app.get("/trajectory/export/csv", summary="Export trajectory to CSV")
def export_trajectory_csv(
    plate: str = Query(..., description="Target license plate number"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
):
    """Generate and stream RFC 4180 CSV file of vehicle movement history."""
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    data = reconstruct_trajectory(
        plate=plate,
        start=start_dt,
        end=end_dt,
        min_confidence=min_confidence,
        limit=2000,
    )

    csv_content = generate_trajectory_csv(data)
    filename = f"trajectory_{plate.strip().upper()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/trajectory/export/pdf", summary="Export Law Enforcement Movement Dossier")
def export_trajectory_pdf(
    plate: str = Query(..., description="Target license plate number"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
):
    """Generate formal Law Enforcement Sighting Dossier in printable HTML/PDF format."""
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    data = reconstruct_trajectory(
        plate=plate,
        start=start_dt,
        end=end_dt,
        min_confidence=min_confidence,
        limit=2000,
    )

    html_content = generate_trajectory_dossier_html(data)
    return HTMLResponse(content=html_content)


@app.get("/trajectory/{plate}")
def get_trajectory_legacy(plate: str):
    """Legacy route: Redirects to reconstruct_trajectory."""
    return reconstruct_trajectory(plate=plate)


@app.get("/analytics/congestion")
def get_congestion():
    """Return per-camera hourly vehicle counts and peak congestion data."""
    if not _state["congestion"]:
        raise HTTPException(
            status_code=404,
            detail="No data. Call POST /simulate first.",
        )
    return {
        "congestion": _state["congestion"],
        "cameras": CAMERAS,
    }


@app.get("/analytics/speeds")
def get_speeds():
    """Return estimated average speeds between camera pairs."""
    if not _state["speeds"]:
        raise HTTPException(
            status_code=404,
            detail="No data. Call POST /simulate first.",
        )
    return {"speeds": _state["speeds"]}


# ─── Component 3: City Traffic Analytics Dashboard Endpoints ─────────────────

@app.get("/analytics/heatmap", summary="Query GIS traffic density heatmap data")
def api_get_heatmap(
    date: Optional[str] = Query(default=None, description="Date in YYYY-MM-DD format"),
    hour_range: Optional[str] = Query(default="all", description="Hour window ('all', 'morning', 'evening', 'night', or 'HH-HH')"),
    zone: Optional[str] = Query(default=None, description="Zone/District filter"),
):
    """
    Returns pre-aggregated camera node densities and online/offline status.
    Explicitly distinguishes camera offline outages from zero traffic.
    """
    return get_traffic_heatmap(date_str=date, hour_range=hour_range, zone=zone)


@app.get("/analytics/speed", summary="Average vehicle speed per road segment")
def api_get_segment_speeds(
    segment_id: Optional[str] = Query(default=None, description="Specific road segment ID (e.g. SEG_01)"),
    date: Optional[str] = Query(default=None, description="Date in YYYY-MM-DD format"),
    hour_range: Optional[str] = Query(default="all", description="Hour window ('all', 'morning', 'evening', etc.)"),
    zone: Optional[str] = Query(default=None, description="Zone filter"),
):
    """
    Returns road corridors with geometry, speed limit, average speed, and congestion classification.
    """
    return get_segment_speeds(date_str=date, hour_range=hour_range, zone=zone, segment_id=segment_id)


@app.get("/analytics/density", summary="Corridor volume rankings and capacity density")
def api_get_route_density(
    zone: Optional[str] = Query(default=None, description="Zone filter"),
    period: Optional[str] = Query(default="today", description="Period ('today' or 'last_week')"),
):
    """
    Returns ranked traffic corridors carrying highest traffic volume with capacity utilization.
    """
    return get_route_density(zone=zone, period=period)


@app.get("/analytics/trends", summary="Comparative 24-hour traffic flow trends")
def api_get_traffic_trends(
    compare: str = Query(default="today_vs_last_week", description="Comparison mode ('today_vs_last_week')"),
    metric: str = Query(default="volume", description="Metric to compare ('volume' or 'speed')"),
):
    """
    Returns 24-hour comparative trend series between current and prior period.
    """
    return get_comparative_trends(compare=compare, metric=metric)


@app.get("/analytics/export/csv", summary="Export city traffic analytics to CSV")
def api_export_analytics_csv(
    date: Optional[str] = Query(default=None),
    hour_range: Optional[str] = Query(default="all"),
    zone: Optional[str] = Query(default=None),
):
    """Generate and stream RFC 4180 CSV export of aggregated city traffic analytics."""
    heatmap_data = get_traffic_heatmap(date_str=date, hour_range=hour_range, zone=zone)
    speeds_data = get_segment_speeds(date_str=date, hour_range=hour_range, zone=zone)
    density_data = get_route_density(zone=zone)

    csv_content = export_city_analytics_csv(heatmap_data, speeds_data, density_data)
    filename = f"city_traffic_analytics_{date or 'today'}_{hour_range}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/analytics/export/pdf", summary="Export City Traffic Intelligence Report")
def api_export_analytics_pdf(
    date: Optional[str] = Query(default=None),
    hour_range: Optional[str] = Query(default="all"),
    zone: Optional[str] = Query(default=None),
):
    """Generate printable HTML report for City Planners and Police Command."""
    heatmap_data = get_traffic_heatmap(date_str=date, hour_range=hour_range, zone=zone)
    speeds_data = get_segment_speeds(date_str=date, hour_range=hour_range, zone=zone)
    density_data = get_route_density(zone=zone)
    trends_data = get_comparative_trends()

    html_content = export_city_analytics_report_html(heatmap_data, speeds_data, density_data, trends_data)
    return HTMLResponse(content=html_content)


from datetime import timedelta

# ─── Component 4: Real-Time Alert System Endpoints ───────────────────────────

@app.get("/alerts", summary="Query alerts with filtering and pagination")
def get_alerts(
    status: Optional[str] = Query(default=None, description="Filter by status (NEW, UNDER_REVIEW, CONFIRMED, DISMISSED, or ALL)"),
    alert_type: Optional[str] = Query(default=None, description="Filter by alert type"),
    priority: Optional[str] = Query(default=None, description="Filter by priority (CRITICAL, HIGH, MEDIUM, LOW)"),
    plate: Optional[str] = Query(default=None, description="Filter by plate number"),
    date_from: Optional[str] = Query(default=None, description="Start date/time in ISO-8601 format"),
    date_to: Optional[str] = Query(default=None, description="End date/time in ISO-8601 format"),
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=50, ge=1, le=500, description="Items per page"),
):
    """
    Component 4 Alert Query Endpoint:
    Returns paginated alerts from database with multi-dimensional filtering.
    """
    session = SessionLocal()
    try:
        query = session.query(AlertRecord)

        if status and status.upper() != "ALL":
            query = query.filter(AlertRecord.status == status.upper())
        if alert_type and alert_type.upper() != "ALL":
            query = query.filter(AlertRecord.alert_type == alert_type.upper())
        if priority and priority.upper() != "ALL":
            query = query.filter(AlertRecord.priority == priority.upper())
        if plate:
            query = query.filter(AlertRecord.plate_number.ilike(f"%{plate.strip()}%"))
        if date_from:
            try:
                dt_from = datetime.fromisoformat(date_from)
                query = query.filter(AlertRecord.timestamp >= dt_from)
            except Exception:
                pass
        if date_to:
            try:
                dt_to = datetime.fromisoformat(date_to)
                query = query.filter(AlertRecord.timestamp <= dt_to)
            except Exception:
                pass

        total = query.count()
        records = (
            query.order_by(AlertRecord.timestamp.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        alerts_list = [r.to_dict() for r in records]

        # Fallback if DB is empty but in-memory state has alerts
        if not alerts_list and _state.get("alerts") and not plate and not status and not alert_type:
            alerts_list = _state["alerts"][:limit]
            total = len(_state["alerts"])

        return {
            "alerts": alerts_list,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
            "count": len(alerts_list),
            "last_simulated": _state.get("last_simulated"),
        }
    except Exception as e:
        print(f"[Alerts API Error]: {e}")
        return {
            "alerts": _state.get("alerts", [])[:limit],
            "total": len(_state.get("alerts", [])),
            "page": page,
            "limit": limit,
            "total_pages": 1,
            "count": len(_state.get("alerts", [])),
            "last_simulated": _state.get("last_simulated"),
        }
    finally:
        session.close()


@app.get("/alerts/stats", summary="Alert summary statistics and KPI metrics")
def get_alert_stats():
    """
    Returns aggregate stats for the alert dashboard:
    - Counts by status (NEW, UNDER_REVIEW, CONFIRMED, DISMISSED)
    - Counts by alert_type
    - Counts by priority
    - Alert volume in last hour and today
    """
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total = session.query(AlertRecord).count()
        new_count = session.query(AlertRecord).filter_by(status="NEW").count()
        under_review_count = session.query(AlertRecord).filter_by(status="UNDER_REVIEW").count()
        confirmed_count = session.query(AlertRecord).filter_by(status="CONFIRMED").count()
        dismissed_count = session.query(AlertRecord).filter_by(status="DISMISSED").count()

        last_hour_count = session.query(AlertRecord).filter(AlertRecord.timestamp >= one_hour_ago).count()
        today_count = session.query(AlertRecord).filter(AlertRecord.timestamp >= today_start).count()

        # Priority breakdown
        critical_count = session.query(AlertRecord).filter_by(priority="CRITICAL").count()
        high_count = session.query(AlertRecord).filter_by(priority="HIGH").count()
        medium_count = session.query(AlertRecord).filter_by(priority="MEDIUM").count()
        low_count = session.query(AlertRecord).filter_by(priority="LOW").count()

        # Type breakdown
        blacklist_hits = session.query(AlertRecord).filter_by(alert_type="BLACKLIST_HIT").count()
        possible_matches = session.query(AlertRecord).filter_by(alert_type="POSSIBLE_MATCH").count()
        loitering_count = session.query(AlertRecord).filter_by(alert_type="LOITERING").count()
        wrong_way_count = session.query(AlertRecord).filter_by(alert_type="WRONG_WAY").count()
        speed_count = session.query(AlertRecord).filter_by(alert_type="SPEED_ANOMALY").count()
        restricted_count = session.query(AlertRecord).filter_by(alert_type="RESTRICTED_ZONE").count()

        blacklist_total = session.query(BlacklistRecord).filter_by(is_active=True).count()

        return {
            "status_counts": {
                "NEW": new_count,
                "UNDER_REVIEW": under_review_count,
                "CONFIRMED": confirmed_count,
                "DISMISSED": dismissed_count,
                "TOTAL": total,
            },
            "priority_counts": {
                "CRITICAL": critical_count,
                "HIGH": high_count,
                "MEDIUM": medium_count,
                "LOW": low_count,
            },
            "type_counts": {
                "BLACKLIST_HIT": blacklist_hits,
                "POSSIBLE_MATCH": possible_matches,
                "LOITERING": loitering_count,
                "WRONG_WAY": wrong_way_count,
                "SPEED_ANOMALY": speed_count,
                "RESTRICTED_ZONE": restricted_count,
            },
            "time_metrics": {
                "last_hour": last_hour_count,
                "today": today_count,
            },
            "active_blacklist_count": blacklist_total,
            "engine_stats": alert_engine.get_stats(),
        }
    except Exception as e:
        print(f"[Alert Stats Error]: {e}")
        return {
            "status_counts": {"NEW": 0, "UNDER_REVIEW": 0, "CONFIRMED": 0, "DISMISSED": 0, "TOTAL": 0},
            "priority_counts": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
            "type_counts": {"BLACKLIST_HIT": 0, "POSSIBLE_MATCH": 0, "LOITERING": 0, "WRONG_WAY": 0, "SPEED_ANOMALY": 0, "RESTRICTED_ZONE": 0},
            "time_metrics": {"last_hour": 0, "today": 0},
            "active_blacklist_count": 0,
            "engine_stats": alert_engine.get_stats(),
        }
    finally:
        session.close()


@app.get("/alerts/{alert_id}", summary="Get full alert detail and audit trail")
def get_alert_detail(alert_id: str):
    session = SessionLocal()
    try:
        record = session.query(AlertRecord).filter_by(id=alert_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Alert not found")
        return record.to_dict(include_audit=True)
    finally:
        session.close()


@app.post("/alerts/{alert_id}/status", summary="Update alert workflow status with audit logging")
def update_alert_status(alert_id: str, req: AlertStatusUpdateRequest):
    valid_statuses = {"NEW", "UNDER_REVIEW", "CONFIRMED", "DISMISSED"}
    target_status = req.status.upper()
    if target_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{req.status}'. Must be one of {valid_statuses}",
        )

    session = SessionLocal()
    try:
        alert = session.query(AlertRecord).filter_by(id=alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        old_status = alert.status
        alert.status = target_status

        # Create audit record
        audit = AlertAuditRecord(
            alert_id=alert_id,
            action="STATUS_CHANGE",
            old_status=old_status,
            new_status=target_status,
            reviewed_by=req.reviewed_by,
            reviewed_at=datetime.now(timezone.utc),
            notes=req.notes,
        )
        session.add(audit)
        session.commit()

        # Broadcast status change via WebSocket
        ws_manager.broadcast_sync({
            "event": "ALERT_STATUS_UPDATED",
            "alert_id": alert_id,
            "old_status": old_status,
            "new_status": target_status,
            "reviewed_by": req.reviewed_by,
            "notes": req.notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return alert.to_dict(include_audit=True)
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update alert: {e}")
    finally:
        session.close()


@app.get("/alerts/{alert_id}/audit", summary="Get audit trail for an alert")
def get_alert_audit_trail(alert_id: str):
    session = SessionLocal()
    try:
        records = (
            session.query(AlertAuditRecord)
            .filter_by(alert_id=alert_id)
            .order_by(AlertAuditRecord.reviewed_at.desc())
            .all()
        )
        return {"alert_id": alert_id, "audit_trail": [r.to_dict() for r in records]}
    finally:
        session.close()


# ─── Blacklist Management Endpoints ──────────────────────────────────────────

@app.get("/blacklist", summary="List all blacklisted plates")
def get_blacklist(
    is_active: Optional[bool] = Query(default=True),
    priority: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
):
    session = SessionLocal()
    try:
        query = session.query(BlacklistRecord)
        if is_active is not None:
            query = query.filter(BlacklistRecord.is_active == is_active)
        if priority and priority.upper() != "ALL":
            query = query.filter(BlacklistRecord.priority == priority.upper())
        if search:
            query = query.filter(
                (BlacklistRecord.plate_number.ilike(f"%{search.strip()}%")) |
                (BlacklistRecord.reason.ilike(f"%{search.strip()}%"))
            )
        records = query.order_by(BlacklistRecord.date_added.desc()).all()
        return {"blacklist": [r.to_dict() for r in records], "total": len(records)}
    finally:
        session.close()


@app.post("/blacklist", summary="Add vehicle plate to blacklist")
def add_to_blacklist(req: BlacklistCreateRequest):
    plate_clean = req.plate_number.strip().upper()
    normalized = normalize_plate(plate_clean)
    if not plate_clean:
        raise HTTPException(status_code=400, detail="Plate number cannot be empty")

    session = SessionLocal()
    try:
        existing = session.query(BlacklistRecord).filter_by(normalized_plate=normalized).first()
        if existing:
            if existing.is_active:
                raise HTTPException(status_code=409, detail=f"Plate {plate_clean} is already on active blacklist")
            else:
                # Re-activate
                existing.is_active = True
                existing.reason = req.reason
                existing.priority = req.priority.upper()
                existing.added_by = req.added_by
                existing.date_added = datetime.now(timezone.utc)
                session.commit()
                alert_engine.blacklist_cache.refresh()
                return existing.to_dict()

        record = BlacklistRecord(
            plate_number=plate_clean,
            normalized_plate=normalized,
            reason=req.reason,
            priority=req.priority.upper(),
            added_by=req.added_by,
            date_added=datetime.now(timezone.utc),
            is_active=True,
        )
        session.add(record)
        session.commit()

        # Invalidate / refresh alert engine in-memory cache
        alert_engine.blacklist_cache.refresh()

        return record.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to add plate to blacklist: {e}")
    finally:
        session.close()


@app.put("/blacklist/{plate}", summary="Update blacklist entry")
def update_blacklist_entry(plate: str, req: BlacklistUpdateRequest):
    normalized = normalize_plate(plate)
    session = SessionLocal()
    try:
        record = session.query(BlacklistRecord).filter_by(normalized_plate=normalized).first()
        if not record:
            raise HTTPException(status_code=404, detail="Blacklist entry not found")

        if req.reason is not None:
            record.reason = req.reason
        if req.priority is not None:
            record.priority = req.priority.upper()
        if req.is_active is not None:
            record.is_active = req.is_active

        session.commit()
        alert_engine.blacklist_cache.refresh()
        return record.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update blacklist entry: {e}")
    finally:
        session.close()


@app.delete("/blacklist/{plate}", summary="Remove vehicle plate from blacklist")
def remove_from_blacklist(plate: str):
    normalized = normalize_plate(plate)
    session = SessionLocal()
    try:
        record = session.query(BlacklistRecord).filter_by(normalized_plate=normalized).first()
        if not record:
            raise HTTPException(status_code=404, detail="Blacklist entry not found")

        record.is_active = False
        session.commit()
        alert_engine.blacklist_cache.refresh()
        return {"status": "ok", "message": f"Plate {plate} deactivated from blacklist", "plate": plate}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to remove from blacklist: {e}")
    finally:
        session.close()


# ─── Alert Configuration Endpoints ───────────────────────────────────────────

@app.get("/alerts/config", summary="Get all anomaly detection configuration thresholds")
def get_alert_configs():
    return {"configs": alert_config.get_all()}


@app.put("/alerts/config", summary="Update anomaly detection configuration thresholds")
def update_alert_configs(req: ConfigBatchUpdateRequest):
    count = alert_config.update_batch(req.updates, updated_by=req.updated_by)
    return {"status": "ok", "updated_count": count, "configs": alert_config.get_all()}


@app.get("/alerts/queue-status", summary="Get message queue consumer status")
def get_queue_status():
    return queue_consumer.status


@app.get("/summary")
def get_summary():
    """Return batch summary statistics."""
    return _state["summary"] or {"message": "No simulation run yet."}


@app.get("/cameras")
def get_cameras():
    """Return the camera network definition."""
    return {"cameras": CAMERAS}


# ─── Enforcement-only endpoint (identity module) ───────────────────────────────

@app.get(
    "/enforcement/identity/{plate}",
    summary="[ENFORCEMENT ONLY] Vehicle identity lookup",
    description=(
        "Returns owner and registration details for a plate. "
        "Protected by RBAC: Admin and Traffic Police only. "
        "All queries logged to audit trail."
    ),
    tags=["Enforcement"],
)
def get_identity(
    plate: str,
    request: Request,
    current_user: User = Depends(require_roles(["Admin", "Traffic Police"]))
):
    """
    Enforcement-only: look up owner details for a plate number.
    Intentionally isolated — only this endpoint touches identity data.
    """
    # Late import — only this endpoint touches identity data
    from identity import get_vehicle_info, is_wanted

    clean_plate = plate.strip().upper()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Audit log
    log_auth_audit(
        user_id=current_user.id,
        username=current_user.username,
        action="IDENTITY_LOOKUP",
        resource=f"/enforcement/identity/{clean_plate}",
        status="SUCCESS",
        ip_address=client_ip,
        user_agent=user_agent,
        details={"plate_number": clean_plate, "user_role": current_user.role}
    )

    info = get_vehicle_info(clean_plate)
    if info is None:
        raise HTTPException(status_code=400, detail="Invalid plate input.")
    return {
        "plate": clean_plate,
        "is_wanted": is_wanted(clean_plate),
        "identity": info,
        "queried_by": current_user.username,
        "role": current_user.role,
        "access_note": (
            "This data is visible to enforcement personnel only. "
            "City Planner role accounts cannot access this endpoint."
        ),
    }


# ─── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "prototype": "ANPR Trajectory Engine v0.1"}


# ─── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
