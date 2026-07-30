"""
factory_run.py — the strategy factory's daily driver (#28, #28b).

Fills a bounded batch (default 20/day, --n to change) from two sources, in order:
  1. tradefabe.factory.TEMPLATES -- the pre-registered, hand-reviewed library.
  2. Once that's exhausted (or from the start, once it always is), LIVE GENERATION --
     factory.generate_candidate() draws a fresh parameter from a pre-registered RANGE
     per family (fixed in factory.py, not adjusted based on results) and logs the full
     spec to factory.GENERATED_LEDGER (git-tracked) at generation time, before its
     verdict is known. This is the compromise Dave asked for explicitly: templates can
     be generated at runtime rather than capped at a fixed list, AS LONG AS every one is
     logged the same way a pre-registered template would be -- no file-drawer problem,
     just a bigger, runtime-extended version of the same "the count IS the record"
     principle graveyard.csv already embodies.

Every candidate in the batch -- template or generated -- goes through the SAME doctrine
gate every hand-tested strategy goes through (harness.evaluate(), DSR/CPCV-gated per
DOCTRINE v1.4 -- no lighter bar for being machine-generated or for being drawn instead
of hand-picked), and every result is appended to graveyard.csv exactly like every other
strategy, regardless of verdict.

After the whole batch is evaluated, one correlation-picked combo is built from the
least-correlated pair in the batch (unchanged from #28) -- evaluated and logged, but not
eligible for promotion (see below).

PROMOTION (#28b, supersedes #29's "promote if ALIVE" rule): the SINGLE best individual
candidate this cycle, ranked by DSR, is promoted to a live paper book regardless of
verdict -- Dave's explicit call: "it doesn't have to be a winner... we still note
whether it's alive or dead but just keep track of it." A promoted DEAD candidate is
monitor-only, same status DOCTRINE v1.2 already gives backtest-DEAD hand-picked books
kept live for research value. This accumulates one new book per cycle -- Dave's explicit
choice over a single rotating "champion" slot. The combo is excluded from this ranking:
piggyback.py's registry is still a fixed hand-picked dict, not yet dynamic; wiring combo
promotion through it is a natural follow-up, not half-wired here.

Usage: .venv/bin/python research/factory_run.py [--n N] [--seed SEED]
"""
from __future__ import annotations
import argparse
import os
import numpy as np
import pandas as pd

from tradefabe.engine import load_prices, size_and_rebalance, net_returns, realized_vol
from harness import (benchmark_returns, noise_floor, evaluate as harness_evaluate,
                     family_n_tested, graveyard_strategy_names, rows_for,
                     OOS_START, NULL_TRIALS, ART)
from tradefabe import factory
from piggyback_backtest import matched_null, evaluate as piggyback_evaluate, SLEEVE

DEFAULT_N = 20          # candidates drawn per cycle -- a config knob, not a fixed trial count
COMBO_TRIALS = 150       # matched-null trials for the one cycle-ending combo (same as piggyback_backtest.py)
MAX_GENERATION_ATTEMPTS_PER_SLOT = 50   # generate_candidate()'s own internal retry cap
FACTORY_RETURNS_PATH = os.path.join(ART, "factory_returns.csv")


def _persist_backtest_curve(name, r_oos):
    """Persists a PROMOTED candidate's OOS return series to artifacts/factory_returns.csv
    (git-tracked, same as full_returns.csv/piggyback_returns.csv) -- only called for the
    single cycle winner, not all `n` tested, so this doesn't grow at 20/day. app.py's
    book_panel_data() needs this for a promoted book's live-vs-backtest divergence chart;
    without it, a live book with no entry in full_returns.csv OR piggyback_returns.csv
    has no backtest curve at all and the dashboard crashes trying to look one up."""
    if os.path.exists(FACTORY_RETURNS_PATH):
        existing = pd.read_csv(FACTORY_RETURNS_PATH, index_col=0, parse_dates=True)
        existing[name] = r_oos
        existing.to_csv(FACTORY_RETURNS_PATH)
    else:
        os.makedirs(ART, exist_ok=True)
        r_oos.rename(name).to_frame().to_csv(FACTORY_RETURNS_PATH)


_FREQ_ORDER = {"D": 0, "W": 1, "M": 2}


def _combo_spec(name, candidates, leg_a, leg_b):
    """Legs carry their full spec so a fresh runner process can rebuild both signals.
    The book rebalances at the FINER of the two legs' frequencies -- a daily leg blended
    into a monthly-rebalanced book would only refresh its signal 12x/yr, which is not the
    strategy that was backtested."""
    by_name = {c["name"]: c for c in candidates}
    legs = []
    for leg in (leg_a, leg_b):
        c = by_name[leg]
        legs.append({"name": leg, "family": c["family"], "params": c["params"]})
    freq = min((by_name[leg_a]["freq"], by_name[leg_b]["freq"]), key=lambda f: _FREQ_ORDER.get(f, 9))
    return {"name": name, "freq": freq, "legs": legs}


def _template_candidates(names):
    out = []
    for name in names:
        sig_fn, freq, rationale, family = factory.TEMPLATES[name]
        out.append({"name": name, "sig_fn": sig_fn, "freq": freq, "rationale": rationale,
                    "family": family, "source": "template", "params": None})
    return out


def _fill_with_generated(candidates, n, rng, exclude, verbose):
    """Tops `candidates` up to `n` entries via live generation, round-robining across
    GENERATION_RANGES' families for the same diversity-by-construction reason
    select_diverse_sample() already round-robins TEMPLATES. Logs every generated spec
    immediately (before evaluation) -- see module docstring."""
    families = list(factory.GENERATION_RANGES)
    i = 0
    while len(candidates) < n:
        family = families[i % len(families)]
        i += 1
        spec = factory.generate_candidate(rng, family, exclude_names=exclude)
        if spec is None:
            if i > len(families) * MAX_GENERATION_ATTEMPTS_PER_SLOT:
                break   # every family's range is (near-)exhausted of fresh names; give up
            continue
        factory.log_generated(spec)
        candidates.append(spec)
        exclude.add(spec["name"])
        if verbose:
            print(f"[{family}] {spec['name']} (generated) -- {spec['rationale']}")
    return candidates


def rank_for_promotion(rows):
    """Picks this cycle's promotion winner from `rows` (rows_for()'s graveyard rows for
    the cycle's candidates) by `cpcv_sharpe_mean` -- the CPCV-resampled, ANNUALIZED OOS
    Sharpe, comparable across rebalance frequencies -- falling back to `oos_sharpe` when
    CPCV wasn't computable for a candidate (too short a series, see
    harness.cpcv_oos_sharpes).

    NOT `dsr` (#145): dsr saturates at exactly 1.0 for every daily-rebalanced candidate
    (families C/turn_of_month and I/donchian) regardless of real quality, because those
    families' noise-floor-implied luck bar (sr_star) comes out deeply negative --
    documented in harness.dsr_gate1's own docstring as the reason DOCTRINE v1.8 added a
    positive-Sharpe floor to the GRAVEYARD VERDICT. That guard was never applied to this
    ranking, so `rows["dsr"].idxmax()` was really breaking a permanent C-vs-I tie by
    candidate list order (_fill_with_generated()'s unshuffled A,B,C,D,I round-robin put C
    first) -- 6/6 promoted generated books were turn_of_month before this fix, despite
    generation itself being even across all 5 families."""
    ranked = rows.copy()
    ranked["_promotion_sharpe"] = pd.to_numeric(
        ranked["cpcv_sharpe_mean"], errors="coerce").fillna(ranked["oos_sharpe"])
    return ranked.loc[ranked["_promotion_sharpe"].idxmax()]


def run_cycle(n=DEFAULT_N, seed=None, verbose=True):
    """Runs one factory cycle: evaluate a batch of up to `n` candidates (templates
    first, then live-generated to fill the rest), one correlation-picked combo, and
    promote the single best-DSR individual regardless of verdict. Returns the list of
    newly-evaluated names (individuals + combo, if one was built). `seed=None` uses OS
    entropy (so successive daily cycles draw different candidates); pass a fixed seed
    for a reproducible test run."""
    rng = np.random.default_rng(seed)
    already_tested = graveyard_strategy_names()
    already_generated = factory.generated_names()
    exclude = set(already_tested) | already_generated

    template_names = factory.select_diverse_sample(factory.TEMPLATES, n, rng, exclude=exclude)
    candidates = _template_candidates(template_names)
    if verbose and candidates:
        print(f"drew {len(candidates)} template candidate(s), families: "
              f"{[c['family'] for c in candidates]}")
    exclude |= {c["name"] for c in candidates}
    candidates = _fill_with_generated(candidates, n, rng, exclude, verbose)

    if not candidates:
        if verbose:
            print("nothing new to test this cycle -- template library AND generation "
                  "ranges both exhausted of fresh names (exceedingly unlikely; check "
                  "GENERATION_RANGES if this actually happens).")
        return []

    prices, source = load_prices()
    if verbose:
        print(f"data: {source} | {prices.index.min().date()} -> {prices.index.max().date()}")
    rv = realized_vol(prices)
    bench = benchmark_returns(prices)

    nulls = {}
    returns = {}
    for c in candidates:
        if c["freq"] not in nulls:
            nulls[c["freq"]] = noise_floor(prices, c["freq"], NULL_TRIALS, rv)
        r = net_returns(prices, size_and_rebalance(prices, c["sig_fn"](prices), c["freq"], rv))
        returns[c["name"]] = r
        if verbose and c["source"] == "template":
            print(f"\n[{c['family']}] {c['name']} -- {c['rationale']}")

    names_this_cycle = [c["name"] for c in candidates]
    n_tested = family_n_tested(names_this_cycle)
    for c in candidates:
        harness_evaluate(c["name"], returns[c["name"]], bench, nulls[c["freq"]], c["freq"], n_tested)

    evaluated = list(names_this_cycle)
    combo_name = combo_returns = combo_spec = None
    oos_returns = {name: r[r.index >= OOS_START] for name, r in returns.items()}
    oos_frame = pd.DataFrame(oos_returns).dropna(how="all")
    if len(names_this_cycle) >= 2:
        pairs = factory.complementary_pairs(oos_frame, names_this_cycle, top_k=1)
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
                combo_returns = combo
                combo_spec = _combo_spec(combo_name, candidates, leg_a, leg_b)

    # ---- promote the single best-ranked candidate this cycle, regardless of verdict ----
    # The combo competes in this SAME ranking (#64) rather than being promoted on top of
    # the winner: it fixes the asymmetry (the factory could promote an individual it
    # discovered but not a combo it discovered) without changing the one-new-book-per-
    # cycle growth rate that CLAUDE.md documents.
    pool = names_this_cycle + ([combo_name] if combo_spec else [])
    rows = rows_for(pool)
    if len(rows):
        best = rank_for_promotion(rows)
        best_name = best["strategy"]
        if combo_spec and best_name == combo_name:
            factory.promote_combo(combo_spec)
            _persist_backtest_curve(best_name, combo_returns)
        else:
            best_candidate = next(c for c in candidates if c["name"] == best_name)
            if best_candidate["source"] == "template":
                factory.promote(best_name)
            else:
                factory.promote_generated(best_candidate)
            _persist_backtest_curve(best_name, oos_returns[best_name])
        if verbose:
            tag = "monitor-only" if best["verdict"] == "DEAD" else "ALIVE"
            print(f"\nbest of cycle: {best_name} (CPCV/OOS Sharpe {best['_promotion_sharpe']:.2f}, "
                  f"DSR {best['dsr']:.3f}, {tag}) -> promoted to a live paper book "
                  f"(opens at $100k on the next tradefabe run)")

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
