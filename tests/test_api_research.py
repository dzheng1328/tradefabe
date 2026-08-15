import numpy as np
from fastapi.testclient import TestClient

from tradefabe.api.main import app


def test_overview_returns_expected_shape():
    client = TestClient(app)
    resp = client.get("/api/research/overview")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("meta", "stats", "strategies", "growth_chart", "correlation_heatmap"):
        assert key in body
    for key in ("source", "start", "end", "oos_start", "n_assets"):
        assert key in body["meta"]
    for key in ("n_tested", "n_alive", "n_dead", "luck_floor_p95", "best_strategy",
                "best_sharpe", "bench_sharpe"):
        assert key in body["stats"]
    assert body["stats"]["n_tested"] == body["stats"]["n_alive"] + body["stats"]["n_dead"]
    assert isinstance(body["strategies"], list) and len(body["strategies"]) > 0


def test_verdicts_row_count_matches_latest_verdicts():
    from tradefabe import dashboard
    client = TestClient(app)
    resp = client.get("/api/research/verdicts")
    assert resp.status_code == 200
    body = resp.json()
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    assert len(body["rows"]) == gy_last.shape[0]
    row = body["rows"][0]
    for key in ("strategy", "freq", "oos_sharpe", "oos_sortino", "oos_calmar",
                "oos_maxdd", "corr_bench", "null_p95", "verdict"):
        assert key in row
    assert row["verdict"] in ("ALIVE", "DEAD")


def test_verdicts_loads_each_ledger_at_most_once_per_request(monkeypatch):
    """Final-review finding 1: research_verdicts() loops over every graveyard row
    (487 as of 2026-08-14) calling dashboard.research_kind(strategy) per row.
    research_kind() calls _load_pipeline_ledger() unconditionally and
    _load_generated_ledger() on most rows -- both deliberately uncached (2026-08-15
    removal of a stale @functools.cache), so an unhoisted per-row call re-read
    generated_templates.csv/pipeline_ideas.csv from disk on every row, measured at
    ~1.5s for the full graveyard. Confirm each loader is now called at most once per
    request regardless of row count."""
    from tradefabe import dashboard

    calls = {"generated": 0, "pipeline": 0}
    real_generated = dashboard._load_generated_ledger
    real_pipeline = dashboard._load_pipeline_ledger

    def counting_generated():
        calls["generated"] += 1
        return real_generated()

    def counting_pipeline():
        calls["pipeline"] += 1
        return real_pipeline()

    monkeypatch.setattr(dashboard, "_load_generated_ledger", counting_generated)
    monkeypatch.setattr(dashboard, "_load_pipeline_ledger", counting_pipeline)

    client = TestClient(app)
    resp = client.get("/api/research/verdicts")
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) > 0
    assert calls["generated"] <= 1
    assert calls["pipeline"] <= 1


def test_strategy_detail_unknown_name_is_404():
    client = TestClient(app)
    resp = client.get("/api/research/strategy/not_a_real_strategy")
    assert resp.status_code == 404


def test_strategy_detail_known_strategy_has_expected_shape():
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    name = gy_last.index[0]
    resp = client.get(f"/api/research/strategy/{name}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == name
    assert body["verdict"] in ("ALIVE", "DEAD")
    assert "Sharpe" in body["stats"]
    if body["has_returns"]:
        assert "CAGR" in body["stats"] and "Vol" in body["stats"]
        assert body["chart"] is not None
    else:
        assert body["chart"] is None


def test_luck_floor_unknown_strategy_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/luck_floor?strategy=not_a_real_strategy")
    assert resp.status_code == 400


def test_luck_floor_known_strategy_returns_chart():
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strategy = gy_last.index[0]
    resp = client.get(f"/api/research/luck_floor?strategy={strategy}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body and "label" in body


def test_luck_floor_falls_back_to_legacy_per_frequency_nulls_shape():
    """Regression test: the real artifacts/nulls.npz on disk is keyed by {D,M,W}, not
    per-strategy, so `strategy not in nulls` used to be true for every strategy and the
    endpoint 400'd for everything. Pick a real strategy whose name isn't itself a key in
    `nulls` (true for any real strategy under the legacy shape) and confirm the endpoint
    falls back to the strategy's own frequency bucket instead of 400ing. Also confirms the
    per-frequency response is labeled as a SHARED distribution (DOCTRINE v1.5 distinction,
    finding 2): `shape` says "per_frequency" and the label doesn't name this one strategy."""
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strategy = next(s for s in gy_last.index if s not in nulls)
    resp = client.get(f"/api/research/luck_floor?strategy={strategy}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body and "label" in body
    assert body["shape"] == "per_frequency"
    assert strategy not in body["label"]


def test_luck_floor_per_strategy_shape_does_not_fall_through_to_frequency(monkeypatch):
    """Finding 3: the real on-disk nulls.npz is legacy per-frequency shaped, so every
    other test here only exercises the `elif freq in nulls` branch. Monkeypatch
    dashboard.load_backtest to simulate the per-strategy shape DOCTRINE v1.5 / harness.py
    would produce going forward, and confirm the endpoint takes the `if strategy in nulls`
    branch: shape == "per_strategy" and the strategy name stays in the label."""
    from tradefabe import dashboard
    from tradefabe.api import main as api_main

    client = TestClient(app)
    full, meta, nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strategy = gy_last.index[0]

    fake_nulls = dict(nulls)
    fake_nulls[strategy] = np.random.default_rng(0).normal(size=500)

    def fake_load_backtest(*args, **kwargs):
        return full, meta, fake_nulls, gy

    monkeypatch.setattr(api_main.dashboard, "load_backtest", fake_load_backtest)

    resp = client.get(f"/api/research/luck_floor?strategy={strategy}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["shape"] == "per_strategy"
    assert strategy in body["label"]


def test_drawdown_bench_pick():
    client = TestClient(app)
    resp = client.get("/api/research/drawdown?pick=60/40")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body
    assert body["max_drawdown"] <= 0


def test_drawdown_unknown_pick_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/drawdown?pick=not_a_real_pick")
    assert resp.status_code == 400


def test_drawdown_resolves_strategy_not_in_full_returns_via_cascade():
    """Finding 1 regression: research_drawdown used to check `full_returns.csv` columns
    only, so 400ing for any strategy resolvable only through the factory/pipeline/etc.
    cascade research_strategy_detail already uses. Pick a real strategy that's in the
    graveyard but NOT a full_returns.csv column, confirm the drawdown endpoint now
    resolves it via the same dashboard._dead_strategy_returns cascade."""
    from tradefabe import dashboard
    import pandas as pd

    client = TestClient(app)
    full, meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    factory_bt = dashboard.load_factory_backtest()
    pipeline_bt = dashboard.load_pipeline_backtest()

    strategy = next(
        (s for s in gy_last.index
         if s not in oos.columns and factory_bt is not None and s in factory_bt.columns),
        None,
    )
    if strategy is None:
        strategy = next(
            (s for s in gy_last.index
             if s not in oos.columns and pipeline_bt is not None and s in pipeline_bt.columns),
            None,
        )
    if strategy is None:
        return  # no such strategy in this environment's artifacts -- nothing to assert

    resp = client.get(f"/api/research/drawdown?pick={strategy}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body
    assert body["max_drawdown"] is None or body["max_drawdown"] <= 0


def test_piggyback_zero_weight_matches_bench_sharpe():
    from tradefabe import dashboard
    import pandas as pd
    client = TestClient(app)
    full, meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    # Pick a strategy that has OOS backtest returns
    strat = next(s for s in gy_last.index if s in oos.columns)
    resp = client.get(f"/api/research/piggyback?sleeve={strat}&weight=0")
    assert resp.status_code == 200
    body = resp.json()
    assert abs(body["stats"]["sharpe_delta"]) < 1e-6
    assert "chart" in body


def test_piggyback_empty_sleeve_is_400():
    client = TestClient(app)
    resp = client.get("/api/research/piggyback?sleeve=&weight=30")
    assert resp.status_code == 400


def test_piggyback_weight_out_of_range_is_400():
    from tradefabe import dashboard
    import pandas as pd
    client = TestClient(app)
    full, meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    # Pick a strategy that has OOS backtest returns
    strat = next(s for s in gy_last.index if s in oos.columns)
    resp = client.get(f"/api/research/piggyback?sleeve={strat}&weight=150")
    assert resp.status_code == 400
