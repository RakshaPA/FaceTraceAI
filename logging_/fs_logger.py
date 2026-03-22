"""
logging_/fs_logger.py
Filesystem logger.

Saves cropped face images to:
  logs/entries/YYYY-MM-DD/<face_uuid>_<timestamp>.jpg
  logs/exits/YYYY-MM-DD/<face_uuid>_<timestamp>.jpg

Also maintains a rotating plain-text events.log with all critical events.
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FSLogger:
    """
    Manages image crops and the mandatory events.log file.

    Parameters
    ----------
    base_dir : str
        Root directory for logs (e.g. 'logs').
    log_file : str
        Path to the text events log (e.g. 'logs/events.log').
    """

    def __init__(self, base_dir: str = "logs", log_file: str = "logs/events.log"):
        self.base_dir = Path(base_dir)
        self.log_file = Path(log_file)

        # Ensure root dirs exist
        (self.base_dir / "entries").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "exits").mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Set up a dedicated file handler for the events log
        self._file_handler = logging.FileHandler(str(self.log_file), mode="a", encoding="utf-8")
        self._file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        )
        self._event_logger = logging.getLogger("events")
        self._event_logger.addHandler(self._file_handler)
        self._event_logger.setLevel(logging.DEBUG)
        self._event_logger.propagate = False  # don't duplicate to root logger

        self._event_logger.info("=== Face Tracker Session Started ===")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_entry(
        self,
        face_uuid: str,
        face_crop: Optional[np.ndarray],
        timestamp: Optional[datetime] = None,
        confidence: float = 0.0,
        frame_number: int = 0,
    ) -> str:
        """
        Save entry crop and log the event.

        Returns
        -------
        str : Path to the saved image (empty string if save failed).
        """
        ts = timestamp or datetime.utcnow()
        img_path = self._save_crop(face_uuid, face_crop, "entries", ts)
        self._event_logger.info(
            f"ENTRY | face_uuid={face_uuid} | conf={confidence:.3f} | "
            f"frame={frame_number} | image={img_path}"
        )
        return img_path

    def log_exit(
        self,
        face_uuid: str,
        face_crop: Optional[np.ndarray],
        timestamp: Optional[datetime] = None,
        dwell_seconds: float = 0.0,
        frame_number: int = 0,
    ) -> str:
        """Save exit crop and log the event."""
        ts = timestamp or datetime.utcnow()
        img_path = self._save_crop(face_uuid, face_crop, "exits", ts)
        self._event_logger.info(
            f"EXIT  | face_uuid={face_uuid} | dwell={dwell_seconds:.1f}s | "
            f"frame={frame_number} | image={img_path}"
        )
        return img_path

    def log_registration(self, face_uuid: str, attributes: Optional[dict] = None):
        self._event_logger.info(
            f"REGISTER | face_uuid={face_uuid} | attributes={attributes}"
        )

    def log_recognition(self, face_uuid: str, similarity: float, track_id: int):
        self._event_logger.debug(
            f"RECOGNISE | face_uuid={face_uuid} | similarity={similarity:.3f} | track_id={track_id}"
        )

    def log_alert(self, alert_type: str, message: str, extra: dict = None):
        self._event_logger.warning(
            f"ALERT | type={alert_type} | msg={message} | extra={extra}"
        )

    def log_system(self, message: str, level: str = "info"):
        getattr(self._event_logger, level, self._event_logger.info)(f"SYSTEM | {message}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_crop(
        self,
        face_uuid: str,
        face_crop: Optional[np.ndarray],
        event_type: str,
        timestamp: datetime,
    ) -> str:
        """Save a face crop image and return its path."""
        date_str = timestamp.strftime("%Y-%m-%d")
        dir_path = self.base_dir / event_type / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        ts_str = timestamp.strftime("%H%M%S%f")[:12]
        filename = f"{face_uuid}_{ts_str}.jpg"
        full_path = dir_path / filename

        if face_crop is not None and face_crop.size > 0:
            try:
                cv2.imwrite(str(full_path), face_crop)
            except Exception as exc:
                logger.error(f"Failed to save crop image: {exc}")
                return ""
        else:
            # Save a blank placeholder so the log entry is consistent
            placeholder = np.zeros((64, 64, 3), dtype=np.uint8)
            cv2.imwrite(str(full_path), placeholder)

        # Always use forward slashes so browser URLs work on Windows too
        return str(full_path).replace('\\', '/')

    def close(self):
        self._event_logger.info("=== Face Tracker Session Ended ===")
        self._file_handler.close()