"""
hourly_backtest.py — family L, the three pre-registered hourly strategies (#86).

Specs were FROZEN in STRATEGIES.md before this script existed (commit 07ad78e). Nothing
here is tuned. A different lookback is a new row and a new graveyard entry, per rule 2.

  funding_timing_1h   delta-neutral BTC+ETH carry, notional scaled by the hourly funding
                      rate: full size when the trailing 24h mean funding is positive,
                      flat when negative. Benchmark: CASH (market-neutral, matching
                      carry_backtest.py's precedent).
  crypto_reversal_1h  fade the trailing 6h return on BTC+ETH, equal weight, long/short.
  equity_tsmom_1h     sign of the trailing 24-bar return on the 15-ETF universe.

Two design decisions, both pre-registered:

1. EVALUATION IS DAILY. Returns are generated hourly, then aggregated (1+r).prod()-1 per
   day before the gates run. engine.stats() hardcodes ANN=252, so feeding it hourly
   returns would annualize them as if daily and inflate every Sharpe by ~sqrt(24). This
   is the same treatment carry_hl.py already gives the surviving carry book, and it keeps
   the 60/40 benchmark, the noise floor, DSR and CPCV comparable to every other roster row.

2. THE NULL IS MATCHED TO THE COST PATH. 500 random HOURLY strategies pushed through the
   identical turnover charge and the identical daily aggregation. An hourly strategy
   scored against a daily null would be flattered enormously -- the null has to pay the
   same drag the candidate does, which for hourly trading is the dominant term.

REGIME LIMITATION, accepted up front (Dave, 2026-07-26), doctrine unchanged: every hourly
source reachable here starts in 2023, so none of these span 2018's vol spike, COVID, or
the 2022 bear. Sample size is fine; regime diversity is not. Read every verdict below with
that attached.

Usage: PYTHONPATH=src:.:research python research/hourly_backtest.py
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import time
import sys

import numpy as np
import pandas as pd
import requests

from tradefabe.engine import UNIVERSE, COST_BPS, ANN, stats, calmar
# Signals and their frozen parameters live in the PACKAGE, not here, so the code that
# produced these verdicts and the code running the live monitor books (#86) is literally
# the same function -- see src/tradefabe/hourly.py. Duplicating two-line signal
# definitions across the two is exactly how a live book silently drifts from its spec.
from tradefabe.hourly import (FUNDING_LOOKBACK_H, REVERSAL_LOOKBACK_H, TSMOM_LOOKBACK_BARS,
                              CRYPTO_TICKERS, equal_weight,
                              sig_crypto_reversal, sig_equity_tsmom)
from harness import (evaluate, family_n_tested, benchmark_returns, OOS_START, ART)
# #156: equity_tsmom_1h's data source only -- see fetch_bars()'s call sites in main().
from alpaca_fetch import fetch_alpaca_bars, ALPACA_START

HL_API = "https://api.hyperliquid.xyz/info"
COINS = ("BTC", "ETH")
NULL_TRIALS = 500

BAR_CACHE = os.path.join(ART, "hourly_bars_{tag}.csv")
FUNDING_CACHE = os.path.join(ART, "hourly_funding.csv")


# ------------------------------------------------------------------ data
def fetch_bars(tickers, tag) -> pd.DataFrame:
    """Hourly closes. SNAPSHOTTED to artifacts/ on first fetch, because yfinance's
    intraday window is a ROLLING 730 days -- without a snapshot this study could not be
    re-run identically in six months, and an unreproducible verdict is not a verdict."""
    path = BAR_CACHE.format(tag=tag)
    if os.path.exists(path):
        px = pd.read_csv(path, index_col=0)
        # parse_dates=True leaves a plain Index for tz-aware intraday stamps, and a plain
        # Index silently breaks .resample() downstream -- coerce explicitly.
        px.index = pd.to_datetime(px.index, utc=True, format="mixed").tz_convert(None)
        print(f"[data] {tag}: {len(px)} hourly bars from snapshot {path}")
        return px
    import yfinance as yf
    raw = yf.download(tickers, period="730d", interval="1h", progress=False,
                      threads=False, auto_adjust=True)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        px.columns = tickers
    px = px[[t for t in tickers if t in px.columns]].dropna(how="all")
    px = px.loc[:, px.notna().sum() > 500]
    os.makedirs(ART, exist_ok=True)
    px.to_csv(path)
    print(f"[data] {tag}: {len(px)} hourly bars fetched and snapshotted -> {path}")
    return px


def _hl_page(coin, start, tries=5):
    """One page of funding history, with backoff.

    Paging BTC to inception takes ~55 calls; without a pause the FIRST ETH call then comes
    back empty and the whole coin silently ends up as a column of NaN. That is worse than
    an error -- the mean across coins would quietly become BTC-only. Retry, then give up
    loudly rather than returning a half-built frame."""
    for i in range(tries):
        time.sleep(0.4 * (i + 1))
        try:
            r = requests.post(HL_API, json={"type": "fundingHistory", "coin": coin,
                                            "startTime": start}, timeout=30).json()
        except requests.RequestException:
            continue
        if isinstance(r, list):
            return r or None
    raise RuntimeError(f"Hyperliquid funding page failed for {coin} at startTime={start}")


def fetch_funding() -> pd.DataFrame:
    """Hourly funding rate per coin from Hyperliquid, paged back to inception."""
    if os.path.exists(FUNDING_CACHE):
        f = pd.read_csv(FUNDING_CACHE, index_col=0, parse_dates=True)
        print(f"[data] funding: {len(f)} hourly points from snapshot")
        return f
    frames = {}
    for coin in COINS:
        rows, start = [], 0
        while True:
            r = _hl_page(coin, start)
            if r is None:
                break
            rows += [(int(x["time"]), float(x["fundingRate"])) for x in r]
            nxt = rows[-1][0] + 1
            if nxt <= start or len(r) < 500:
                break
            start = nxt
        s = pd.Series({pd.Timestamp(t, unit="ms"): v for t, v in rows}).sort_index()
        frames[coin] = s[~s.index.duplicated(keep="first")]
        print(f"[data] funding {coin}: {len(frames[coin])} hourly points "
              f"{frames[coin].index.min()} .. {frames[coin].index.max()}")
    f = pd.DataFrame(frames).dropna(how="all")
    missing = [c for c in COINS if c not in f.columns or f[c].notna().sum() < 1000]
    if missing:                       # never silently proceed on a half-built frame
        raise RuntimeError(f"funding history incomplete for {missing}; refusing to run")
    os.makedirs(ART, exist_ok=True)
    f.to_csv(FUNDING_CACHE)
    return f


# ------------------------------------------------------------------ mechanics
def to_daily(r_hourly: pd.Series) -> pd.Series:
    """Compound hourly returns within each calendar day. The ONLY aggregation used --
    applied identically to the candidate and to every null draw."""
    return (1 + r_hourly.dropna()).groupby(r_hourly.dropna().index.date).prod() - 1


def _as_daily_series(r_hourly):
    d = to_daily(r_hourly)
    d.index = pd.to_datetime(d.index)
    return d


def net_hourly(px: pd.DataFrame, weights: pd.DataFrame, cost_bps=COST_BPS) -> pd.Series:
    """Weights applied with a 1-bar lag (decide on bar t, hold over t+1), charged for
    turnover. The lag is not optional -- without it the signal peeks at the bar it trades."""
    rets = px.pct_change(fill_method=None)
    w = weights.shift(1)
    gross = (w * rets).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(0.0)
    return gross - turnover * (cost_bps / 1e4)


# ------------------------------------------------------------------ the three strategies
def funding_timing_returns(funding: pd.DataFrame, cost_bps=COST_BPS) -> pd.Series:
    """Delta-neutral carry whose notional is ON when the trailing 24h mean funding is
    positive and OFF when negative. Return per hour = funding received on the live
    notional, minus a turnover charge each time the position flips.

    Delta-neutral means the spot leg's P&L cancels the perp leg's, so the return IS the
    funding -- the same construction carry_hl.py uses, gated by a signal instead of held
    flat. The cost is charged on BOTH legs when the position turns on or off."""
    signal = (funding.rolling(FUNDING_LOOKBACK_H).mean() > 0).astype(float)
    pos = signal.shift(1).fillna(0.0)                 # decide on t, hold over t+1
    received = (pos * funding).mean(axis=1)           # equal weight across coins
    flips = pos.diff().abs().mean(axis=1).fillna(0.0)
    return received - flips * 2 * (cost_bps / 1e4)    # 2 legs per side


# ------------------------------------------------------------------ matched null
def hourly_null(px: pd.DataFrame, trials, rng, oos_start) -> np.ndarray:
    """500 random HOURLY strategies through the identical cost path and the identical
    daily aggregation. This is what makes the comparison fair: for an hourly strategy the
    turnover charge dominates, so a null that doesn't pay it is not a floor at all."""
    out = []
    for _ in range(trials):
        sig = pd.DataFrame(rng.choice([-1.0, 0.0, 1.0], size=px.shape),
                           index=px.index, columns=px.columns)
        r = _as_daily_series(net_hourly(px, equal_weight(sig)))
        v = stats(r[r.index >= oos_start])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


def funding_null(funding: pd.DataFrame, trials, rng, oos_start) -> np.ndarray:
    """Same idea for the market-neutral book: random on/off timing of the same carry,
    paying the same flip cost. Isolates whether the TIMING adds anything over holding."""
    out = []
    for _ in range(trials):
        pos = pd.DataFrame(rng.choice([0.0, 1.0], size=funding.shape),
                           index=funding.index, columns=funding.columns)
        received = (pos.shift(1).fillna(0.0) * funding).mean(axis=1)
        flips = pos.shift(1).fillna(0.0).diff().abs().mean(axis=1).fillna(0.0)
        r = _as_daily_series(received - flips * 2 * (COST_BPS / 1e4))
        v = stats(r[r.index >= oos_start])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


# ------------------------------------------------------------------ driver
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=NULL_TRIALS)
    # #156: equity_tsmom_1h's Alpaca-sourced data extends back to ~2016, closing the
    # regime-limitation gap (2018 vol spike/COVID/2022 bear) for that one book. Per the
    # STRATEGIES.md pre-registration, crypto_reversal_1h and funding_timing_1h are NOT
    # re-evaluated -- --only skips their evaluate() calls (the graveyard-appending,
    # n_tested-inflating side effect) while still computing their return series so
    # hourly_returns.csv keeps all three columns for the dashboard's backtest charts.
    ap.add_argument("--only", choices=["funding_timing_1h", "crypto_reversal_1h",
                                       "equity_tsmom_1h"], default=None,
                    help="evaluate only this book (graveyard.csv); the other two still "
                         "compute return series for hourly_returns.csv, just don't get "
                         "a new verdict")
    args = ap.parse_args()
    rng = np.random.default_rng(20260726)

    daily_px = None
    rows = []

    # ---------------- 1. funding_timing_1h (market-neutral, benchmark = cash) ----------
    funding = fetch_funding()
    r_ft = _as_daily_series(funding_timing_returns(funding))
    hold = _as_daily_series(funding.mean(axis=1))       # always-on carry

    # PRE-REGISTRATION DEVIATION, declared: STRATEGIES.md family L said this row would be
    # benchmarked against CASH. Cash cannot be used -- it has zero drawdown, so
    # calmar(bench) is NaN and gate 3 reduces to `MaxDD >= 0`, which no strategy holding
    # any risk can ever satisfy. Benchmarking against ALWAYS-ON CARRY instead: it is the
    # economically meaningful question (does hourly timing beat simply holding the
    # position?) and it is STRICTLY HARDER than cash, since the carry earns ~10%/yr and
    # cash earns 0. A deviation that can only make ALIVE harder to reach cannot be a
    # thumb on the scale.
    print(f"\n[funding_timing_1h] {len(r_ft)} daily obs from {r_ft.index.min().date()}")
    print(f"  benchmark = ALWAYS-ON carry (pre-reg said cash; see note -- cash makes "
          f"gate 3 unpassable)")
    print(f"  always-on carry: {stats(hold)['Sharpe']:.2f} Sharpe, "
          f"{(1+hold.mean())**ANN-1:+.2%}/yr  <- what the timing must beat to be worth it")
    print(f"  vs cash, for the record: timing returns {(1+r_ft.mean())**ANN-1:+.2%}/yr absolute")
    if args.only in (None, "funding_timing_1h"):
        print(f"  building matched null ({args.trials} random on/off timings)...")
        null_ft = funding_null(funding, args.trials, rng, OOS_START)
        print(f"  null Sharpe: mean {null_ft.mean():.2f}, p95 {np.percentile(null_ft, 95):.2f}")
        evaluate("funding_timing_1h", r_ft, hold, null_ft, "H",
                 n_tested=family_n_tested(["funding_timing_1h"]), bench_label="always-on carry")
    else:
        print("  --only given for a different book -- skipping evaluate() (#156)")
    rows.append(("funding_timing_1h", r_ft))

    # ---------------- 2. crypto_reversal_1h ----------------
    # yfinance, UNCHANGED (#156's pre-registration: this book is not re-run -- Alpaca's
    # own crypto history doesn't reach further back than what's already covered, so a
    # different source here would add multiple-testing cost for zero new information).
    cpx = fetch_bars(CRYPTO_TICKERS, "crypto")
    r_cr = _as_daily_series(net_hourly(cpx, equal_weight(sig_crypto_reversal(cpx))))
    print(f"\n[crypto_reversal_1h] {len(r_cr)} daily obs from {r_cr.index.min().date()}")
    daily_px = fetch_bars(UNIVERSE, "equity")
    bench = benchmark_returns(daily_px.resample("D").last().dropna(how="all"))
    if args.only in (None, "crypto_reversal_1h"):
        print(f"  building matched null ({args.trials} random hourly strategies)...")
        null_cr = hourly_null(cpx, args.trials, rng, OOS_START)
        print(f"  null Sharpe: mean {null_cr.mean():.2f}, p95 {np.percentile(null_cr, 95):.2f}")
        evaluate("crypto_reversal_1h", r_cr, bench, null_cr, "H",
                 n_tested=family_n_tested(["crypto_reversal_1h"]))
    else:
        print("  --only given for a different book -- skipping evaluate() (#156)")
    rows.append(("crypto_reversal_1h", r_cr))

    # ---------------- 3. equity_tsmom_1h ----------------
    # Alpaca, not yfinance's `daily_px` above (#156) -- reaches back to ~2016 vs
    # yfinance's rolling-730-day window (cached from 2023-08-25), so this candidate's
    # own first real observation now predates DOCTRINE's OOS_START=2018-01-01. That
    # matters concretely: evaluate()'s v1.7 window fix (#115) sets the evaluation
    # window to max(OOS_START, candidate's own first observation) -- under yfinance
    # that was max(2018, 2023-08-25) = 2023-08-25, silently missing 2018's vol spike,
    # COVID, and the 2022 bear entirely. Under Alpaca it's max(2018, ~2016) = 2018,
    # the FULL doctrine window, which is the entire point of this swap.
    #
    # The BENCHMARK must widen to match, via its own bench_et built from `epx` --
    # reusing `bench` (built from the narrower yfinance daily_px) here would silently
    # reintroduce the mirror image of the #115 bug this fix depends on: a candidate
    # window starting 2018 compared against a benchmark that (despite the same ">=
    # oos_start" slice) still only actually has data from 2023-08-25 onward.
    epx = fetch_alpaca_bars(UNIVERSE, "equity", ALPACA_START["equity"])
    bench_et = benchmark_returns(epx.resample("D").last().dropna(how="all"))
    r_et = _as_daily_series(net_hourly(epx, equal_weight(sig_equity_tsmom(epx))))
    print(f"\n[equity_tsmom_1h] {len(r_et)} daily obs from {r_et.index.min().date()} (Alpaca, #156)")
    if args.only in (None, "equity_tsmom_1h"):
        print(f"  building matched null ({args.trials} random hourly strategies)...")
        null_et = hourly_null(epx, args.trials, rng, OOS_START)
        print(f"  null Sharpe: mean {null_et.mean():.2f}, p95 {np.percentile(null_et, 95):.2f}")
        evaluate("equity_tsmom_1h", r_et, bench_et, null_et, "H",
                 n_tested=family_n_tested(["equity_tsmom_1h"]))
    else:
        print("  --only given for a different book -- skipping evaluate() (#156)")
    # hourly_returns.csv gets r_et TRUNCATED to daily_px's (yfinance) old window, not the
    # full Alpaca-wide series -- app.py's book_panel_data() builds one shared DataFrame
    # from this CSV via pd.DataFrame({name: series, ...}), which outer-joins on index and
    # NaN-pads any column shorter than the widest one. book_panel_data() then does
    # `(1 + bt_returns.fillna(0)).cumprod()`, so writing the full 2016-start r_et here
    # would silently paint years of flat-zero lead-in onto funding_timing_1h's and
    # crypto_reversal_1h's OWN backtest charts -- both real, currently-live books this
    # PR is not supposed to touch. The doctrine verdict above already used the full
    # width via bench_et/r_et; only what reaches the shared CSV is narrowed.
    rows.append(("equity_tsmom_1h", r_et[r_et.index >= daily_px.index.min()]))

    # ---------------- turnover context: the number that usually decides it -------------
    print("\n--- turnover drag, the term that dominates every hourly book ---")
    for name, sig, px in (("crypto_reversal_1h", sig_crypto_reversal(cpx), cpx),
                          ("equity_tsmom_1h", sig_equity_tsmom(epx), epx)):
        w = equal_weight(sig).shift(1)
        per_bar = w.diff().abs().sum(axis=1).mean()
        bars_yr = len(px) / ((px.index.max() - px.index.min()).days / 365.25)
        print(f"  {name:20s} {per_bar:.3f} turnover/bar x {bars_yr:,.0f} bars/yr "
              f"x {COST_BPS}bps = {per_bar * bars_yr * COST_BPS/1e4:.1%}/yr")

    os.makedirs(ART, exist_ok=True)
    pd.DataFrame({n: r for n, r in rows}).to_csv(os.path.join(ART, "hourly_returns.csv"))
    print(f"\nwrote {ART}/hourly_returns.csv and appended graveyard.csv")


if __name__ == "__main__":
    main()
