import math

from fastapi.testclient import TestClient

from tradefabe.api.main import app, _carry_meta_json
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


def test_carry_meta_json_passes_non_numeric_fields_through_unchanged():
    """carry_hl_meta.json's real shape mixes numeric fields with a [start, end] date-pair
    list and an ISO-string timestamp -- _finite_or_none's float(v) raises TypeError on
    the list and ValueError on the string, and blanket-routing every field through it
    silently swallowed both into None. Numeric fields must still get NaN-safety; every
    other field must survive as its original type and value."""
    raw = {"window": ["2023-05-12", "2026-07-23"], "net_yield": 0.1216,
           "gross_yield": 0.1386, "net_maxdd": -0.0132, "pct_days_positive": 0.876,
           "btc_worst_dd": -0.531, "carry_through_crash": 0.0133,
           "generated_at": "2026-07-22T19:38:49", "bad_numeric": float("nan")}
    out = _carry_meta_json(raw)
    assert out["window"] == ["2023-05-12", "2026-07-23"]
    assert out["generated_at"] == "2026-07-22T19:38:49"
    assert out["net_yield"] == 0.1216
    assert out["net_maxdd"] == -0.0132
    assert out["bad_numeric"] is None  # NaN still nulled, not left as a bare NaN token


def test_carry_book_detail_preserves_window_and_generated_at():
    """End-to-end guard on the real carry_btc_eth book (live in state/paper today):
    GET .../detail must not null out carry_meta's window/generated_at fields."""
    client = TestClient(app)
    psum, _phist = dashboard.load_paper_state()
    if psum is None or "carry_btc_eth" not in psum["book"].values:
        return  # no carry book opened in this environment
    resp = client.get("/api/books/carry_btc_eth/detail")
    assert resp.status_code == 200
    carry_meta = resp.json()["carry_meta"]
    assert carry_meta["window"] is not None
    assert isinstance(carry_meta["window"], list)
    assert carry_meta["generated_at"] is not None
    assert isinstance(carry_meta["generated_at"], str)


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
