"""
core/stop_flag.py
Shared stop flag — imported by both main.py and api/app.py
so they reference the exact same threading.Event object.
"""
import threading
stop_event = threading.Event()