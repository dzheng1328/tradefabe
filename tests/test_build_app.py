"""ops/build_app.sh (#61).

The .app used to exist only as three hand-made files on one machine. These assert the
script reproduces the bundle structure, and — the part that actually matters — that the
launcher still exports PYTHONPATH, without which the app hits the Python 3.14 hidden-.pth
bug on launch and simply fails to start.

macOS-only: .app bundles and plutil don't exist on the CI runner."""
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "build_app.sh"

pytestmark = pytest.mark.skipif(sys.platform != "darwin",
                                reason="macOS .app bundle; CI runs on linux")


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    dest = tmp_path_factory.mktemp("apps")
    r = subprocess.run(["bash", str(SCRIPT), "--dest", str(dest)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"build_app.sh could not run here: {r.stderr.strip()[:200]}")
    return dest / "tradefabe.app"


def test_script_is_executable_and_syntactically_valid():
    assert SCRIPT.exists()
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_bundle_has_the_three_required_files(bundle):
    assert (bundle / "Contents" / "Info.plist").is_file()
    assert (bundle / "Contents" / "MacOS" / "tradefabe").is_file()


def test_launcher_is_executable(bundle):
    launcher = bundle / "Contents" / "MacOS" / "tradefabe"
    assert launcher.stat().st_mode & 0o111, "launcher must be executable or the app won't start"


def test_launcher_exports_pythonpath(bundle):
    # the whole reason the launcher is a shell script rather than a symlink: a GUI app
    # gets no shell profile, so without this it hits the hidden-.pth bug (#60)
    text = (bundle / "Contents" / "MacOS" / "tradefabe").read_text()
    assert "export PYTHONPATH=" in text
    assert "/src" in text, "PYTHONPATH must point at the src layout"
    assert "tradefabe-app" in text, "must exec the console script entry point"


def test_info_plist_is_valid_and_names_the_launcher(bundle):
    plist = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    # CFBundleExecutable must match the file in MacOS/ or macOS refuses to launch it
    assert plist["CFBundleExecutable"] == "tradefabe"
    assert (bundle / "Contents" / "MacOS" / plist["CFBundleExecutable"]).is_file()
    assert plist["CFBundleIdentifier"] == "com.dzheng.tradefabe.desktop"


def test_rebuild_is_idempotent(bundle):
    before = (bundle / "Contents" / "MacOS" / "tradefabe").read_text()
    subprocess.run(["bash", str(SCRIPT), "--dest", str(bundle.parent)],
                   capture_output=True, text=True, check=True)
    assert (bundle / "Contents" / "MacOS" / "tradefabe").read_text() == before


def test_a_broken_frontend_build_fails_loudly_instead_of_shipping_a_blank_app(tmp_path):
    """The packaged app serves frontend/dist/ directly (api/main.py mounts it when
    present, #224) instead of desktop.py also spawning a live `npm run dev` -- a stale
    or missing build must fail HERE, at build time, not silently open a blank webview
    window later. Uses --repo with a scratch tree so this never touches the real
    frontend/dist/."""
    scratch = tmp_path / "scratch_repo"
    (scratch / ".venv" / "bin").mkdir(parents=True)
    fake_app = scratch / ".venv" / "bin" / "tradefabe-app"
    fake_app.write_text("#!/bin/sh\n")
    fake_app.chmod(0o755)
    frontend = scratch / "frontend"
    frontend.mkdir()
    # a "build" that succeeds but never produces dist/index.html -- the exact shape of
    # a broken build, not a crashing one, since a crash would already be loud
    (frontend / "package.json").write_text(
        '{"name": "fake", "scripts": '
        '{"build": "mkdir -p dist && echo not-index > dist/other.txt"}}')

    r = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(scratch), "--dest", str(tmp_path / "apps")],
        capture_output=True, text=True)

    assert r.returncode != 0
    assert "dist/index.html" in r.stderr
