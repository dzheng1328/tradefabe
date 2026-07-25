"""
factory_run.py — the strategy factory's daily driver (#28).

Draws a bounded, family-diverse sample from tradefabe.factory.TEMPLATES (the
pre-registered search space -- see that module's docstring for why pre-registration,
not free-form generation, is the whole point), runs each candidate through the SAME
doctrine gate every hand-tested strategy goes through (harness.evaluate(), DSR/CPCV-
gated per DOCTRINE v1.4 -- no lighter bar for being machine-generated), and appends
every result to graveyard.csv exactly like every other strategy.

After individual templates are evaluated, picks the single least-correlated pair among
this cycle's candidates (tradefabe.factory.complementary_pairs()) and evaluates ONE
70/30-on-60/40 construction from it -- reusing piggyback_backtest.py's own matched_null
(a fair luck floor for a k-legged construction, not a bare-strategy one) rather than
inventing a new one. "Mix everything" is deliberately not the default; one correlation-
picked pair per cycle is.

Usage: .venv/bin/python research/factory_run.py [--n N] [--seed SEED]
"""
from __future__ import annotations
import argparse
import numpy as np
import pandas as pd

from tradefabe.engine import load_prices, size_and_rebalance, net_returns, realized_vol
from harness import (benchmark_returns, noise_floor, evaluate as harness_evaluate,
                     family_n_tested, graveyard_strategy_names, OOS_START, NULL_TRIALS)
from tradefabe import factory
from piggyback_backtest import matched_null, evaluate as piggyback_evaluate, SLEEVE

DEFAULT_N = 6           # candidates drawn per cycle -- a config knob, not a fixed trial count
COMBO_TRIALS = 150       # matched-null trials for the one cycle-ending combo (same as piggyback_backtest.py)


def run_cycle(n=DEFAULT_N, seed=None, verbose=True):
    """Runs one factory cycle: evaluate up to `n` fresh templates, then one
    correlation-picked combo. Returns the list of newly-evaluated names (individual +
    combo, if one was built) for the caller to inspect/log. `seed=None` uses OS entropy
    (so successive daily cycles draw different templates); pass a fixed seed for a
    reproducible test run."""
    rng = np.random.default_rng(seed)
    already_tested = graveyard_strategy_names()
    sample = factory.select_diverse_sample(factory.TEMPLATES, n, rng, exclude=already_tested)
    if verbose:
        print(f"drew {len(sample)} candidate(s), families: "
              f"{[factory.TEMPLATES[s][3] for s in sample]}")
    if not sample:
        if verbose:
            print("template library exhausted (every template already in graveyard.csv) -- "
                  "nothing new to test this cycle.")
        return []

    prices, source = load_prices()
    if verbose:
        print(f"data: {source} | {prices.index.min().date()} -> {prices.index.max().date()}")
    rv = realized_vol(prices)
    bench = benchmark_returns(prices)

    nulls = {}
    returns = {}
    for name in sample:
        sig_fn, freq, rationale, family = factory.TEMPLATES[name]
        if freq not in nulls:
            nulls[freq] = noise_floor(prices, freq, NULL_TRIALS, rv)
        r = net_returns(prices, size_and_rebalance(prices, sig_fn(prices), freq, rv))
        returns[name] = r
        if verbose:
            print(f"\n[{family}] {name} -- {rationale}")

    n_tested = family_n_tested(sample)
    for name in sample:
        _, freq, _, _ = factory.TEMPLATES[name]
        harness_evaluate(name, returns[name], bench, nulls[freq], freq, n_tested)

    evaluated = list(sample)
    oos_returns = {name: r[r.index >= OOS_START] for name, r in returns.items()}
    oos_frame = pd.DataFrame(oos_returns).dropna(how="all")
    if len(sample) >= 2:
        pairs = factory.complementary_pairs(oos_frame, sample, top_k=1)
        if pairs:
            leg_a, leg_b, corr = pairs[0]
            combo_name = f"factory_combo_{leg_a}_{leg_b}"
            if combo_name not in already_tested:
                if verbose:
                    print(f"\nleast-correlated pair this cycle: {leg_a} + {leg_b} "
                          f"(corr {corr:+.2f}) -> building {combo_name}")
                bench_oos = bench[bench.index >= OOS_START]
                sleeve = pd.concat([oos_returns[leg_a], oos_returns[leg_b]], axis=1).dropna().mean(axis=1)
                combo = ((1 - SLEEVE) * bench_oos.reindex(sleeve.index) + SLEEVE * sleeve).dropna()
                null_k2 = matched_null(prices, bench_oos, 2, COMBO_TRIALS, rng)
                combo_n_tested = family_n_tested([combo_name])
                piggyback_evaluate(combo_name, combo, bench_oos, null_k2, 2,
                                   (leg_a, leg_b), combo_n_tested)
                evaluated.append(combo_name)
    return evaluated


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=DEFAULT_N,
                    help=f"candidates to draw this cycle (default {DEFAULT_N})")
    ap.add_argument("--seed", type=int, default=None,
                    help="fixed RNG seed for a reproducible run (default: OS entropy)")
    args = ap.parse_args()
    evaluated = run_cycle(n=args.n, seed=args.seed)
    print(f"\nevaluated {len(evaluated)} candidate(s) this cycle, appended to graveyard.csv: "
          f"{evaluated}")


if __name__ == "__main__":
    main()
