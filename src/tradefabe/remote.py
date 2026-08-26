"""Reads git-tracked dashboard data straight from GitHub's `main`, so staleness in the
local checkout -- a forgotten `git pull`, or a packaged desktop bundle frozen at build
time -- never makes the dashboard under-report what the cloud automations
(paper-engine, pipeline-daily) have already committed. graveyard.csv, state/paper/*,
and artifacts/* are all written by those Actions, never by the dashboard process
itself (see tradefabe/CLAUDE.md's Automations section).

Deliberately UNCACHED, same reasoning as load_paper_state()/_load_generated_ledger() in
dashboard.py: a freshly-committed row (a candidate the factory just drew, a verdict the
pipeline just logged) must show up on the very next request, not after some TTL expires --
that class of bug already bit this dashboard once (2026-08-15) from an in-process
@functools.cache with no invalidation. One small file per call is cheap enough not to
need caching.

Falls back to the local disk copy on any network/API failure -- real-but-old over
invented, the same doctrine engine.py's price cache already applies (TRADEFABE_CACHE_HOURS).
"""
import json
import urllib.error
import urllib.request

from tradefabe.paths import REPO_ROOT

OWNER_REPO = "dzheng1328/tradefabe"
BRANCH = "main"
TIMEOUT = 5


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tradefabe-dashboard"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def read_bytes(relpath):
    """Bytes for relpath: GitHub main if reachable, else the local disk copy. None only
    if neither has it (never generated, or genuinely doesn't exist yet)."""
    try:
        return _get(f"https://raw.githubusercontent.com/{OWNER_REPO}/{BRANCH}/{relpath}")
    except (urllib.error.URLError, OSError, TimeoutError):
        pass
    local = REPO_ROOT / relpath
    return local.read_bytes() if local.exists() else None


def exists(relpath):
    return read_bytes(relpath) is not None


def read_json(relpath):
    data = read_bytes(relpath)
    return json.loads(data) if data is not None else None
