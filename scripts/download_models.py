"""
scripts/download_models.py
Downloads YOLOv8 face model weights and verifies InsightFace is ready.

Usage:
    python scripts/download_models.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def download_yolo_face():
    """
    Downloads yolov8n-face.pt – a YOLOv8n model fine-tuned for face detection.
    Source: derronqi/yolov8-face (Hugging Face / GitHub releases)
    """
    import urllib.request
    import os

    model_path = Path("yolov8n-face.pt")
    if model_path.exists():
        print(f"[models] {model_path} already present – skipping.")
        return

    # Primary: ultralytics hub (generic face weights)
    url = "https://github.com/derronqi/yolov8-face/releases/download/v1/yolov8n-face.pt"
    print(f"[models] Downloading yolov8n-face.pt from {url} …")
    try:
        urllib.request.urlretrieve(url, str(model_path))
        print("[models] ✅ yolov8n-face.pt downloaded.")
    except Exception as e:
        print(f"[models] ⚠️  Primary download failed: {e}")
        print("[models] Falling back to standard yolov8n.pt (lower face accuracy).")
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        print("[models] yolov8n.pt ready as fallback.")


def verify_insightface():
    print("[models] Verifying InsightFace …")
    try:
        from insightface.app import FaceAnalysis
        app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(320, 320))
        print("[models] ✅ InsightFace buffalo_l model ready.")
    except Exception as e:
        print(f"[models] ⚠️  InsightFace issue: {e}")
        print("[models] Run: pip install insightface onnxruntime")


if __name__ == "__main__":
    download_yolo_face()
    verify_insightface()
    print("\n[models] All models ready. Run: python main.py")
