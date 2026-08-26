"""Reads git-tracked dashboard data straight from GitHub's `main`, so staleness in the
local checkout -- a forgotten `git pull`, or a packaged desktop bundle frozen at build
time -- never makes the dashboard under-report what the cloud automations
(paper-engine, pipeline-daily) have already committed. graveyard.csv, state/paper/*,
and artifacts/* are all written by those Actions, never by the dashboard process
itself (see tradefabe/CLAUDE.md's Automations section).

Cached for CACHE_SECONDS (TRADEFABE_REMOTE_CACHE_SECONDS, default 600 = 10min): a
dashboard page reads dozens of these files (one state/paper/*.json per book), and paying
a fresh HTTPS round trip for every one of them on every page navigation is exactly the
multi-second reload #227 traded the old "forgot to git pull" bug for. #229 first set this
to 20s, which fixed rapid back-and-forth clicking but not realistic usage -- reading a
chart for more than 20s before switching books or timeframe was enough to fall out of
cache and pay the multi-second reload again on every single action (#233). 10 minutes is
still short against the automations' own cadence (mark is hourly at the fastest, run/
factory/pipeline daily) but long enough to cover a normal browsing session, matching
Dave's own framing: "pull when we open the app", not on every click within it -- a fresh
`tradefabe-api` process (started once per desktop-app launch) gets a cold cache on
startup either way. Callers that must see a just-written row on the very next call (a
candidate the factory just drew, mid-request) pass ttl=0 -- see
_load_generated_ledger()/_load_pipeline_ledger() in dashboard.py, the same freshness
contract that caught the 2026-08-15 permanent-cache bug this doesn't repeat: THAT bug
never invalidated at all; this one self-heals within CACHE_SECONDS even if a caller
forgets to ask for ttl=0.

Falls back to the local disk copy on any network/API failure -- real-but-old over
invented, the same doctrine engine.py's price cache already applies (TRADEFABE_CACHE_HOURS).
Uses a shared requests.Session so repeat fetches reuse one TLS connection to GitHub
instead of paying a fresh handshake per file.
"""
import json
import os
import time

import requests

from tradefabe.paths import REPO_ROOT

OWNER_REPO = "dzheng1328/tradefabe"
BRANCH = "main"
TIMEOUT = 5
CACHE_SECONDS = float(os.environ.get("TRADEFABE_REMOTE_CACHE_SECONDS", 600))

_session = requests.Session()
_cache = {}  # relpath -> (fetched_at, bytes | None)


def _get(url):
    resp = _session.get(url, timeout=TIMEOUT, headers={"User-Agent": "tradefabe-dashboard"})
    resp.raise_for_status()
    return resp.content


def read_bytes(relpath, ttl=CACHE_SECONDS):
    """Bytes for relpath: GitHub main if reachable, else the local disk copy. None only
    if neither has it (never generated, or genuinely doesn't exist yet).

    ttl=0 forces a fresh fetch, bypassing the cache entirely -- for a caller that must
    reflect a write made moments ago (see the module docstring)."""
    now = time.time()
    cached = _cache.get(relpath)
    if cached is not None and ttl > 0 and now - cached[0] < ttl:
        data = cached[1]
    else:
        try:
            data = _get(f"https://raw.githubusercontent.com/{OWNER_REPO}/{BRANCH}/{relpath}")
        except (requests.RequestException, OSError):
            data = None
        _cache[relpath] = (now, data)
    if data is not None:
        return data
    local = REPO_ROOT / relpath
    return local.read_bytes() if local.exists() else None


def exists(relpath, ttl=CACHE_SECONDS):
    return read_bytes(relpath, ttl=ttl) is not None


def read_json(relpath, ttl=CACHE_SECONDS):
    data = read_bytes(relpath, ttl=ttl)
    return json.loads(data) if data is not None else None
