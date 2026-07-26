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
