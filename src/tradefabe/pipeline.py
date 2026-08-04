"""
pipeline.py — the research pipeline's package-side primitives and promotion registry
(#177, #180).

Two things live here, both because runner.py (part of the INSTALLED package, invoked as
`tradefabe run` with no PYTHONPATH tricks) needs to reach them directly, the same reason
factory.py keeps TEMPLATES/rebuild_signal/its promotion registries in the installed
package rather than in research/factory_run.py:

  1. The primitive vocabulary (PRIMITIVES, build_signal()) -- moved here from
     research/pipeline_ideas.py (#177) so a promoted pipeline candidate's signal can be
     rebuilt in a fresh `tradefabe run` process, not just inside the research/ driver
     that proposed it. research/pipeline_ideas.py imports these from here; nothing about
     the LLM-facing proposal/validation logic moved, only the deterministic primitive ->
     signal-function mapping.
  2. The promotion registry for OOS-ALIVE pipeline candidates (#180), same shape as
     factory.py's PROMOTED_GENERATED_PATH/load_promoted_generated()/promote_generated():
     a pipeline candidate has no importable module-level signal either, so each entry
     carries its own primitive+params for build_signal() to reconstruct.
"""
from __future__ import annotations
import json

import numpy as np
import pandas as pd

from .paths import STATE_DIR
from .engine import UNIVERSE

# ---------- the primitive vocabulary (pre-registered, STRATEGIES.md) ----------
# Fixed here, reviewed once, same discipline as factory.GENERATION_RANGES: the LLM picks
# a primitive and parameters WITHIN this pre-registered space, never a new mechanism or
# code. A numeric (lo, hi) 2-tuple is a RANGE; a list or a tuple whose elements aren't
# both int/float is a CATEGORICAL choice set (see pipeline_ideas.validate_proposal()'s
# dispatch, which still owns proposal validation -- only the vocabulary itself lives here).
PRIMITIVES = {
    "pair_zscore": {
        "description": ("Mean-reversion of the z-scored log-spread between two UNIVERSE "
                        "tickers -- long-the-spread when it's unusually low, short when "
                        "unusually high, flat near the mean. A simple 1:1 log-spread, "
                        "not a regressed hedge ratio (unlike family N's pre-registered "
                        "pairs, this primitive has no dedicated calibration step of its "
                        "own -- appropriate for a cheap, general-purpose first look)."),
        "params": {"ticker_a": UNIVERSE, "ticker_b": UNIVERSE,
                   "z_window": (20, 120), "z_entry": (1.5, 3.0), "z_stop": (3.0, 6.0)},
    },
    "cross_sectional_rank": {
        "description": ("Long the top-K, short the bottom-K of the full UNIVERSE ranked "
                        "by a fixed metric over a lookback window."),
        "params": {"metric": ("momentum", "low_vol", "reversal"),
                   "lookback": (20, 252), "k": (1, 7)},
    },
    "single_asset_trend": {
        "description": ("Long/short a single ticker by the sign of its own trailing "
                        "return over a lookback window."),
        "params": {"ticker": UNIVERSE, "lookback": (20, 252)},
    },
    "static_spread_carry": {
        "description": ("A fixed, always-on long-short between two tickers -- a "
                        "structural risk-premium bet, not a mean-reversion signal."),
        "params": {"ticker_a": UNIVERSE, "ticker_b": UNIVERSE, "long_leg": ("a", "b")},
    },
}


def _sig_pair_zscore(params):
    a, b = params["ticker_a"], params["ticker_b"]
    window, entry, stop = params["z_window"], params["z_entry"], params["z_stop"]

    def sig(prices):
        spread = np.log(prices[a]) - np.log(prices[b])
        z = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()
        pos = np.zeros(len(z))
        state = 0.0
        for i, zi in enumerate(z.to_numpy()):
            if np.isnan(zi):
                state = 0.0
            elif state == 0.0:
                if -stop < zi < -entry:
                    state = 1.0
                elif entry < zi < stop:
                    state = -1.0
            elif state == 1.0:
                if zi >= 0 or zi < -stop:
                    state = 0.0
            elif state == -1.0:
                if zi <= 0 or zi > stop:
                    state = 0.0
            pos[i] = state
        pos_s = pd.Series(pos, index=z.index)
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[a] = pos_s
        out[b] = -pos_s
        return out
    return sig


def _sig_cross_sectional_rank(params):
    metric, lookback, k = params["metric"], params["lookback"], params["k"]

    def sig(prices):
        if metric == "momentum":
            score = prices / prices.shift(lookback) - 1
        elif metric == "reversal":
            score = -(prices / prices.shift(lookback) - 1)
        elif metric == "low_vol":
            score = -prices.pct_change().rolling(lookback).std()
        else:
            raise ValueError(f"unknown metric {metric!r}")
        rank = score.rank(axis=1, ascending=False)
        n = score.notna().sum(axis=1)   # per-row count -- must align on axis=0, not the
                                         # default axis=1 a bare `rank > (n - k)` would use
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[rank <= k] = 1.0
        out[rank.gt(n - k, axis=0)] = -1.0
        return out
    return sig


def _sig_single_asset_trend(params):
    ticker, lookback = params["ticker"], params["lookback"]

    def sig(prices):
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[ticker] = np.sign(prices[ticker] / prices[ticker].shift(lookback) - 1)
        return out
    return sig


def _sig_static_spread_carry(params):
    a, b = params["ticker_a"], params["ticker_b"]
    long_leg = params["long_leg"]

    def sig(prices):
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[a] = 1.0 if long_leg == "a" else -1.0
        out[b] = -1.0 if long_leg == "a" else 1.0
        return out
    return sig


_BUILDERS = {
    "pair_zscore": _sig_pair_zscore,
    "cross_sectional_rank": _sig_cross_sectional_rank,
    "single_asset_trend": _sig_single_asset_trend,
    "static_spread_carry": _sig_static_spread_carry,
}


def build_signal(primitive: str, params: dict):
    """Reconstructs a signal function from a primitive name + params -- pure and
    deterministic, so it can be rebuilt identically in a later process (research/
    pipeline_verdict.py's OOS test, or a fresh `tradefabe run` for a promoted book) the
    same way factory.rebuild_signal() reconstructs a generated candidate."""
    if primitive not in _BUILDERS:
        raise ValueError(f"unknown primitive {primitive!r}")
    return _BUILDERS[primitive](params)


def is_numeric_range(bound) -> bool:
    return (isinstance(bound, tuple) and len(bound) == 2
            and all(isinstance(b, (int, float)) and not isinstance(b, bool) for b in bound))


# ---------- promotion registry for OOS-ALIVE pipeline candidates (#180) ----------
# Separate pool from factory.PROMOTED_GENERATED_PATH by design (#180's own issue leans
# this way: "a different kind of candidate, deserve their own budget rather than
# competing with factory promotions for the same slots") and separate cap number, Dave's
# explicit call (2026-08-04): 10, not factory's 20 -- appropriate given the pipeline
# proposes at most ONE candidate/day (rate-limited by pipeline_ideas.already_proposed_
# today()) against the factory's ~20/cycle, so this pool was always going to fill far
# slower regardless of the number chosen.
PROMOTED_PIPELINE_PATH = STATE_DIR / "promoted_pipeline.json"
MAX_PIPELINE_PROMOTED = 10


def load_promoted_pipeline():
    """Every currently-promoted pipeline candidate, as full {"name", "primitive", "freq",
    "params"} dicts -- same shape as factory.load_promoted_generated(), for the same
    reason: a pipeline candidate's signal function lives in no importable module-level
    dict, so runner.py needs primitive+params here to reconstruct it via build_signal()."""
    if not PROMOTED_PIPELINE_PATH.exists():
        return []
    with open(PROMOTED_PIPELINE_PATH) as fh:
        return json.load(fh)


def promote_pipeline(spec: dict) -> None:
    """Registers a pipeline candidate (name/primitive/freq/params) as a live paper book,
    idempotent by name -- same contract as factory.promote_generated()."""
    entries = load_promoted_pipeline()
    if any(e["name"] == spec["name"] for e in entries):
        return
    entries.append({"name": spec["name"], "primitive": spec["primitive"],
                    "freq": spec["freq"], "params": spec["params"]})
    PROMOTED_PIPELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMOTED_PIPELINE_PATH, "w") as fh:
        json.dump(entries, fh, indent=1)
