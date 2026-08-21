from __future__ import annotations

import threading
import time
from typing import Any


class LocalLifecycle:
    """Coordinates browser presence with the lifetime of the local web server."""

    def __init__(self, startup_timeout: float = 60.0, heartbeat_timeout: float = 15.0) -> None:
        self.startup_timeout = startup_timeout
        self.heartbeat_timeout = heartbeat_timeout
        self._first_heartbeat = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._last_heartbeat: float | None = None
        self._server: Any = None
        self._manager: Any = None
        self._shutdown_requested = False
        self._monitor: threading.Thread | None = None

    def attach_server(self, server: Any) -> None:
        with self._lock:
            self._server = server

    def start(self, manager: Any) -> None:
        with self._lock:
            self._manager = manager
            if self._monitor is not None:
                return
            self._monitor = threading.Thread(
                target=self._monitor_loop,
                name="video-inspector-lifecycle",
                daemon=True,
            )
            self._monitor.start()

    def record_heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = time.monotonic()
        self._first_heartbeat.set()

    def request_shutdown(self, reason: str = "requested") -> bool:
        with self._lock:
            if self._shutdown_requested:
                return False
            self._shutdown_requested = True
            manager = self._manager
            server = self._server
        self._stop.set()
        if manager is not None:
            manager.cancel_all()
        if server is not None:
            server.should_exit = True
        return True

    def stop(self) -> None:
        self._stop.set()
        monitor = self._monitor
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=2)
        self._monitor = None

    def _monitor_loop(self) -> None:
        startup_deadline = time.monotonic() + self.startup_timeout
        while not self._first_heartbeat.is_set():
            remaining = startup_deadline - time.monotonic()
            if remaining <= 0:
                self.request_shutdown("browser did not connect")
                return
            if self._stop.wait(min(0.25, remaining)):
                return

        while not self._stop.wait(0.25):
            with self._lock:
                last_heartbeat = self._last_heartbeat
            if last_heartbeat is not None and time.monotonic() - last_heartbeat >= self.heartbeat_timeout:
                self.request_shutdown("browser heartbeat timeout")
                return
