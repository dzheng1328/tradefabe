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
    falls back to the strategy's own frequency bucket instead of 400ing."""
    from tradefabe import dashboard
    client = TestClient(app)
    _full, _meta, nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    strategy = next(s for s in gy_last.index if s not in nulls)
    resp = client.get(f"/api/research/luck_floor?strategy={strategy}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body and "label" in body


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
