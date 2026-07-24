"""Carry book risk monitor: funding-flip alert + short-leg liquidation distance.

carry_live.py accrues the book's equity as a pure funding yield -- it never models an
actual leveraged short-perp position. This module is a monitoring OVERLAY on top of
that: it asks "IF an operator ran this trade on Hyperliquid at some leverage, how much
pump-room would the short leg have before liquidation?" It does not change how the
paper book's returns are computed.

Pre-registered before looking at any live funding data (doctrine's own ethos: decide
the thresholds first, then look):

  FUNDING_ALERT_WINDOW_DAYS = 7      -- trailing window for the funding-flip alert
  LEVERAGE_FRACTIONS = 10/25/50/100% of Hyperliquid's LIVE max leverage per coin --
      stress-tested operator postures. Not a guessed absolute number: fetched from
      Hyperliquid's own margin-tier API each run, so it tracks reality if their
      leverage limits change.
  HEADLINE_LEVERAGE_FRACTION = 0.25  -- the single number used for the high-risk flag;
      a moderate, not maximal, posture.
  LIQ_DISTANCE_WARN = 0.25           -- flag high-risk if the headline posture's
      liquidation distance is under a 25% price-pump cushion. Crypto majors can move
      10-20% in a single volatile day, so 25% is a real but not extreme buffer.

Maintenance margin is derived from Hyperliquid's documented convention (maintenance =
half of initial margin, i.e. mmr = 1/(2*max_leverage)) applied to their live max-leverage
tier for our book's (small) notional size. This is Hyperliquid-specific and approximate
-- it ignores funding's effect on margin balance over time and any cross-margin
interactions. Named as an approximation, not modeled as exact.
"""
from __future__ import annotations
import datetime as dt
import json
import time

import requests

from .paths import STATE_DIR

API = "https://api.hyperliquid.xyz/info"
COINS = ["BTC", "ETH"]

FUNDING_ALERT_WINDOW_DAYS = 7
LEVERAGE_FRACTIONS = [0.10, 0.25, 0.50, 1.00]
HEADLINE_LEVERAGE_FRACTION = 0.25
LIQ_DISTANCE_WARN = 0.25


def maintenance_margin_fraction(max_leverage: float) -> float:
    """Hyperliquid's documented convention: maintenance margin = half of initial margin."""
    return 1.0 / (2.0 * max_leverage)


def liquidation_distance(leverage: float, maint_margin: float) -> float:
    """Fraction the price can rise before an isolated short position is liquidated.

    Derivation: notional N = leverage * margin M. As price moves from entry to P, the
    short's mark-to-market loss is (P/entry - 1) * N. Liquidation hits when remaining
    equity (M - loss) falls to the maintenance requirement (maint_margin * N):
        M - (P/entry - 1)*N = maint_margin*N
        P/entry - 1 = 1/leverage - maint_margin
    """
    return 1.0 / leverage - maint_margin


def margin_usage_at_pump(pump_pct: float, leverage: float, maint_margin: float) -> float:
    """Fraction of the distance-to-liquidation consumed by a given price pump. 1.0 means
    liquidated; capped there since margin usage cannot exceed 100% in this simple model."""
    dist = liquidation_distance(leverage, maint_margin)
    if dist <= 0:
        return 1.0
    return min(pump_pct / dist, 1.0)


def fetch_max_leverage(coin: str) -> float | None:
    """Live max leverage for `coin`'s base margin tier (our book's notional is always far
    under Hyperliquid's tier-drop thresholds). Returns None on any network failure --
    callers must handle a missing leverage gracefully rather than crash the daily cycle."""
    try:
        meta = requests.post(API, json={"type": "meta"}, timeout=15).json()
        asset = next((a for a in meta["universe"] if a["name"] == coin), None)
        if asset is None:
            return None
        return float(asset["maxLeverage"])
    except Exception:
        return None


def _funding_since(coin: str, start_ms: int) -> list[tuple[int, float]]:
    """Same fetch pattern as carry_live._funding_since -- duplicated rather than imported
    to keep this module independently usable (it's a monitor, not part of the accrual
    critical path) and because the two call sites want slightly different windows."""
    out, t = [], start_ms
    for _ in range(10):
        r = None
        for attempt in range(3):
            try:
                r = requests.post(API, json={"type": "fundingHistory", "coin": coin,
                                             "startTime": t}, timeout=30).json()
                if isinstance(r, list):
                    break
            except Exception:
                pass
            time.sleep(1 + attempt)
        if not isinstance(r, list) or not r:
            break
        out += [(int(x["time"]), float(x["fundingRate"])) for x in r]
        last = int(r[-1]["time"])
        if last <= t or len(r) < 500:
            break
        t = last + 1
        time.sleep(0.15)
    return out


def trailing_funding(coin: str, days: int = FUNDING_ALERT_WINDOW_DAYS) -> float | None:
    """Sum of hourly funding over the trailing `days` window -- the same accrual
    convention carry_live.py uses (funding received by the short, per period). Returns
    None on network failure."""
    now_ms = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start_ms = now_ms - days * 24 * 3600 * 1000
    try:
        pts = _funding_since(coin, start_ms)
    except Exception:
        return None
    if not pts:
        return None
    return sum(f for _, f in pts)


def check_carry_risk() -> dict:
    """Compute the full risk report for BTC + ETH and persist it to
    state/paper/carry_risk.json. Never raises -- a monitor hiccup (e.g. Hyperliquid
    unreachable) must not crash the daily paper-trading cycle."""
    per_coin = {}
    for coin in COINS:
        funding_7d = trailing_funding(coin)
        max_lev = fetch_max_leverage(coin)
        mmr = maintenance_margin_fraction(max_lev) if max_lev else None
        postures = {}
        if max_lev and mmr is not None:
            for frac in LEVERAGE_FRACTIONS:
                lev = max_lev * frac
                postures[f"{frac:.0%}"] = {
                    "leverage": round(lev, 2),
                    "liq_distance": round(liquidation_distance(lev, mmr), 4),
                }
        per_coin[coin] = {
            "funding_7d": funding_7d,
            "funding_flip_alert": (funding_7d is not None and funding_7d < 0),
            "max_leverage": max_lev,
            "maint_margin": mmr,
            "postures": postures,
        }

    blended_funding = None
    known = [v["funding_7d"] for v in per_coin.values() if v["funding_7d"] is not None]
    if known:
        blended_funding = sum(known) / len(per_coin)   # same averaging as carry_live's accrual

    headline_key = f"{HEADLINE_LEVERAGE_FRACTION:.0%}"
    high_risk = {
        coin: (headline_key in v["postures"]
               and v["postures"][headline_key]["liq_distance"] < LIQ_DISTANCE_WARN)
        for coin, v in per_coin.items()
    }

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "funding_window_days": FUNDING_ALERT_WINDOW_DAYS,
        "coins": per_coin,
        "blended_funding_7d": blended_funding,
        "blended_funding_flip_alert": (blended_funding is not None and blended_funding < 0),
        "headline_leverage_fraction": HEADLINE_LEVERAGE_FRACTION,
        "liq_distance_warn": LIQ_DISTANCE_WARN,
        "high_risk_alert": high_risk,
    }

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "carry_risk.json").write_text(json.dumps(report, indent=2))
    except Exception:
        pass
    return report
