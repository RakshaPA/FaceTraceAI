"""
main.py
Entry point for the Intelligent Face Tracker.

Fixes applied vs v1:
  - datetime.utcnow() replaced with datetime.now(timezone.utc)
  - crop_face: padding 10→20px, minimum face size check (40x40)
  - thumbnail_path saved to DB on first registration
  - Video upload support: POST /api/upload triggers processing
"""
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

from core.multi_camera import MultiCameraManager, CameraConfig
from core.detector import FaceDetector
from core.adaptive_skip import AdaptiveFrameSkipper
from core.multi_camera import MultiCameraManager
from core.embedder import FaceEmbedder
from core.event_router import EventRouter
from core.recognizer import FaceRecognizer
from core.tracker import FaceTracker, Track
from db.session import init_db
from logging_.db_logger import DBLogger
from logging_.fs_logger import FSLogger
import api.app as flask_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

from core.stop_flag import stop_event as _stop_event
_running = True

# Shared pipeline status — read by /api/pipeline-status endpoint
_adaptive_skip: AdaptiveFrameSkipper = None
_camera_manager: MultiCameraManager = None
_pipeline_status: dict = {
    "running": False,
    "source": None,
    "progress": 0,
    "total_frames": 0,
    "unique_visitors": 0,
    "done": False,
    "error": None,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str = "config.json") -> dict:
    with open(path) as f:
        cfg = json.load(f)
    logger.info(f"Config loaded from {path}")
    return cfg


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------

def annotate_frame(frame, tracks, recognizer, event_router, frame_number, unique_count):
    out = frame.copy()
    for track in tracks:
        x1, y1, x2, y2 = track.bbox
        face_uuid = track.face_uuid
        is_wl = recognizer.is_watchlist(face_uuid) if face_uuid else False
        colour = (0, 0, 255) if is_wl else (0, 255, 0)
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        label = f"ID:{face_uuid[-6:] if face_uuid else '?'}"
        dwell = event_router.dwell_time(track.track_id)
        if dwell is not None:
            label += f" {dwell:.0f}s"
        cv2.putText(out, label, (x1, max(y1 - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)

    for i, line in enumerate([
        f"Frame: {frame_number}",
        f"Unique: {unique_count}",
        f"In frame: {event_router.current_occupancy}",
        datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
    ]):
        cv2.putText(out, line, (10, 24 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(out, line, (10, 24 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------------------
# FIX 1 — improved crop with min size check
# ---------------------------------------------------------------------------

MIN_FACE_PX = 40  # skip faces smaller than 40×40 px

def crop_face(frame: np.ndarray, bbox: tuple, pad: int = 20) -> Optional[np.ndarray]:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    if (x2 - x1) < MIN_FACE_PX or (y2 - y1) < MIN_FACE_PX:
        return None  # too small to embed reliably
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)
    crop = frame[y1:y2, x1:x2].copy()
    return crop if crop.size > 0 else None


# ---------------------------------------------------------------------------
# FIX 3 — save thumbnail on registration
# ---------------------------------------------------------------------------

def save_thumbnail(face_uuid: str, crop: np.ndarray) -> str:
    """Save first-seen crop as permanent thumbnail. Returns path string."""
    try:
        thumb_dir = Path("logs") / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{face_uuid}.jpg"
        cv2.imwrite(str(thumb_path), crop)

        from db.session import session_scope
        from db.models import Face
        with session_scope() as session:
            face = session.query(Face).filter_by(face_uuid=face_uuid).first()
            if face:
                face.thumbnail_path = str(thumb_path)
        return str(thumb_path).replace('\\', '/')
    except Exception as e:
        logger.error(f"Thumbnail save error for {face_uuid}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Event callbacks
# ---------------------------------------------------------------------------

class EventCallbacks:
    def __init__(self, fs_logger: FSLogger, db_logger: DBLogger, frame_ref: dict):
        self.fs = fs_logger
        self.db = db_logger
        self.frame_ref = frame_ref
        self._last_crops: Dict[int, np.ndarray] = {}
        self._new_faces: set = set()  # UUIDs registered this session

    def mark_new_face(self, face_uuid: str):
        """Call from pipeline loop when a face is newly registered."""
        self._new_faces.add(face_uuid)

    def on_entry(self, track: Track, face_uuid: str):
        frame = self.frame_ref.get("frame")
        crop = crop_face(frame, track.bbox) if frame is not None else None
        if crop is not None:
            self._last_crops[track.track_id] = crop

        ts = datetime.now(timezone.utc)
        is_new = face_uuid in self._new_faces
        img_path = self.fs.log_entry(face_uuid, crop, timestamp=ts,
                                     confidence=track.confidence,
                                     frame_number=self.frame_ref.get("frame_number", 0))
        self.db.log_entry(face_uuid=face_uuid, image_path=img_path,
                          tracker_id=track.track_id, confidence=track.confidence,
                          frame_number=self.frame_ref.get("frame_number", 0),
                          bbox=track.bbox, timestamp=ts, is_new_face=is_new)
        flask_app.emit_face_event("entry", face_uuid, {"dwell": 0})

    def on_exit(self, track: Track, face_uuid: str):
        frame = self.frame_ref.get("frame")
        crop = self._last_crops.pop(track.track_id, None)
        if crop is None and frame is not None and any(track.bbox):
            crop = crop_face(frame, track.bbox)

        ts = datetime.now(timezone.utc)  # FIX 2
        dwell = track.extra.get("dwell_seconds", 0.0)
        entry_time = track.extra.get("entry_time")

        img_path = self.fs.log_exit(face_uuid, crop, timestamp=ts,
                                    dwell_seconds=dwell,
                                    frame_number=self.frame_ref.get("frame_number", 0))
        self.db.log_exit(face_uuid=face_uuid, image_path=img_path,
                         tracker_id=track.track_id, dwell_seconds=dwell,
                         frame_number=self.frame_ref.get("frame_number", 0),
                         entry_time=entry_time, timestamp=ts)
        flask_app.emit_face_event("exit", face_uuid, {"dwell": dwell})

    def on_alert(self, alert_type: str, message: str, extra: dict):
        self.fs.log_alert(alert_type, message, extra)
        self.db.log_alert(alert_type=alert_type, message=message, severity="warning",
                          face_uuid=extra.get("face_uuid"), extra=extra)
        flask_app.emit_alert(alert_type, message, extra)


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _run_multi_camera(config: dict, sources: list, db_logger: DBLogger):
    """Run multiple video sources in parallel using MultiCameraManager."""
    from core.multi_camera import MultiCameraManager
    from core.embedder import FaceEmbedder
    from core.recognizer import FaceRecognizer

    log_cfg = config["logging"]
    fs_logger = FSLogger(base_dir=log_cfg["image_base_dir"], log_file=log_cfg["log_file"])

    rec_cfg = config["recognition"]
    embedder = FaceEmbedder(model_name=rec_cfg["model_name"], ctx_id=-1)
    recognizer = FaceRecognizer(embedder=embedder,
                                similarity_threshold=rec_cfg["similarity_threshold"])

    def on_event(cam_id, evt_type, face_uuid, extra):
        flask_app.emit_face_event(evt_type, face_uuid, {**extra, "camera": cam_id})

    def on_alert(alert_type, message, extra):
        flask_app.emit_alert(alert_type, message, extra)

    manager = MultiCameraManager(
        config=config, recognizer=recognizer,
        db_logger=db_logger, fs_logger=fs_logger,
        on_event_callback=on_event, on_alert_callback=on_alert,
    )
    flask_app.inject_multi_camera_manager(manager)

    for cam in sources:
        manager.add_camera(cam["camera_id"], cam["path"])

    manager.start_all()
    logger.info(f"[MultiCam] {len(sources)} cameras running in parallel")

    # Poll and emit status every 2s
    import time
    while any(not s["done"] for s in manager.get_status()):
        flask_app.emit_pipeline_status({
            "running": True,
            "cameras": manager.get_status(),
            "global_unique": manager.global_unique_count,
            "multi_mode": True,
        })
        time.sleep(2)

    flask_app.emit_pipeline_status({
        "running": False, "done": True, "multi_mode": True,
        "cameras": manager.get_status(),
        "global_unique": manager.global_unique_count,
    })
    logger.info(f"[MultiCam] All cameras done. Global unique visitors: {manager.global_unique_count}")
    fs_logger.close()


def run_pipeline(config: dict, video_source: Optional[str] = None, multi_sources: Optional[list] = None):
    global _running, _pipeline_status

    _running = True
    _stop_event.clear()

    init_db(config)
    db_logger = DBLogger()

    # Multi-camera mode — run all sources in parallel
    if multi_sources and len(multi_sources) > 1:
        _run_multi_camera(config, multi_sources, db_logger)
        return

    log_cfg = config["logging"]
    fs_logger = FSLogger(base_dir=log_cfg["image_base_dir"], log_file=log_cfg["log_file"])

    det_cfg = config["detection"]
    detector = FaceDetector(model_path=det_cfg["model_path"],
                            confidence=det_cfg["confidence_threshold"],
                            frame_skip=det_cfg["frame_skip"],
                            input_size=det_cfg["input_size"])

    rec_cfg = config["recognition"]
    embedder = FaceEmbedder(model_name=rec_cfg["model_name"], ctx_id=-1)
    recognizer = FaceRecognizer(embedder=embedder,
                                similarity_threshold=rec_cfg["similarity_threshold"])

    trk_cfg = config["tracking"]
    tracker = FaceTracker(max_age=trk_cfg["max_age"], min_hits=trk_cfg["min_hits"],
                          iou_threshold=trk_cfg["iou_threshold"])

    # Adaptive frame skip
    global _adaptive_skip
    alert_cfg = config.get("alerts", {})
    frame_ref: dict = {"frame": None, "frame_number": 0}
    callbacks = EventCallbacks(fs_logger, db_logger, frame_ref)

    event_router = EventRouter(
        on_entry=callbacks.on_entry,
        on_exit=callbacks.on_exit,
        on_alert=callbacks.on_alert,
        crowd_threshold=alert_cfg.get("crowd_threshold", 10),
        loitering_seconds=alert_cfg.get("loitering_seconds", 30),
    )

    flask_app.inject_dependencies(db_logger, recognizer, event_router)

    # Resolve video source
    if video_source is None:
        video_source = config["rtsp_url"] if config.get("use_rtsp") else config["video_source"]

    output_cfg = config.get("output", {})
    cap = open_video(video_source)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    writer = None
    if output_cfg.get("annotated_video"):
        out_path = output_cfg.get("output_video_path", "logs/annotated_output.mp4")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_path, fourcc, fps, (frame_w, frame_h))

    track_embedding_done: set = set()

    # Adaptive frame skipping — auto-tunes detector.frame_skip
    adaptive = AdaptiveFrameSkipper(
        detector=detector,
        target_fps=25.0,
        min_skip=1,
        max_skip=6,
        cpu_high_threshold=80.0,
        cpu_low_threshold=40.0,
    )
    adaptive.start()
    flask_app.inject_adaptive_skipper(adaptive)
    frame_number = 0

    _pipeline_status.update({"running": True, "source": str(video_source),
                              "progress": 0, "total_frames": total_frames,
                              "unique_visitors": 0, "done": False, "error": None})

    # Emit immediately so frontend shows total_frames right away
    flask_app.emit_pipeline_status(_pipeline_status)

    logger.info("=== Pipeline running. Press Ctrl+C to stop. ===")
    fs_logger.log_system(f"Pipeline started — source: {video_source}")

    try:
        while _running and not _stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                logger.info("End of video stream.")
                break

            frame_number += 1
            frame_ref["frame"] = frame
            frame_ref["frame_number"] = frame_number

            adaptive.record_frame()  # track FPS for adaptive skip
            # Adaptive skip: dynamically update detector's frame_skip
            if _adaptive_skip:
                new_skip = _adaptive_skip.tick(len(event_router.active_face_uuids))
                detector.frame_skip = new_skip

            detections = detector.detect(frame)
            tracks = tracker.update(detections, frame)

            for track in tracks:
                if track.track_id in track_embedding_done:
                    continue
                if tracker.get_face_uuid(track.track_id):
                    track.face_uuid = tracker.get_face_uuid(track.track_id)
                    continue

                crop = crop_face(frame, track.bbox)  # FIX 1
                if crop is None:
                    continue  # too small, skip — no anon_ ID assigned

                face_uuid, is_new, similarity, attributes = recognizer.identify(crop)
                tracker.assign_face_uuid(track.track_id, face_uuid)
                track.face_uuid = face_uuid
                track_embedding_done.add(track.track_id)

                if is_new:
                    fs_logger.log_registration(face_uuid, attributes)
                    save_thumbnail(face_uuid, crop)  # FIX 3
                    callbacks.mark_new_face(face_uuid)  # tell entry callback it's new
                else:
                    fs_logger.log_recognition(face_uuid, similarity, track.track_id)

            event_router.update(tracks, frame_number)

            annotated = annotate_frame(frame, tracks, recognizer, event_router,
                                       frame_number, event_router.unique_visitor_count)
            if writer:
                writer.write(annotated)

            if output_cfg.get("show_live_window", False):
                cv2.imshow("Face Tracker", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if frame_number % 30 == 0:
                flask_app.emit_stats(event_router.unique_visitor_count,
                                     event_router.current_occupancy)
                _pipeline_status["progress"] = frame_number
                _pipeline_status["unique_visitors"] = event_router.unique_visitor_count
                flask_app.emit_pipeline_status(_pipeline_status)

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        _pipeline_status["error"] = str(e)
    finally:
        _running = False
        adaptive.stop()
        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()
        fs_logger.close()
        unique = event_router.unique_visitor_count
        logger.info(f"Session complete. Unique visitors: {unique}")
        _pipeline_status.update({"running": False, "done": True,
                                  "unique_visitors": unique, "progress": frame_number})
        flask_app.emit_pipeline_status(_pipeline_status)


def open_video(source: str):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source}")
    logger.info(f"Video source opened: {source}")
    return cap


# ---------------------------------------------------------------------------
# Signal handler
# ---------------------------------------------------------------------------

def _handle_signal(signum, frame):
    global _running
    logger.info(f"Signal {signum} — shutting down.")
    _running = False
    _stop_event.set()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    config = load_config("config.json")
    api_cfg = config.get("api", {})
    app = flask_app.create_app(config)

    # Give Flask access to config + pipeline runner for upload endpoint
    flask_app.inject_config(config)
    flask_app.inject_pipeline_runner(run_pipeline)

    def _run_flask():
        flask_app.socketio.run(app,
                               host=api_cfg.get("host", "0.0.0.0"),
                               port=api_cfg.get("port", 5000),
                               debug=False, use_reloader=False, log_output=False)

    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"API server started on http://0.0.0.0:{api_cfg.get('port', 5000)}")
    logger.info("Waiting for video upload via dashboard. No auto-processing on startup.")

    # Keep main thread alive — pipeline runs only when a video is uploaded via /api/upload
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down.")