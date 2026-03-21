"""
core/event_router.py
Determines entry / exit events from track lifecycle changes and
dispatches them to the logging and alerting subsystems.

Also handles:
  - Dwell time tracking
  - Return-visitor detection
  - Loitering detection
  - Crowd threshold alerts
  - Watchlist face alerts
"""
import logging
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

from core.tracker import Track

logger = logging.getLogger(__name__)


class EventRouter:
    """
    Maintains state about which tracks are currently in frame and fires
    entry / exit callbacks when that state changes.

    Parameters
    ----------
    on_entry : Callable[[Track, str], None]
        Called with (track, face_uuid) when a face enters the scene.
    on_exit : Callable[[Track, str], None]
        Called with (track, face_uuid) when a face leaves the scene.
    on_alert : Callable[[str, str, dict], None]
        Called with (alert_type, message, extra) for system alerts.
    crowd_threshold : int
        Fire a crowd alert when simultaneous faces ≥ this value.
    loitering_seconds : float
        Fire a loitering alert when a face stays longer than this.
    """

    def __init__(
        self,
        on_entry: Callable,
        on_exit: Callable,
        on_alert: Callable,
        crowd_threshold: int = 10,
        loitering_seconds: float = 30.0,
    ):
        self.on_entry = on_entry
        self.on_exit = on_exit
        self.on_alert = on_alert
        self.crowd_threshold = crowd_threshold
        self.loitering_seconds = loitering_seconds

        # track_id → (face_uuid, entry_time)
        self._active: Dict[int, tuple] = {}

        # face_uuids seen in the current session (for unique count)
        self._seen_uuids: Set[str] = set()

        # track_ids that already fired a loitering alert this session
        self._loitering_alerted: Set[int] = set()

        # crowd alert cooldown (seconds between repeat alerts)
        self._last_crowd_alert: Optional[datetime] = None
        self._crowd_alert_cooldown = 60.0

    # ------------------------------------------------------------------
    # Main update – call once per frame
    # ------------------------------------------------------------------

    def update(self, tracks: List[Track], frame_number: int = 0):
        """
        Diff the current track list against the previous active set,
        firing entry / exit events for changes.
        """
        current_ids = {t.track_id: t for t in tracks}

        # --- Entries -------------------------------------------------------
        for tid, track in current_ids.items():
            if tid not in self._active and track.face_uuid:
                self._active[tid] = (track.face_uuid, datetime.utcnow())
                self._seen_uuids.add(track.face_uuid)
                logger.info(f"ENTRY  track={tid} face={track.face_uuid}")
                self.on_entry(track, track.face_uuid)

        # --- Exits ---------------------------------------------------------
        exited_ids = set(self._active.keys()) - set(current_ids.keys())
        for tid in exited_ids:
            face_uuid, entry_time = self._active.pop(tid)
            # Build a minimal track object for the exit callback
            exit_track = Track(
                track_id=tid,
                bbox=(0, 0, 0, 0),
                confidence=0.0,
                face_uuid=face_uuid,
            )
            dwell = (datetime.utcnow() - entry_time).total_seconds()
            exit_track.extra["dwell_seconds"] = dwell
            exit_track.extra["entry_time"] = entry_time
            logger.info(f"EXIT   track={tid} face={face_uuid} dwell={dwell:.1f}s")
            self.on_exit(exit_track, face_uuid)

        # --- Loitering check -----------------------------------------------
        now = datetime.utcnow()
        for tid, (face_uuid, entry_time) in self._active.items():
            dwell = (now - entry_time).total_seconds()
            if dwell >= self.loitering_seconds and tid not in self._loitering_alerted:
                self._loitering_alerted.add(tid)
                msg = f"Loitering: face {face_uuid} in frame for {dwell:.0f}s"
                logger.warning(msg)
                self.on_alert("loitering", msg, {"face_uuid": face_uuid, "dwell_seconds": dwell})

        # --- Crowd threshold check -----------------------------------------
        crowd = len(self._active)
        if crowd >= self.crowd_threshold:
            if (
                self._last_crowd_alert is None
                or (now - self._last_crowd_alert).total_seconds() > self._crowd_alert_cooldown
            ):
                self._last_crowd_alert = now
                msg = f"Crowd threshold reached: {crowd} faces in frame"
                logger.warning(msg)
                self.on_alert("crowd_threshold", msg, {"count": crowd})

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def unique_visitor_count(self) -> int:
        return len(self._seen_uuids)

    @property
    def current_occupancy(self) -> int:
        return len(self._active)

    @property
    def active_face_uuids(self) -> List[str]:
        return [v[0] for v in self._active.values()]

    def dwell_time(self, track_id: int) -> Optional[float]:
        if track_id in self._active:
            _, entry_time = self._active[track_id]
            return (datetime.utcnow() - entry_time).total_seconds()
        return None
