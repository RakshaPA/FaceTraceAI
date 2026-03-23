# FaceTraceAI — Intelligent Face Tracker & Visitor Counter

> **Real-time face detection, recognition, tracking, and unique visitor counting using YOLOv8 + InsightFace ArcFace + PostgreSQL + React.**

---

##  Demo Video

[> **[Add your Loom / YouTube link here]**](https://drive.google.com/file/d/11aicfIn-jv52KZ3Rer3Am6BV8yTZ5AN9/view?usp=sharing)
https://1drv.ms/v/c/0f55c946cdfb8cbf/IQDrQk2YBsqHSpdNqFWoAa76AfKfAVjuoLwnTSU9_Jc9Rdc?e=8CEjZI

---

##  Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VIDEO SOURCE                                  │
│               (MP4 file  ──or──  RTSP stream)                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ frames
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FRAME LOOP  (main.py)                                               │
│                                                                      │
│  ┌───────────────┐   detections    ┌──────────────────┐             │
│  │  FaceDetector │ ──────────────► │   FaceTracker    │             │
│  │  (YOLOv8)     │                 │   (IoU Tracker)  │             │
│  └───────────────┘                 └────────┬─────────┘             │
│         ▲ frame_skip (adaptive)             │ tracks                │
│         │ (config.json)                     ▼                       │
│  ┌──────────────────┐             ┌──────────────────┐              │
│  │ AdaptiveSkipper  │             │  FaceEmbedder    │              │
│  │ CPU/FPS monitor  │             │  (InsightFace /  │              │
│  └──────────────────┘             │   ArcFace)       │              │
│                                   └────────┬─────────┘              │
│                                            │ embeddings             │
│                                            ▼                        │
│                                   ┌──────────────────┐              │
│                                   │  FaceRecognizer  │              │
│                                   │  cosine sim +    │              │
│                                   │  auto-register   │              │
│                                   └────────┬─────────┘              │
│                                            │ face_uuid              │
│                                            ▼                        │
│                                   ┌──────────────────┐              │
│                                   │  EventRouter     │              │
│                                   │  entry/exit      │              │
│                                   │  dwell tracking  │              │
│                                   │  crowd/loitering │              │
│                                   └──┬───────────────┘              │
└──────────────────────────────────────┼──────────────────────────────┘
                                       │
              ┌────────────────────────┼───────────────────────┐
              ▼                        ▼                        ▼
     ┌─────────────────┐   ┌─────────────────┐   ┌────────────────────┐
     │   FSLogger      │   │   DBLogger      │   │  Flask-SocketIO    │
     │  logs/entries/  │   │  PostgreSQL     │   │  REST API +        │
     │  logs/exits/    │   │  faces          │   │  WebSocket push    │
     │  events.log     │   │  face_events    │   └────────┬───────────┘
     └─────────────────┘   │  dwell_records  │            │
                           │  system_alerts  │            ▼
                           │  visitor_stats  │  ┌────────────────────┐
                           └─────────────────┘  │  React Dashboard   │
                                                 │  Upload Video      │
                                                 │  Dashboard         │
                                                 │  Face Gallery      │
                                                 │  Event Log         │
                                                 │  Alerts            │
                                                 └────────────────────┘
```

---

##  Feature List

### Mandatory (as per problem statement)
| # | Feature | Implementation |
|---|---------|----------------|
| 1 | YOLOv8 face detection | `core/detector.py` — configurable confidence + frame_skip |
| 2 | InsightFace ArcFace embeddings | `core/embedder.py` — 512-d normalised vectors |
| 3 | Auto-registration of new faces | `core/recognizer.py` — cosine similarity + UUID assignment |
| 4 | IoU / DeepSort tracking | `core/tracker.py` — stable IDs across frames |
| 5 | Entry/exit event logging | `core/event_router.py` + `logging_/fs_logger.py` |
| 6 | Cropped face images on disk | `logs/entries/YYYY-MM-DD/` and `logs/exits/YYYY-MM-DD/` |
| 7 | PostgreSQL metadata storage | `db/models.py` — faces, face_events, dwell_records |
| 8 | Mandatory events.log file | `logs/events.log` — all critical system events |
| 9 | Unique visitor count | `EventRouter.unique_visitor_count` + DB query |
| 10 | config.json with frame_skip | `config.json` — all parameters including `detection.frame_skip` |
| 11 | RTSP stream support | Toggle `use_rtsp: true` in config.json |

### Extra Features
| Feature | Where |
|---------|-------|
| **Adaptive Frame Skipping** | `core/adaptive_skip.py` — auto-tunes skip based on CPU/FPS |
| **Dwell time tracking** | `DwellRecord` table, EventRouter, dashboard chart |
| **Return visitor detection** | `visit_count` on Face row, session numbering |
| **Demographic estimation** | InsightFace age+gender → stored in `Face.metadata` |
| **Crowd threshold alerts** | EventRouter → SystemAlert table + WebSocket toast |
| **Loitering detection** | Configurable `loitering_seconds`, fires alert |
| **Watchlist mode** | `POST /api/watchlist/<uuid>`, red border in UI |
| **React dashboard** | Live stats, hourly bar chart, face gallery, event log, alerts |
| **Video upload via dashboard** | Drag & drop video → pipeline starts automatically |
| **WebSocket live feed** | Flask-SocketIO — real-time entry/exit toasts |
| **Annotated output video** | Bounding boxes + IDs + timestamps burned into MP4 |
| **Stop processing button** | Stop pipeline mid-run from dashboard |
| **Clear old data button** | Reset DB + gallery for fresh run |
| **Dark/Light mode** | Toggle in sidebar |
| **Health-check endpoint** | `GET /api/health` |
| **Graceful shutdown** | SIGINT/SIGTERM handler preserves all state |

---

## AI Planning Document

### Planning Steps
1. **Problem decomposition** — Split into 4 concerns: detection, recognition, tracking, logging.
2. **Model selection** — YOLOv8n for speed + accuracy; InsightFace buffalo_l for SOTA ArcFace embeddings.
3. **State management** — EventRouter holds a single source of truth for active tracks.
4. **Database design** — Normalised schema with `faces` as identity table and `face_events` as event log.
5. **API design** — REST for dashboards + WebSocket for real-time pushes.
6. **Resilience** — try/except wrapping all DB writes; graceful shutdown handler preserves state.
7. **Performance** — Adaptive frame skipping auto-tunes detection frequency based on CPU load.

### Technology Choices
- **YOLOv8** — native Python API, easy frame_skip config, best speed/accuracy trade-off.
- **InsightFace ArcFace** — used instead of `face_recognition` library as required. 10× more accurate, includes age/gender estimation.
- **IoU Tracker** — lightweight, no external dependencies, DeepSort-compatible fallback.
- **PostgreSQL** — concurrent reads from API + writes from pipeline; JSON column for flexible metadata.
- **Flask-SocketIO** — battle-tested, integrates with existing Flask REST routes.
- **React** — fast, component-based, great chart.js integration.

---

## Compute Load Estimate

### CPU-only (development)
| Module | Approximate Load |
|--------|-----------------|
| YOLOv8n face detection | 15–25% single core (640px, every 2nd frame) |
| InsightFace ArcFace (ONNX CPU) | 30–50ms per face crop |
| IoU Tracker | < 5% |
| Adaptive Frame Skipper | < 1% (background thread) |
| PostgreSQL writes | negligible |
| Flask-SocketIO | < 2% |
| **Total (CPU)** | **~1–2 CPU cores @ 10–25 FPS** |

### GPU-accelerated (production)
| Module | Approximate Load |
|--------|-----------------|
| YOLOv8n (CUDA) | ~5ms/frame → 100+ FPS capable |
| InsightFace (CUDAExecutionProvider) | ~8–12ms per face |
| GPU memory | ~1.5 GB VRAM |

---

## Setup Instructions

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Node.js 18+ (for frontend build)

### 1. Clone the repository
```bash
git clone https://github.com/RakshaPA/FaceTraceAI
cd face-tracker
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure PostgreSQL
Edit `config.json` with your PostgreSQL credentials:
```json
"database": {
  "host": "localhost",
  "port": 5432,
  "name": "face_tracker",
  "user": "postgres",
  "password": "your_password"
}
```

### 4. Create the database and tables
```bash
python scripts/setup_db.py
```

### 5. Download AI models
```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
python -c "from insightface.app import FaceAnalysis; app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1); print('InsightFace OK')"
```

### 6. Build the React frontend
```bash
cd frontend
npm install
npm run build
cd ..
```

### 7. Run the system
```bash
python main.py
```

Open **http://localhost:5000** in your browser.

### 8. Upload a video
- Go to **Upload Video** tab
- Drag & drop your video file
- Click **Start Processing**
- Watch real-time results on Dashboard, Faces, Events, and Alerts tabs

### 9. For RTSP camera (interview)
Edit `config.json`:
```json
"use_rtsp": true,
"rtsp_url": "rtsp://your-camera-ip:554/stream"
```
Then run `python main.py` — no upload needed.

---

## 🔧 Sample config.json

```json
{
  "video_source": "sample_video.mp4",
  "rtsp_url": "rtsp://your-camera-ip:554/stream",
  "use_rtsp": false,

  "detection": {
    "model_path": "yolov8n.pt",
    "confidence_threshold": 0.5,
    "frame_skip": 2,
    "input_size": 640
  },

  "recognition": {
    "model_name": "buffalo_l",
    "similarity_threshold": 0.45,
    "embedding_size": 512
  },

  "tracking": {
    "max_age": 30,
    "min_hits": 3,
    "iou_threshold": 0.3
  },

  "database": {
    "host": "localhost",
    "port": 5432,
    "name": "face_tracker",
    "user": "postgres",
    "password": "your_password"
  },

  "logging": {
    "log_file": "logs/events.log",
    "image_base_dir": "logs",
    "log_level": "INFO"
  },

  "alerts": {
    "crowd_threshold": 10,
    "loitering_seconds": 30,
    "watchlist_enabled": true
  },

  "output": {
    "annotated_video": true,
    "output_video_path": "logs/annotated_output.mp4",
    "show_live_window": false
  },

  "api": {
    "host": "0.0.0.0",
    "port": 5000,
    "secret_key": "change-me-in-production"
  }
}
```

### Key config parameters

| Parameter | Description |
|-----------|-------------|
| `detection.frame_skip` | Run YOLO every N frames. Default 2. Adaptive skip overrides this at runtime. |
| `detection.confidence_threshold` | Minimum YOLO detection confidence (0–1). |
| `recognition.similarity_threshold` | Cosine similarity cutoff for face matching (0–1). |
| `tracking.max_age` | Frames a track persists without detection before deletion. |
| `alerts.crowd_threshold` | Simultaneous faces to trigger crowd alert. |
| `alerts.loitering_seconds` | Seconds in frame before loitering alert fires. |
| `use_rtsp` | Set `true` to use RTSP camera instead of video file. |

---

## Output Structure

```
logs/
├── events.log                        ← mandatory system event log
├── annotated_output.mp4              ← annotated video with bounding boxes
├── entries/
│   └── YYYY-MM-DD/
│       └── <face_uuid>_<time>.jpg    ← entry face crops
├── exits/
│   └── YYYY-MM-DD/
│       └── <face_uuid>_<time>.jpg    ← exit face crops
└── thumbnails/
    └── <face_uuid>.jpg               ← one thumbnail per registered face
```

### Sample events.log entries
```
2026-03-22 08:15:32 | INFO     | SYSTEM | Pipeline started — source: uploads/upload_0001.mp4
2026-03-22 08:15:35 | INFO     | REGISTER | face_uuid=3f8a2b1c-... | attributes={'age': 28, 'gender': 'M'}
2026-03-22 08:15:35 | INFO     | ENTRY | face_uuid=3f8a2b1c-... | conf=0.921 | frame=12 | image=logs/entries/...
2026-03-22 08:16:10 | DEBUG    | RECOGNISE | face_uuid=3f8a2b1c-... | similarity=0.847 | track_id=1
2026-03-22 08:16:45 | INFO     | EXIT | face_uuid=3f8a2b1c-... | dwell=70.2s | frame=1836 | image=logs/exits/...
2026-03-22 08:17:00 | WARNING  | ALERT | type=crowd_threshold | msg=Crowd threshold reached: 10 faces in frame
2026-03-22 08:18:10 | WARNING  | ALERT | type=loitering | msg=Loitering: face 3f8a2b1c-... in frame for 31s
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `faces` | One row per unique person — UUID, embedding, first/last seen, visit count, demographics |
| `face_events` | Every entry and exit event with timestamp, crop path, confidence, bbox |
| `dwell_records` | Entry→exit pairs with dwell time in seconds |
| `system_alerts` | Crowd, loitering, and watchlist alerts |
| `visitor_stats` | Hourly aggregated traffic data for dashboard charts |

---

##  REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | System health + gallery size |
| GET | `/api/stats` | Unique visitors, occupancy, dwell stats |
| GET | `/api/faces` | All registered faces |
| GET | `/api/events?limit=50` | Recent entry/exit events |
| GET | `/api/alerts?limit=20` | Recent system alerts |
| GET | `/api/hourly?hours=24` | Hourly traffic data for charts |
| GET | `/api/dwell` | Avg/min/max dwell time |
| GET | `/api/pipeline-status` | Current processing progress |
| GET | `/api/adaptive-skip` | Current frame skip stats |
| POST | `/api/upload` | Upload video and start processing |
| POST | `/api/stop` | Stop current pipeline |
| POST | `/api/clear` | Clear all data for fresh run |
| POST | `/api/watchlist/<uuid>` | Add/remove face from watchlist |

### WebSocket events (port 5000)
| Event | Direction | Payload |
|-------|-----------|---------|
| `face_event` | server → client | `{event_type, face_uuid, extra}` |
| `alert` | server → client | `{alert_type, message, extra}` |
| `stats` | server → client | `{unique_visitors, current_occupancy}` |
| `pipeline_status` | server → client | `{running, progress, total_frames, unique_visitors, done}` |

---

## Assumptions Made

1. **One face = one person** — Two crops are considered the same person if cosine similarity ≥ `similarity_threshold` (default 0.45).
2. **Entry = track confirmed** — A face is considered "entered" once the tracker confirms the track (≥ `min_hits` detections). Prevents false entries.
3. **Exit = track lost** — A face is "exited" when not seen for `max_age` frames.
4. **Demographics are estimates** — Age and gender from InsightFace are statistical only, never used for identification.
5. **No GPU required** — Runs on CPU by default. GPU recommended for RTSP at 25+ FPS.
6. **PostgreSQL must be running** — Run `python scripts/setup_db.py` before starting.
7. **face_recognition library NOT used** — InsightFace ArcFace is used as required by the problem statement, which is significantly more accurate.
8. **Minimum face size** — Faces smaller than 40×40 pixels are skipped to avoid poor quality embeddings.

---

*This project is a part of a hackathon run by https://katomaran.com*
