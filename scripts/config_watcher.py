"""
scripts/config_watcher.py
Watches config.json for changes and reloads tunable parameters at runtime
WITHOUT restarting the process.

Tunable at runtime (no restart needed):
  - detection.frame_skip
  - detection.confidence_threshold
  - alerts.crowd_threshold
  - alerts.loitering_seconds
  - recognition.similarity_threshold

Usage: imported and called by main.py.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """
    Polls config.json every `interval` seconds and fires callbacks
    when specified keys change.
    """

    def __init__(self, config_path: str = "config.json", interval: float = 5.0):
        self.config_path = Path(config_path)
        self.interval = interval
        self._last_mtime = 0.0
        self._callbacks: list[Callable] = []
        self._thread: threading.Thread | None = None
        self._running = False

    def register(self, callback: Callable):
        """Register a function(new_config: dict) called on change."""
        self._callbacks.append(callback)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"Config watcher started (polling every {self.interval}s).")

    def stop(self):
        self._running = False

    def _watch_loop(self):
        while self._running:
            try:
                mtime = self.config_path.stat().st_mtime
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    with open(self.config_path) as f:
                        new_cfg = json.load(f)
                    logger.info("config.json changed – reloading hot-swappable params.")
                    for cb in self._callbacks:
                        try:
                            cb(new_cfg)
                        except Exception as e:
                            logger.error(f"Config reload callback error: {e}")
            except Exception as e:
                logger.warning(f"Config watcher error: {e}")
            time.sleep(self.interval)
