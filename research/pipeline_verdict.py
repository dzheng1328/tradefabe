"""
pipeline_verdict.py — the research pipeline's OOS test runner + promotion cap (#180).

Once a spec is pre-registered (#179 -- frozen to STRATEGIES.md and
pipeline_preregistered.csv, before this module ever runs), this module runs the SAME
doctrine gate every other family goes through: harness.evaluate()/noise_floor(), against
the pipeline's own segregated n_tested bucket (DOCTRINE v1.10, #176 -- a pipeline
candidate's name is `rp_`-prefixed, so harness.family_n_tested() classifies it as
pipeline-origin automatically). No lighter bar for having arrived via an automatic
pre-registration checkpoint.

Every candidate this runs -- ALIVE or DEAD -- gets exactly one graveyard.csv row, same as
every other strategy in this lab ("one verdict per spec," STRATEGIES.md's roster rule 2).

PROMOTION is capped and origin-segregated, mirroring research/factory_run.py's
MAX_FACTORY_PROMOTED (#147) but as its OWN pool (tradefabe.pipeline.MAX_PIPELINE_PROMOTED
= 10, Dave's explicit call, 2026-08-04) -- these are a different kind of candidate,
deserving their own budget rather than competing with factory promotions for the same
slots, per #180's own issue text. At/over the cap, a candidate is still evaluated and
logged, promotion just doesn't happen until a slot is freed by `tradefabe retire`.

DEAD candidates are NEVER promoted "anyway" regardless of verdict -- unlike the factory's
"best of cycle, regardless of verdict" rule (#28b), which exists because the factory
always promotes exactly one candidate per cycle to keep its research value even when nothing
that day is a real edge. The pipeline has no such per-cycle promotion quota: a DEAD verdict
here is a terminal outcome, full stop. This is the factory's own original mistake (#98,
where every draw simply raised n_tested for everyone with no promotion gate at all) framed
the other way around, and #180's own issue text is explicit that omitting this check would
repeat it.

Usage: PYTHONPATH=src:.:research python research/pipeline_verdict.py
"""
from __future__ import annotations
import json
import os

import pandas as pd

import harness
import pipeline_register
from tradefabe import books
from tradefabe import pipeline as pkg_pipeline

PIPELINE_RETURNS_PATH = os.path.join(harness.ART, "pipeline_returns.csv")


def pending_candidates() -> list[str]:
    """Pre-registered pipeline names (#179) with no graveyard.csv row yet -- the
    machine-readable "pre-registered, not yet OOS-tested" queue pipeline_register.py's
    own docstring promised this module. In pre-registration order (oldest first) so a
    backlog -- e.g. this module not having run for a few days -- clears in the order
    specs were frozen, not an arbitrary one."""
    if not os.path.exists(pipeline_register.PREREGISTERED_LEDGER):
        return []
    ledger = pd.read_csv(pipeline_register.PREREGISTERED_LEDGER)
    already_tested = harness.graveyard_strategy_names()
    names = list(dict.fromkeys(ledger["name"]))   # de-dup, preserve first-seen order
    return [n for n in names if n not in already_tested]


def _spec_for(name: str) -> dict:
    """Pulls a pending candidate's full spec back from PIPELINE_LEDGER
    (pipeline_ideas.record_proposal() writes one row per proposal, at proposal time --
    long before screening, pre-registration, or this OOS test). This is the SAME ledger
    #176 already reads for origin classification; #180 just also reads its
    primitive/params/freq/rationale/citation columns, which #176 itself never needed.

    Returns every field a caller downstream of proposal could need -- #180's OOS test
    only reads primitive/params/freq, but pipeline_daily.py's screening backlog (added
    when #181's research routine started writing PIPELINE_LEDGER rows directly, not
    through propose_idea()'s in-process API call) needs rationale/citation too, to
    pre-register a passing candidate the same way preregister_candidate() always has."""
    ledger = pd.read_csv(harness.PIPELINE_LEDGER)
    rows = ledger[ledger["name"] == name]
    if not len(rows):
        raise RuntimeError(f"{name!r} has no PIPELINE_LEDGER row -- cannot reconstruct its spec")
    row = rows.iloc[-1]
    return {"name": name, "primitive": row["primitive"], "freq": row["freq"],
            "params": json.loads(row["params"]), "rationale": row["rationale"],
            "citation": row["citation"]}


def pipeline_owned_count() -> int:
    """Current size of the pool MAX_PIPELINE_PROMOTED bounds -- mirrors
    factory_run.factory_owned_count(): the promotion registry is a pure append-only log
    (books.retire() never removes a name from it), so a retired book must be excluded by
    checking books.is_retired() per name, not by registry length alone."""
    names = [e["name"] for e in pkg_pipeline.load_promoted_pipeline()]
    return sum(1 for n in names if not books.is_retired(books.load(n)))


def _persist_backtest_curve(name: str, r_oos: pd.Series) -> None:
    """Persists a PROMOTED candidate's OOS return series to artifacts/pipeline_returns.csv
    (git-tracked, same shape as factory_returns.csv) -- app.py's book_panel_data() and
    _dead_strategy_returns() need this for a live pipeline book to have a backtest curve
    at all; CLAUDE.md's own documented gotcha ("a new source that can become a live book
    needs its own persisted-curve story") is exactly this."""
    if os.path.exists(PIPELINE_RETURNS_PATH):
        existing = pd.read_csv(PIPELINE_RETURNS_PATH, index_col=0, parse_dates=True)
        existing[name] = r_oos
        existing.to_csv(PIPELINE_RETURNS_PATH)
    else:
        os.makedirs(harness.ART, exist_ok=True)
        r_oos.rename(name).to_frame().to_csv(PIPELINE_RETURNS_PATH)


def run_pending_oos_tests(verbose: bool = True) -> list[dict]:
    """Runs the real doctrine evaluation on every pending pre-registered candidate
    (usually 0 or 1, given #177's one-proposal-per-day rate limit, but a backlog is
    handled the same way). Returns a list of {"name", "verdict", "promoted"} summaries,
    one per candidate actually tested this call."""
    pending = pending_candidates()
    if not pending:
        if verbose:
            print("[pipeline_verdict] nothing pending -- no pre-registered candidate "
                  "is waiting on an OOS test")
        return []

    prices, source = harness.load_prices()
    if verbose:
        print(f"[pipeline_verdict] data: {source} | {prices.index.min().date()} -> "
              f"{prices.index.max().date()}")
    rv = harness.realized_vol(prices)
    bench = harness.benchmark_returns(prices)
    nulls: dict[str, object] = {}

    results = []
    for name in pending:
        spec = _spec_for(name)
        sig_fn = pkg_pipeline.build_signal(spec["primitive"], spec["params"])
        freq = spec["freq"]
        if freq not in nulls:
            nulls[freq] = harness.noise_floor(prices, freq, harness.NULL_TRIALS, rv)

        r_full = harness.net_returns(prices, harness.size_and_rebalance(
            prices, sig_fn(prices), freq, rv))
        n_tested = harness.family_n_tested([name])
        harness.evaluate(name, r_full, bench, nulls[freq], freq, n_tested)
        verdict = harness.last_verdict(name)

        promoted = False
        if verdict == "ALIVE":
            owned = pipeline_owned_count()
            if owned >= pkg_pipeline.MAX_PIPELINE_PROMOTED:
                if verbose:
                    print(f"[pipeline_verdict] pipeline-owned pool at "
                          f"{owned}/{pkg_pipeline.MAX_PIPELINE_PROMOTED} -- {name} is "
                          f"ALIVE but promotion is skipped this cycle (still evaluated "
                          f"and logged to graveyard.csv). Retire one with `tradefabe "
                          f"retire <book>` to free a slot.")
            else:
                pkg_pipeline.promote_pipeline(spec)
                r_oos = r_full[r_full.index >= harness.OOS_START]
                _persist_backtest_curve(name, r_oos)
                promoted = True
                if verbose:
                    print(f"[pipeline_verdict] {name} ALIVE -> promoted to a live paper "
                          f"book (opens at $100k on the next `tradefabe run`)")
        elif verbose:
            print(f"[pipeline_verdict] {name} DEAD -> graveyard.csv, no rescue, "
                  f"not promoted")

        results.append({"name": name, "verdict": verdict, "promoted": promoted})

    return results


def main():
    run_pending_oos_tests()


if __name__ == "__main__":
    main()
