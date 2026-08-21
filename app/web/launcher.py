from __future__ import annotations

import os
import socket
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path


def _startup_log(message: str) -> None:
    try:
        log_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VideoInspector"
        log_root.mkdir(parents=True, exist_ok=True)
        with (log_root / "startup.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    _startup_log("launcher started")
    _startup_log("importing uvicorn")
    import uvicorn

    _startup_log("importing web application")
    from app.web.lifecycle import LocalLifecycle
    from app.web.server import create_app

    configured_port = os.environ.get("VIDEO_INSPECTOR_PORT")
    try:
        port = int(configured_port) if configured_port else _available_port()
    except ValueError as exc:
        raise RuntimeError("VIDEO_INSPECTOR_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("VIDEO_INSPECTOR_PORT must be between 1 and 65535")
    url = f"http://127.0.0.1:{port}"
    _startup_log(f"starting server at {url}")
    lifecycle = LocalLifecycle()
    config = uvicorn.Config(
        create_app(lifecycle=lifecycle),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    lifecycle.attach_server(server)
    if os.environ.get("VIDEO_INSPECTOR_NO_BROWSER") != "1":
        browser_timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        browser_timer.daemon = True
        browser_timer.start()
    server.run()
    _startup_log("server stopped")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception:
        _startup_log(traceback.format_exc())
        exit_code = 1
    raise SystemExit(exit_code)
