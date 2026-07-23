"""Repo-anchored paths (package lives in src/tradefabe, state/artifacts at repo root)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "state" / "paper"
ARTIFACTS = REPO_ROOT / "artifacts"
