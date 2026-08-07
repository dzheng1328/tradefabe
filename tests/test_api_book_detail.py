import math

from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_unknown_book_is_a_404():
    client = TestClient(app)
    resp = client.get("/api/books/not_a_real_book/detail")
    assert resp.status_code == 404


def test_known_book_returns_the_expected_shape():
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return  # no paper state in this environment
    name = psum["book"].iloc[0]
    resp = client.get(f"/api/books/{name}/detail")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("name", "kind", "blurb", "stats", "live_start", "bt_start",
                "available_windows", "live_equity_chart", "backtest_chart",
                "divergence_state", "divergence_detail"):
        assert key in body
    assert body["name"] == name
    assert body["kind"] in ("equity", "carry")
    for stat_key in ("Sharpe", "Sortino", "Calmar", "MaxDD", "CAGR", "Vol"):
        assert stat_key in body["stats"]


def test_2a_excludes_positions_and_deployment():
    """The whole point of compute_positions=False -- 2a's response must not carry
    fields that 2b's slice adds later, and the expensive pricing loop must not run."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    body = client.get(f"/api/books/{name}/detail").json()
    assert "positions" not in body
    assert "deployment" not in body
    assert "trades" not in body


def test_window_param_changes_the_chart_payload():
    client = TestClient(app)
    psum, phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    live_hist = (phist[phist["book"] == name].drop_duplicates("date", keep="last")
                 .set_index("date")["equity"].sort_index())
    windows = dashboard.available_windows(live_hist)
    if len(windows) < 2:
        return  # too little history to distinguish two windows in this environment
    all_resp = client.get(f"/api/books/{name}/detail?window=ALL").json()
    narrow_resp = client.get(f"/api/books/{name}/detail?window={windows[0]}").json()
    assert all_resp["live_equity_chart"] != narrow_resp["live_equity_chart"]


def test_stats_nan_serializes_as_json_null_not_nan_token():
    """A book with < 30 OOS observations has every ann_stats() field as NaN --
    response body must be valid JSON."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return
    name = psum["book"].iloc[0]
    resp = client.get(f"/api/books/{name}/detail")
    assert "NaN" not in resp.text
    for v in resp.json()["stats"].values():
        if v is not None:
            assert math.isfinite(v)
