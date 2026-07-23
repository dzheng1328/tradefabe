"""Native desktop window for the dashboard (macOS .app entry point).

Starts the Streamlit server if it isn't already running, then opens the UI in a
native WKWebView window owned by this process — so the Dock shows tradefabe's own
icon, not a browser. Closing the window stops the server only if we started it.
"""
from __future__ import annotations
import socket
import subprocess
import time
from .paths import REPO_ROOT

PORT = 8501


def _serving() -> bool:
    s = socket.socket()
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> None:
    import webview  # deferred: pyobjc-backed, only needed for the desktop entry

    proc = None
    if not _serving():
        streamlit = REPO_ROOT / ".venv" / "bin" / "streamlit"
        proc = subprocess.Popen(
            [str(streamlit), "run", str(REPO_ROOT / "app.py"),
             "--server.headless", "true", "--server.port", str(PORT)],
            cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if _serving():
                break
            time.sleep(0.5)

    webview.create_window("tradefabe lab", f"http://127.0.0.1:{PORT}",
                          width=1320, height=880, min_size=(900, 600))
    try:
        webview.start()
    finally:
        if proc is not None:
            proc.terminate()


if __name__ == "__main__":
    main()
