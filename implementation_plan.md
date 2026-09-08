# System Extensions Implementation Plan

This plan details the architecture and implementation for extending the City-Wide ANPR Trajectory Tracking & Traffic Platform with 4 major capabilities:

1. **Authentication & Authorization (RBAC)** — JWT auth, role restrictions (`Admin`, `Traffic Police`, `City Planner`), session inactivity timeout, refresh tokens, and plate search audit logging.
2. **Real-Time Live Traffic View** — WebSocket-based live detection stream, interactive Leaflet OpenStreetMap with live camera node markers, and auto-refreshing traffic congestion heatmap overlay.
3. **Video Upload with ML-Based Plate Detection** — Multipart video upload with $\ge 10\text{s}$ duration validation, frame-by-frame OCR pipeline execution, and live streaming progress/results feedback.
4. **Indian Road Network & OSRM Integration** — Street-level road snapping between Delhi NCR camera stations using OpenStreetMap (OSM) and OSRM routing engine.

---

## User Review Required

> [!IMPORTANT]
> **Authentication & Access Matrix**:
> - **`Admin`**: Full access to all components, system configurations, user management, blacklist CRUD, analytics, trajectory dossiers, and audit logs.
> - **`Traffic Police`**: Access to vehicle trajectory reconstruction, private owner identity vault, alert review/resolution, live traffic view, video upload detection, and plate searches.
> - **`City Planner`**: Access to city traffic analytics dashboard, congestion heatmaps, speed corridors, route density, comparative trends, and non-sensitive aggregated trajectory analytics. (Blocked from citizen owner privacy vault and alert dispositions).
> 
> All plate searches and login events are permanently recorded in `AuthAuditRecord` for statutory compliance.

> [!IMPORTANT]
> **Video Upload Minimum Duration**:
> As specified, uploaded videos are inspected using OpenCV. If the video duration is strictly less than $10.0$ seconds, the upload is rejected with a descriptive HTTP 400 error.

> [!NOTE]
> **Indian Road Network & Routing**:
> Road geometries between camera pairs will query the OSRM routing engine with an offline, high-precision Delhi NCR road polyline fallback dataset (Ring Road, NH-48, Barapullah, Outer Ring Road, Vikas Marg) to ensure reliable operation in offline/isolated network environments.

---

## Proposed Changes

### Backend: Authentication, RBAC, & Audit Logging

#### [NEW] [auth.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/auth.py)
- Password hashing using `passlib[bcrypt]` / `bcrypt`.
- JWT access token generation ($\text{default } 30\text{ min}$) and refresh token generation ($7\text{ days}$).
- FastAPI dependencies: `get_current_user`, `require_roles(["Admin", "Traffic Police", ...])`.
- Audit log helper function `log_user_action(db, user_id, action, resource, details)`.

#### [MODIFY] [database.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/database.py)
- Add `UserRecord`: `id`, `username`, `hashed_password`, `role`, `full_name`, `badge_id`, `is_active`, `created_at`, `last_login`.
- Add `AuthAuditRecord`: `id`, `user_id`, `username`, `action`, `resource`, `ip_address`, `details` (JSON text), `timestamp`.
- Seed 3 default accounts in `init_seed_data()`:
  - `admin` / `Admin@123` (`Admin`)
  - `police_sharma` / `Police@123` (`Traffic Police`)
  - `planner_verma` / `Planner@123` (`City Planner`)

---

### Backend: Live Traffic & WebSocket Feed

#### [NEW] [live_traffic.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/live_traffic.py)
- `LiveTrafficManager`: Manages active `/ws/live-traffic` WebSocket connections.
- Generates periodic broadcast packages (active detections, camera status, rolling 1-minute congestion index per camera node).

---

### Backend: Video Upload & Frame-by-Frame OCR Engine

#### [NEW] [video_processor.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/video_processor.py)
- Accepts uploaded video files (`.mp4`, `.avi`, `.mov`, `.mkv`).
- Validates video length: computes $\text{duration} = \frac{\text{frame\_count}}{\text{fps}}$. Rejects with HTTP 400 if $< 10.0$ seconds.
- Background asynchronous worker that samples video frames (e.g., at 2–4 FPS), invokes the YOLOv8/CRNN ANPR pipeline, and streams live progress percentages, timestamps, and detected plates.
- Task status storage with WebSocket feed at `/ws/video-process/{task_id}` and REST status endpoint `GET /video/status/{task_id}`.

---

### Backend: Indian Road Network & OSRM Routing

#### [NEW] [routing_engine.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/routing_engine.py)
- Integrates OpenStreetMap (OSM) / OSRM API for Indian city road networks.
- Computes turn-by-turn road polyline coordinates between camera stations across Delhi NCR (Ring Road, NH-48, Barapullah, Outer Ring Road, Mathura Road).
- Pre-cached road segment geometries for instant offline performance.
- Upgrades `trajectory_engine.py` to return actual road-following geometries instead of straight-line coordinates.

---

### Backend: API Router & Endpoint Extensions

#### [MODIFY] [main.py](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/backend/main.py)
- Integrate Auth routes:
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `GET /auth/me`
  - `POST /auth/logout`
  - `GET /auth/audit-logs`
- Protect endpoints with RBAC:
  - `/trajectory`: Requires authentication; logs plate search in `AuthAuditRecord`.
  - `/enforcement/identity/{plate}`: Requires `Admin` or `Traffic Police` role; logs vault access.
  - `/analytics/*`: Accessible to `Admin` and `City Planner`.
  - `/alerts/*`: Status updates require `Admin` or `Traffic Police`.
- Add Video Upload endpoints:
  - `POST /video/upload` (validates duration $\ge 10\text{s}$)
  - `GET /video/status/{task_id}`
  - `GET /video/tasks`
  - `WebSocket /ws/video-process/{task_id}`
- Add Live Traffic WebSocket:
  - `WebSocket /ws/live-traffic`
- Add Route Geometry endpoint:
  - `GET /routing/corridor-path`

---

### Frontend Components

#### [NEW] [AuthModal.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/components/AuthModal.jsx) & [AuthContext.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/context/AuthContext.jsx)
- Authentication state management with token storage, inactivity timeout tracker, and auto-refresh token logic.
- Login modal with role badges, one-click demo credentials switcher, and session indicator.

#### [NEW] [LiveTrafficMapDashboard.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/components/LiveTrafficMapDashboard.jsx)
- Real-time Leaflet OpenStreetMap view of Delhi NCR.
- Pulsing camera station markers with live detection popups.
- Dynamic congestion heatmap overlay with auto-refresh interval selector (5s, 10s, 30s).
- Live incoming detection stream ticker.

#### [NEW] [VideoUploadLab.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/components/VideoUploadLab.jsx)
- Drag-and-drop video uploader supporting MP4, AVI, MOV.
- Clear 10-second minimum duration validation banner and error feedback.
- Processing progress indicator (percentage, frame count, elapsed video time).
- Live-updating detection results table with frame numbers, timestamps, plate badges, and confidence meters.
- Clear user note: *"Asynchronous video processing with live progress feedback"*.

#### [MODIFY] [TrajectoryMap.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/components/TrajectoryMap.jsx) & [CityTrafficMap.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/components/CityTrafficMap.jsx)
- Update polyline paths to render exact OSM road geometries instead of straight lines.

#### [MODIFY] [api.js](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/api.js) & [App.jsx](file:///c:/Users/Win11/OneDrive/Documents/SIH_127/frontend/src/App.jsx)
- Integrate auth headers (`Authorization: Bearer <token>`) into all API requests.
- Add tabs for **Live Map & Heatmap** and **Video ANPR Lab**.
- Add role-aware UI elements (e.g. disabling enforcement vault for City Planner).

---

## Verification Plan

### Automated Tests
1. **Auth & RBAC Test Suite**:
   ```powershell
   cd backend
   python test_auth_and_audit.py
   ```
   - Validates login success/failure, token generation, role restrictions, session timeout, and `AuthAuditRecord` query logging.

2. **Video Upload Validation Test Suite**:
   ```powershell
   cd backend
   python test_video_processor.py
   ```
   - Tests $< 10\text{s}$ rejection (HTTP 400), $\ge 10\text{s}$ acceptance, and frame-by-frame detection output.

3. **OSRM Road Network Test Suite**:
   ```powershell
   cd backend
   python test_road_routing.py
   ```
   - Validates road coordinate snapping between camera nodes.

4. **Frontend Production Build**:
   ```powershell
   cd frontend
   npm run build
   ```

### Manual End-to-End Verification
1. Log in as `police_sharma` $\to$ verify access to trajectory searches, alerts, owner vault, and video upload.
2. Log in as `planner_verma` $\to$ verify access to traffic analytics/heatmaps, verify owner privacy vault is blocked.
3. Upload a 5s test video $\to$ verify rejection with clear 10s duration error message.
4. Upload a 12s test video $\to$ verify live progress bar and detection streaming.
5. Open Live Map $\to$ run traffic simulation $\to$ verify camera markers pulse and heatmap updates in real time.
6. Verify trajectory map lines follow actual Delhi roads (Ring Road, NH-48) instead of straight lines.
