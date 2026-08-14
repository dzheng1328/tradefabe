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
