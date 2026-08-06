"""
rates.py -- yield-curve data infrastructure for generalizing structural carry beyond
crypto (Phase 1 of docs/superpowers/specs/2026-08-04-carry-generalization-design.md).

Same source-of-truth discipline as engine.py: this is the ONLY place that fetches or
caches yield-curve data. Mirrors engine.load_prices()'s cache -> fetch -> stale-cache ->
synthetic fallback chain and CACHE_MAX_AGE_HOURS discipline exactly, so operators don't
learn a second caching policy.

FRED's key-less CSV endpoint (fred.stlouisfed.org/graph/fredgraph.csv) needs no signup,
no API key -- confirmed live 2026-08-04: `observation_date,DGS2,DGS10,...` columns, ISO
dates, non-trading days (weekends/holidays) absent as rows entirely, and a trading day
with no observation is an EMPTY CSV field (not FRED's older "." marker -- that belongs to
a different, key-gated FRED API). pandas parses an empty field as NaN with no special
coercion needed.

DGS2/DGS10/DGS30 are Treasury's actual daily quoted par yields, not revised/modeled
economic estimates (unlike GDP or employment series) -- no vintage/revision-leak risk.
"""
from __future__ import annotations
import os
import sys
from io import StringIO

import pandas as pd
import requests

from .paths import REPO_ROOT
from .engine import START, _cache_is_fresh

RATES_SERIES = ("DGS2", "DGS10", "DGS30")
BASE = str(REPO_ROOT)
RATES_CACHE = os.path.join(BASE, "data", "yield_curve.csv")
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def load_yield_curve(series=RATES_SERIES, start=START):
    """fresh cache -> FRED -> stale cache -> synthetic. Returns (curve, source_label),
    same contract shape as engine.load_prices()."""
    os.makedirs(os.path.dirname(RATES_CACHE), exist_ok=True)
    cached = None
    if os.path.exists(RATES_CACHE):
        cached = pd.read_csv(RATES_CACHE, index_col=0, parse_dates=True)
        if _cache_is_fresh(RATES_CACHE):
            return cached, "cache"
    try:
        resp = requests.get(FRED_URL, params={"id": ",".join(series)}, timeout=10)
        resp.raise_for_status()
        raw = pd.read_csv(StringIO(resp.text), parse_dates=["observation_date"])
        raw = raw.set_index("observation_date").sort_index()
        raw.index.name = None
        raw = raw.loc[raw.index >= pd.Timestamp(start)]
        raw = raw[[c for c in series if c in raw.columns]]
        if raw.empty:
            raise RuntimeError("FRED returned no rows for the requested series/range")
        raw.to_csv(RATES_CACHE)
        return raw, "FRED"
    except Exception as e:
        if cached is not None:
            print(f"[warn] live yield-curve data unavailable ({e}); "
                  f"falling back to STALE cache.", file=sys.stderr)
            return cached, "cache (stale)"
        print(f"[warn] live yield-curve data unavailable ({e}); "
              f"generating SYNTHETIC data.", file=sys.stderr)
        return _synthetic_curve(series, start), "SYNTHETIC (do not trust the numbers)"


def _synthetic_curve(series, start):
    raise NotImplementedError("synthetic fallback added in Task 3")
