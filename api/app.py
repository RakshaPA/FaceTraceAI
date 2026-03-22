"""
api/app.py
Flask + Flask-SocketIO REST and WebSocket API.

New endpoints vs v1:
  POST /api/upload          – upload a video file and start processing
  GET  /api/pipeline-status – current pipeline progress
  GET  /api/upload-history  – list of previously processed videos

Existing endpoints:
  GET  /api/health
  GET  /api/stats
  GET  /api/faces
  GET  /api/events
  GET  /api/alerts
  GET  /api/dwell
  GET  /api/hourly
  POST /api/watchlist/<id>

WebSocket events:
  face_event       – entry/exit
  alert            – system alert
  stats            – visitor count update
  pipeline_status  – progress of video processing
"""
import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

logger = logging.getLogger(__name__)

# Injected by main.py
_db_logger = None
_recognizer = None
_event_router = None
_config = None
_pipeline_runner = None

# Track uploaded video history
_upload_history = []
_adaptive_skipper = None
_multi_camera_manager = None

UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def create_app(config: dict) -> Flask:
    api_cfg = config.get("api", {})
    app = Flask(
        __name__,
        static_folder=str(Path(__file__).parent.parent / "frontend" / "build"),
        static_url_path="/",
    )
    app.config["SECRET_KEY"] = api_cfg.get("secret_key", "dev-secret")
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB max upload

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio.init_app(app)

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "db_connected": _db_logger is not None,
            "gallery_size": _recognizer.gallery_size() if _recognizer else 0,
            "unique_visitors": _event_router.unique_visitor_count if _event_router else 0,
            "current_occupancy": _event_router.current_occupancy if _event_router else 0,
        })

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    @app.route("/api/stats")
    def stats():
        if not _db_logger:
            return jsonify({"error": "not initialised"}), 503
        dwell = _db_logger.get_dwell_stats()
        return jsonify({
            "unique_visitors": _db_logger.get_unique_visitor_count(),
            "current_occupancy": _event_router.current_occupancy if _event_router else 0,
            "dwell": dwell,
        })

    @app.route("/api/faces")
    def faces():
        return jsonify(_db_logger.get_all_faces() if _db_logger else [])

    @app.route("/api/events")
    def events():
        limit = request.args.get("limit", 50, type=int)
        return jsonify(_db_logger.get_recent_events(limit=limit) if _db_logger else [])

    @app.route("/api/alerts")
    def alerts():
        limit = request.args.get("limit", 20, type=int)
        return jsonify(_db_logger.get_alerts(limit=limit) if _db_logger else [])

    @app.route("/api/dwell")
    def dwell():
        return jsonify(_db_logger.get_dwell_stats() if _db_logger else {})

    @app.route("/api/hourly")
    def hourly():
        hours = request.args.get("hours", 24, type=int)
        return jsonify(_db_logger.get_hourly_stats(hours=hours) if _db_logger else [])

    @app.route("/api/watchlist/<face_uuid>", methods=["POST"])
    def toggle_watchlist(face_uuid):
        if not _recognizer:
            return jsonify({"error": "not initialised"}), 503
        data = request.json or {}
        remove = data.get("remove", False)
        _recognizer.mark_watchlist(face_uuid, data.get("label", ""), remove=remove)
        return jsonify({"status": "ok", "face_uuid": face_uuid, "removed": remove})

    # -----------------------------------------------------------------------
    # Video upload + processing
    # -----------------------------------------------------------------------

    @app.route("/api/upload", methods=["POST"])
    def upload_video():
        """
        Upload a video file and start the face tracker pipeline on it.
        Returns immediately with a job ID; progress via WebSocket pipeline_status.
        """
        if _pipeline_runner is None or _config is None:
            return jsonify({"error": "Pipeline not ready"}), 503

        if "video" not in request.files:
            return jsonify({"error": "No video file in request"}), 400

        f = request.files["video"]
        if not f.filename:
            return jsonify({"error": "Empty filename"}), 400

        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Unsupported format: {ext}. Use: {ALLOWED_EXTENSIONS}"}), 400

        # Save uploaded file
        safe_name = f"upload_{len(_upload_history):04d}{ext}"
        save_path = UPLOAD_FOLDER / safe_name
        f.save(str(save_path))
        logger.info(f"Video uploaded: {save_path}")

        _upload_history.append({
            "filename": f.filename,
            "saved_as": str(save_path),
            "size_mb": round(save_path.stat().st_size / 1024 / 1024, 2),
        })

        # Reset pipeline status so frontend shows fresh progress
        emit_pipeline_status({"running": False, "done": False, "progress": 0,
                               "total_frames": 0, "unique_visitors": 0, "error": None})

        # Reset stop flag so pipeline can run again after a stop
        try:
            from core.stop_flag import stop_event
            stop_event.clear()
        except Exception:
            pass

        # Run pipeline in background thread so API stays responsive
        def _run():
            try:
                _pipeline_runner(_config, video_source=str(save_path))
            except Exception as e:
                logger.error(f"Upload pipeline error: {e}")
                emit_pipeline_status({"running": False, "error": str(e), "done": True})

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        return jsonify({
            "status": "started",
            "filename": f.filename,
            "saved_as": str(save_path),
            "message": "Processing started. Watch pipeline_status WebSocket event for progress.",
        })

    @app.route("/api/clear", methods=["POST"])
    def clear_data():
        """Clear all face data from DB and reset in-memory state for a fresh run."""
        try:
            from db.session import init_db, session_scope
            init_db()  # ensure DB is initialised before clearing
            from db.session import session_scope
            from db.models import Face, FaceEvent, DwellRecord, SystemAlert, VisitorStats
            with session_scope() as session:
                session.query(DwellRecord).delete()
                session.query(FaceEvent).delete()
                session.query(SystemAlert).delete()
                session.query(VisitorStats).delete()
                session.query(Face).delete()
            # Clear in-memory gallery
            if _recognizer:
                _recognizer._gallery.clear()
            # Reset pipeline status
            try:
                import main as main_module
                main_module._pipeline_status.update({
                    "running": False, "source": None, "progress": 0,
                    "total_frames": 0, "unique_visitors": 0,
                    "done": False, "error": None,
                })
            except Exception:
                pass
            # Notify frontend via WebSocket
            emit_pipeline_status({"running": False, "done": False,
                                   "cleared": True, "unique_visitors": 0})
            emit_stats(0, 0)
            logger.info("Database cleared via API.")
            return jsonify({"status": "cleared"})
        except Exception as e:
            logger.error(f"Clear error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/stop", methods=["POST"])
    def stop_pipeline():
        try:
            from core.stop_flag import stop_event
            stop_event.set()
            logger.info("Pipeline stop requested via API.")
            # Emit stopped — NOT done:True so frontend doesn't show 100%
            emit_pipeline_status({"running": False, "done": False,
                                   "stopped": True, "error": "Stopped by user"})
        except Exception as e:
            logger.error(f"Stop error: {e}")
        return jsonify({"status": "stopped"})

    @app.route("/api/pipeline-status")
    def pipeline_status():
        """Current pipeline progress — also emitted via WebSocket."""
        from main import _pipeline_status
        return jsonify(_pipeline_status)

    @app.route("/api/upload-history")
    def upload_history():
        return jsonify(_upload_history)


    @app.route("/api/adaptive-skip")
    def adaptive_skip():
        if _adaptive_skipper is None:
            return jsonify({"error": "not running"})
        return jsonify(_adaptive_skipper.get_stats())

    @app.route("/api/cameras")
    def cameras():
        if _multi_camera_manager is None:
            return jsonify([])
        return jsonify(_multi_camera_manager.get_status())

    @app.route("/api/cameras/global-count")
    def global_count():
        if _multi_camera_manager is None:
            return jsonify({"global_unique": 0})
        return jsonify({"global_unique": _multi_camera_manager.global_unique_count})

    @app.route("/api/multi-upload", methods=["POST"])
    def multi_upload():
        if _pipeline_runner is None or _config is None:
            return jsonify({"error": "Pipeline not ready"}), 503
        files = request.files.getlist("videos")
        if not files:
            return jsonify({"error": "No video files provided"}), 400
        saved = []
        for i, f in enumerate(files):
            ext = Path(f.filename).suffix.lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            save_path = UPLOAD_FOLDER / f"multicam_{len(_upload_history):04d}_{i}{ext}"
            f.save(str(save_path))
            saved.append({"camera_id": f"cam_{i+1:02d}", "path": str(save_path), "filename": f.filename})
            _upload_history.append({"filename": f.filename, "saved_as": str(save_path),
                                    "size_mb": round(save_path.stat().st_size / 1024 / 1024, 2)})
        if not saved:
            return jsonify({"error": "No valid video files"}), 400
        def _run():
            try:
                _pipeline_runner(_config, multi_sources=saved)
            except Exception as e:
                logger.error(f"Multi-camera pipeline error: {e}")
        threading.Thread(target=_run, daemon=True).start()
        return jsonify({"status": "started", "cameras": saved,
                        "message": f"{len(saved)} camera streams started."})

    # -----------------------------------------------------------------------
    # Serve log images
    # -----------------------------------------------------------------------

    @app.route("/logs/<path:filename>")
    def serve_log_image(filename):
        logs_dir = Path(__file__).parent.parent / "logs"
        # Normalize Windows backslashes to forward slashes
        filename = filename.replace('\\', '/').replace('\\', '/')
        # Security: prevent path traversal
        safe_path = logs_dir / filename
        try:
            return send_from_directory(str(logs_dir), filename)
        except Exception:
            from flask import abort
            abort(404)

    # -----------------------------------------------------------------------
    # Serve React SPA
    # -----------------------------------------------------------------------

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        build_dir = Path(__file__).parent.parent / "frontend" / "build"
        if path and (build_dir / path).exists():
            return send_from_directory(str(build_dir), path)
        index = build_dir / "index.html"
        if index.exists():
            return send_from_directory(str(build_dir), "index.html")
        return jsonify({"message": "Face Tracker API running. Frontend not built yet."}), 200

    return app


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

def inject_dependencies(db_logger, recognizer, event_router):
    global _db_logger, _recognizer, _event_router
    _db_logger = db_logger
    _recognizer = recognizer
    _event_router = event_router


def inject_config(config: dict):
    global _config
    _config = config


def inject_adaptive_skipper(skipper):
    global _adaptive_skipper
    _adaptive_skipper = skipper


def inject_multi_camera_manager(manager):
    global _multi_camera_manager
    _multi_camera_manager = manager


def inject_pipeline_runner(runner):
    global _pipeline_runner
    _pipeline_runner = runner


# ---------------------------------------------------------------------------
# WebSocket emitters
# ---------------------------------------------------------------------------

def emit_face_event(event_type: str, face_uuid: str, extra: dict = None):
    try:
        socketio.emit("face_event", {"event_type": event_type,
                                     "face_uuid": face_uuid, "extra": extra or {}})
    except Exception as e:
        logger.debug(f"SocketIO emit error: {e}")


def emit_alert(alert_type: str, message: str, extra: dict = None):
    try:
        socketio.emit("alert", {"alert_type": alert_type,
                                "message": message, "extra": extra or {}})
    except Exception as e:
        logger.debug(f"SocketIO alert error: {e}")


def emit_stats(unique_count: int, occupancy: int):
    try:
        socketio.emit("stats", {"unique_visitors": unique_count,
                                "current_occupancy": occupancy})
    except Exception as e:
        logger.debug(f"SocketIO stats error: {e}")


def emit_pipeline_status(status: dict):
    try:
        socketio.emit("pipeline_status", status)
    except Exception as e:
        logger.debug(f"SocketIO pipeline_status error: {e}")