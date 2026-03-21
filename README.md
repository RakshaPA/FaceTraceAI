# 👁️ Intelligent Face Tracker — AI Visitor Counter

> **Real-time face detection, recognition, tracking, and unique visitor counting using YOLOv8 + InsightFace + PostgreSQL + React.**

---

## 🏗️ Architecture Diagram

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
│  │  (YOLOv8)     │                 │   (DeepSort)     │             │
│  └───────────────┘                 └────────┬─────────┘             │
│         ▲ frame_skip                        │ tracks                │
│         │ (config.json)                     ▼                       │
│                                    ┌──────────────────┐             │
│                                    │  FaceEmbedder    │             │
│                                    │  (InsightFace /  │             │
│                                    │   ArcFace)       │             │
│                                    └────────┬─────────┘             │
│                                             │ embeddings            │
│                                             ▼                       │
│                                    ┌──────────────────┐             │
│                                    │  FaceRecognizer  │             │
│                                    │  (cosine sim +   │             │
│                                    │   auto-register) │             │
│                                    └────────┬─────────┘             │
│                                             │ face_uuid             │
│                                             ▼                       │
│                                    ┌──────────────────┐             │
│                                    │  EventRouter     │             │
│                                    │  entry/exit logic│             │
│                                    │  dwell tracking  │             │
│                                    │  crowd/loitering │             │
│                                    └──┬───────────────┘             │
└───────────────────────────────────────┼─────────────────────────────┘
                                        │
               ┌────────────────────────┼───────────────────────┐
               ▼                        ▼                       ▼
      ┌─────────────────┐    ┌─────────────────┐    ┌────────────────────┐
      │   FSLogger       │    │   DBLogger       │    │   Flask-SocketIO   │
      │  logs/entries/   │    │  PostgreSQL      │    │   REST API +       │
      │  logs/exits/     │    │  faces           │    │   WebSocket push   │
      │  events.log      │    │  face_events     │    │                    │
      └─────────────────┘    │  dwell_records   │    └────────┬───────────┘
                              │  system_alerts   │             │
                              │  visitor_stats   │             ▼
                              └─────────────────┘    ┌────────────────────┐
                                                       │   React Dashboard  │
                                                       │  Dashboard         │
                                                       │  Face Gallery      │
                                                       │  Event Log         │
                                                       │  Alerts            │
                                                       └────────────────────┘
```

---

## 📋 Feature List

### Mandatory (as per problem statement)
| # | Feature | Implementation |
|---|---------|----------------|
| 1 | YOLOv8 face detection | `core/detector.py` — configurable confidence + frame_skip |
| 2 | InsightFace ArcFace embeddings | `core/embedder.py` — 512-d normalised vectors |
| 3 | Auto-registration of new faces | `core/recognizer.py` — cosine similarity + UUID assignment |
| 4 | DeepSort tracking | `core/tracker.py` — stable IDs across frames |
| 5 | Entry/exit event logging | `core/event_router.py` + `logging_/fs_logger.py` |
| 6 | Cropped face images on disk | `logs/entries/YYYY-MM-DD/` and `logs/exits/YYYY-MM-DD/` |
| 7 | PostgreSQL metadata storage | `db/models.py` — faces, face_events, dwell_records |
| 8 | Mandatory events.log file | `logs/events.log` — all critical system events |
| 9 | Unique visitor count | `EventRouter.unique_visitor_count` + DB query |
| 10 | config.json with frame_skip | `config.json` — all parameters including `detection.frame_skip` |
| 11 | RTSP stream support | Toggle `use_rtsp: true` in config.json |

### Extra / Impressive Features
| Feature | Where |
|---------|-------|
| **Dwell time tracking** | `DwellRecord` table, EventRouter, dashboard chart |
| **Return visitor detection** | `visit_count` on Face row, session numbering |
| **Demographic estimation** | InsightFace age+gender → stored in `Face.metadata_` |
| **Crowd threshold alerts** | EventRouter → SystemAlert table + WebSocket toast |
| **Loitering detection** | Configurable `loitering_seconds`, fires alert |
| **Watchlist / VIP mode** | `POST /api/watchlist/<uuid>`, red border in UI |
| **Config hot-reload** | `scripts/config_watcher.py` — change params without restart |
| **React dashboard** | Live stats, hourly bar chart, face gallery, event log, alerts |
| **WebSocket live feed** | Flask-SocketIO — real-time entry/exit toasts |
| **Annotated output video** | Bounding boxes + IDs + timestamps burned into MP4 |
| **Face heatmap** | `scripts/generate_heatmap.py` — spatial density visualisation |
| **Health-check endpoint** | `GET /api/health` |
| **Graceful shutdown** | SIGINT/SIGTERM handler preserves all state |

---

## ⚡ Compute Load Estimate

### CPU-only (recommended for development)
| Module | Approximate Load |
|--------|-----------------|
| YOLOv8n face detection | 15–25% single core (640px, every 2nd frame) |
| InsightFace ArcFace (ONNX CPU) | 30–50ms per face crop |
| DeepSort tracker | < 5% |
| PostgreSQL writes | negligible |
| Flask-SocketIO | < 2% |
| **Total (CPU)** | **~1–2 CPU cores @ 15–25 FPS** |

### GPU-accelerated (production)
| Module | Approximate Load |
|--------|-----------------|
| YOLOv8n (CUDA) | ~5ms/frame → 100+ FPS capable |
| InsightFace (CUDAExecutionProvider) | ~8–12ms per face |
| GPU memory | ~1.5 GB VRAM |

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Node.js 18+ (for frontend build)
- `git`, `pip`, `npm`

### 1. Clone and install Python dependencies
```bash
git clone <your-repo-url>
cd face-tracker
pip install -r requirements.txt
```

### 2. Configure PostgreSQL
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

### 3. Create the database and tables
```bash
python scripts/setup_db.py
```

### 4. Download AI models
```bash
python scripts/download_models.py
```
This downloads `yolov8n-face.pt` and verifies InsightFace `buffalo_l`.

### 5. Add your video file
Place your video at the path set in `config.json → video_source` (default: `sample_video.mp4`).

### 6. Build the React frontend (optional but recommended)
```bash
cd frontend
npm install
npm run build
cd ..
```

### 7. Run the tracker
```bash
python main.py
```
The API will be available at **http://localhost:5000**  
Dashboard: **http://localhost:5000/**  
Health check: **http://localhost:5000/api/health**

---

## 🔧 Sample config.json

```json
{
  "video_source": "sample_video.mp4",
  "rtsp_url": "rtsp://192.168.1.100:554/stream",
  "use_rtsp": false,

  "detection": {
    "model_path": "yolov8n-face.pt",
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
    "password": "postgres"
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
    "port": 5000
  }
}
```

### Key config parameters

| Parameter | Description |
|-----------|-------------|
| `detection.frame_skip` | Run YOLO inference every N frames (1 = every frame). Higher = faster but less responsive. |
| `detection.confidence_threshold` | Minimum detection confidence (0–1). Lower catches more faces but increases false positives. |
| `recognition.similarity_threshold` | Cosine similarity cutoff for face matching (0–1). Lower = looser matching. |
| `tracking.max_age` | Frames a track can persist without a new detection before being deleted. |
| `alerts.crowd_threshold` | Number of simultaneous faces to trigger a crowd alert. |
| `alerts.loitering_seconds` | Seconds a face must remain in frame to trigger a loitering alert. |

---

## 📁 Output Structure

```
logs/
├── events.log                      ← mandatory system event log
├── annotated_output.mp4            ← annotated video output
├── heatmap.png                     ← generated by scripts/generate_heatmap.py
├── entries/
│   └── YYYY-MM-DD/
│       └── <face_uuid>_<time>.jpg  ← entry face crops
└── exits/
    └── YYYY-MM-DD/
        └── <face_uuid>_<time>.jpg  ← exit face crops
```

### Sample events.log entries
```
2024-03-21 10:15:32 | INFO     | SYSTEM | Pipeline started
2024-03-21 10:15:35 | INFO     | REGISTER | face_uuid=3f8a2b1c-... | attributes={'age': 28, 'gender': 'M'}
2024-03-21 10:15:35 | INFO     | ENTRY | face_uuid=3f8a2b1c-... | conf=0.921 | frame=12 | image=logs/entries/...
2024-03-21 10:16:10 | DEBUG    | RECOGNISE | face_uuid=3f8a2b1c-... | similarity=0.847 | track_id=1
2024-03-21 10:16:45 | INFO     | EXIT | face_uuid=3f8a2b1c-... | dwell=70.2s | frame=1836 | image=logs/exits/...
2024-03-21 10:17:00 | WARNING  | ALERT | type=crowd_threshold | msg=Crowd threshold reached: 10 faces in frame
```

---

## 🗄️ Database Schema

| Table | Purpose |
|-------|---------|
| `faces` | One row per unique person — UUID, embedding, first/last seen, visit count |
| `face_events` | Every entry and exit event with timestamp, crop path, bbox |
| `dwell_records` | Entry→exit pairs with dwell time in seconds |
| `system_alerts` | Crowd, loitering, watchlist alerts |
| `visitor_stats` | Hourly aggregated traffic data for dashboard charts |

---

## 🌐 REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | System health + gallery size |
| GET | `/api/stats` | Unique visitors, occupancy, dwell stats |
| GET | `/api/faces` | All registered faces |
| GET | `/api/events?limit=50` | Recent entry/exit events |
| GET | `/api/alerts?limit=20` | Recent system alerts |
| GET | `/api/hourly?hours=24` | Hourly traffic data for charts |
| GET | `/api/dwell` | Avg/min/max dwell time |
| POST | `/api/watchlist/<uuid>` | Add face to watchlist |

### WebSocket events (port 5000)
| Event | Direction | Payload |
|-------|-----------|---------|
| `face_event` | server → client | `{event_type, face_uuid, extra}` |
| `alert` | server → client | `{alert_type, message, extra}` |
| `stats` | server → client | `{unique_visitors, current_occupancy}` |

---

## 💡 Assumptions Made

1. **One face = one person** — The system uses InsightFace embeddings as the ground truth for identity. Two crops are considered the same person if cosine similarity ≥ `similarity_threshold`.
2. **Entry = track confirmed** — A face is considered "entered" once the tracker marks a track as confirmed (≥ `min_hits` detections). This prevents false entries from spurious detections.
3. **Exit = track deleted** — A face is considered "exited" when DeepSort removes the track (not seen for `max_age` frames).
4. **Demographics are estimates** — Age and gender from InsightFace are statistical estimates, not ground truth. Used for analytics only, never for identification.
5. **No GPU required** — The system runs on CPU by default. For RTSP streams at 25+ FPS, a GPU is recommended.
6. **PostgreSQL must be running** — The system will crash on startup if PostgreSQL is unreachable. Run `python scripts/setup_db.py` first.

---

## 📊 AI Planning Document

### Planning Steps
1. **Problem decomposition** — Split into 4 concerns: detection, recognition, tracking, logging.
2. **Model selection** — YOLOv8n-face for speed + accuracy; InsightFace buffalo_l for SOTA embeddings.
3. **State management** — EventRouter holds a single source of truth for active tracks; all other modules are stateless.
4. **Database design** — Normalised schema with `faces` as the identity table and `face_events` as the event log.
5. **API design** — REST for dashboards + WebSocket for real-time pushes.
6. **Resilience** — try/except wrapping all DB writes; graceful shutdown handler preserves state.

### Technology Choices
- **YOLOv8** over older detectors: native Python API, easy frame_skip config, best speed/accuracy trade-off.
- **InsightFace** over `face_recognition`: 10× more accurate embeddings; age/gender attributes included.
- **DeepSort** over simple IoU: handles occlusion, re-entry, consistent IDs across frames.
- **PostgreSQL** over SQLite: concurrent reads from API + writes from pipeline; JSON column for flexible metadata.
- **Flask-SocketIO** over raw WebSocket: battle-tested, integrates with existing Flask REST routes.
- **React** for dashboard: fast, component-based, great chart.js integration.

---

## 🎥 Demo Video

> **[Add your Loom / YouTube link here]**

---

## 📜 License

MIT

---

*This project is a part of a hackathon run by https://katomaran.com*
