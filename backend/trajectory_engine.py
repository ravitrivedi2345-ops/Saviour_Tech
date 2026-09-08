"""
trajectory_engine.py — High-Precision Trajectory Reconstruction Engine (Component 2).

Reconstructs historical vehicle trajectories from ANPR detection records with:
- Temporal and confidence filtering
- Near-simultaneous burst frame deduplication (e.g. multiple camera hits within 60s)
- Chronological physics computation (distance, time delta, speed in km/h)
- Explicit gap identification (coverage gaps > 30 mins or speed anomalies > 100 km/h)
- Dual segment emission (continuous vs dashed gaps for map rendering)
- Pagination support
- CSV export & Law Enforcement Movement Dossier generation
"""

import io
import csv
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from database import SessionLocal, DetectionRecord, CameraRecord
from camera_graph import CAMERAS, camera_distance_km
from matcher import normalize_plate, levenshtein
from routing_engine import get_road_segment_geometry


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight line distance between two coordinates on Earth."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def format_duration(seconds: float) -> str:
    """Format seconds into readable human string."""
    seconds = max(0, int(seconds))
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs}h {mins}m"
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def reconstruct_trajectory(
    plate: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    min_confidence: float = 0.0,
    page: int = 1,
    limit: int = 50,
    deduplicate: bool = True,
    dedup_window_seconds: int = 60,
    gap_time_threshold_minutes: float = 30.0,
    max_speed_kmph: float = 100.0,
    db: Optional[Session] = None,
) -> Dict:
    """
    Reconstruct vehicle trajectory for a license plate number.
    """
    session = db or SessionLocal()
    try:
        clean_plate = plate.strip().upper().replace(" ", "").replace("-", "")
        canon_clean = normalize_plate(clean_plate)

        # 1. Query all detection records from database
        query = session.query(DetectionRecord).join(CameraRecord)

        # Time range filter
        if start:
            query = query.filter(DetectionRecord.timestamp >= start)
        if end:
            query = query.filter(DetectionRecord.timestamp <= end)

        # Confidence filter
        if min_confidence > 0.0:
            query = query.filter(DetectionRecord.confidence >= min_confidence)

        records = query.order_by(DetectionRecord.timestamp.asc()).all()

        # Fuzzy match to plate (exact or canonical or edit distance <= 2)
        matched_records = []
        for r in records:
            r_canon = normalize_plate(r.plate_number)
            if r.plate_number == clean_plate or r_canon == canon_clean or levenshtein(r_canon, canon_clean) <= 2:
                matched_records.append(r)

        raw_count = len(matched_records)
        if raw_count == 0:
            return {
                "plate_number": clean_plate,
                "found": False,
                "total_detections_raw": 0,
                "total_waypoints": 0,
                "summary": None,
                "waypoints": [],
                "all_waypoints": [],
                "segments": [],
                "pagination": {"page": page, "limit": limit, "total": 0, "total_pages": 0},
            }

        # 2. Burst Frame Deduplication
        # When a car drives past a camera, it may trigger multiple frame reads within ~30-60s.
        deduped = []
        if deduplicate:
            current_burst = [matched_records[0]]
            for r in matched_records[1:]:
                prev = current_burst[-1]
                dt = (r.timestamp - prev.timestamp).total_seconds()
                if r.camera_id == prev.camera_id and dt <= dedup_window_seconds:
                    current_burst.append(r)
                else:
                    # Pick the detection with the highest confidence from current burst
                    best = max(current_burst, key=lambda d: d.confidence)
                    best_dict = best.to_dict()
                    best_dict["burst_count"] = len(current_burst)
                    deduped.append(best_dict)
                    current_burst = [r]
            if current_burst:
                best = max(current_burst, key=lambda d: d.confidence)
                best_dict = best.to_dict()
                best_dict["burst_count"] = len(current_burst)
                deduped.append(best_dict)
        else:
            for r in matched_records:
                d = r.to_dict()
                d["burst_count"] = 1
                deduped.append(d)

        # 3. Physics & Chronological Gap Analysis
        waypoints = []
        segments = []
        current_continuous_points = []
        current_continuous_stops = []
        current_road_polyline = []

        total_distance_km = 0.0
        gap_count = 0
        speed_sum = 0.0
        speed_count = 0

        for i, pt in enumerate(deduped):
            wp = dict(pt)
            wp["sequence"] = i + 1

            if i == 0:
                wp["distance_km"] = 0.0
                wp["time_delta_seconds"] = 0.0
                wp["speed_kmph"] = 0.0
                wp["is_gap"] = False
                wp["gap_reason"] = None
                wp["formatted_delta"] = "Departure"
                current_continuous_points.append([wp["lat"], wp["lon"]])
                current_continuous_stops.append(wp)
                current_road_polyline.append([wp["lat"], wp["lon"]])
            else:
                prev = deduped[i - 1]
                dist = haversine_km(prev["lat"], prev["lon"], wp["lat"], wp["lon"])
                t_prev = datetime.fromisoformat(prev["timestamp"])
                t_curr = datetime.fromisoformat(wp["timestamp"])
                delta_sec = max(1.0, (t_curr - t_prev).total_seconds())
                speed = round((dist / delta_sec) * 3600.0, 1)

                is_gap = False
                gap_reason = None

                # Check 1: Large time gap (> threshold minutes)
                gap_threshold_sec = gap_time_threshold_minutes * 60.0
                if delta_sec > gap_threshold_sec:
                    is_gap = True
                    gap_reason = f"Coverage Gap: {format_duration(delta_sec)} unobserved transit (missing camera coverage or vehicle stopped)"
                # Check 2: Physical impossibility (> max speed km/h)
                elif speed > max_speed_kmph and dist > 0.5:
                    is_gap = True
                    gap_reason = f"Speed Anomaly: Implied speed {speed} km/h exceeds city limits (potential cloned plate or sensor anomaly)"

                dist = camera_distance_km(prev["camera_id"], wp["camera_id"])
                if dist is None:
                    dist = haversine_km(prev["lat"], prev["lon"], wp["lat"], wp["lon"])

                speed = round((dist / (delta_sec / 3600.0)), 1)

                wp["distance_km"] = round(dist, 2)
                wp["time_delta_seconds"] = round(delta_sec, 1)
                wp["speed_kmph"] = speed

                # 3. Gap & Anomaly Check
                delta_minutes = delta_sec / 60.0
                is_time_gap = delta_minutes > gap_time_threshold_minutes
                is_speed_anomaly = (speed > max_speed_kmph) and (prev["camera_id"] != wp["camera_id"])

                if is_time_gap or is_speed_anomaly:
                    wp["is_gap"] = True
                    gap_count += 1
                    gap_reason = (
                        f"Coverage Gap: {format_duration(delta_sec)} unobserved transit ({round(delta_minutes, 1)} mins > {gap_time_threshold_minutes} min threshold)"
                        if is_time_gap
                        else f"Speed Anomaly: Implied speed {speed} km/h exceeds city limits ({max_speed_kmph} km/h threshold)"
                    )
                    wp["gap_reason"] = gap_reason

                    # Close out current continuous segment
                    if len(current_continuous_points) >= 1:
                        segments.append({
                            "type": "continuous",
                            "coordinates": list(current_road_polyline) if current_road_polyline else list(current_continuous_points),
                            "stops": list(current_continuous_stops),
                        })
                        current_continuous_points = []
                        current_continuous_stops = []
                        current_road_polyline = []

                    # Add explicit gap segment
                    segments.append({
                        "type": "gap",
                        "coordinates": [[prev["lat"], prev["lon"]], [wp["lat"], wp["lon"]]],
                        "from_stop": prev["camera_name"],
                        "to_stop": wp["camera_name"],
                        "gap_duration": format_duration(delta_sec),
                        "distance_km": round(dist, 2),
                        "implied_speed_kmph": speed,
                        "reason": gap_reason,
                    })

                    current_continuous_points.append([wp["lat"], wp["lon"]])
                    current_continuous_stops.append(wp)
                    current_road_polyline.append([wp["lat"], wp["lon"]])
                else:
                    total_distance_km += dist
                    speed_sum += speed
                    speed_count += 1
                    current_continuous_points.append([wp["lat"], wp["lon"]])
                    current_continuous_stops.append(wp)
                    
                    # Road-snapped geometry connection
                    road_pts = get_road_segment_geometry(prev["camera_id"], wp["camera_id"])
                    if road_pts:
                        current_road_polyline.extend(road_pts[1:] if current_road_polyline else road_pts)
                    else:
                        current_road_polyline.append([wp["lat"], wp["lon"]])

            waypoints.append(wp)

        # Final continuous segment
        if len(current_continuous_points) >= 1:
            segments.append({
                "type": "continuous",
                "coordinates": list(current_road_polyline) if current_road_polyline else list(current_continuous_points),
                "stops": list(current_continuous_stops),
            })

        # Summary Metrics
        first_time = datetime.fromisoformat(waypoints[0]["timestamp"])
        last_time = datetime.fromisoformat(waypoints[-1]["timestamp"])
        total_duration = (last_time - first_time).total_seconds()
        avg_speed = round(speed_sum / max(1, speed_count), 1)

        summary = {
            "total_distance_km": round(total_distance_km, 2),
            "total_travel_time": format_duration(total_duration),
            "total_duration_seconds": total_duration,
            "avg_speed_kmph": avg_speed,
            "gap_count": gap_count,
            "continuous_segments_count": len([s for s in segments if s["type"] == "continuous"]),
            "deduplicated_bursts_collapsed": raw_count - len(waypoints),
            "first_sighted": waypoints[0]["timestamp"],
            "last_sighted": waypoints[-1]["timestamp"],
            "vehicle_type": waypoints[0].get("vehicle_type", "Car"),
        }

        # 4. Pagination
        total_waypoints = len(waypoints)
        total_pages = math.ceil(total_waypoints / limit) if limit > 0 else 1
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_waypoints = waypoints[start_idx:end_idx]
        road_geometry = [
            {
                "type": segment["type"],
                "coordinates": segment.get("coordinates", []),
            }
            for segment in segments
            if segment.get("coordinates")
        ]

        return {
            "plate_number": clean_plate,
            "found": True,
            "total_detections_raw": raw_count,
            "total_waypoints": total_waypoints,
            "summary": summary,
            "waypoints": paginated_waypoints,
            "all_waypoints": waypoints,  # complete list for full map rendering
            "segments": segments,
            "road_geometry": road_geometry,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_waypoints,
                "total_pages": total_pages,
            },
        }

    finally:
        if not db:
            session.close()


# ─── Export Generators ───────────────────────────────────────────────────────

def generate_trajectory_csv(trajectory_data: Dict) -> str:
    """Generate RFC 4180 compliant CSV of trajectory waypoints."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Metadata headers
    writer.writerow(["# ANPR TRAJECTORY RECONSTRUCTION REPORT"])
    writer.writerow(["# Plate Number", trajectory_data.get("plate_number", "")])
    writer.writerow(["# Generated At", datetime.now(timezone.utc).isoformat()])
    writer.writerow([])

    # Table columns
    writer.writerow([
        "Sequence",
        "Timestamp (UTC)",
        "Camera ID",
        "Camera Name",
        "Latitude",
        "Longitude",
        "Confidence",
        "Distance From Prev (km)",
        "Time Delta (s)",
        "Speed (km/h)",
        "Is Coverage Gap",
        "Gap / Anomaly Reason",
        "Burst Frames Collapsed",
    ])

    for wp in trajectory_data.get("all_waypoints", []):
        writer.writerow([
            wp.get("sequence"),
            wp.get("timestamp"),
            wp.get("camera_id"),
            wp.get("camera_name"),
            wp.get("lat"),
            wp.get("lon"),
            wp.get("confidence"),
            wp.get("distance_km"),
            wp.get("time_delta_seconds"),
            wp.get("speed_kmph"),
            "YES" if wp.get("is_gap") else "NO",
            wp.get("gap_reason") or "",
            wp.get("burst_count", 1),
        ])

    return output.getvalue()


def generate_trajectory_dossier_html(trajectory_data: Dict) -> str:
    """Generate formal Law Enforcement Movement History Dossier in printable HTML format."""
    plate = trajectory_data.get("plate_number", "UNKNOWN")
    summary = trajectory_data.get("summary") or {}
    waypoints = trajectory_data.get("all_waypoints", [])

    rows_html = ""
    for wp in waypoints:
        is_gap = wp.get("is_gap")
        gap_badge = f'<span style="background:#fef3c7;color:#b45309;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;">GAP: {wp.get("gap_reason", "")}</span>' if is_gap else '<span style="color:#059669;font-weight:bold;">CONTINUOUS</span>'
        rows_html += f"""
        <tr style="border-bottom: 1px solid #e5e7eb; {'background:#fffbeb;' if is_gap else ''}">
            <td style="padding: 8px; font-weight:bold;">{wp.get('sequence')}</td>
            <td style="padding: 8px; font-family:monospace;">{wp.get('timestamp')}</td>
            <td style="padding: 8px;"><strong>{wp.get('camera_name')}</strong> <span style="font-size:11px;color:#6b7280;">({wp.get('camera_id')})</span></td>
            <td style="padding: 8px; font-family:monospace;">{wp.get('lat'):.4f}, {wp.get('lon'):.4f}</td>
            <td style="padding: 8px;">{(wp.get('confidence', 0)*100):.1f}%</td>
            <td style="padding: 8px;">{wp.get('distance_km')} km</td>
            <td style="padding: 8px;">{wp.get('speed_kmph')} km/h</td>
            <td style="padding: 8px;">{gap_badge}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Law Enforcement Trajectory Dossier — {plate}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #111827; padding: 40px; margin: 0; }}
        .header {{ border-bottom: 3px solid #1e3a8a; padding-bottom: 16px; margin-bottom: 24px; }}
        .badge-confidential {{ background: #dc2626; color: white; padding: 4px 10px; font-size: 12px; font-weight: bold; border-radius: 4px; text-transform: uppercase; float: right; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
        .kpi-card {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; }}
        .kpi-label {{ font-size: 11px; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; }}
        .kpi-val {{ font-size: 18px; font-weight: bold; color: #111827; font-family: monospace; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 16px; }}
        th {{ background: #f3f4f6; text-align: left; padding: 10px 8px; font-size: 11px; text-transform: uppercase; border-bottom: 2px solid #d1d5db; }}
        .footer {{ margin-top: 40px; border-top: 1px solid #e5e7eb; padding-top: 16px; font-size: 11px; color: #6b7280; }}
        @media print {{
            body {{ padding: 10px; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 20px; text-align: right;">
        <button onclick="window.print()" style="background:#2563eb; color:white; padding:8px 16px; border:none; border-radius:4px; cursor:pointer; font-weight:bold;">🖨️ Print / Save as PDF</button>
    </div>

    <div class="header">
        <span class="badge-confidential">Law Enforcement Official Record</span>
        <h1 style="margin: 0 0 6px 0; font-size: 22px; color: #1e3a8a;">DELHI POLICE TRAFFIC &amp; SURVEILLANCE DIRECTORATE</h1>
        <div style="font-size: 14px; color: #4b5563;">AI Trajectory Reconstruction Dossier &bull; Automated Forensic Sighting Log</div>
    </div>

    <div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px; margin-bottom: 20px; font-size: 13px;">
        <strong>Target License Plate:</strong> <span style="font-family: monospace; font-size: 16px; font-weight: bold; color: #1d4ed8;">{plate}</span>
        &nbsp;&bull;&nbsp; <strong>Vehicle Type:</strong> {summary.get('vehicle_type', 'Car')}
        &nbsp;&bull;&nbsp; <strong>Reconstruction Period:</strong> {summary.get('first_sighted', '—')} to {summary.get('last_sighted', '—')}
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Total Tracked Distance</div>
            <div class="kpi-val">{summary.get('total_distance_km', 0)} km</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Transit Duration</div>
            <div class="kpi-val">{summary.get('total_travel_time', '—')}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Average Observed Speed</div>
            <div class="kpi-val">{summary.get('avg_speed_kmph', 0)} km/h</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Coverage Gaps Detected</div>
            <div class="kpi-val" style="color: {'#d97706' if summary.get('gap_count', 0) > 0 else '#059669'}">{summary.get('gap_count', 0)} Gaps</div>
        </div>
    </div>

    <div style="margin-bottom: 8px; font-size: 13px; font-weight: bold;">CHRONOLOGICAL WAYPOINT AUDIT LOG</div>
    <table>
        <thead>
            <tr>
                <th>Seq</th>
                <th>Timestamp (UTC)</th>
                <th>Camera Node</th>
                <th>GPS Location</th>
                <th>OCR Conf</th>
                <th>Distance</th>
                <th>Speed</th>
                <th>Segment Status</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="footer">
        <p><strong>Chain of Custody &amp; Evidentiary Disclaimer:</strong> This log is programmatically generated by Component 2 of the AI Trajectory Tracking System. Sightings marked with "GAP" reflect intervals where direct camera coverage was absent; no continuous vehicle movement is implied during those intervals. Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}.</p>
    </div>
</body>
</html>
"""
    return html
