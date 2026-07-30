"""The repo must not live under an iCloud-synced tree (moved 2026-07-26).

Two incidents came out of `~/Documents/tradefabe` being inside macOS's "Desktop &
Documents Folders" sync: iCloud stamped the venv's `.pth` files with the `hidden` flag
(Python 3.14's `site` skips those, so `import tradefabe` broke after a clean install,
#60), and it wrote `"<name> 2.<ext>"` conflict copies of TRACKED files -- one of which
was a duplicate of the paper-engine workflow that GitHub registered as a second live
workflow, double-billing Actions minutes and double-committing the ledger.

The venv was moved out first; that fixed only half of it, because tracked files were
still exposed. The repo itself now lives at `~/tradefabe`, with a compatibility symlink
left at the old path so every hardcoded reference keeps resolving.

macOS-only: the sync directories don't exist on the CI runner, and the physical path
there is `/home/runner/work/...`, so the assertion would be vacuous."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFLICT_COPY = re.compile(r" \d+(\.[A-Za-z0-9]+)?$")   # "paper-engine 2.yml", ".venv 3"

pytestmark = pytest.mark.skipif(sys.platform != "darwin",
                                reason="iCloud sync dirs are macOS-only; CI runs on linux")

SYNCED = ("Documents", "Desktop")


def test_repo_is_not_inside_an_icloud_synced_tree():
    # Path.resolve() already followed the compatibility symlink, so this checks where the
    # files really are, not the path we happened to be invoked through.
    home = Path.home()
    for name in SYNCED:
        synced = home / name
        assert not REPO.is_relative_to(synced), (
            f"repo resolves to {REPO}, inside {synced} -- iCloud will stamp hidden flags "
            f"on the venv and write '<name> 2.<ext>' copies of tracked files")


def test_the_venv_is_not_inside_an_icloud_synced_tree():
    venv = (REPO / ".venv").resolve()
    if not venv.exists():
        pytest.skip("no .venv here")
    for name in SYNCED:
        assert not venv.is_relative_to(Path.home() / name), f"venv resolves to {venv}"


def test_build_app_bakes_the_physical_path_not_the_symlink():
    # a launcher built through ~/Documents/tradefabe would route the app back through the
    # synced path even though the repo itself moved
    text = (REPO / "ops" / "build_app.sh").read_text()
    assert 'pwd -P' in text, "build_app.sh must resolve REPO with `pwd -P`"
    assert '&& pwd)"' not in text, "a bare `pwd` would bake the symlinked path in"


def test_no_icloud_conflict_copies_are_tracked():
    # same pattern the CI guard in tests.yml greps for; here it fails fast, before a push
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    dupes = [f for f in out.stdout.splitlines() if CONFLICT_COPY.search(f)]
    assert not dupes, f"iCloud conflict copies are tracked: {dupes}"
