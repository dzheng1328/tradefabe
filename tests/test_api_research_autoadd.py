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


def test_all_candidate_returns_is_not_cached_across_calls(monkeypatch):
    """2026-08-15: _all_candidate_returns() was wrapped in @functools.cache with no
    invalidation -- once a long-lived process (the FastAPI dev server, or app.py's
    Streamlit process) called it once, a newly-committed factory/pipeline curve stayed
    invisible on the Research Lab overview growth chart/correlation table until the
    process restarted. This proves a SECOND call sees data that changed after the
    FIRST call."""
    idx = pd.date_range("2018-01-01", periods=5, freq="D")
    full = pd.DataFrame(
        {"a": [0.001] * 5, "bench_6040": [0.0005] * 5, "spy": [0.0004] * 5}, index=idx
    )
    meta = {"oos_start": idx[0].isoformat()}
    monkeypatch.setattr(dashboard, "load_backtest", lambda: (full, meta, None, None))
    monkeypatch.setattr(dashboard, "load_pipeline_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_hourly_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_kronos_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pairs_backtest", lambda: None)

    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: None)
    combined_before, _bench = dashboard._all_candidate_returns()
    assert "brand_new_factory_candidate" not in combined_before.columns

    new_curve = pd.DataFrame({"brand_new_factory_candidate": [0.002] * 5}, index=idx)
    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: new_curve)
    combined_after, _bench = dashboard._all_candidate_returns()
    assert "brand_new_factory_candidate" in combined_after.columns


def test_load_generated_ledger_is_not_cached_across_calls(tmp_path, monkeypatch):
    """Same bug, same fix, for the factory's own name/family/rationale ledger -- a
    freshly-generated candidate's family/rationale must resolve without a restart."""
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    ledger_before = dashboard._load_generated_ledger()
    assert "tsmom_gen_999d" not in ledger_before

    pd.DataFrame([{"name": "tsmom_gen_999d", "family": "A", "rationale": "..."}]).to_csv(
        tmp_path / "generated_templates.csv", index=False
    )
    ledger_after = dashboard._load_generated_ledger()
    assert "tsmom_gen_999d" in ledger_after


def test_load_pipeline_ledger_is_not_cached_across_calls(tmp_path, monkeypatch):
    """Same bug, same fix, for the research pipeline's own rp_-prefixed ledger."""
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    ledger_before = dashboard._load_pipeline_ledger()
    assert "rp_new_idea_999" not in ledger_before

    pd.DataFrame([{"name": "rp_new_idea_999", "rationale": "..."}]).to_csv(
        tmp_path / "pipeline_ideas.csv", index=False
    )
    ledger_after = dashboard._load_pipeline_ledger()
    assert "rp_new_idea_999" in ledger_after
