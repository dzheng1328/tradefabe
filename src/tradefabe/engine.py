"""
engine.py — the extracted research/paper engine core: data, sizing, returns, stats.

Single source of truth for the config parameters and the sizing/returns math that the
research scripts (harness.py, tsmom_backtest.py, combine.py) and the live paper books
(signals.py, runner.py) all build on. Before this module existed, the same math lived in
three places; now it lives here once. See DOCTRINE.md for why the parameters are frozen.

Paper only.
"""
from __future__ import annotations
import os
import sys
import numpy as np
import pandas as pd

from .paths import REPO_ROOT

# ------------------------------------------------------------------ CONFIG (frozen; see DOCTRINE.md)
UNIVERSE   = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
              "GLD", "SLV", "DBC", "USO", "VNQ", "UUP"]  # ~15 markets for real breadth
START      = "2007-01-01"
LOOKBACK   = 252        # ~12 months, the canonical TSMOM signal (do NOT tune this)
VOL_WINDOW = 60         # trailing window for volatility targeting
TARGET_VOL = 0.10       # annualized vol budget per sleeve
MAX_LEG    = 2.0        # cap per-asset leverage
MAX_GROSS  = 3.0        # cap total gross exposure
COST_BPS   = 5.0        # per-side slippage in bps, charged on turnover (pessimistic)
LONG_SHORT = True       # canonical TSMOM is long/short
SPLIT_DATE = "2018-01-01"   # everything on/after this date is OUT-OF-SAMPLE
BENCH_W    = {"SPY": 0.60, "IEF": 0.40}     # the fair 60/40 benchmark's own weights
BENCH      = "SPY"
ANN        = 252

BASE       = str(REPO_ROOT)                              # repo root: data/ and artifacts/ live here
DATA_CACHE = os.path.join(BASE, "data", "prices.csv")


def load_prices():
    """cache -> yfinance -> synthetic fallback. Returns (prices, source_label)."""
    os.makedirs(os.path.dirname(DATA_CACHE), exist_ok=True)
    if os.path.exists(DATA_CACHE):
        px = pd.read_csv(DATA_CACHE, index_col=0, parse_dates=True)
        return px.dropna(how="all"), "cache"
    try:
        import yfinance as yf
        raw = yf.download(UNIVERSE, start=START, auto_adjust=True, progress=False, threads=False)
        px = raw["Close"]
        px = px[[c for c in UNIVERSE if c in px.columns]]
        px = px.dropna(axis=1, how="all")          # drop tickers that failed to download...
        dropped = [t for t in UNIVERSE if t not in px.columns]
        if dropped:                                # ...loudly, so N is sized to real data
            print(f"[warn] no data for {dropped}; proceeding with {list(px.columns)}", file=sys.stderr)
        px = px.dropna(how="all")
        if px.shape[0] < 500 or px.shape[1] < 4:
            raise RuntimeError("insufficient data returned from yfinance")
        px.to_csv(DATA_CACHE)
        return px, "yfinance"
    except Exception as e:  # offline / sandbox fallback so the pipeline still runs end-to-end
        print(f"[warn] live data unavailable ({e}); generating SYNTHETIC data.", file=sys.stderr)
        return _synthetic_prices(), "SYNTHETIC (do not trust the numbers)"


def _synthetic_prices():
    """Correlated GBM so the machinery can be smoke-tested with no network."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(START, periods=ANN * 17)
    n = len(UNIVERSE)
    drift = rng.uniform(0.02, 0.09, n) / ANN
    vol   = rng.uniform(0.10, 0.25, n) / np.sqrt(ANN)
    mkt   = rng.normal(0, 1, len(idx))            # shared factor -> realistic correlation
    beta  = rng.uniform(0.2, 1.0, n)
    rets  = np.zeros((len(idx), n))
    for i in range(n):
        idio = rng.normal(0, 1, len(idx))
        rets[:, i] = drift[i] + vol[i] * (beta[i] * mkt + np.sqrt(max(1 - beta[i] ** 2, 0)) * idio)
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=UNIVERSE)


def stats(r):
    r = r.dropna()
    if len(r) < 30:
        return {k: np.nan for k in ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD"]}
    eq = (1 + r).cumprod()
    cagr    = eq.iloc[-1] ** (ANN / len(r)) - 1
    vol     = r.std() * np.sqrt(ANN)
    sharpe  = r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan
    dn      = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(ANN) if dn > 0 else np.nan
    maxdd   = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": maxdd}


def calmar(s):
    m = s["MaxDD"]
    return s["CAGR"] / abs(m) if (m and np.isfinite(m) and m != 0) else np.nan


# ---------- shared sizing + engine (identical for every strategy, incl. the null) ----------
def realized_vol(prices):
    return prices.pct_change().rolling(VOL_WINDOW).std() * np.sqrt(ANN)


def _reb_mask(index, freq):
    """True on days the book may change: 'D' daily, 'W' weekly, 'M' monthly."""
    if freq == "D":
        return pd.Series(True, index=index)
    per = pd.Series(index.to_period(freq), index=index)
    return per.ne(per.shift(1))


def sized_weights(prices, signal, rv=None):
    """Vol-targeted, per-asset-capped, gross-capped weights — the sizing shared by the
    full-history backtest (size_and_rebalance) and the live single-day book
    (signals.target_weights). No rebalance calendar is applied here; callers add it."""
    if rv is None:
        rv = realized_vol(prices)
    raw   = (signal * (TARGET_VOL / rv)).clip(-MAX_LEG, MAX_LEG)
    w     = raw / prices.shape[1]
    gross = w.abs().sum(axis=1)
    scale = (MAX_GROSS / gross).clip(upper=1.0).replace([np.inf, -np.inf], 1.0)
    return w.mul(scale, axis=0)


def size_and_rebalance(prices, signal, freq="M", rv=None):
    w = sized_weights(prices, signal, rv)
    m = _reb_mask(prices.index, freq)
    mask = pd.DataFrame(np.tile(m.values.reshape(-1, 1), (1, w.shape[1])),
                        index=w.index, columns=w.columns)
    return w.where(mask).ffill().fillna(0.0)


def net_returns(prices, w):
    rets   = prices.pct_change()
    w_exec = w.shift(1)                        # execute next day: no lookahead
    gross  = (w_exec * rets).sum(axis=1)
    cost   = w_exec.diff().abs().sum(axis=1) * (COST_BPS / 1e4)
    return (gross - cost).dropna()
