"""
identity.py — Vehicle identity / owner lookup module.

═══════════════════════════════════════════════════════════════════════════════
  ACCESS CONTROL NOTE
  This module is intentionally SEPARATE from the trajectory and analytics
  pipeline. In the real system:

  • analytics.py / matcher.py = "Urban Planner View"
      → Can see: trajectory paths, speeds, congestion, camera sightings
      → Cannot see: owner names, addresses, RTO details

  • identity.py = "Police / Enforcement View"
      → Can see: all of the above PLUS owner PII and vehicle registration data
      → Must be accessed via a separate authenticated API endpoint (not wired
        into the public /analytics or /trajectory routes)

  This separation enforces the access-control boundary described in the
  project brief. In production this module would query a Vahan/SARATHI API
  behind an authenticated service account, not a local mock dict.
═══════════════════════════════════════════════════════════════════════════════

All data below is MOCK / DEMO data only. No real individuals are represented.
"""

from typing import Optional, Dict

# ─── Mock registry ─────────────────────────────────────────────────────────────

_MOCK_REGISTRY: Dict[str, dict] = {
    "DL01AB1234": {
        "owner_name": "Ramesh Kumar Sharma",
        "owner_contact": "+91-98XXXXXXX1",
        "address": "47-B, Lajpat Nagar II, New Delhi - 110024",
        "vehicle_make": "Maruti Suzuki Swift",
        "vehicle_colour": "White",
        "registration_date": "2019-03-15",
        "rto_district": "Delhi Central",
        "status": "WANTED",
        "remarks": "Flagged under Section 41 CrPC",
    },
    "MH12XY5678": {
        "owner_name": "Sunita Patil",
        "owner_contact": "+91-97XXXXXXX2",
        "address": "12, Dadar East, Mumbai - 400014",
        "vehicle_make": "Honda City",
        "vehicle_colour": "Silver",
        "registration_date": "2021-07-20",
        "rto_district": "Pune West",
        "status": "WANTED",
        "remarks": "Challan outstanding ×7, warrant issued",
    },
    "UP32CD9999": {
        "owner_name": "Vikas Tripathi",
        "owner_contact": "+91-96XXXXXXX3",
        "address": "C-3, Vasundhara Enclave, Lucknow - 226010",
        "vehicle_make": "Toyota Innova",
        "vehicle_colour": "Grey",
        "registration_date": "2018-11-01",
        "rto_district": "Lucknow",
        "status": "WANTED",
        "remarks": "Reported stolen vehicle",
    },
    "KA05EF2222": {
        "owner_name": "Priya Venkatesh",
        "owner_contact": "+91-95XXXXXXX4",
        "address": "204, Indiranagar 1st Stage, Bengaluru - 560038",
        "vehicle_make": "Hyundai Creta",
        "vehicle_colour": "Red",
        "registration_date": "2022-02-28",
        "rto_district": "Bengaluru East",
        "status": "WANTED",
        "remarks": "Subject of traffic court summons",
    },
    "RJ14GH7777": {
        "owner_name": "Arvind Meena",
        "owner_contact": "+91-94XXXXXXX5",
        "address": "Plot 9, Malviya Nagar, Jaipur - 302017",
        "vehicle_make": "Tata Nexon",
        "vehicle_colour": "Blue",
        "registration_date": "2020-09-10",
        "rto_district": "Jaipur",
        "status": "WANTED",
        "remarks": "Linked to overloading violation, commercial permit expired",
    },
}

_NOT_FOUND_RESPONSE: dict = {
    "owner_name": "NOT FOUND",
    "owner_contact": "—",
    "address": "—",
    "vehicle_make": "—",
    "vehicle_colour": "—",
    "registration_date": "—",
    "rto_district": "—",
    "status": "UNKNOWN",
    "remarks": "Not present in mock registry",
}


# ─── Public API ────────────────────────────────────────────────────────────────

def get_vehicle_info(plate: str) -> Optional[Dict]:
    """
    Look up owner and vehicle information for a plate number.

    THIS FUNCTION MUST ONLY BE CALLED FROM AUTHENTICATED ENFORCEMENT ENDPOINTS.
    It must never be exposed through the public analytics API.

    Args:
        plate: The plate number (normalised or raw).

    Returns:
        Dict with owner/vehicle info, or a NOT_FOUND placeholder.
        Returns None only if plate is empty/None.
    """
    if not plate:
        return None
    plate = plate.upper().strip()
    return _MOCK_REGISTRY.get(plate, dict(_NOT_FOUND_RESPONSE))


def is_wanted(plate: str) -> bool:
    """Return True if the plate is in the wanted registry."""
    if not plate:
        return False
    return plate.upper().strip() in _MOCK_REGISTRY
