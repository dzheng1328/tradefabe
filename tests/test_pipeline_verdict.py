"""research/pipeline_verdict.py (#180): the research pipeline's OOS test runner +
promotion cap.

Three things matter more than any other behavior here: every pending pre-registered
candidate gets exactly one graveyard.csv row regardless of verdict, a DEAD verdict is a
terminal outcome -- never promoted "anyway" the way the factory's own original mistake
(#98) did -- and promotion is capped by its OWN pool (tradefabe.pipeline.
MAX_PIPELINE_PROMOTED), separate from the factory's.

The plumbing tests (pending-candidate discovery, spec reconstruction, one-row-per-
candidate logging) run harness.evaluate() for real against synthetic data, the same way
test_factory_run.py does, and only assert the verdict lands in {ALIVE, DEAD}. The
promotion-cap and DEAD-terminal tests monkeypatch harness.last_verdict() directly so they
do not depend on which way a random synthetic series happens to score.
"""
import json
import os

import numpy as np
import pandas as pd
import pytest

import harness
import pipeline_register
import pipeline_verdict as pv
from tradefabe import books


def _synthetic_prices(n=1200, seed=3):
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    cols = ["SPY", "QQQ", "IEF", "TLT", "GLD"]
    drift = rng.uniform(0.02, 0.08, len(cols)) / 252
    vol = rng.uniform(0.10, 0.20, len(cols)) / np.sqrt(252)
    rets = rng.normal(drift, vol, size=(n, len(cols)))
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=cols)


NAME_A = "rp_single_asset_trend_SPY_90"
NAME_B = "rp_pair_zscore_GLD_TLT"


def _record_pipeline_ledger_row(name, primitive, params, freq="M"):
    row = {"timestamp": "2026-08-04T00:00:00+00:00", "name": name, "primitive": primitive,
           "freq": freq, "params": json.dumps(params), "rationale": "x", "citation": "y"}
    header = not os.path.exists(harness.PIPELINE_LEDGER)
    pd.DataFrame([row]).to_csv(harness.PIPELINE_LEDGER, mode="a", header=header, index=False)


def _preregister(name):
    row = {"timestamp": "2026-08-04T00:00:01+00:00", "name": name}
    header = not os.path.exists(pipeline_register.PREREGISTERED_LEDGER)
    pd.DataFrame([row]).to_csv(pipeline_register.PREREGISTERED_LEDGER, mode="a",
                               header=header, index=False)


def _preregister_candidate(name, primitive="single_asset_trend", params=None, freq="M"):
    """A candidate that's both logged to PIPELINE_LEDGER (#177's proposal-time ledger,
    which #180 reads for the full spec) and pre-registered (#179) -- the state #180
    expects to find a pending candidate in."""
    params = params if params is not None else {"ticker": "SPY", "lookback": 90}
    _record_pipeline_ledger_row(name, primitive, params, freq)
    _preregister(name)


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "graveyard.csv"))
    monkeypatch.setattr(harness, "PIPELINE_LEDGER", str(tmp_path / "pipeline_ideas.csv"))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "gen.csv"))
    monkeypatch.setattr(harness, "NULL_TRIALS", 30)   # plumbing tests, not statistical precision
    monkeypatch.setattr(harness, "load_prices", lambda: (_synthetic_prices(), "SYNTHETIC (test)"))
    monkeypatch.setattr(pipeline_register, "PREREGISTERED_LEDGER", str(tmp_path / "preregistered.csv"))
    monkeypatch.setattr(pipeline_register, "STRATEGIES_PATH", str(tmp_path / "STRATEGIES.md"))
    monkeypatch.setattr(pv, "PIPELINE_RETURNS_PATH", str(tmp_path / "pipeline_returns.csv"))
    monkeypatch.setattr(pv.pkg_pipeline, "PROMOTED_PIPELINE_PATH", tmp_path / "promoted_pipeline.json")
    # pipeline_owned_count() reads each promoted book's own ledger via books.load() to
    # check retirement status -- point it at scratch too, same reason test_factory_run.py's
    # scratch_graveyard fixture patches factory_run.books.STATE_DIR.
    monkeypatch.setattr(pv.books, "STATE_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------- pending_candidates
def test_pending_candidates_is_empty_with_no_preregistration_ledger(scratch):
    assert pv.pending_candidates() == []


def test_pending_candidates_lists_a_preregistered_untested_name(scratch):
    _preregister_candidate(NAME_A)
    assert pv.pending_candidates() == [NAME_A]


def test_pending_candidates_excludes_a_name_already_in_the_graveyard(scratch):
    _preregister_candidate(NAME_A)
    row = {"strategy": NAME_A, "verdict": "DEAD", "timestamp": "2026-08-04T00:00:02+00:00"}
    pd.DataFrame([row]).to_csv(harness.GRAVEYARD, index=False)
    assert pv.pending_candidates() == []


def test_pending_candidates_preserves_preregistration_order(scratch):
    _preregister_candidate(NAME_B, primitive="pair_zscore",
                           params={"ticker_a": "GLD", "ticker_b": "TLT", "z_window": 60,
                                  "z_entry": 2.0, "z_stop": 4.0}, freq="D")
    _preregister_candidate(NAME_A)
    assert pv.pending_candidates() == [NAME_B, NAME_A]


# ---------------------------------------------------------------- _spec_for
def test_spec_for_reconstructs_the_full_proposal(scratch):
    _record_pipeline_ledger_row(NAME_A, "single_asset_trend", {"ticker": "SPY", "lookback": 90}, "M")
    spec = pv._spec_for(NAME_A)
    assert spec == {"name": NAME_A, "primitive": "single_asset_trend", "freq": "M",
                    "params": {"ticker": "SPY", "lookback": 90}}


def test_spec_for_raises_for_a_name_with_no_ledger_row(scratch):
    pd.DataFrame(columns=["timestamp", "name", "primitive", "freq", "params",
                          "rationale", "citation"]).to_csv(harness.PIPELINE_LEDGER, index=False)
    with pytest.raises(RuntimeError, match="no PIPELINE_LEDGER row"):
        pv._spec_for("rp_never_proposed")


# ---------------------------------------------------------------- run_pending_oos_tests
def test_nothing_pending_means_no_evaluation_and_an_empty_result(scratch):
    assert pv.run_pending_oos_tests(verbose=False) == []
    assert not os.path.exists(harness.GRAVEYARD)


def test_a_pending_candidate_gets_exactly_one_graveyard_row(scratch):
    _preregister_candidate(NAME_A)
    results = pv.run_pending_oos_tests(verbose=False)
    assert len(results) == 1
    assert results[0]["name"] == NAME_A
    assert results[0]["verdict"] in ("ALIVE", "DEAD")

    gy = pd.read_csv(harness.GRAVEYARD)
    assert list(gy["strategy"]) == [NAME_A]


def test_a_second_call_does_not_retest_an_already_tested_candidate(scratch):
    _preregister_candidate(NAME_A)
    pv.run_pending_oos_tests(verbose=False)
    assert pv.run_pending_oos_tests(verbose=False) == []

    gy = pd.read_csv(harness.GRAVEYARD)
    assert len(gy) == 1   # not re-tested, not duplicated


def test_a_dead_verdict_is_never_promoted(scratch, monkeypatch):
    """#180's own issue text: DEAD candidates log to graveyard.csv and STOP, explicitly
    NOT promoted "anyway" -- the factory's original #98 mistake, must not repeat it even
    by omission. harness.last_verdict is forced here so this doesn't depend on whether
    the synthetic series happens to score ALIVE or DEAD for real."""
    _preregister_candidate(NAME_A)
    monkeypatch.setattr(harness, "last_verdict", lambda name: "DEAD")

    results = pv.run_pending_oos_tests(verbose=False)
    assert results == [{"name": NAME_A, "verdict": "DEAD", "promoted": False}]
    assert pv.pkg_pipeline.load_promoted_pipeline() == []
    assert not os.path.exists(pv.PIPELINE_RETURNS_PATH)


def test_an_alive_verdict_is_promoted_and_gets_a_persisted_curve(scratch, monkeypatch):
    _preregister_candidate(NAME_A)
    monkeypatch.setattr(harness, "last_verdict", lambda name: "ALIVE")

    results = pv.run_pending_oos_tests(verbose=False)
    assert results == [{"name": NAME_A, "verdict": "ALIVE", "promoted": True}]

    promoted = pv.pkg_pipeline.load_promoted_pipeline()
    assert [e["name"] for e in promoted] == [NAME_A]
    assert promoted[0]["primitive"] == "single_asset_trend"

    curve = pd.read_csv(pv.PIPELINE_RETURNS_PATH, index_col=0)
    assert NAME_A in curve.columns


def test_promotion_is_idempotent_for_the_same_name(scratch, monkeypatch):
    _preregister_candidate(NAME_A)
    monkeypatch.setattr(harness, "last_verdict", lambda name: "ALIVE")
    pv.run_pending_oos_tests(verbose=False)

    # force a re-run against the same name by wiping the graveyard row it earned, the
    # only thing pending_candidates() checks -- promote_pipeline() must still be a no-op
    os.remove(harness.GRAVEYARD)
    pv.run_pending_oos_tests(verbose=False)

    promoted = pv.pkg_pipeline.load_promoted_pipeline()
    assert len(promoted) == 1   # not duplicated


def test_promotion_stops_once_the_pipeline_pool_is_at_cap(scratch, monkeypatch):
    monkeypatch.setattr(pv.pkg_pipeline, "MAX_PIPELINE_PROMOTED", 1)
    monkeypatch.setattr(harness, "last_verdict", lambda name: "ALIVE")

    _preregister_candidate(NAME_A)
    first = pv.run_pending_oos_tests(verbose=False)
    assert first[0]["promoted"] is True

    _preregister_candidate(NAME_B, primitive="pair_zscore",
                           params={"ticker_a": "GLD", "ticker_b": "TLT", "z_window": 60,
                                  "z_entry": 2.0, "z_stop": 4.0}, freq="D")
    second = pv.run_pending_oos_tests(verbose=False)
    assert second == [{"name": NAME_B, "verdict": "ALIVE", "promoted": False}]

    promoted = pv.pkg_pipeline.load_promoted_pipeline()
    assert [e["name"] for e in promoted] == [NAME_A]   # the cap held -- B still evaluated
    gy = pd.read_csv(harness.GRAVEYARD)                # and logged, just not promoted
    assert set(gy["strategy"]) == {NAME_A, NAME_B}


def test_a_retired_promoted_book_frees_a_slot(scratch, monkeypatch):
    """pipeline_owned_count() must check books.is_retired(), not just registry length --
    the registry is append-only (mirrors factory_run.factory_owned_count()'s own
    reasoning), so a slot freed by `tradefabe retire` must actually count as free."""
    monkeypatch.setattr(pv.pkg_pipeline, "MAX_PIPELINE_PROMOTED", 1)
    monkeypatch.setattr(harness, "last_verdict", lambda name: "ALIVE")

    _preregister_candidate(NAME_A)
    pv.run_pending_oos_tests(verbose=False)
    assert pv.pipeline_owned_count() == 1

    books.save(books.load(NAME_A))   # retire() refuses a name with no ledger on disk yet
    books.retire(NAME_A, reason="test retirement")
    assert pv.pipeline_owned_count() == 0

    _preregister_candidate(NAME_B, primitive="pair_zscore",
                           params={"ticker_a": "GLD", "ticker_b": "TLT", "z_window": 60,
                                  "z_entry": 2.0, "z_stop": 4.0}, freq="D")
    results = pv.run_pending_oos_tests(verbose=False)
    assert results == [{"name": NAME_B, "verdict": "ALIVE", "promoted": True}]
