"""
core/tracker.py
DeepSort-based multi-object tracker wrapper.

Takes detections from the detector and returns Track objects with
stable IDs across frames.  Handles the track lifecycle (new / active /
lost / deleted) and exposes helpers used by the event router.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Try deep_sort_realtime (pip install deep-sort-realtime)
try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
    import pkg_resources  # test it works
    _DEEPSORT_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _DEEPSORT_AVAILABLE = False
    logger.warning("deep_sort_realtime not available – using simple IoU tracker fallback.")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class Track:
    """A single tracked object."""
    track_id: int
    bbox: Tuple[int, int, int, int]   # x1 y1 x2 y2
    confidence: float
    is_confirmed: bool = False
    age: int = 0                       # frames since first seen
    time_since_update: int = 0         # frames since last matched detection
    face_uuid: Optional[str] = None    # set by recognizer after matching
    extra: dict = field(default_factory=dict)

    @property
    def centroid(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)


# ---------------------------------------------------------------------------
# Fallback IoU tracker (used when deep_sort_realtime is not available)
# ---------------------------------------------------------------------------

class _SimpleTracker:
    """Minimal IoU-based tracker for environments without DeepSort."""

    def __init__(self, max_age=30, min_hits=3, iou_threshold=0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self._tracks: Dict[int, dict] = {}
        self._next_id = 1
        self._hit_streak: Dict[int, int] = {}
        self._age: Dict[int, int] = {}
        self._tsu: Dict[int, int] = {}

    def update(self, detections):
        """detections: list of [x1,y1,x2,y2,conf]"""
        active = list(self._tracks.keys())
        matched = set()

        for tid in active:
            self._tsu[tid] = self._tsu.get(tid, 0) + 1
            self._age[tid] = self._age.get(tid, 0) + 1

        for det in detections:
            x1, y1, x2, y2, conf = det
            best_iou = self.iou_threshold
            best_tid = None
            for tid, trk in self._tracks.items():
                if tid in matched:
                    continue
                iou = self._iou((x1, y1, x2, y2), trk["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_tid is not None:
                self._tracks[best_tid] = {"bbox": (x1, y1, x2, y2), "conf": conf}
                self._tsu[best_tid] = 0
                self._hit_streak[best_tid] = self._hit_streak.get(best_tid, 0) + 1
                matched.add(best_tid)
            else:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = {"bbox": (x1, y1, x2, y2), "conf": conf}
                self._tsu[tid] = 0
                self._hit_streak[tid] = 1
                self._age[tid] = 1

        # Remove stale tracks
        for tid in list(self._tracks.keys()):
            if self._tsu.get(tid, 0) > self.max_age:
                del self._tracks[tid]
                self._hit_streak.pop(tid, None)
                self._age.pop(tid, None)
                self._tsu.pop(tid, None)

        results = []
        for tid, trk in self._tracks.items():
            hits = self._hit_streak.get(tid, 0)
            results.append({
                "track_id": tid,
                "bbox": trk["bbox"],
                "conf": trk["conf"],
                "is_confirmed": hits >= self.min_hits,
                "age": self._age.get(tid, 1),
                "tsu": self._tsu.get(tid, 0),
            })
        return results

    @staticmethod
    def _iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / ua if ua > 0 else 0.0


# ---------------------------------------------------------------------------
# Public FaceTracker
# ---------------------------------------------------------------------------

class FaceTracker:
    """
    Wraps DeepSort (or the simple fallback) and converts raw output to
    a list of Track dataclass instances.
    """

    def __init__(self, max_age: int = 30, min_hits: int = 3, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self._face_uuid_map: Dict[int, str] = {}  # track_id → face_uuid

        if _DEEPSORT_AVAILABLE:
            self._tracker = DeepSort(
                max_age=max_age,
                n_init=min_hits,
                nms_max_overlap=1.0,
                max_cosine_distance=0.3,
            )
            self._use_deepsort = True
            logger.info("Using DeepSort tracker.")
        else:
            self._tracker = _SimpleTracker(max_age, min_hits, iou_threshold)
            self._use_deepsort = False
            logger.info("Using simple IoU tracker (DeepSort unavailable).")

    def update(
        self,
        detections: List[Tuple[int, int, int, int, float]],
        frame: np.ndarray,
    ) -> List[Track]:
        """
        Parameters
        ----------
        detections : list of (x1, y1, x2, y2, conf)
        frame : BGR numpy array (needed by DeepSort for appearance features)

        Returns
        -------
        list of Track
        """
        if not detections:
            if self._use_deepsort:
                raw = self._tracker.update_tracks([], frame=frame)
                return self._parse_deepsort(raw)
            else:
                return self._parse_simple(self._tracker.update([]))

        if self._use_deepsort:
            # DeepSort expects [[x1,y1,w,h], conf, class]
            ds_input = []
            for x1, y1, x2, y2, conf in detections:
                ds_input.append(([x1, y1, x2 - x1, y2 - y1], conf, 0))
            raw = self._tracker.update_tracks(ds_input, frame=frame)
            return self._parse_deepsort(raw)
        else:
            return self._parse_simple(self._tracker.update(detections))

    def assign_face_uuid(self, track_id: int, face_uuid: str):
        self._face_uuid_map[track_id] = face_uuid

    def get_face_uuid(self, track_id: int) -> Optional[str]:
        return self._face_uuid_map.get(track_id)

    # ------------------------------------------------------------------
    # Internal parsers
    # ------------------------------------------------------------------

    def _parse_deepsort(self, raw_tracks) -> List[Track]:
        tracks = []
        for t in raw_tracks:
            if not t.is_confirmed():
                continue
            ltrb = t.to_ltrb()
            x1, y1, x2, y2 = int(ltrb[0]), int(ltrb[1]), int(ltrb[2]), int(ltrb[3])
            tid = t.track_id
            tracks.append(Track(
                track_id=tid,
                bbox=(x1, y1, x2, y2),
                confidence=t.det_conf if t.det_conf is not None else 1.0,
                is_confirmed=True,
                age=t.age,
                time_since_update=t.time_since_update,
                face_uuid=self._face_uuid_map.get(tid),
            ))
        return tracks

    def _parse_simple(self, raw_tracks) -> List[Track]:
        tracks = []
        for t in raw_tracks:
            tid = t["track_id"]
            if not t["is_confirmed"]:
                continue
            tracks.append(Track(
                track_id=tid,
                bbox=t["bbox"],
                confidence=t["conf"],
                is_confirmed=True,
                age=t["age"],
                time_since_update=t["tsu"],
                face_uuid=self._face_uuid_map.get(tid),
            ))
        return tracks

    @property
    def active_track_ids(self) -> List[int]:
        return list(self._face_uuid_map.keys())
