"""Native desktop window for the dashboard (macOS .app entry point).

Starts the FastAPI backend if it isn't already running, then opens its origin in a
native WKWebView window owned by this process -- so the Dock shows tradefabe's own
icon, not a browser. Closing the window stops the server only if we started it.

One process, not two: the API serves the frontend's built static assets directly
(api/main.py mounts frontend/dist/ when present), rather than this also spawning a
live `npm run dev`. ops/build_app.sh runs `npm run build` before bundling so dist/
exists by the time this ever runs. Two independently-spawned dev processes racing a
polling port check was the leading suspect for this app opening flakily (#224) -- now
there's only one process and one port to wait on.
"""
from __future__ import annotations
import socket
import subprocess
import time
from .paths import REPO_ROOT

API_PORT = 8000


def _serving(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _wait_for(port: int, attempts: int = 120) -> None:
    for _ in range(attempts):
        if _serving(port):
            return
        time.sleep(0.5)


def main() -> None:
    import webview  # deferred: pyobjc-backed, only needed for the desktop entry

    proc = None
    if not _serving(API_PORT):
        api = REPO_ROOT / ".venv" / "bin" / "tradefabe-api"
        proc = subprocess.Popen(
            [str(api)], cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _wait_for(API_PORT)

    webview.create_window("tradefabe lab", f"http://127.0.0.1:{API_PORT}",
                          width=1320, height=880, min_size=(900, 600))
    try:
        webview.start()
    finally:
        if proc is not None:
            proc.terminate()


if __name__ == "__main__":
    main()
