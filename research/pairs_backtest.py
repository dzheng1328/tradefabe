"""
pairs_backtest.py — family N, pairs/cointegration trading (#172).

Six economically-motivated pairs (not a blind cointegration scan over all C(15,2)
combinations -- see STRATEGIES.md's family N section for why that distinction matters):

  GLD/SLV   precious metals
  TLT/IEF   treasury duration spread
  EFA/EEM   developed vs. emerging international equities
  SPY/QQQ   broad market vs. tech-heavy
  USO/DBC   oil vs. broad commodities
  LQD/HYG   investment-grade vs. high-yield credit

Method (Engle & Granger 1987, the standard two-step cointegration test):
  1. Regress log(A) on log(B) on the CALIBRATION window (2007-2017, identical to
     DOCTRINE's own core split) to get hedge ratio beta + intercept alpha. FROZEN --
     never re-estimated in the OOS period, same discipline as every other family.
  2. ADF-test the calibration-window residual for stationarity. A pair clears the
     filter at p < 0.05; a pair that fails does not trade OOS at all.

Signal (Gatev, Goetzmann & Rouwenhorst 2006's standard z-score construction): the frozen
spread is z-scored against its own trailing 60-day mean/std (engine.VOL_WINDOW's
convention -- a live normalization of the CURRENT spread level, not a re-fit of the
cointegrating relationship, which stays frozen). Enter long-the-spread (long A, short B)
at z < -2.0, short-the-spread at z > +2.0, exit at z crossing 0, force-flat at |z| > 4.0
(structural-break stop). Position MAGNITUDE per leg comes from the engine's existing
per-asset vol-targeting (sized_weights()), same as every other family -- beta is used
only to define and test the spread, not to weight the legs (GGR's own equal-weighted
convention, not a beta-dollar-neutral construction).

Rebalance freq D. Benchmark 60/40. Noise floor: harness.noise_floor(..., like=signal),
DOCTRINE v1.5's duty-cycle-matched null, reused as-is -- no custom null needed, unlike
family L's hourly-specific hourly_null/funding_null, since this signal's turnover shape
has no reason to differ from the generic D-rebalanced case those corrected for.

Usage: PYTHONPATH=src:.:research python research/pairs_backtest.py
"""
from __future__ import annotations
import argparse
import os

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

from tradefabe.engine import load_prices, realized_vol, size_and_rebalance, net_returns
from harness import evaluate, family_n_tested, benchmark_returns, noise_floor, ART

CALIB_START = "2007-01-01"
CALIB_END = "2017-12-31"   # DOCTRINE's own calibration window -- never the OOS window a
                           # verdict is rendered on

PAIRS = [
    ("GLD", "SLV"),
    ("TLT", "IEF"),
    ("EFA", "EEM"),
    ("SPY", "QQQ"),
    ("USO", "DBC"),
    ("LQD", "HYG"),
]

Z_WINDOW = 60      # matches engine.VOL_WINDOW's convention
Z_ENTRY = 2.0
Z_STOP = 4.0
ADF_ALPHA = 0.05


def fit_pair(prices: pd.DataFrame, a: str, b: str) -> tuple[float, float, float]:
    """Engle-Granger step 1: OLS hedge ratio + intercept on the CALIBRATION window only,
    frozen for OOS use. Returns (beta, alpha, adf_pvalue)."""
    calib = prices.loc[CALIB_START:CALIB_END, [a, b]].dropna()
    log_a = np.log(calib[a])
    log_b = np.log(calib[b])
    beta, alpha = np.polyfit(log_b, log_a, 1)
    resid = log_a - beta * log_b - alpha
    adf_p = adfuller(resid, autolag="AIC")[1]
    return float(beta), float(alpha), float(adf_p)


def spread_z(prices: pd.DataFrame, a: str, b: str, beta: float, alpha: float) -> pd.Series:
    spread = np.log(prices[a]) - beta * np.log(prices[b]) - alpha
    return (spread - spread.rolling(Z_WINDOW).mean()) / spread.rolling(Z_WINDOW).std()


def pair_position(z: pd.Series) -> pd.Series:
    """Stateful long/short/flat position from z-score threshold crossings. +1 = long the
    spread (long A, short B), -1 = short the spread, 0 = flat. Entry/exit is inherently
    path-dependent (exit depends on WHEN z crosses back through 0, which varies per
    episode) -- not vectorizable as a fixed hold period the way ict_backtest.py's
    signals are, so this is a straightforward per-day loop. ~2,700 obs x 6 pairs is
    trivial wall-clock time; not worth a cleverer trick that's harder to audit.

    Not shifted here -- callers (size_and_rebalance -> net_returns) already execute the
    signal one bar later, the same no-lookahead convention every other family uses.

    Entry requires Z_ENTRY < |z| < Z_STOP, not just |z| > Z_ENTRY -- entering a position
    that's already past the level that would immediately stop it back out is
    self-contradictory (found while writing this function's own tests: without the
    upper bound, a bar with |z| > Z_STOP that follows a stop-out re-enters on the very
    next bar, since a fresh flat-state check only looks at the entry threshold)."""
    pos = np.zeros(len(z))
    state = 0.0
    for i, zi in enumerate(z.to_numpy()):
        if np.isnan(zi):
            state = 0.0
        elif state == 0.0:
            if -Z_STOP < zi < -Z_ENTRY:
                state = 1.0
            elif Z_ENTRY < zi < Z_STOP:
                state = -1.0
        elif state == 1.0:
            if zi >= 0 or zi < -Z_STOP:
                state = 0.0
        elif state == -1.0:
            if zi <= 0 or zi > Z_STOP:
                state = 0.0
        pos[i] = state
    return pd.Series(pos, index=z.index)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=500)
    args = ap.parse_args()

    prices, source = load_prices()
    print(f"[data] {len(prices)} daily obs from {source}")

    # Filter FIRST, over the full 12-ticker frame (fit_pair only needs each pair's own
    # two columns), THEN rebuild px from only the tickers whose pair cleared -- not the
    # full 12 regardless of how many pairs pass. sized_weights() divides by
    # prices.shape[1] (#172 debugging: this is 1/N-of-the-UNIVERSE-PASSED-IN, not
    # 1/N-of-what's-actually-active): every other family in this repo populates ALL
    # columns with a view every day, so that normalization naturally spreads capital
    # across the whole universe. A pairs signal is structurally SPARSE -- usually only
    # one pair's two columns are ever nonzero -- so passing the full 12-ticker frame in
    # regardless of how many pairs pass would divide by 12 when only 2 (or 4, or 6...)
    # are ever active, silently shrinking every position to a fraction of its intended
    # size and manufacturing a near-zero-Sharpe, flat-looking result that looks like "no
    # edge" but is actually "position too small to matter."
    kept = []
    for a, b in PAIRS:
        beta, alpha, adf_p = fit_pair(prices, a, b)
        passed = adf_p < ADF_ALPHA
        print(f"[{a}/{b}] beta={beta:.3f} alpha={alpha:.3f} adf_p={adf_p:.4f} "
              f"{'PASS' if passed else 'FAIL -- dropped, not traded OOS'}")
        if passed:
            kept.append((a, b, beta, alpha, adf_p))

    if not kept:
        print("\nNo pair cleared the cointegration filter (p < 0.05) -- nothing to "
              "evaluate. Not appending graveyard.csv.")
        return

    print(f"\n{len(kept)}/{len(PAIRS)} pair(s) cleared the cointegration filter: "
          f"{', '.join(f'{a}/{b}' for a, b, *_ in kept)}")

    active_tickers = sorted({t for a, b, *_ in kept for t in (a, b)})
    px = prices[active_tickers]
    signal = pd.DataFrame(0.0, index=px.index, columns=active_tickers)
    for a, b, beta, alpha, adf_p in kept:
        z = spread_z(px, a, b, beta, alpha)
        pos = pair_position(z)
        n_trades = int((pos.diff().abs() > 0).sum())
        print(f"  [{a}/{b}] {n_trades} position change(s) over the full history")
        signal[a] = signal[a] + pos
        signal[b] = signal[b] - pos

    rv = realized_vol(px)
    w = size_and_rebalance(px, signal, "D", rv)
    r_full = net_returns(px, w)
    # benchmark_returns() needs SPY+IEF (BENCH_W's fixed 60/40 weights) -- call it on the
    # full 15-ticker `prices`, not the possibly-narrower `px`, which only has whichever
    # pairs' tickers cleared the cointegration filter and may not include either.
    bench = benchmark_returns(prices)
    print(f"\n[pairs_cointegration] {len(r_full.dropna())} daily obs from "
          f"{r_full.dropna().index.min().date()}")
    print(f"  building matched null ({args.trials} random D-rebalanced strategies, "
          f"duty-cycle matched to this signal)...")
    null = noise_floor(px, "D", trials=args.trials, rv=rv, like=signal)
    print(f"  null Sharpe: mean {null.mean():.2f}, p95 {np.percentile(null, 95):.2f}")
    evaluate("pairs_cointegration", r_full, bench, null, "D",
             n_tested=family_n_tested(["pairs_cointegration"]))

    os.makedirs(ART, exist_ok=True)
    r_full.to_frame("pairs_cointegration").to_csv(os.path.join(ART, "pairs_returns.csv"))
    print(f"\nwrote {ART}/pairs_returns.csv and appended graveyard.csv")


if __name__ == "__main__":
    main()
