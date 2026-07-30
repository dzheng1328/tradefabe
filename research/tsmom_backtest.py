"""
tsmom_backtest.py — Honest first-slice backtest: cross-asset time-series momentum.

This is the "Executor's step" from our planning: ONE documented strategy, run
through an honest pipeline, before any platform gets built.

Discipline baked in on purpose:
  * Canonical parameters (12-month lookback) — NOT optimized, to avoid overfitting.
  * Signal at day t is applied to returns t -> t+1 (positions shifted 1 day): no lookahead.
  * Monthly rebalance + pessimistic slippage: costs are not hand-waved.
  * In-sample / out-of-sample split with a KILL RULE written before results are seen.
  * Benchmarked against just-buy-SPY, the honest bar to beat.

The data cache, config, sizing and returns math now live in the installed package
(tradefabe.engine); this script is the standalone TSMOM study + plotting on top of it.
The engine names are re-exported below so existing `from tsmom_backtest import ...`
callers keep working.

Run:    PYTHONPATH="$(pwd)" python research/tsmom_backtest.py
Output: prints a metrics table + writes equity_curve.png and results.csv to the repo root.
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Engine core (single source of truth). Re-exported so `from tsmom_backtest import stats`
# etc. still resolves for any notebook/script that relied on this module.
from tradefabe.engine import (  # noqa: F401
    UNIVERSE, START, LOOKBACK, VOL_WINDOW, TARGET_VOL, MAX_LEG, MAX_GROSS,
    COST_BPS, LONG_SHORT, SPLIT_DATE, BENCH, ANN, BASE, DATA_CACHE,
    load_prices, stats, size_and_rebalance, net_returns)
from tradefabe.signals import sig_tsmom_12m

# KILL RULE — written before results are seen:
#   The strategy is DEAD unless, out-of-sample and after costs, it delivers
#   Sharpe >= 1.0 AND beats buy-&-hold SPY on Sharpe. No tweaking to rescue it.
KILL_OOS_SHARPE = 1.0


def build_weights(prices):
    """Canonical long/short TSMOM weights: sign(trailing 12-mo) sized to target vol,
    gross-capped, monthly-rebalanced. Now just the shared sizing applied to the
    12-month trend signal (identical math to the pre-extraction inline version)."""
    return size_and_rebalance(prices, sig_tsmom_12m(prices), "M")


def main():
    prices, source = load_prices()
    print(f"data source: {source}  |  {prices.index.min().date()} -> {prices.index.max().date()}  |  {prices.shape[1]} assets")
    rets   = prices.pct_change()
    w      = build_weights(prices)
    net    = net_returns(prices, w)                       # execute next day: no lookahead
    bench  = rets[BENCH].reindex(net.index)

    split = pd.Timestamp(SPLIT_DATE)
    seg = {
        "FULL":                       net,
        f"IN-SAMPLE  (<{split.date()})":  net[net.index < split],
        f"OUT-SAMPLE (>={split.date()})": net[net.index >= split],
    }
    print("\n=== TSMOM (net of costs) ===")
    hdr = f"{'segment':<26}{'CAGR':>8}{'Vol':>8}{'Sharpe':>8}{'Sortino':>9}{'MaxDD':>8}"
    print(hdr); print("-" * len(hdr))
    rows = {}
    for name, r in seg.items():
        s = stats(r); rows[name] = s
        print(f"{name:<26}{s['CAGR']:>7.1%}{s['Vol']:>8.1%}{s['Sharpe']:>8.2f}{s['Sortino']:>9.2f}{s['MaxDD']:>8.1%}")

    b_oos = stats(bench[bench.index >= split])
    s_oos = rows[f"OUT-SAMPLE (>={split.date()})"]
    print(f"{'buy&hold ' + BENCH + ' (OOS)':<26}{b_oos['CAGR']:>7.1%}{b_oos['Vol']:>8.1%}{b_oos['Sharpe']:>8.2f}{b_oos['Sortino']:>9.2f}{b_oos['MaxDD']:>8.1%}")

    print("\n=== KILL RULE (written before results) ===")
    passes = (s_oos["Sharpe"] >= KILL_OOS_SHARPE) and (s_oos["Sharpe"] > b_oos["Sharpe"])
    print(f"  need: OOS Sharpe >= {KILL_OOS_SHARPE:.2f}  AND  > buy&hold {BENCH} OOS Sharpe ({b_oos['Sharpe']:.2f})")
    print(f"  got : OOS Sharpe  = {s_oos['Sharpe']:.2f}")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if passes else 'DEAD -> do not tweak to rescue'}")
    if source.startswith("SYNTHETIC"):
        print("  (NOTE: synthetic data — this is a pipeline smoke-test, not a real result.)")

    # artifacts
    eq  = (1 + net).cumprod()
    beq = (1 + bench.reindex(net.index).fillna(0)).cumprod()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7),
                                   gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    ax1.plot(eq.index, eq, label="TSMOM (net)", lw=1.5)
    ax1.plot(beq.index, beq, label=f"buy&hold {BENCH}", lw=1.0, alpha=0.7)
    ax1.axvline(split, color="k", ls="--", lw=0.8)
    ax1.set_yscale("log"); ax1.set_title(f"Cross-asset TSMOM   [source: {source}]")
    ax1.legend(); ax1.grid(alpha=0.3)
    dd = eq / eq.cummax() - 1
    ax2.fill_between(dd.index, dd, 0, color="crimson", alpha=0.4)
    ax2.set_ylabel("drawdown"); ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(BASE, "equity_curve.png"), dpi=110)
    pd.DataFrame(rows).T.to_csv(os.path.join(BASE, "results.csv"))
    print("\nwrote equity_curve.png and results.csv")


if __name__ == "__main__":
    main()
