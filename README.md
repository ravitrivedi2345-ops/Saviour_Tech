# City-Wide ANPR Trajectory Engine — Hackathon Prototype

## Project Structure

```
SIH_127/
├── anpr_ocr_service/     # [Component 1] Standalone High-Precision ANPR OCR Microservice
│   ├── app/
│   │   ├── detector.py       # Stage 1: YOLOv8 / Morphological plate detection with CLAHE
│   │   ├── recognizer.py     # Stage 2: CRNN with greedy/beam-search CTC decoding
│   │   ├── validator.py      # Regex validator + slot confusion heuristics (0↔O, 8↔B)
│   │   ├── pipeline.py       # End-to-end two-stage pipeline orchestrator
│   │   ├── database.py       # PostgreSQL persistence (B-tree & composite indexes) + SQLite fallback
│   │   ├── queue_publisher.py# RabbitMQ/Kafka publisher with resilient memory buffering
│   │   └── main.py           # FastAPI service (port 8001)
│   ├── benchmarks/           # Decoupled degradation benchmarks (clear, night, rain, blur, oblique)
│   ├── scripts/              # Active learning dataset curator & retrain pipeline
│   ├── Dockerfile            # Production multi-stage container
│   └── docker-compose.yml    # Full stack: OCR Service + PostgreSQL 16 + RabbitMQ 3
├── backend/              # [Component 2 & 3] Trajectory Engine & City Traffic Analytics
│   ├── camera_graph.py       # Delhi NCR 9-camera network, distances, speed bounds
│   ├── simulator.py          # Synthetic detection generator with OCR character noise
│   ├── matcher.py            # Levenshtein fuzzy matching + physics gap trajectory reconstruction
│   ├── analytics.py          # Legacy corridor congestion & vehicle alerts
│   ├── city_analytics.py     # [Component 3] GIS Heatmap, segment speed deltas, route density, 60s cache
│   ├── database.py           # Pre-aggregated hourly & daily corridor summaries + SQLite fallback
│   ├── identity.py           # Privacy-by-design vault (citizen PII isolated for enforcement)
│   └── main.py               # FastAPI service (port 8000)
└── frontend/             # Interactive Student & Developer React Dashboard (port 5173)
    └── src/
        ├── App.jsx           # Master dashboard with 5 tabs + Student Guide Banner
        ├── components/
        │   ├── CityTrafficDashboard.jsx     # [Component 3] Dual-role GIS traffic analytics hub
        │   ├── CityTrafficMap.jsx           # [Component 3] GIS Leaflet map with speed corridors & outage pins
        │   ├── ComparativeTrendChart.jsx    # [Component 3] 24-hr comparative flow & speed trend charts
        │   ├── TrajectoryReconstructionLab.jsx # [Component 2] Trajectory query lab & interactive timeline
        │   ├── OcrLiveLab.jsx               # [Component 1] Live visual OCR testing across 5 weather conditions
        │   ├── DetectionsPanel.jsx          # Live camera sightings stream
        │   ├── TrajectorySearch.jsx         # Stepper with Physics GAP explainers
        │   ├── CongestionTable.jsx          # Road congestion & average speed tables
        │   ├── AlertsPanel.jsx              # Wanted vehicle alerts & Police Vault modal
        │   └── StudentGuideBanner.jsx       # 4-step concept banner explaining the AI algorithms
        └── api.js            # Unified API client for backend (8000) & OCR service (8001)
```

## Quick Start

### Option A: Local Native Services (Fastest for Development)

1. **Component 1 (ANPR OCR Microservice)**:
   ```powershell
   python -m uvicorn anpr_ocr_service.app.main:app --port 8001 --reload
   ```
2. **Component 2 (Trajectory & Analytics Backend)**:
   ```powershell
   python -m uvicorn backend.main:app --port 8000 --reload
   ```
3. **Frontend Dashboard**:
   ```powershell
   cd frontend
   npm run dev
   ```

Open http://localhost:5173 to test both systems live!

### Option B: Docker Compose (Full Stack Deployment)

To deploy Component 1 with dedicated PostgreSQL 16 and RabbitMQ 3 message broker:

```powershell
docker compose -f anpr_ocr_service/docker-compose.yml up --build -d
```

- OCR API: http://localhost:8001/docs
- RabbitMQ Management Console: http://localhost:15672 (guest/guest)
- PostgreSQL: `localhost:5432` (db: `anpr_db`, user: `anpr_user`)

---

## Component 1 — Model Selection & Performance Rationale

### Why CRNN over Vision Transformers (TrOCR)?

| Dimension | CRNN (CNN + BiLSTM + CTC) | Vision Transformer (TrOCR) |
|---|---|---|
| **Inference Latency** | **3.5 ms – 7.0 ms** per crop | **45 ms – 110 ms** per crop |
| **Multi-Stream Target** | **300 FPS (20 cameras @ 15 FPS)**: Supported | Max 2–3 streams before memory saturation |
| **Model Footprint** | **~15 MB** (lightweight edge/CPU friendly) | **~350 MB – 1.2 GB** (heavy GPU required) |
| **Character Induction**| CTC handles variable plate lengths with zero-padding | Autoregressive decoding token-by-token (slower) |

### Decoupled Environmental Degradation Benchmark

*(Evaluated across 5 realistic conditions via `python anpr_ocr_service/benchmarks/evaluate_accuracy.py`)*:

| Condition | Plate Acc | Char Acc | Format Compliance | Human Review Flag Rate | Latency |
|---|---|---|---|---|---|
| **Clear Daytime (Optimal)** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | 16.7 ms |
| **Night / Low-Light** | **100.0%** | **100.0%** | **100.0%** | **88.0%** | 12.2 ms |
| **Rain / Wet Road Glare** | **96.0%** | **96.0%** | **96.0%** | **24.0%** | 13.4 ms |
| **Motion Blur (>60 km/h)** | **28.0%** | **28.0%** | **28.0%** | **72.0%** | 9.9 ms |
| **Oblique Angle (>35°)** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | 10.8 ms |

> [!NOTE]
> When plates experience severe motion blur, the system's confidence thresholding (<85%) automatically triggers `"needs_review": true`, isolating corrupt reads before they pollute downstream trajectory graph reconstruction!

---

## API Endpoints Overview

### Component 1 (OCR Service — Port 8001)
- `POST /api/v1/detect/image`: Upload raw image file (JPEG/PNG).
- `POST /api/v1/detect/base64`: Submit base64-encoded frame.
- `POST /api/v1/detect/batch`: Batch multi-camera frame processing.
- `GET /api/v1/detections`: Query persisted sightings with filtering (`needs_review`, `camera_id`, `plate_number`).
- `GET /api/v1/health`: Service health, hardware engine (CUDA/CPU), and broker status.
- `GET /api/v1/metrics`: Prometheus-compatible throughput and latency telemetry.

### Component 2 & 3 (Trajectory & City Traffic Analytics — Port 8000)
- `POST /simulate?count=N`: Inject simulated camera detections with deliberate OCR character noise.
- `GET /trajectory?plate={plate}&start={date}&end={date}`: Trajectory query interface with collapsed bursts and speed calculations.
- `GET /trajectory/export/csv`: Stream trajectory waypoints in RFC 4180 CSV format.
- `GET /trajectory/export/pdf`: Printable Law Enforcement Vehicle Tracking Dossier HTML.
- `GET /analytics/heatmap?hour_range={range}&zone={zone}`: GIS heatmap density coordinates with explicit sensor outage statuses.
- `GET /analytics/speed?hour_range={range}&zone={zone}`: Road segment speeds calculated from consecutive camera timestamp deltas.
- `GET /analytics/density?zone={zone}&period={period}`: Corridor volume rankings and capacity utilization (%).
- `GET /analytics/trends?compare=today_vs_last_week&metric=volume`: 24-hr comparative traffic flow vs prior period.
- `GET /analytics/export/csv`: Pre-aggregated daily corridor summary CSV export.
- `GET /analytics/export/pdf`: Printable Executive Traffic Congestion Brief HTML.
- `GET /enforcement/identity/{plate}`: Isolated identity vault (PII access limited to authorized police).

## Key Design Decisions

- **Pre-Aggregation Over Raw Scans**: Dashboard analytics strictly query pre-aggregated `hourly_traffic_summary` and `daily_corridor_summary` tables via an in-memory 60-second TTL cache, ensuring sub-20ms queries regardless of historical detection volume.
- **Sensor Outage vs. Zero Traffic Isolation**: A camera hardware/network failure (`CAM_08` Shahdara Flyover) is explicitly flagged with `[OFFLINE]` badges and warning banners — NEVER conflated with 0 vehicles or free-flow traffic.
- **Dual Role-Based Interface**:
  - **Traffic Police (Operational)**: Immediate bottleneck alerts, speed enforcement (<25 km/h), and field technician outage dispatch.
  - **City Planner (Strategic)**: Long-range capacity utilization bars, corridor rankings, and 24-hour comparative flow trend charts.
- **Fuzzy matching** uses pure-Python Levenshtein (no compiled deps). Edit distance ≤ 2 groups plates.
- **Gap detection**: consecutive sightings physically impossible at 80 km/h are split into separate segments with a `GAP` marker.
- **Access control**: `identity.py` is only imported by the `/enforcement/identity/` endpoint — never by analytics or trajectory routes.
- **OCR noise**: 15% of detections get character swaps (0↔O, 1↔I, 8↔B, etc.) with reduced confidence scores.

## Wanted Plates (hardcoded for demo)

```
DL01AB1234, MH12XY5678, UP32CD9999, KA05EF2222, RJ14GH7777
```

These appear naturally in the detection pool — run the simulation and check the Alerts panel.
