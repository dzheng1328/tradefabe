"""
kronos_backtest.py — family M, the three pre-registered Kronos strategies (#105).

Specs were FROZEN in STRATEGIES.md before this script existed (#106), and amended once
before any verdict existed (#108, the fed context). Nothing here is tuned. A different
parameter is a new row and a new graveyard entry, per roster rule 2.

  kronos_dir_daily   sign of the Kronos-forecast 5-day return over the 15-ETF UNIVERSE,
                     long/short, vol-targeted through engine.sized_weights like every
                     other daily book. Benchmark: 60/40.
  kronos_wick_agg    PREDICTED HAMMER on daytrade_tests.py's 14-name universe -- the same
                     hammer test that study applied to REALIZED bars, applied to FORECAST
                     bars instead. Aggressive by frozen construction: long-only,
                     equal-weight, gross 1.0, no vol targeting, no MAX_LEG cap.
                     Benchmark: 60/40.
  carry_kronos_vol   delta-neutral BTC+ETH funding carry with notional scaled by the
                     forecast vol, capped at 1.0. Benchmark: ALWAYS-ON CARRY, pre-registered
                     rather than declared afterwards (family L had to declare it late).

THREE THINGS THAT MAKE THIS FAMILY DIFFERENT
--------------------------------------------
1. THE OOS WINDOW IS 2025-06-05, NOT 2018. Kronos's pretraining corpus ends there, so an
   earlier backtest asks the model to predict bars already inside its own weights --
   leakage in the PARAMETERS, which no CPCV purge or embargo can touch. This script
   overrides `harness.OOS_START` for the whole run (see `_use_kronos_window`). That
   override is not a convenience: `evaluate()` and `noise_floor()` must slice the SAME
   window, or the candidate is scored on 1.1 years while its null gets 7.5 and gate 1
   becomes meaningless.

2. FEEDING THE MODEL PRE-CUTOFF BARS AS CONTEXT IS FINE; SCORING ON THEM IS NOT. Using
   memorized history as INPUT is what the model is for -- that is ordinary usage. The
   contamination is in evaluating returns whose future the model memorized. So context
   windows may reach back before the cutoff; the evaluated return series may not.

3. THE WINDOW IS ONE REGIME AND IT IS SHORT (~287 days). Expect DEAD across the board.
   That is information about the window, not a failed study -- and it is why the live
   monitor-only books, whose every future day is guaranteed post-cutoff and unselected,
   are the real test for this family. Stated in STRATEGIES.md, repeated here so nobody
   reads a DEAD row as a surprise.

RESUMABILITY. The forecast pass is ~1.9h of CPU (8,323 forecasts at 0.84s). It writes
`artifacts/kronos_forecasts.csv` incrementally and skips any (date, ticker) already
present, so a crash or a Ctrl-C costs only the current row. Doctrine also REQUIRES the
snapshot: Kronos sampling is stochastic and the weights are an external download, so a
verdict that could not be reproduced from a stored forecast could not be reproduced at all.

Usage:
    PYTHONPATH=src:.:research python research/kronos_backtest.py            # forecast + judge
    PYTHONPATH=src:.:research python research/kronos_backtest.py --forecast # snapshot only
    PYTHONPATH=src:.:research python research/kronos_backtest.py --judge    # gates only
    PYTHONPATH=src:.:research python research/kronos_backtest.py --contaminated
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd
import yfinance as yf

import harness
from harness import ART, benchmark_returns, evaluate, family_n_tested, noise_floor
from tradefabe import kronos
from tradefabe.engine import (ANN, COST_BPS, UNIVERSE, net_returns, size_and_rebalance,
                              sized_weights, stats)

FORECASTS = os.path.join(ART, "kronos_forecasts.csv")
FUNDING_CACHE = os.path.join(ART, "hourly_funding.csv")

# Union of every universe family M touches. SPY/QQQ appear in both equity universes; the
# forecast is per (date, ticker) and shared, so each is computed ONCE.
ALL_TICKERS = sorted(set(UNIVERSE) | set(kronos.WICK_UNIVERSE) | set(kronos.CARRY_COINS))

# Fetch start. Needs DAILY_CONTEXT (90) bars of model context PLUS VOL_WINDOW (60) bars of
# sizing warm-up before the first evaluated day, with slack for holidays. Reaching before
# the cutoff is deliberate and harmless -- see note 2 in the module docstring.
FETCH_START = "2024-06-01"


def _use_kronos_window():
    """Point the whole doctrine machinery at family M's OOS boundary.

    `harness.OOS_START` is a module constant read by BOTH `evaluate()` and `noise_floor()`.
    Overriding it here is what keeps candidate and null on the same window; slicing only
    the candidate would hand the null 7.5 years against the candidate's 1.1 and make gate 1
    a comparison between two different experiments."""
    harness.OOS_START = kronos.KRONOS_OOS_START
    print(f"[doctrine] OOS_START overridden to {harness.OOS_START.date()} for family M "
          f"(Kronos pretraining cutoff). Pre-cutoff bars are CONTAMINATED and may not "
          f"produce an ALIVE verdict.")


# ------------------------------------------------------------------------------ data
def fetch_ohlcv(tickers, start=FETCH_START) -> dict[str, pd.DataFrame]:
    """Per-ticker OHLCV frames. Kronos needs all five columns, not just close, which is
    what makes `kronos_wick_agg` expressible at all."""
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, threads=False)
    out = {}
    for t in tickers:
        try:
            df = pd.DataFrame({"open": raw["Open"][t], "high": raw["High"][t],
                               "low": raw["Low"][t], "close": raw["Close"][t],
                               "volume": raw["Volume"][t]})
        except KeyError:
            print(f"[warn] {t}: absent from download, skipped")
            continue
        df = df.dropna()
        if len(df) > kronos.DAILY_CONTEXT:
            out[t] = df
    print(f"[data] {len(out)} tickers, "
          f"{min(len(d) for d in out.values())}-{max(len(d) for d in out.values())} bars each")
    return out


def close_frame(ohlcv: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({t: d["close"] for t, d in ohlcv.items()}).sort_index()


# ------------------------------------------------------------------------- forecasting
def load_snapshot() -> pd.DataFrame:
    if not os.path.exists(FORECASTS):
        return pd.DataFrame(columns=["date", "ticker", "fc_ret", "fc_vol", "fc_hammer"])
    df = pd.read_csv(FORECASTS, parse_dates=["date"])
    print(f"[snapshot] {len(df)} forecasts already stored")
    return df


def run_forecasts(ohlcv, start_date, limit=None) -> pd.DataFrame:
    """Walk forward, one forecast per (date, ticker), appending to the snapshot as we go.

    Strictly causal: the context ends at `d`, so bar d+1..d+5 is genuinely unseen. The seed
    is derived from the DATE, not from a running counter, so a resumed run reproduces the
    same paths for the same day rather than depending on how many forecasts preceded it.
    """
    if not kronos.is_available():
        raise SystemExit("needs the optional extra: pip install -e '.[kronos]'")
    kronos.predictor("cpu")          # measured faster than MPS at this model size

    done = load_snapshot()
    seen = set(zip(done["date"], done["ticker"])) if len(done) else set()

    dates = close_frame(ohlcv).loc[start_date:].index
    todo = [(d, t) for d in dates for t in sorted(ohlcv)
            if (pd.Timestamp(d), t) not in seen and d in ohlcv[t].index]
    if limit:
        todo = todo[:limit]
    print(f"[forecast] {len(todo)} to compute ({len(seen)} cached) "
          f"-> est. {len(todo) * 0.84 / 3600:.1f} h")

    new, t0 = [], time.time()
    header = not os.path.exists(FORECASTS)
    for i, (d, t) in enumerate(todo, 1):
        hist = ohlcv[t].loc[:d]
        ctx = kronos.trim_context(hist)                 # 90 bars -- the #108 amendment
        if len(ctx) < kronos.DAILY_CONTEXT:
            continue
        y_ts = pd.bdate_range(d + pd.Timedelta(days=1), periods=kronos.PRED_LEN)
        try:
            paths = kronos.forecast_paths(ctx, y_ts, n_paths=kronos.SAMPLE_COUNT,
                                          seed=int(pd.Timestamp(d).strftime("%Y%m%d")))
        except Exception as e:                           # noqa: BLE001
            print(f"[warn] {t} {d.date()}: {str(e)[:80]}")
            continue
        s = kronos.summarize_paths(paths, float(ctx["close"].iloc[-1]))
        row = {"date": d, "ticker": t, **s}
        new.append(row)
        # Flush every 25 so a crash costs seconds, not hours.
        if len(new) >= 25 or i == len(todo):
            pd.DataFrame(new).to_csv(FORECASTS, mode="a", header=header, index=False)
            header, new = False, []
            rate = i / max(time.time() - t0, 1e-9)
            print(f"  {i}/{len(todo)}  {rate:.2f}/s  eta "
                  f"{(len(todo) - i) / max(rate, 1e-9) / 60:.0f} min", flush=True)
    return load_snapshot()


def forecast_frame(snap: pd.DataFrame, tickers) -> pd.DataFrame:
    """Long snapshot -> the (ticker, field) wide frame the pure signals consume."""
    s = snap[snap["ticker"].isin(tickers)]
    fc = s.pivot(index="date", columns="ticker", values=["fc_ret", "fc_vol", "fc_hammer"])
    fc.columns = pd.MultiIndex.from_tuples([(t, f) for f, t in fc.columns])
    return fc.sort_index(axis=1).sort_index()


# ------------------------------------------------------------------------- strategies
def dir_returns(fc, prices):
    """kronos_dir_daily: vol-targeted, capped, daily-rebalanced -- the standard path every
    other daily book in this repo takes, so the comparison isolates the forecast."""
    sig = kronos.sig_kronos_dir(fc).reindex(index=prices.index, columns=prices.columns)
    return net_returns(prices, size_and_rebalance(prices, sig.fillna(0.0), "D")), sig


def wick_returns(fc, prices):
    """kronos_wick_agg: the frozen aggressive construction -- equal-weight, gross 1.0,
    NO sized_weights. Applying vol targeting on top would silently rewrite the spec."""
    sig = kronos.sig_kronos_wick(fc, prices).reindex(index=prices.index,
                                                     columns=prices.columns).fillna(0.0)
    w = sig.shift(1).fillna(0.0)                      # decide on t, hold over t+1
    gross = (prices.pct_change() * w).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1).fillna(0.0)
    return gross - turnover * (COST_BPS / 1e4), sig


def carry_returns(funding: pd.DataFrame, scale: pd.Series):
    """carry_kronos_vol vs always-on carry, both from the same funding series.

    Delta-neutral, so the spot leg's P&L cancels the perp's and the return IS the funding
    -- the construction carry_hl.py already uses. Cost is charged on both legs whenever the
    scale moves, which is the honest penalty for a continuously-varying notional."""
    daily = funding.resample("D").sum().mean(axis=1).dropna()
    always = daily.copy()
    sc = scale.reindex(daily.index).ffill().fillna(kronos.VOL_SCALE_CAP)
    pos = sc.shift(1).fillna(kronos.VOL_SCALE_CAP)
    turn = pos.diff().abs().fillna(0.0)
    return (daily * pos) - turn * 2 * (COST_BPS / 1e4), always


def carry_null(daily_always, trials, rng):
    """Random notional scaling of the SAME carry, paying the same adjustment cost. Isolates
    whether the vol signal adds anything over simply holding the position it scales."""
    out = []
    for _ in range(trials):
        pos = pd.Series(rng.uniform(0.0, 1.0, len(daily_always)), index=daily_always.index)
        turn = pos.diff().abs().fillna(0.0)
        r = (daily_always * pos.shift(1).fillna(1.0)) - turn * 2 * (COST_BPS / 1e4)
        v = stats(r[r.index >= harness.OOS_START])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


# ------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", action="store_true", help="snapshot forecasts only")
    ap.add_argument("--judge", action="store_true", help="run gates on the existing snapshot")
    ap.add_argument("--limit", type=int, default=None, help="cap forecasts (smoke test)")
    ap.add_argument("--trials", type=int, default=harness.NULL_TRIALS)
    # Only enough pre-cutoff forecasts to warm the SIGNAL logic: kronos_wick_agg's 5-bar
    # pullback and its HOLD_BARS carry-forward. The vol-targeting warm-up that actually
    # needs 60 bars comes from PRICES (fetched from FETCH_START), not from forecasts --
    # confusing the two would double the run for nothing. `--contaminated` wants a much
    # longer warm-up; the snapshot is additive, so extend it in a later pass rather than
    # paying for it on every run.
    ap.add_argument("--warmup-days", type=int, default=30,
                    help="calendar days of pre-cutoff forecasts (signal warm-up only)")
    ap.add_argument("--contaminated", action="store_true",
                    help="ALSO report the pre-cutoff window, labelled, never written as ALIVE")
    args = ap.parse_args()
    do_forecast = args.forecast or not args.judge
    do_judge = args.judge or not args.forecast

    _use_kronos_window()
    ohlcv = fetch_ohlcv(ALL_TICKERS)

    fc_start = kronos.KRONOS_OOS_START - pd.Timedelta(days=args.warmup_days)
    snap = run_forecasts(ohlcv, fc_start, args.limit) if do_forecast else load_snapshot()
    if not do_judge:
        print(f"[done] snapshot at {FORECASTS}")
        return
    if snap.empty:
        raise SystemExit("no forecasts snapshotted -- run with --forecast first")

    px_all = close_frame(ohlcv)
    n_tested = family_n_tested(["kronos_dir_daily", "kronos_wick_agg", "carry_kronos_vol"])
    print(f"\n[doctrine] n_tested = {n_tested} (graveyard union, NOT reset for a new family)")

    # ---- kronos_dir_daily -------------------------------------------------------
    eq = [t for t in UNIVERSE if t in ohlcv]
    px_eq = px_all[eq].dropna(how="all")
    fc_eq = forecast_frame(snap, eq)
    r_dir, sig_dir = dir_returns(fc_eq, px_eq)
    bench = benchmark_returns(px_eq)
    null_dir = noise_floor(px_eq, "D", args.trials,
                           like=sig_dir.reindex(index=px_eq.index, columns=px_eq.columns))
    kronos.assert_clean_window(r_dir[r_dir.index >= harness.OOS_START].index, "kronos_dir_daily")
    evaluate("kronos_dir_daily", r_dir, bench, null_dir, "D", n_tested=n_tested)

    # ---- kronos_wick_agg --------------------------------------------------------
    wk = [t for t in kronos.WICK_UNIVERSE if t in ohlcv]
    px_wk = px_all[wk].dropna(how="all")
    fc_wk = forecast_frame(snap, wk)
    r_wick, sig_wick = wick_returns(fc_wk, px_wk)
    null_wick = noise_floor(px_wk, "D", args.trials,
                            like=sig_wick.reindex(index=px_wk.index, columns=px_wk.columns))
    kronos.assert_clean_window(r_wick[r_wick.index >= harness.OOS_START].index, "kronos_wick_agg")
    evaluate("kronos_wick_agg", r_wick, benchmark_returns(px_wk), null_wick, "D",
             n_tested=n_tested)

    # ---- carry_kronos_vol -------------------------------------------------------
    if os.path.exists(FUNDING_CACHE):
        funding = pd.read_csv(FUNDING_CACHE, index_col=0, parse_dates=True)
        coin_map = {"BTC-USD": "BTC", "ETH-USD": "ETH"}
        vols = pd.DataFrame({
            c: snap[snap["ticker"] == t].set_index("date")["fc_vol"]
            for t, c in coin_map.items() if t in set(snap["ticker"])})
        if not vols.empty:
            scale = kronos.vol_scale(vols.mean(axis=1))
            r_carry, always = carry_returns(funding, scale)
            rng = np.random.default_rng(0)
            evaluate("carry_kronos_vol", r_carry, always,
                     carry_null(always, args.trials, rng), "D", n_tested=n_tested)
        else:
            print("\n[skip] carry_kronos_vol: no crypto forecasts in the snapshot")
    else:
        print(f"\n[skip] carry_kronos_vol: no funding snapshot at {FUNDING_CACHE} "
              f"(run research/hourly_backtest.py first)")

    # ---- the contaminated comparison, for the record only -----------------------
    if args.contaminated:
        print("\n" + "=" * 78)
        print("CONTAMINATED pre-cutoff window -- reported for comparison ONLY.")
        print("The model was trained on these bars. This is NOT a verdict, is NOT written")
        print("to graveyard.csv, and may NEVER be reported as ALIVE (STRATEGIES.md dev. 1).")
        print("=" * 78)
        pre = r_dir[r_dir.index < kronos.KRONOS_OOS_START]
        if len(pre) > 30:
            s, b = stats(pre), stats(bench[bench.index < kronos.KRONOS_OOS_START])
            print(f"  kronos_dir_daily  Sharpe {s['Sharpe']:.2f} vs 60/40 {b['Sharpe']:.2f}"
                  f"   CAGR {s['CAGR']:+.1%}   MaxDD {s['MaxDD']:.1%}   (n={len(pre)})")
            print("  If this looks BETTER than the clean window above, that is the")
            print("  contamination showing, not an edge that faded.")
        else:
            print(f"  only {len(pre)} pre-cutoff bars available -- nothing to compare")


if __name__ == "__main__":
    main()
