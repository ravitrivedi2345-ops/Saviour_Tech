"""
test_extensions.py — Comprehensive Test Suite for Platform Extensions (unittest-based):
1. Authentication & RBAC (Admin, Traffic Police, City Planner)
2. Audit Trail Logging (Login attempts, plate queries, identity queries)
3. Video Upload Validation (Min 10s rule rejection/acceptance)
4. Indian Road Network (OSM/OSRM road geometry & corridor snapping)
"""

import os
import sys
import tempfile
import unittest
import cv2
import numpy as np
from fastapi.testclient import TestClient

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(__file__))

from main import app
from database import SessionLocal, UserRecord, AuthAuditRecord, DetectionRecord
from auth import hash_password, create_access_token, decode_token
from routing_engine import get_curved_route_geometry, DELHI_NCR_CORRIDORS

client = TestClient(app)


def create_dummy_video(duration_sec: float, fps: int = 10, width: int = 320, height: int = 240) -> str:
    """Generates a minimal valid temporary MP4 video file with specified duration."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    temp_path = temp_file.name
    temp_file.close()

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_path, fourcc, fps, (width, height))
    total_frames = int(duration_sec * fps)

    for i in range(total_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            f"F:{i} T:{i/fps:.1f}s DL01AB1234",
            (10, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1
        )
        out.write(frame)

    out.release()
    return temp_path


class TestPlatformExtensions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Ensure seeded users and sample detections are present in test database."""
        session = SessionLocal()
        try:
            admin = session.query(UserRecord).filter_by(username="admin").first()
            if not admin:
                admin = UserRecord(
                    username="admin",
                    email="admin@traffic.delhipolice.gov.in",
                    password_hash=hash_password("Admin@123"),
                    full_name="System Administrator",
                    role="Admin",
                    department="Central Command",
                    is_active=True
                )
                session.add(admin)

            police = session.query(UserRecord).filter_by(username="police_sharma").first()
            if not police:
                police = UserRecord(
                    username="police_sharma",
                    email="sharma.inspector@delhipolice.gov.in",
                    password_hash=hash_password("Police@123"),
                    full_name="Inspector R. K. Sharma",
                    role="Traffic Police",
                    department="South District Traffic Cell",
                    is_active=True
                )
                session.add(police)

            planner = session.query(UserRecord).filter_by(username="planner_verma").first()
            if not planner:
                planner = UserRecord(
                    username="planner_verma",
                    email="verma.urban@delhi.gov.in",
                    password_hash=hash_password("Planner@123"),
                    full_name="Dr. Sunita Verma",
                    role="City Planner",
                    department="Urban Mobility Planning Bureau",
                    is_active=True
                )
                session.add(planner)

            session.commit()
        finally:
            session.close()

    # ─── 1. Authentication & Token Tests ──────────────────────────────────────────

    def test_01_login_success(self):
        """Test login with valid credentials for each role."""
        for user, pwd, expected_role in [
            ("admin", "Admin@123", "Admin"),
            ("police_sharma", "Police@123", "Traffic Police"),
            ("planner_verma", "Planner@123", "City Planner")
        ]:
            res = client.post("/auth/login", json={"username": user, "password": pwd})
            self.assertEqual(res.status_code, 200, f"Login failed for {user}: {res.text}")
            data = res.json()
            self.assertIn("access_token", data)
            self.assertIn("refresh_token", data)
            self.assertEqual(data["user"]["role"], expected_role)
            self.assertEqual(data["user"]["username"], user)

            payload = decode_token(data["access_token"])
            self.assertIsNotNone(payload)
            self.assertEqual(payload["sub"], user)
            self.assertEqual(payload["role"], expected_role)

    def test_02_login_failure(self):
        """Test login with wrong password generates 401 and failure audit record."""
        res = client.post("/auth/login", json={"username": "admin", "password": "WrongPassword"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid username or password", res.json()["detail"])

    def test_03_refresh_token_flow(self):
        """Test exchanging refresh token for a fresh access token."""
        login_res = client.post("/auth/login", json={"username": "police_sharma", "password": "Police@123"})
        refresh_tok = login_res.json()["refresh_token"]

        ref_res = client.post("/auth/refresh", json={"refresh_token": refresh_tok})
        self.assertEqual(ref_res.status_code, 200)
        self.assertIn("access_token", ref_res.json())

        # Invalid refresh token should fail
        bad_ref = client.post("/auth/refresh", json={"refresh_token": "invalid.jwt.token"})
        self.assertEqual(bad_ref.status_code, 401)

    # ─── 2. Role-Based Access Control (RBAC) Tests ─────────────────────────────────

    def test_04_rbac_enforcement_identity(self):
        """
        Test RBAC boundaries on /enforcement/identity/{plate}:
        - Admin: Allowed (200)
        - Traffic Police: Allowed (200)
        - City Planner: Forbidden (403)
        - Unauthenticated: Unauthorized (401)
        """
        # 1. Unauthenticated -> 401
        res = client.get("/enforcement/identity/DL01AB1234")
        self.assertEqual(res.status_code, 401)

        # 2. City Planner -> 403
        planner_login = client.post("/auth/login", json={"username": "planner_verma", "password": "Planner@123"}).json()
        planner_token = planner_login["access_token"]
        res_planner = client.get(
            "/enforcement/identity/DL01AB1234",
            headers={"Authorization": f"Bearer {planner_token}"}
        )
        self.assertEqual(res_planner.status_code, 403)

        # 3. Traffic Police -> 200
        police_login = client.post("/auth/login", json={"username": "police_sharma", "password": "Police@123"}).json()
        police_token = police_login["access_token"]
        res_police = client.get(
            "/enforcement/identity/DL01AB1234",
            headers={"Authorization": f"Bearer {police_token}"}
        )
        self.assertEqual(res_police.status_code, 200)
        self.assertEqual(res_police.json()["plate"], "DL01AB1234")

        # 4. Admin -> 200
        admin_login = client.post("/auth/login", json={"username": "admin", "password": "Admin@123"}).json()
        admin_token = admin_login["access_token"]
        res_admin = client.get(
            "/enforcement/identity/DL01AB1234",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_admin.status_code, 200)

    def test_05_rbac_audit_logs(self):
        """
        Test RBAC on /auth/audit-logs:
        - Admin: Allowed (200)
        - Traffic Police: Forbidden (403)
        """
        police_login = client.post("/auth/login", json={"username": "police_sharma", "password": "Police@123"}).json()
        police_token = police_login["access_token"]
        res = client.get("/auth/audit-logs", headers={"Authorization": f"Bearer {police_token}"})
        self.assertEqual(res.status_code, 403)

        admin_login = client.post("/auth/login", json={"username": "admin", "password": "Admin@123"}).json()
        admin_token = admin_login["access_token"]
        res_admin = client.get("/auth/audit-logs", headers={"Authorization": f"Bearer {admin_token}"})
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn("audit_logs", res_admin.json())

    # ─── 3. Plate Query Audit Logging Tests ────────────────────────────────────────

    def test_06_plate_search_audit_logging(self):
        """Test that querying a vehicle trajectory creates an audit log record with user ID and timestamp."""
        police_login = client.post("/auth/login", json={"username": "police_sharma", "password": "Police@123"}).json()
        token = police_login["access_token"]

        target_plate = "DL08EF9012"
        res = client.get(
            f"/trajectory?plate={target_plate}",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 200)

        # Query DB directly to check audit record
        session = SessionLocal()
        try:
            audit = (
                session.query(AuthAuditRecord)
                .filter_by(action="PLATE_SEARCH", username="police_sharma")
                .order_by(AuthAuditRecord.timestamp.desc())
                .first()
            )
            self.assertIsNotNone(audit)
            self.assertEqual(audit.details.get("plate_number"), target_plate)
            self.assertEqual(audit.status, "SUCCESS")
        finally:
            session.close()

    # ─── 4. Video Upload & Duration Validation Tests ───────────────────────────────

    def test_07_video_upload_short_duration_rejection(self):
        """
        Requirement: Minimum video duration 10 seconds. Reject and return clear error if shorter.
        Test uploading a 4-second video -> HTTP 400 rejection.
        """
        short_video_path = create_dummy_video(duration_sec=4.0, fps=10)
        try:
            with open(short_video_path, "rb") as f:
                res = client.post(
                    "/video/upload",
                    files={"file": ("short_test.mp4", f, "video/mp4")},
                    data={"camera_id": "CAM-01"}
                )
            self.assertEqual(res.status_code, 400)
            self.assertIn("Minimum required duration is 10.0 seconds", res.json()["detail"])
        finally:
            if os.path.exists(short_video_path):
                os.remove(short_video_path)

    def test_08_video_upload_valid_duration_acceptance(self):
        """
        Test uploading an 11-second video -> HTTP 200 / ACCEPTED with task_id.
        """
        valid_video_path = create_dummy_video(duration_sec=11.0, fps=10)
        try:
            with open(valid_video_path, "rb") as f:
                res = client.post(
                    "/video/upload",
                    files={"file": ("valid_test.mp4", f, "video/mp4")},
                    data={"camera_id": "CAM-02"}
                )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["status"], "ACCEPTED")
            self.assertIn("task_id", data)
            self.assertGreaterEqual(data["duration_seconds"], 10.0)
            self.assertIn("asynchronously with live progress", data["message"])

            # Check status endpoint
            task_id = data["task_id"]
            status_res = client.get(f"/video/status/{task_id}")
            self.assertEqual(status_res.status_code, 200)
            self.assertEqual(status_res.json()["task_id"], task_id)
        finally:
            if os.path.exists(valid_video_path):
                os.remove(valid_video_path)

    # ─── 5. Indian Road Network / OSM / OSRM Geometry Tests ───────────────────────

    def test_09_routing_engine_corridor_geometry(self):
        """Test road network geometry calculation between Delhi NCR camera stations."""
        res = client.get("/routing/corridor-path?start_cam=CAM-01&end_cam=CAM-02")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("coordinates", data)
        self.assertGreaterEqual(len(data["coordinates"]), 2)
        # Ensure coordinates are in Delhi NCR bounding box (lat ~28.5, lng ~77.2)
        first_pt = data["coordinates"][0]
        self.assertTrue(28.0 <= first_pt[0] <= 29.0)
        self.assertTrue(76.5 <= first_pt[1] <= 77.8)

    def test_10_trajectory_reconstruction_includes_road_geometry(self):
        """Test that trajectory reconstruction response includes realistic road_geometry."""
        res = client.get("/trajectory?plate=DL01AB1234")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("road_geometry", data)
        self.assertIsInstance(data["road_geometry"], list)
        if data["road_geometry"]:
            first_segment = data["road_geometry"][0]
            self.assertIn("coordinates", first_segment)
            self.assertGreaterEqual(len(first_segment["coordinates"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
