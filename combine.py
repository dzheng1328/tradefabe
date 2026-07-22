"""
combine.py — does piggybacking / blending strategies help?  (run: python combine.py)

Two honest tests, same doctrine ethos:
  1. Blend the strategies (equal weight, NO tuning) and judge vs a MATCHED null
     (a blend of the same number of random strategies) — so the diversification of the
     blend gets a fair luck bar.
  2. Piggyback: a fixed sleeve of a strategy on top of the 60/40 core. Does the COMBINED
     portfolio's risk-adjusted return beat 60/40 alone?  (doctrine-v1.1, empirically.)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from harness import (load_prices, size_and_rebalance, net_returns, benchmark_returns,
                     sig_green_line, sig_tsmom, sig_tsmom_ensemble, sig_xsec_momentum,
                     sig_random, stats, calmar, OOS_START, NULL_PCTILE)

SLEEVE      = 0.30     # fixed piggyback weight on a 0.70 core (pre-committed, NOT optimized)
NULL_BLEND_TRIALS = 200


def sret(prices, fn):
    r = net_returns(prices, size_and_rebalance(prices, fn(prices)))
    return r[r.index >= OOS_START]


def line(name, r, ref=None):
    s = stats(r)
    extra = f"   dSharpe vs 60/40: {s['Sharpe'] - stats(ref)['Sharpe']:+.2f}" if ref is not None else ""
    print(f"  {name:<24} Sharpe {s['Sharpe']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%}{extra}")
    return s


def main():
    prices, source = load_prices()
    print(f"data: {source} | OOS from {OOS_START.date()}\n")

    strat = {"green_line_200d": sig_green_line, "tsmom_12m": sig_tsmom,
             "tsmom_ensemble": sig_tsmom_ensemble, "xsec_momentum": sig_xsec_momentum}
    R = pd.DataFrame({k: sret(prices, fn) for k, fn in strat.items()}).dropna()
    bench = benchmark_returns(prices)
    bench = bench[bench.index >= OOS_START].reindex(R.index)

    print("=== correlation matrix — different bets, or the same bet 4x? ===")
    print(R.join(bench.rename("benchmark")).corr().round(2).to_string())

    print("\n=== individual strategies (OOS) ===")
    for k in R:
        line(k, R[k], ref=bench)
    line("** 60/40 benchmark **", bench)

    blend = R.mean(axis=1)
    print("\n=== equal-weight blend of all 4 (no tuning) ===")
    sb = line("blend_equal_weight", blend, ref=bench)

    # matched luck floor: blend of k random strategies
    k = R.shape[1]
    rng = np.random.default_rng(0)
    null = []
    for _ in range(NULL_BLEND_TRIALS):
        parts = []
        for _ in range(k):
            x = net_returns(prices, size_and_rebalance(prices, sig_random(prices, rng)))
            parts.append(x[x.index >= OOS_START])
        v = stats(pd.concat(parts, axis=1).mean(axis=1))["Sharpe"]
        if np.isfinite(v):
            null.append(v)
    nbar = float(np.percentile(null, NULL_PCTILE))
    print(f"  matched luck floor (blend of {k} random) p{NULL_PCTILE} = {nbar:.2f}"
          f"  ->  blend {'CLEARS' if sb['Sharpe'] > nbar else 'below'} it")

    print(f"\n=== piggyback: {int((1-SLEEVE)*100)}% 60/40 core + {int(SLEEVE*100)}% strategy sleeve ===")
    core = 1 - SLEEVE
    for tag, sleeve in [("blend", blend), ("xsec_momentum", R["xsec_momentum"]), ("tsmom_12m", R["tsmom_12m"])]:
        combo = core * bench + SLEEVE * sleeve.reindex(bench.index)
        line(f"60/40 + {tag}", combo, ref=bench)
    print("\n(+Sharpe vs 60/40 means the 'failed' strategy still improved the combined portfolio.)")


if __name__ == "__main__":
    main()
