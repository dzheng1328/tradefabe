"""
overnight_backtest.py — the overnight (close→open) effect (#23).

The anomaly is well documented: a disproportionate share of historical equity return
accrues between the close and the next open, not during the session. The usual
explanations are structural — index/ETF rebalancing flows at the close, overnight
information absorption, and a premium for holding gap risk you cannot exit. A
flow thesis, not a predictive one, so it belongs in family C beside turn_of_month.

This script asks two separate questions and keeps them apart, because conflating them is
how the anomaly gets oversold:

  1. Is the decomposition real?  Split each day's total return into overnight
     (Open_t / Close_t-1 - 1) and intraday (Close_t / Open_t - 1), and compare.
     No trading, no costs -- just where the return lived.
  2. Can you HARVEST it?  A close-to-open-only book buys at every close and sells at
     every open: two sides every single trading day. At the engine's 5bps per side that
     is ~2.5%/yr of turnover cost before any signal is right or wrong.

Question 1 can be a resounding yes while question 2 is a flat no. That gap is the whole
point of this lab.

Usage: PYTHONPATH=src:. python research/overnight_backtest.py
"""
from __future__ import annotations
import argparse
import os
import numpy as np
import pandas as pd
import yfinance as yf

from tradefabe.engine import UNIVERSE, COST_BPS, ANN, stats, calmar
from harness import (dsr_gate1, bonferroni_bar, family_n_tested, benchmark_returns,
                     CORR_DIV, DD_MULT, OOS_START, ART)

SIDES_PER_DAY = 2          # buy at the close, sell at the open -- every single day
NULL_TRIALS = 500


def fetch(tickers, start="2004-01-01"):
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, threads=False)
    op, cl = raw["Open"], raw["Close"]
    keep = [t for t in tickers if t in cl.columns and cl[t].notna().sum() > 1000]
    return op[keep].dropna(how="all"), cl[keep].dropna(how="all")


def decompose(op, cl):
    """Where the return actually lived. Gross, no costs -- this is question 1."""
    overnight = (op / cl.shift(1) - 1).dropna(how="all")
    intraday = (cl / op - 1).dropna(how="all")
    total = (cl / cl.shift(1) - 1).dropna(how="all")
    return overnight, intraday, total


def _ann_from_daily(r):
    return (1 + r.mean()) ** ANN - 1


def harvest_returns(overnight, cost_bps=COST_BPS):
    """Question 2: an equal-weight book long the universe overnight only, flat all day.
    Charged for both sides every day, because that is what the strategy does."""
    gross = overnight.mean(axis=1)
    cost = SIDES_PER_DAY * (cost_bps / 1e4)
    return gross - cost


def noise_floor(overnight, trials, rng):
    """Random long/short overnight exposure at the same daily turnover, through the
    identical cost path. Matched to what the strategy actually pays."""
    n_days, n_assets = overnight.shape
    out = []
    for _ in range(trials):
        w = rng.choice([-1.0, 1.0], size=(n_days, n_assets))
        r = (overnight.values * w).mean(axis=1) - SIDES_PER_DAY * (COST_BPS / 1e4)
        out.append(stats(pd.Series(r, index=overnight.index))["Sharpe"])
    return np.array(out)


def judge(name, r, bench, null, n_tested):
    s, b = stats(r), stats(bench)
    corr = float(pd.concat([r, bench], axis=1).dropna().corr().iloc[0, 1])
    g1 = dsr_gate1(r, null, n_tested)
    gate2 = (calmar(s) >= calmar(b)) or (abs(corr) < CORR_DIV and calmar(s) > 0)
    gate3 = s["MaxDD"] >= DD_MULT * b["MaxDD"]
    bar, method, _ = bonferroni_bar(null, n_tested)
    verdict = "ALIVE" if (g1["beats_luck"] and gate2 and gate3) else "DEAD"
    print(f"\n=== {name} ===")
    print(f"  Sharpe {s['Sharpe']:6.2f} | Calmar {calmar(s):6.2f} | MaxDD {s['MaxDD']:7.1%} | corr {corr:+.2f}")
    print(f"  bench  {b['Sharpe']:6.2f} | Calmar {calmar(b):6.2f} | MaxDD {b['MaxDD']:7.1%}")
    print(f"  DSR {g1['dsr']:.3f} vs SR* {g1['sr_star']:.2f} | Bonferroni {bar:.2f} ({method}, logged only)")
    print(f"  gate1 {g1['beats_luck']} | gate2 {gate2} | gate3 {gate3}  ->  {verdict}")
    return {"strategy": name, "verdict": verdict, "sharpe": s["Sharpe"],
            "calmar": calmar(s), "maxdd": s["MaxDD"], "corr_bench": corr, "dsr": g1["dsr"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=NULL_TRIALS)
    args = ap.parse_args()
    rng = np.random.default_rng(20260726)

    op, cl = fetch(UNIVERSE)
    overnight, intraday, total = decompose(op, cl)
    print(f"universe {list(cl.columns)}")
    print(f"{len(cl)} days, {cl.index.min().date()} -> {cl.index.max().date()}\n")

    # ---- question 1: is the decomposition real? (gross, no costs) ----
    on_m, id_m = overnight.mean(axis=1), intraday.mean(axis=1)
    print("where the return lived (equal-weight universe, GROSS, no costs):")
    print(f"  overnight  {_ann_from_daily(on_m):+7.2%}/yr   Sharpe {stats(on_m)['Sharpe']:5.2f}")
    print(f"  intraday   {_ann_from_daily(id_m):+7.2%}/yr   Sharpe {stats(id_m)['Sharpe']:5.2f}")
    print(f"  full day   {_ann_from_daily(total.mean(axis=1)):+7.2%}/yr")
    share = _ann_from_daily(on_m) / _ann_from_daily(total.mean(axis=1))
    print(f"  -> overnight accounts for {share:.0%} of the full-day return\n")

    # ---- question 2: can you harvest it, net of what it costs to trade? ----
    r_full = harvest_returns(overnight)
    r_oos = r_full[r_full.index >= OOS_START]
    drag = SIDES_PER_DAY * (COST_BPS / 1e4) * ANN
    print(f"cost of harvesting: {SIDES_PER_DAY} sides/day at {COST_BPS:.0f}bps "
          f"= {drag:.2%}/yr of turnover drag\n")

    bench = benchmark_returns(cl)
    b_oos = bench[bench.index >= OOS_START]
    print(f"building matched null ({args.trials} trials)...")
    null = noise_floor(overnight[overnight.index >= OOS_START], args.trials, rng)
    print(f"  null Sharpe: mean {null.mean():.2f}, p95 {np.percentile(null, 95):.2f}")

    n_tested = family_n_tested(["overnight_effect"])
    rows = [judge("overnight_effect", r_oos, b_oos, null, n_tested)]

    gross_oos = overnight.mean(axis=1)[overnight.index >= OOS_START]
    gross_ann = _ann_from_daily(gross_oos)
    print(f"\nsame book with costs switched OFF: Sharpe {stats(gross_oos)['Sharpe']:.2f} "
          f"({gross_ann:+.2%}/yr)")
    print("  The gap between that and the row above is the entire finding: the effect is\n"
          "  visible in the data and is eaten by the cost of touching it twice a day.")

    # pre-empt the obvious objection ("your cost assumption is too pessimistic") with the
    # number that settles it: the per-side cost at which this breaks even.
    breakeven_bps = gross_oos.mean() / SIDES_PER_DAY * 1e4
    print(f"\nbreak-even cost: {breakeven_bps:.2f} bps per side. Below that the book makes "
          f"money,\n  above it loses. The engine assumes {COST_BPS:.0f}bps. Even at a "
          f"1bp institutional\n  spread the margin is thin, and it must hold for both "
          f"sides, every session, forever.")

    out = pd.DataFrame(rows)
    os.makedirs(ART, exist_ok=True)
    pd.DataFrame({"overnight": on_m, "intraday": id_m}).to_csv(
        os.path.join(ART, "overnight_decomposition.csv"))
    out.to_csv(os.path.join(ART, "overnight_verdicts.csv"), index=False)
    print(f"\nwrote {ART}/overnight_decomposition.csv and overnight_verdicts.csv")
    return out


if __name__ == "__main__":
    main()
