"""
core/recognizer.py
Cosine-similarity face recognizer with auto-registration.

Maintains an in-memory gallery of known embeddings and matches
incoming embeddings against it.  Unknown faces are automatically
registered and persisted to PostgreSQL.
"""
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.embedder import FaceEmbedder
from db.session import session_scope
from db.models import Face

logger = logging.getLogger(__name__)


class FaceRecognizer:
    """
    Matches embeddings against a registered gallery using cosine similarity.

    Parameters
    ----------
    embedder : FaceEmbedder
        Used to generate embeddings and attributes for new faces.
    similarity_threshold : float
        Min cosine similarity to consider two faces the same person.
        Range [0, 1]; typical production value ~0.45–0.55.
    """

    def __init__(self, embedder: FaceEmbedder, similarity_threshold: float = 0.45):
        self.embedder = embedder
        self.threshold = similarity_threshold

        # In-memory gallery: face_uuid → embedding (np.ndarray)
        self._gallery: Dict[str, np.ndarray] = {}

        # Load existing faces from DB on startup
        self._load_gallery()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def identify(
        self, face_crop: np.ndarray
    ) -> Tuple[str, bool, float, Optional[dict]]:
        """
        Identify a face crop.

        Returns
        -------
        face_uuid : str
        is_new : bool   – True if this is a first-time registration
        similarity : float
        attributes : dict or None  – age/gender from InsightFace
        """
        embedding, attributes = self.embedder.get_embedding_and_attributes(face_crop)

        if embedding is None:
            # Can't generate embedding – return a temporary anonymous ID
            anon_id = f"anon_{uuid.uuid4().hex[:8]}"
            logger.warning(f"Could not generate embedding; assigned temporary ID {anon_id}")
            return anon_id, False, 0.0, None

        # Try to match against gallery
        face_uuid, similarity = self._match(embedding)

        if face_uuid is not None:
            # Known face – update last_seen and return
            self._update_last_seen(face_uuid)
            logger.debug(f"Recognised face {face_uuid} (similarity={similarity:.3f})")
            return face_uuid, False, similarity, attributes

        # New face – register
        face_uuid = self._register(embedding, face_crop, attributes)
        logger.info(f"New face registered: {face_uuid}")
        return face_uuid, True, 1.0, attributes

    def get_embedding(self, face_uuid: str) -> Optional[np.ndarray]:
        return self._gallery.get(face_uuid)

    def gallery_size(self) -> int:
        return len(self._gallery)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def _match(self, embedding: np.ndarray) -> Tuple[Optional[str], float]:
        """
        Brute-force cosine similarity search across the in-memory gallery.
        Returns (face_uuid, similarity) of best match or (None, 0.0).
        """
        if not self._gallery:
            return None, 0.0

        best_uuid = None
        best_sim = -1.0

        for uid, stored_emb in self._gallery.items():
            sim = float(np.dot(embedding, stored_emb))
            if sim > best_sim:
                best_sim = sim
                best_uuid = uid

        if best_sim >= self.threshold:
            return best_uuid, best_sim
        return None, best_sim

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register(
        self,
        embedding: np.ndarray,
        face_crop: np.ndarray,
        attributes: Optional[dict],
    ) -> str:
        """Create a new Face record in the DB and add to gallery."""
        face_uuid = str(uuid.uuid4())
        serialised = FaceEmbedder.serialize(embedding)

        meta = {}
        if attributes:
            meta.update(attributes)

        with session_scope() as session:
            face = Face(
                face_uuid=face_uuid,
                first_seen=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                visit_count=1,
                embedding=serialised,
                metadata_=meta,
            )
            session.add(face)

        # Add to in-memory gallery
        self._gallery[face_uuid] = embedding
        return face_uuid

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_gallery(self):
        """Load all registered faces from DB into memory."""
        try:
            with session_scope() as session:
                faces = session.query(Face).all()
                for face in faces:
                    try:
                        emb = FaceEmbedder.deserialize(face.embedding)
                        if emb is not None and len(emb) > 0:
                            self._gallery[face.face_uuid] = emb
                    except Exception as e:
                        logger.warning(f"Could not deserialise embedding for {face.face_uuid}: {e}")
            logger.info(f"Gallery loaded with {len(self._gallery)} known faces.")
        except Exception as exc:
            logger.error(f"Failed to load gallery from DB: {exc}")

    def _update_last_seen(self, face_uuid: str):
        try:
            with session_scope() as session:
                face = session.query(Face).filter_by(face_uuid=face_uuid).first()
                if face:
                    face.last_seen = datetime.utcnow()
                    face.visit_count = (face.visit_count or 0) + 1
        except Exception as exc:
            logger.error(f"DB update error for {face_uuid}: {exc}")

    def mark_watchlist(self, face_uuid: str, label: str = ""):
        """Mark a face as part of the watchlist."""
        try:
            with session_scope() as session:
                face = session.query(Face).filter_by(face_uuid=face_uuid).first()
                if face:
                    face.is_watchlist = True
                    face.label = label
        except Exception as exc:
            logger.error(f"Watchlist update error: {exc}")

    def is_watchlist(self, face_uuid: str) -> bool:
        try:
            with session_scope() as session:
                face = session.query(Face).filter_by(face_uuid=face_uuid).first()
                return bool(face and face.is_watchlist)
        except Exception:
            return False
