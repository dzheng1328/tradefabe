"""Regression test for the auto-add claim in
docs/superpowers/specs/2026-08-13-dashboard-research-lab-design.md: a strategy that
exists ONLY in factory_returns.csv (never in full_returns.csv, piggyback_returns.csv,
or any state/paper/*.json book file) must still resolve through
dashboard._dead_strategy_returns -- the exact code path Research Lab's strategy-detail
endpoint uses for any graveyard entry that was never promoted to a live paper book.
This is the generic-resolution guarantee CLAUDE.md's 2026-07-26 outage note warns
about breaking silently."""
import pandas as pd

from tradefabe import dashboard


def test_dead_strategy_returns_resolves_a_factory_only_strategy():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    oos = pd.DataFrame({"bench_6040": [0.001] * 10, "spy": [0.001] * 10}, index=idx)
    factory_bt = pd.DataFrame({"brand_new_factory_candidate_xyz": [0.002] * 10}, index=idx)

    result = dashboard._dead_strategy_returns(
        "brand_new_factory_candidate_xyz", oos, piggy=None, factory_bt=factory_bt,
        hourly_bt=None, kronos_bt=None, pairs_bt=None, pipeline_bt=None,
    )
    assert result is not None
    assert len(result) == 10


def test_dead_strategy_returns_resolves_a_pipeline_only_strategy():
    """Same guarantee for the pipeline's own promoted-candidate CSV (#180) -- the
    source this repo's daily pipeline actually writes to (see pipeline_returns.csv
    in dashboard.load_pipeline_backtest's docstring)."""
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    oos = pd.DataFrame({"bench_6040": [0.001] * 10, "spy": [0.001] * 10}, index=idx)
    pipeline_bt = pd.DataFrame({"rp_new_candidate_abc": [0.0015] * 10}, index=idx)

    result = dashboard._dead_strategy_returns(
        "rp_new_candidate_abc", oos, piggy=None, factory_bt=None, hourly_bt=None,
        kronos_bt=None, pairs_bt=None, pipeline_bt=pipeline_bt,
    )
    assert result is not None
    assert len(result) == 10


def test_books_summary_has_no_hardcoded_book_names():
    """books_summary()'s output is entirely a function of load_paper_state() --
    confirms the API layer itself never special-cases a strategy name (the only
    intentional exception is the frontend's single FEATURED_BOOK cosmetic pick,
    which is a UI badge, not a data-inclusion filter -- out of scope for this test)."""
    from tradefabe import dashboard
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    names_in_state = set(psum["book"].tolist())
    from fastapi.testclient import TestClient
    from tradefabe.api.main import app
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=recent")
    body = resp.json()
    names_in_response = {b["book"] for b in body["books"]}
    assert names_in_response == names_in_state
