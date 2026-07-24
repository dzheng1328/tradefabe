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
from tradefabe.engine import load_prices, size_and_rebalance, net_returns, stats, calmar, BASE
from tradefabe.signals import sig_random
from tradefabe.piggyback import LEGS, SPECS, SLEEVE
from harness import (benchmark_returns, OOS_START, CORR_DIV, DD_MULT, GRAVEYARD,
                     bonferroni_bar, family_n_tested)

NULL_TRIALS = 150
FREQ = "M"
ART = os.path.join(BASE, "artifacts")

# name -> tuple of legs, from tradefabe.piggyback's SPECS (the single source of truth,
# pre-registered in STRATEGIES.md family H before this script was run).
PIGGYBACK_SPECS = {name: legs for name, (legs, _freq) in SPECS.items()}


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


def evaluate(name, combo, bench, null, k, legs, n_tested):
    s, b = stats(combo), stats(bench.reindex(combo.index).dropna())
    both = pd.concat([combo, bench], axis=1).dropna()
    corr = both.iloc[:, 0].corr(both.iloc[:, 1])
    null_bar, bar_method, bar_pctile = bonferroni_bar(null, n_tested)

    beats_luck = s["Sharpe"] > null_bar
    earns = (calmar(s) > calmar(b)) or (abs(corr) < CORR_DIV and s["Sharpe"] >= b["Sharpe"])
    dd_ok = s["MaxDD"] >= DD_MULT * b["MaxDD"]
    alive = bool(beats_luck and earns and dd_ok)

    print(f"\n=== DOCTRINE verdict: {name}  (sleeve: {' + '.join(legs)}) ===")
    print(f"  combo     Sharpe {s['Sharpe']:.2f} | Sortino {s['Sortino']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr->bench {corr:.2f}")
    print(f"  benchmark Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}   (60/40)")
    print(f"  matched luck floor (depth-{k} construction, {NULL_TRIALS} trials, n_tested={n_tested}, {bar_method} p{bar_pctile:.2f}): Sharpe = {null_bar:.2f}")
    print(f"  gate 1  beats luck  : {beats_luck}   ({s['Sharpe']:.2f} > {null_bar:.2f})")
    print(f"  gate 2  earns place : {earns}   (Calmar {calmar(s):.2f} vs {calmar(b):.2f}; |corr| {abs(corr):.2f} -- structurally high, informational only)")
    print(f"  gate 3  not painful : {dd_ok}   (MaxDD {s['MaxDD']:.1%} vs limit {DD_MULT * b['MaxDD']:.1%})")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if alive else 'DEAD -> graveyard, no rescue'}")

    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "freq": FREQ, "oos_sharpe": round(s["Sharpe"], 3),
           "oos_sortino": round(s["Sortino"], 3), "oos_calmar": round(calmar(s), 3),
           "oos_maxdd": round(s["MaxDD"], 3), "corr_bench": round(corr, 3),
           "null_p95": round(null_bar, 3), "bench_sharpe": round(b["Sharpe"], 3),
           "bench_calmar": round(calmar(b), 3), "verdict": "ALIVE" if alive else "DEAD",
           "n_tested": n_tested, "bar_method": bar_method, "bar_pctile": round(bar_pctile, 3)}
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

    n_tested = family_n_tested(PIGGYBACK_SPECS.keys())
    combo_returns = {}
    for name, legs in PIGGYBACK_SPECS.items():
        sleeve = pd.DataFrame({leg: leg_returns[leg] for leg in legs}).dropna().mean(axis=1)
        combo = (1 - SLEEVE) * bench.reindex(sleeve.index) + SLEEVE * sleeve
        combo = combo.dropna()
        combo_returns[name] = combo
        evaluate(name, combo, bench, nulls[len(legs)], len(legs), legs, n_tested)

    os.makedirs(ART, exist_ok=True)
    pd.DataFrame(combo_returns).to_csv(os.path.join(ART, "piggyback_returns.csv"))
    print(f"\nappended 4 verdicts to graveyard.csv, wrote artifacts/piggyback_returns.csv "
          f"(dashboard backtest-curve source for the ALIVE constructions)")


if __name__ == "__main__":
    main()
