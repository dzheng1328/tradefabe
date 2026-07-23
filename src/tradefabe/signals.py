"""Signal + sizing logic for the paper books.

Mirrors the research engine in harness.py (same math, same pre-registered specs).
Kept self-contained so the installed package has no repo-root import; unifying the
two copies is tracked on the roadmap.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
            "GLD", "SLV", "DBC", "USO", "VNQ", "UUP"]
LOOKBACK, VOL_WINDOW = 252, 60
TARGET_VOL, MAX_LEG, MAX_GROSS = 0.10, 2.0, 3.0
COST_BPS = 5.0
ANN = 252


def sig_tsmom_12m(prices: pd.DataFrame) -> pd.DataFrame:
    return np.sign(prices / prices.shift(LOOKBACK) - 1)


def sig_tsmom_ensemble(prices: pd.DataFrame) -> pd.DataFrame:
    sigs = [np.sign(prices / prices.shift(lb) - 1) for lb in (63, 126, 252)]
    return sum(sigs) / len(sigs)


def sig_green_line_200d(prices: pd.DataFrame) -> pd.DataFrame:
    return np.sign(prices - prices.rolling(200).mean())


def sig_turn_of_month(prices: pd.DataFrame) -> pd.DataFrame:
    # Calendar-based window (first ~3 / last ~4 trading days). The research harness uses
    # trading-day counts, which needs the COMPLETE month — that breaks live on the current
    # partial month (the tail of available data always looks like "month end").
    idx = prices.index
    in_tom = (idx.day <= 4) | (idx.day > idx.days_in_month - 6)
    sig = pd.DataFrame(0.0, index=idx, columns=prices.columns)
    sig.loc[in_tom, :] = 1.0
    return sig


# book name -> (signal fn, rebalance freq: "M" month-start only, "D" daily)
REGISTRY = {
    "tsmom_12m":       (sig_tsmom_12m,      "M"),
    "tsmom_ensemble":  (sig_tsmom_ensemble, "M"),
    "green_line_200d": (sig_green_line_200d, "M"),
    "turn_of_month":   (sig_turn_of_month,  "D"),
}


def target_weights(prices: pd.DataFrame, name: str) -> pd.Series:
    """Today's vol-targeted, capped portfolio weights for a registered book."""
    fn, _ = REGISTRY[name]
    sig = fn(prices)
    rv = prices.pct_change().rolling(VOL_WINDOW).std() * np.sqrt(ANN)
    raw = (sig * (TARGET_VOL / rv)).clip(-MAX_LEG, MAX_LEG) / prices.shape[1]
    gross = raw.abs().sum(axis=1)
    scale = (MAX_GROSS / gross).clip(upper=1.0).replace([np.inf, -np.inf], 1.0)
    w = raw.mul(scale, axis=0)
    return w.iloc[-1].fillna(0.0)


def is_month_first_trading_day(idx: pd.DatetimeIndex) -> bool:
    if len(idx) < 2:
        return True
    return idx[-1].to_period("M") != idx[-2].to_period("M")
