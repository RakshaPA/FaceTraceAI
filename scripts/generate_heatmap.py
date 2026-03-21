"""
scripts/generate_heatmap.py
Generates a face-position heatmap from logged FaceEvent bounding-box data.

Usage:
    python scripts/generate_heatmap.py --width 1920 --height 1080 --output logs/heatmap.png

Reads bbox JSON from the face_events table and overlays a heat gradient
on a blank canvas the same size as the source video frame.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.session import init_db
from db.models import FaceEvent


def generate_heatmap(width: int, height: int, output: str):
    init_db()

    from db.session import session_scope

    heat = np.zeros((height, width), dtype=np.float32)

    with session_scope() as session:
        events = session.query(FaceEvent).filter(FaceEvent.bbox.isnot(None)).all()

    if not events:
        print("[heatmap] No events with bbox data found.")
        return

    for ev in events:
        bbox = ev.bbox
        if not isinstance(bbox, dict):
            continue
        x1, y1, x2, y2 = bbox.get("x1",0), bbox.get("y1",0), bbox.get("x2",0), bbox.get("y2",0)
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
        if 0 <= cx < width and 0 <= cy < height:
            cv2.circle(heat, (cx, cy), radius=40, color=1.0, thickness=-1)

    # Blur and normalise
    heat = cv2.GaussianBlur(heat, (101, 101), 0)
    if heat.max() > 0:
        heat = heat / heat.max()

    heat_uint8 = (heat * 255).astype(np.uint8)
    coloured = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_JET)

    # Blend onto dark background
    bg = np.zeros((height, width, 3), dtype=np.uint8)
    result = cv2.addWeighted(bg, 0.3, coloured, 0.7, 0)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(output, result)
    print(f"[heatmap] Saved to {output} ({len(events)} events plotted)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", default="logs/heatmap.png")
    args = parser.parse_args()
    generate_heatmap(args.width, args.height, args.output)
