"""
core/detector.py
YOLOv8-based face detection wrapper.

Returns bounding boxes in (x1, y1, x2, y2, confidence) format per frame.
Supports configurable frame-skip so detection doesn't run every frame,
reducing CPU/GPU load while tracking fills the gap.
"""
import logging
from pathlib import Path
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy import so the app can start even without a GPU / model downloaded
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    logger.warning("ultralytics not installed – detector will return empty results.")


class FaceDetector:
    """
    Wraps a YOLOv8 model for face detection.

    Parameters
    ----------
    model_path : str
        Path to a .pt weights file or a model name that ultralytics will
        download automatically (e.g. 'yolov8n-face.pt').
    confidence : float
        Minimum detection confidence to keep a box.
    frame_skip : int
        Run inference only every N frames (1 = every frame).
    input_size : int
        Image size passed to the model (square, e.g. 640).
    """

    def __init__(
        self,
        model_path: str = "yolov8n-face.pt",
        confidence: float = 0.5,
        frame_skip: int = 2,
        input_size: int = 640,
    ):
        self.confidence = confidence
        self.frame_skip = frame_skip
        self.input_size = input_size
        self._frame_count = 0
        self._last_detections: List[Tuple] = []
        self.model = None

        if _YOLO_AVAILABLE:
            try:
                self.model = YOLO(model_path)
                logger.info(f"YOLOv8 model loaded from '{model_path}'")
            except Exception as exc:
                logger.error(f"Failed to load YOLO model: {exc}")
        else:
            logger.error("ultralytics package missing – using dummy detector.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int, float]]:
        """
        Run face detection on a BGR frame.

        Returns
        -------
        list of (x1, y1, x2, y2, confidence)
            Empty list if frame_skip prevents inference this frame.
        """
        self._frame_count += 1

        # On skipped frames return the previous detections so tracker can
        # still use them without re-running inference.
        if self._frame_count % self.frame_skip != 0:
            return self._last_detections

        if self.model is None:
            return []

        try:
            results = self.model.predict(
                source=frame,
                imgsz=self.input_size,
                conf=self.confidence,
                verbose=False,
                device="cpu",   # swap to 0 for GPU
            )
        except Exception as exc:
            logger.error(f"YOLO inference error: {exc}")
            return self._last_detections

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                # Clamp to frame bounds
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(frame.shape[1], x2)
                y2 = min(frame.shape[0], y2)
                if x2 > x1 and y2 > y1:
                    detections.append((x1, y1, x2, y2, conf))

        self._last_detections = detections
        return detections

    def reset(self):
        """Reset internal frame counter (call when opening a new stream)."""
        self._frame_count = 0
        self._last_detections = []

    @property
    def frame_count(self) -> int:
        return self._frame_count
