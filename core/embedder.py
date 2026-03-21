"""
core/embedder.py
InsightFace face embedding generator.

Extracts 512-d normalised facial embeddings from cropped face images.
Also exposes attribute estimation (age, gender) for analytics.
"""
import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import insightface
    from insightface.app import FaceAnalysis
    _INSIGHTFACE_AVAILABLE = True
except ImportError:
    _INSIGHTFACE_AVAILABLE = False
    logger.warning("insightface not installed – embedder will return zero vectors.")


class FaceEmbedder:
    """
    Generates facial embeddings and (optionally) demographic attributes
    using InsightFace's ArcFace backbone.

    Parameters
    ----------
    model_name : str
        InsightFace model pack name, e.g. 'buffalo_l'.
    ctx_id : int
        -1 for CPU, 0+ for GPU device index.
    """

    EMBEDDING_SIZE = 512

    def __init__(self, model_name: str = "buffalo_l", ctx_id: int = -1):
        self.model_name = model_name
        self.ctx_id = ctx_id
        self._app = None

        if _INSIGHTFACE_AVAILABLE:
            try:
                self._app = FaceAnalysis(
                    name=model_name,
                    allowed_modules=["detection", "recognition", "genderage"],
                    providers=["CPUExecutionProvider"] if ctx_id < 0 else ["CUDAExecutionProvider"],
                )
                self._app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                logger.info(f"InsightFace model '{model_name}' loaded (ctx_id={ctx_id}).")
            except Exception as exc:
                logger.error(f"InsightFace init error: {exc}")
                self._app = None
        else:
            logger.error("insightface package missing.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_embedding(
        self, face_crop: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Generate a normalised embedding for a BGR face crop.

        Returns
        -------
        np.ndarray of shape (512,) or None if inference fails.
        """
        if self._app is None or face_crop is None or face_crop.size == 0:
            return None

        try:
            faces = self._app.get(face_crop)
            if not faces:
                return None
            # Pick the face with the largest bbox area
            face = max(faces, key=lambda f: self._bbox_area(f.bbox))
            emb = face.embedding
            if emb is None:
                return None
            norm = np.linalg.norm(emb)
            return emb / norm if norm > 0 else emb
        except Exception as exc:
            logger.error(f"Embedding error: {exc}")
            return None

    def get_attributes(
        self, face_crop: np.ndarray
    ) -> Optional[dict]:
        """
        Return estimated age and gender for analytics dashboards.
        NOT used for identification, purely statistical.

        Returns
        -------
        dict with keys 'age' (int), 'gender' ('M'|'F') or None.
        """
        if self._app is None or face_crop is None or face_crop.size == 0:
            return None
        try:
            faces = self._app.get(face_crop)
            if not faces:
                return None
            face = max(faces, key=lambda f: self._bbox_area(f.bbox))
            age = getattr(face, "age", None)
            gender_val = getattr(face, "gender", None)
            gender = "M" if gender_val == 1 else "F" if gender_val == 0 else None
            return {"age": int(age) if age is not None else None, "gender": gender}
        except Exception:
            return None

    def get_embedding_and_attributes(
        self, face_crop: np.ndarray
    ) -> Tuple[Optional[np.ndarray], Optional[dict]]:
        """Convenience method returning (embedding, attributes) in one pass."""
        if self._app is None or face_crop is None or face_crop.size == 0:
            return None, None
        try:
            faces = self._app.get(face_crop)
            if not faces:
                return None, None
            face = max(faces, key=lambda f: self._bbox_area(f.bbox))
            emb = face.embedding
            if emb is not None:
                norm = np.linalg.norm(emb)
                emb = emb / norm if norm > 0 else emb
            age = getattr(face, "age", None)
            gender_val = getattr(face, "gender", None)
            gender = "M" if gender_val == 1 else "F" if gender_val == 0 else None
            attrs = {"age": int(age) if age is not None else None, "gender": gender}
            return emb, attrs
        except Exception as exc:
            logger.error(f"Embedding+attributes error: {exc}")
            return None, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_area(bbox) -> float:
        if bbox is None:
            return 0.0
        x1, y1, x2, y2 = bbox[:4]
        return max(0.0, float((x2 - x1) * (y2 - y1)))

    @staticmethod
    def serialize(embedding: np.ndarray) -> bytes:
        """Convert embedding to bytes for DB storage."""
        return embedding.astype(np.float32).tobytes()

    @staticmethod
    def deserialize(data: bytes) -> np.ndarray:
        """Convert bytes from DB back to numpy array."""
        return np.frombuffer(data, dtype=np.float32)
