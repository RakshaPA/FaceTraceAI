"""
core/adaptive_skip.py
Adaptive Frame Skip — dynamically tunes detector.frame_skip at runtime
based on CPU load and actual FPS, without restarting the pipeline.
"""
import logging
import threading
import time
from collections import deque
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


class AdaptiveFrameSkipper:
    def __init__(self, detector, target_fps=25.0, min_skip=1, max_skip=6,
                 check_interval=3.0, cpu_high_threshold=80.0, cpu_low_threshold=40.0):
        self.detector = detector
        self.target_fps = target_fps
        self.min_skip = min_skip
        self.max_skip = max_skip
        self.check_interval = check_interval
        self.cpu_high = cpu_high_threshold
        self.cpu_low = cpu_low_threshold
        self._frame_times = deque(maxlen=60)
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self.current_fps = 0.0
        self.current_cpu = 0.0
        self.current_skip = detector.frame_skip
        self.history = []

    def record_frame(self):
        with self._lock:
            self._frame_times.append(time.monotonic())

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"AdaptiveFrameSkipper started (range {self.min_skip}-{self.max_skip})")

    def stop(self):
        self._running = False

    def get_stats(self):
        return {
            "current_skip": self.current_skip,
            "current_fps": round(self.current_fps, 1),
            "current_cpu": round(self.current_cpu, 1),
            "target_fps": self.target_fps,
            "min_skip": self.min_skip,
            "max_skip": self.max_skip,
            "history": self.history[-20:],
        }

    def _loop(self):
        while self._running:
            time.sleep(self.check_interval)
            try:
                self._adapt()
            except Exception as e:
                logger.error(f"AdaptiveFrameSkipper error: {e}")

    def _adapt(self):
        with self._lock:
            times = list(self._frame_times)
        fps = (len(times) / (times[-1] - times[0])) if len(times) >= 2 else 0.0
        cpu = psutil.cpu_percent(interval=0.5)
        skip = self.detector.frame_skip
        self.current_fps = fps
        self.current_cpu = cpu
        self.current_skip = skip
        new_skip = skip
        if cpu > self.cpu_high or (fps > 0 and fps < self.target_fps * 0.6):
            new_skip = min(skip + 1, self.max_skip)
            reason = f"high load CPU={cpu:.0f}% FPS={fps:.1f}"
        elif cpu < self.cpu_low and fps >= self.target_fps * 0.9:
            new_skip = max(skip - 1, self.min_skip)
            reason = f"low load CPU={cpu:.0f}% FPS={fps:.1f}"
        else:
            reason = "stable"
        if new_skip != skip:
            self.detector.frame_skip = new_skip
            self.current_skip = new_skip
            logger.info(f"[AdaptiveSkip] {skip} → {new_skip} | {reason}")
            self.history.append({
                "time": time.strftime("%H:%M:%S"),
                "skip": new_skip, "fps": round(fps, 1),
                "cpu": round(cpu, 1), "reason": reason,
            })