"""
logging_/db_logger.py
PostgreSQL event logger.

Fixes vs v1:
  - _upsert_hourly_stats: strip timezone from datetime before DB write
  - _upsert_hourly_stats: now increments unique_visitors correctly
  - log_entry / log_exit: pass new_unique flag when it's a first-time face
  - datetime.utcnow() replaced with datetime.now(timezone.utc)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.session import session_scope
from db.models import Face, FaceEvent, DwellRecord, SystemAlert, VisitorStats

logger = logging.getLogger(__name__)


class DBLogger:

    # ------------------------------------------------------------------
    # Event logging
    # ------------------------------------------------------------------

    def log_entry(
        self,
        face_uuid: str,
        image_path: str,
        tracker_id: int,
        confidence: float,
        frame_number: int,
        bbox: Optional[tuple] = None,
        timestamp: Optional[datetime] = None,
        is_new_face: bool = False,
    ) -> Optional[int]:
        """Insert an entry FaceEvent row. Returns the new row ID."""
        ts = timestamp or datetime.now(timezone.utc)
        try:
            with session_scope() as session:
                face = session.query(Face).filter_by(face_uuid=face_uuid).first()
                if not face:
                    logger.warning(f"log_entry: face {face_uuid} not in DB, skipping.")
                    return None

                event = FaceEvent(
                    face_id=face.id,
                    face_uuid=face_uuid,
                    event_type="entry",
                    timestamp=ts,
                    image_path=image_path,
                    tracker_id=tracker_id,
                    confidence=confidence,
                    frame_number=frame_number,
                    bbox={"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]} if bbox else None,
                )
                session.add(event)
                session.flush()
                event_id = event.id

            self._upsert_hourly_stats(ts, entries_delta=1, new_unique=is_new_face)
            return event_id
        except Exception as exc:
            logger.error(f"DB log_entry error: {exc}")
            return None

    def log_exit(
        self,
        face_uuid: str,
        image_path: str,
        tracker_id: int,
        dwell_seconds: float,
        frame_number: int,
        entry_time: Optional[datetime] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[int]:
        """Insert an exit FaceEvent and a DwellRecord."""
        ts = timestamp or datetime.now(timezone.utc)
        try:
            with session_scope() as session:
                face = session.query(Face).filter_by(face_uuid=face_uuid).first()
                if not face:
                    return None

                event = FaceEvent(
                    face_id=face.id,
                    face_uuid=face_uuid,
                    event_type="exit",
                    timestamp=ts,
                    image_path=image_path,
                    tracker_id=tracker_id,
                    confidence=0.0,
                    frame_number=frame_number,
                )
                session.add(event)

                session_no = (
                    session.query(DwellRecord)
                    .filter_by(face_uuid=face_uuid)
                    .count()
                ) + 1

                dwell = DwellRecord(
                    face_id=face.id,
                    face_uuid=face_uuid,
                    entry_time=entry_time or (ts - timedelta(seconds=dwell_seconds)),
                    exit_time=ts,
                    dwell_seconds=dwell_seconds,
                    session_number=session_no,
                )
                session.add(dwell)
                session.flush()
                event_id = event.id

            self._upsert_hourly_stats(ts, exits_delta=1, dwell=dwell_seconds)
            return event_id
        except Exception as exc:
            logger.error(f"DB log_exit error: {exc}")
            return None

    def log_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning",
        face_uuid: Optional[str] = None,
        extra: Optional[dict] = None,
    ):
        try:
            with session_scope() as session:
                alert = SystemAlert(
                    alert_type=alert_type,
                    severity=severity,
                    message=message,
                    timestamp=datetime.now(timezone.utc),
                    face_uuid=face_uuid,
                    extra=extra or {},
                )
                session.add(alert)
        except Exception as exc:
            logger.error(f"DB log_alert error: {exc}")

    # ------------------------------------------------------------------
    # Queries used by API
    # ------------------------------------------------------------------

    def get_unique_visitor_count(self) -> int:
        try:
            with session_scope() as session:
                return session.query(Face).count()
        except Exception:
            return 0

    def get_recent_events(self, limit: int = 50) -> list:
        try:
            with session_scope() as session:
                rows = (
                    session.query(FaceEvent)
                    .order_by(FaceEvent.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "face_uuid": r.face_uuid,
                        "event_type": r.event_type,
                        "timestamp": r.timestamp.isoformat(),
                        "image_path": r.image_path,
                        "confidence": r.confidence,
                        "frame_number": r.frame_number,
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error(f"get_recent_events error: {exc}")
            return []

    def get_all_faces(self) -> list:
        try:
            with session_scope() as session:
                rows = session.query(Face).order_by(Face.first_seen.desc()).all()
                return [
                    {
                        "id": r.id,
                        "face_uuid": r.face_uuid,
                        "first_seen": r.first_seen.isoformat(),
                        "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                        "visit_count": r.visit_count,
                        "thumbnail_path": r.thumbnail_path,
                        "is_watchlist": r.is_watchlist,
                        "label": r.label,
                        "metadata": r.metadata_ or {},
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error(f"get_all_faces error: {exc}")
            return []

    def get_hourly_stats(self, hours: int = 24) -> list:
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
            with session_scope() as session:
                rows = (
                    session.query(VisitorStats)
                    .filter(VisitorStats.hour_bucket >= cutoff)
                    .order_by(VisitorStats.hour_bucket)
                    .all()
                )
                return [
                    {
                        "hour": r.hour_bucket.isoformat(),
                        "unique_visitors": r.unique_visitors,
                        "total_entries": r.total_entries,
                        "total_exits": r.total_exits,
                        "avg_dwell_seconds": r.avg_dwell_seconds,
                        "peak_concurrent": r.peak_concurrent,
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error(f"get_hourly_stats error: {exc}")
            return []

    def get_alerts(self, limit: int = 20) -> list:
        try:
            with session_scope() as session:
                rows = (
                    session.query(SystemAlert)
                    .order_by(SystemAlert.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    {
                        "id": r.id,
                        "alert_type": r.alert_type,
                        "severity": r.severity,
                        "message": r.message,
                        "timestamp": r.timestamp.isoformat(),
                        "face_uuid": r.face_uuid,
                        "extra": r.extra,
                        "acknowledged": r.acknowledged,
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.error(f"get_alerts error: {exc}")
            return []

    def get_dwell_stats(self) -> dict:
        try:
            with session_scope() as session:
                records = session.query(DwellRecord).filter(
                    DwellRecord.dwell_seconds.isnot(None)
                ).all()
                if not records:
                    return {"avg": 0, "min": 0, "max": 0, "count": 0}
                dwells = [r.dwell_seconds for r in records]
                return {
                    "avg": round(sum(dwells) / len(dwells), 2),
                    "min": round(min(dwells), 2),
                    "max": round(max(dwells), 2),
                    "count": len(dwells),
                }
        except Exception as exc:
            logger.error(f"get_dwell_stats error: {exc}")
            return {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upsert_hourly_stats(
        self,
        ts: datetime,
        entries_delta: int = 0,
        exits_delta: int = 0,
        dwell: Optional[float] = None,
        new_unique: bool = False,
    ):
        """Upsert the VisitorStats row for the current hour bucket."""
        try:
            # Strip timezone — PostgreSQL TIMESTAMP WITHOUT TIME ZONE column
            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
            bucket = ts_naive.replace(minute=0, second=0, microsecond=0)

            with session_scope() as session:
                row = session.query(VisitorStats).filter_by(hour_bucket=bucket).first()
                if row is None:
                    row = VisitorStats(
                        hour_bucket=bucket,
                        unique_visitors=0,
                        total_entries=0,
                        total_exits=0,
                        avg_dwell_seconds=None,
                        peak_concurrent=0,
                    )
                    session.add(row)

                row.total_entries = (row.total_entries or 0) + entries_delta
                row.total_exits = (row.total_exits or 0) + exits_delta

                # Only increment unique_visitors when a brand new face is registered
                if new_unique:
                    row.unique_visitors = (row.unique_visitors or 0) + 1

                if dwell is not None:
                    prev_avg = row.avg_dwell_seconds or 0.0
                    prev_count = max(row.total_exits or 1, 1)
                    row.avg_dwell_seconds = (prev_avg * (prev_count - 1) + dwell) / prev_count

        except Exception as exc:
            logger.error(f"_upsert_hourly_stats error: {exc}")