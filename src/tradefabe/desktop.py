"""Native desktop window for the dashboard (macOS .app entry point).

Starts the Vite dev server and the FastAPI backend if either isn't already running,
then opens the frontend in a native WKWebView window owned by this process — so the
Dock shows tradefabe's own icon, not a browser. Closing the window stops only the
servers this process started.
"""
from __future__ import annotations
import socket
import subprocess
import time
from .paths import REPO_ROOT

FRONTEND_PORT = 5173
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

    procs = []

    if not _serving(API_PORT):
        api = REPO_ROOT / ".venv" / "bin" / "tradefabe-api"
        procs.append(subprocess.Popen(
            [str(api)], cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _wait_for(API_PORT)

    if not _serving(FRONTEND_PORT):
        procs.append(subprocess.Popen(
            ["npm", "run", "dev"], cwd=REPO_ROOT / "frontend",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        _wait_for(FRONTEND_PORT)

    webview.create_window("tradefabe lab", f"http://127.0.0.1:{FRONTEND_PORT}",
                          width=1320, height=880, min_size=(900, 600))
    try:
        webview.start()
    finally:
        for proc in procs:
            proc.terminate()


if __name__ == "__main__":
    main()
