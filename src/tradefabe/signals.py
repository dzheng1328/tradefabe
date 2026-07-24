"""Signal functions + live book registry for the paper engine.

Signals are defined ONCE here and imported by both the research harness (harness.py) and
the live paper books (runner.py). The sizing/returns/data math lives in engine.py.

Two signals carry a research-vs-live split that is INTENTIONAL, not un-deduplicated code:

  * turn_of_month — the research harness counts TRADING days (it always has complete
    months); the live book counts CALENDAR days, because under a trading-day count the
    current partial month always looks like "month end". See the two functions below.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .engine import (UNIVERSE, LOOKBACK, VOL_WINDOW, TARGET_VOL, MAX_LEG, MAX_GROSS,
                     COST_BPS, ANN, sized_weights)


# ---------- pure signals: prices -> signal matrix (defined once; shared research + live) ----------
def sig_tsmom_12m(prices):
    """Trend: long if the trailing 12-month return is positive, else short."""
    return np.sign(prices / prices.shift(LOOKBACK) - 1)


def sig_tsmom_ensemble(prices):
    """Trend: blend of 3/6/12-month time-series momentum."""
    sigs = [np.sign(prices / prices.shift(lb) - 1) for lb in (63, 126, 252)]
    return sum(sigs) / len(sigs)


def sig_green_line_200d(prices):
    """Trend: the Instagram-reel rule — long above the 200-day MA, short below."""
    return np.sign(prices - prices.rolling(200).mean())


def sig_xsec_momentum(prices):
    """Trend (relative): long the 12-month winners, short the losers."""
    r12 = prices / prices.shift(252) - 1
    pr  = r12.rank(axis=1, pct=True)
    return np.sign(pr - 0.5)


def sig_str_reversal(prices):
    """Mean reversion: fade the trailing 5-day move (weekly rebalance)."""
    return -np.sign(prices / prices.shift(5) - 1)


def sig_low_vol(prices):
    """Defensive anomaly (BAB-lite): long the calmer half of the universe, short the wilder half."""
    vol = prices.pct_change().rolling(60).std()
    pr  = vol.rank(axis=1, pct=True)
    return np.sign(0.5 - pr)


def sig_random(prices, rng):
    return pd.DataFrame(rng.choice([-1.0, 1.0], size=prices.shape),
                        index=prices.index, columns=prices.columns)


def sig_turn_of_month_research(prices):
    """Calendar: long during the turn-of-month window, counting TRADING days
    (first 3 + last 4). Used by the research harness, which always sees complete months."""
    df = pd.DataFrame(index=prices.index)
    df["g"]   = prices.index.to_period("M")
    df["one"] = 1
    pos      = df.groupby("g").cumcount() + 1
    tot      = df.groupby("g")["one"].transform("size")
    in_tom   = (pos <= 3) | ((tot - pos) < 4)
    sig = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    sig.loc[in_tom.values, :] = 1.0
    return sig


def sig_turn_of_month_live(prices):
    """Calendar: long during the turn-of-month window, counting CALENDAR days
    (first ~3 / last ~4). Used live — a trading-day count breaks on the current partial
    month, whose tail always looks like "month end"."""
    idx = prices.index
    in_tom = (idx.day <= 4) | (idx.day > idx.days_in_month - 6)
    sig = pd.DataFrame(0.0, index=idx, columns=prices.columns)
    sig.loc[in_tom, :] = 1.0
    return sig


# The bare name resolves to the LIVE variant — its historical meaning in this module.
sig_turn_of_month = sig_turn_of_month_live


# book name -> (signal fn, rebalance freq: "M" month-start only, "D" daily)
REGISTRY = {
    "tsmom_12m":       (sig_tsmom_12m,        "M"),
    "tsmom_ensemble":  (sig_tsmom_ensemble,   "M"),
    "green_line_200d": (sig_green_line_200d,  "M"),
    "turn_of_month":   (sig_turn_of_month_live, "D"),
}


def target_weights(prices: pd.DataFrame, name: str) -> pd.Series:
    """Today's vol-targeted, capped portfolio weights for a registered book."""
    fn, _ = REGISTRY[name]
    return sized_weights(prices, fn(prices)).iloc[-1].fillna(0.0)


def is_month_first_trading_day(idx: pd.DatetimeIndex) -> bool:
    if len(idx) < 2:
        return True
    return idx[-1].to_period("M") != idx[-2].to_period("M")
