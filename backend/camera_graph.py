"""
camera_graph.py — Static camera network definition for the ANPR prototype.

Contains 9 simulated camera locations across Delhi NCR with realistic
lat/lon coordinates, a precomputed inter-camera distance matrix (Haversine),
and a time-feasibility helper used by the trajectory matcher.
"""

import math
from typing import Dict, List, Optional, Tuple

# ─── Camera definitions ────────────────────────────────────────────────────────

CAMERAS: Dict[str, dict] = {
    "CAM_01": {
        "name": "Connaught Place — Rajiv Chowk",
        "lat": 28.6329,
        "lon": 77.2197,
        "zone": "Central Delhi",
        "typical_congestion": "high",
    },
    "CAM_02": {
        "name": "India Gate — Kartavya Path",
        "lat": 28.6129,
        "lon": 77.2295,
        "zone": "Central Delhi",
        "typical_congestion": "medium",
    },
    "CAM_03": {
        "name": "Lajpat Nagar — Ring Road Intersection",
        "lat": 28.5677,
        "lon": 77.2433,
        "zone": "South Delhi",
        "typical_congestion": "high",
    },
    "CAM_04": {
        "name": "Nehru Place — Outer Ring Road",
        "lat": 28.5491,
        "lon": 77.2518,
        "zone": "South Delhi",
        "typical_congestion": "high",
    },
    "CAM_05": {
        "name": "Saket — Press Enclave Road",
        "lat": 28.5244,
        "lon": 77.2090,
        "zone": "South Delhi",
        "typical_congestion": "medium",
    },
    "CAM_06": {
        "name": "Dwarka Sector 10 — NH48",
        "lat": 28.5823,
        "lon": 77.0517,
        "zone": "West Delhi",
        "typical_congestion": "medium",
    },
    "CAM_07": {
        "name": "Rohini Sector 14 — Pitampura T-Point",
        "lat": 28.7041,
        "lon": 77.1025,
        "zone": "North Delhi",
        "typical_congestion": "medium",
    },
    "CAM_08": {
        "name": "Shahdara — NH24 Flyover",
        "lat": 28.6692,
        "lon": 77.2994,
        "zone": "East Delhi",
        "typical_congestion": "high",
    },
    "CAM_09": {
        "name": "Gurugram — Sohna Road Toll",
        "lat": 28.4089,
        "lon": 77.0425,
        "zone": "Gurugram",
        "typical_congestion": "high",
    },
}

CAMERA_IDS: List[str] = list(CAMERAS.keys())

# ─── Max city speed used for feasibility checks ────────────────────────────────
MAX_SPEED_KMPH: float = 80.0  # realistic city traffic upper bound

# ─── Haversine distance ────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def camera_distance_km(cam_a: str, cam_b: str) -> Optional[float]:
    """Return the straight-line distance between two camera nodes (km), or None if unknown."""
    if cam_a not in CAMERAS or cam_b not in CAMERAS:
        return None
    c1, c2 = CAMERAS[cam_a], CAMERAS[cam_b]
    return haversine_km(c1["lat"], c1["lon"], c2["lat"], c2["lon"])


# ─── Precomputed distance matrix ───────────────────────────────────────────────

DISTANCE_MATRIX: Dict[Tuple[str, str], float] = {}
for _a in CAMERA_IDS:
    for _b in CAMERA_IDS:
        if _a != _b:
            DISTANCE_MATRIX[(_a, _b)] = camera_distance_km(_a, _b)


# ─── Feasibility check ─────────────────────────────────────────────────────────

def is_feasible(cam_a: str, cam_b: str, delta_seconds: float) -> bool:
    """
    Return True if a vehicle could realistically travel from cam_a to cam_b
    in delta_seconds seconds without exceeding MAX_SPEED_KMPH.

    A gap of zero or negative seconds is always infeasible (time travel).
    """
    if delta_seconds <= 0:
        return False
    dist_km = camera_distance_km(cam_a, cam_b)
    if dist_km is None:
        return False
    min_time_seconds = (dist_km / MAX_SPEED_KMPH) * 3600.0
    return delta_seconds >= min_time_seconds


def min_travel_seconds(cam_a: str, cam_b: str) -> float:
    """Return the minimum travel time in seconds between two cameras at max speed."""
    dist_km = camera_distance_km(cam_a, cam_b) or 0.0
    return (dist_km / MAX_SPEED_KMPH) * 3600.0


def implied_speed_kmph(cam_a: str, cam_b: str, delta_seconds: float) -> Optional[float]:
    """Compute the implied speed in km/h for a hop between two cameras."""
    if delta_seconds <= 0:
        return None
    dist_km = camera_distance_km(cam_a, cam_b)
    if dist_km is None:
        return None
    return (dist_km / delta_seconds) * 3600.0
