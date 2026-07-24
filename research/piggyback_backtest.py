"""
piggyback_backtest.py — formal doctrine verdict for the 4 pre-registered piggyback
constructions in STRATEGIES.md family H.

Same 3-gate kill rule as harness.py, applied to a CONSTRUCTION (70% 60/40 core + 30%
equal-weight sleeve of named DEAD legs) instead of a bare strategy. The luck floor is
matched accordingly: a distribution of the same construction built from `k` random
sleeve legs (k = sleeve depth), not from a single random strategy — a random sleeve gets
a fair shot at improving on 60/40 by chance alone before any real sleeve is asked to beat
that bar. Diversification-by-correlation (gate 2's OR clause) is structurally weak here
since every construction already holds 70% of the benchmark by construction — corr to
bench is reported for the record but the "earns its place" gate in practice runs on the
Calmar branch only.

The sleeve specs (which legs, which order, why) were frozen in STRATEGIES.md BEFORE this
script was run — chosen by a full itertools.combinations search over all 7 backtest-DEAD
equity candidates, logged in that session (see STRATEGIES.md family H for the writeup).
"""
from __future__ import annotations
import datetime
import os
import numpy as np
import pandas as pd
from tradefabe.engine import load_prices, size_and_rebalance, net_returns, stats, calmar
from tradefabe.signals import (sig_tsmom_12m, sig_tsmom_ensemble, sig_xsec_momentum,
                               sig_green_line_200d, sig_low_vol,
                               sig_turn_of_month_research, sig_random)
from harness import benchmark_returns, OOS_START, NULL_PCTILE, CORR_DIV, DD_MULT, GRAVEYARD

SLEEVE = 0.30           # fixed piggyback weight on a 0.70 60/40 core (pre-committed, combine.py)
NULL_TRIALS = 150
FREQ = "M"

LEGS = {
    "tsmom_12m":       sig_tsmom_12m,
    "tsmom_ensemble":  sig_tsmom_ensemble,
    "xsec_momentum":   sig_xsec_momentum,
    "green_line_200d": sig_green_line_200d,
    "low_vol_xsec":    sig_low_vol,
    "turn_of_month":   sig_turn_of_month_research,
}

# name -> tuple of legs. Pre-registered in STRATEGIES.md family H before this ran.
PIGGYBACK_SPECS = {
    "piggyback_2a": ("tsmom_12m", "low_vol_xsec"),
    "piggyback_2b": ("low_vol_xsec", "turn_of_month"),
    "piggyback_3":  ("tsmom_12m", "green_line_200d", "low_vol_xsec"),
    "piggyback_4":  ("tsmom_12m", "xsec_momentum", "green_line_200d", "low_vol_xsec"),
}


def sret(prices, fn):
    r = net_returns(prices, size_and_rebalance(prices, fn(prices)))
    return r[r.index >= OOS_START]


def matched_null(prices, bench, k, trials, rng):
    """Sharpe distribution of `0.70*bench + 0.30*mean(k random legs)` — the fair luck
    floor for a k-deep piggyback construction, not just for a bare k-blend sleeve."""
    out = []
    for _ in range(trials):
        parts = [sret(prices, lambda p, rng=rng: sig_random(p, rng)) for _ in range(k)]
        sleeve = pd.concat(parts, axis=1).dropna().mean(axis=1)
        combo = (1 - SLEEVE) * bench.reindex(sleeve.index) + SLEEVE * sleeve
        v = stats(combo.dropna())["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


def evaluate(name, combo, bench, null, k, legs):
    s, b = stats(combo), stats(bench.reindex(combo.index).dropna())
    both = pd.concat([combo, bench], axis=1).dropna()
    corr = both.iloc[:, 0].corr(both.iloc[:, 1])
    null_bar = float(np.percentile(null, NULL_PCTILE))

    beats_luck = s["Sharpe"] > null_bar
    earns = (calmar(s) > calmar(b)) or (abs(corr) < CORR_DIV and s["Sharpe"] >= b["Sharpe"])
    dd_ok = s["MaxDD"] >= DD_MULT * b["MaxDD"]
    alive = bool(beats_luck and earns and dd_ok)

    print(f"\n=== DOCTRINE verdict: {name}  (sleeve: {' + '.join(legs)}) ===")
    print(f"  combo     Sharpe {s['Sharpe']:.2f} | Sortino {s['Sortino']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr->bench {corr:.2f}")
    print(f"  benchmark Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}   (60/40)")
    print(f"  matched luck floor (depth-{k} construction, {NULL_TRIALS} trials): p{NULL_PCTILE} Sharpe = {null_bar:.2f}")
    print(f"  gate 1  beats luck  : {beats_luck}   ({s['Sharpe']:.2f} > {null_bar:.2f})")
    print(f"  gate 2  earns place : {earns}   (Calmar {calmar(s):.2f} vs {calmar(b):.2f}; |corr| {abs(corr):.2f} -- structurally high, informational only)")
    print(f"  gate 3  not painful : {dd_ok}   (MaxDD {s['MaxDD']:.1%} vs limit {DD_MULT * b['MaxDD']:.1%})")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if alive else 'DEAD -> graveyard, no rescue'}")

    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "freq": FREQ, "oos_sharpe": round(s["Sharpe"], 3),
           "oos_sortino": round(s["Sortino"], 3), "oos_calmar": round(calmar(s), 3),
           "oos_maxdd": round(s["MaxDD"], 3), "corr_bench": round(corr, 3),
           "null_p95": round(null_bar, 3), "bench_sharpe": round(b["Sharpe"], 3),
           "bench_calmar": round(calmar(b), 3), "verdict": "ALIVE" if alive else "DEAD"}
    pd.DataFrame([row]).to_csv(GRAVEYARD, mode="a", header=not os.path.exists(GRAVEYARD), index=False)


def main():
    prices, source = load_prices()
    print(f"data: {source} | OOS from {OOS_START.date()}")

    bench = benchmark_returns(prices)
    bench = bench[bench.index >= OOS_START]
    leg_returns = {name: sret(prices, fn) for name, fn in LEGS.items()}

    rng = np.random.default_rng(0)
    nulls = {}
    for k in sorted({len(legs) for legs in PIGGYBACK_SPECS.values()}):
        print(f"\ncomputing depth-{k} matched luck floor ({NULL_TRIALS} random constructions)...")
        nulls[k] = matched_null(prices, bench, k, NULL_TRIALS, rng)

    for name, legs in PIGGYBACK_SPECS.items():
        sleeve = pd.DataFrame({leg: leg_returns[leg] for leg in legs}).dropna().mean(axis=1)
        combo = (1 - SLEEVE) * bench.reindex(sleeve.index) + SLEEVE * sleeve
        evaluate(name, combo.dropna(), bench, nulls[len(legs)], len(legs), legs)

    print("\nappended 4 verdicts to graveyard.csv")


if __name__ == "__main__":
    main()
