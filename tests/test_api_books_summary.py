import math

from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_summary_default_sort_is_total_return_and_flat():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "books" in body
    assert "families" not in body
    default_body = client.get("/api/books/summary?sort=total_return").json()
    assert body == default_body


def test_summary_flat_sort_modes_return_a_flat_books_list():
    client = TestClient(app)
    for sort in ("recent", "return_today", "total_return", "sharpe"):
        resp = client.get(f"/api/books/summary?sort={sort}")
        assert resp.status_code == 200
        body = resp.json()
        assert "books" in body
        assert "families" not in body


def test_summary_family_sort_is_no_longer_accepted():
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=family")
    assert resp.status_code == 400


def test_summary_unknown_sort_is_a_400():
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=bogus")
    assert resp.status_code == 400


def test_summary_unknown_sort_is_a_400_even_with_no_paper_state(monkeypatch):
    """The sort-validity check must run before the psum-is-None early return, or an
    unknown sort silently succeeds (200 with an empty list) whenever no local paper
    state exists -- inconsistent with the same request against a populated state."""
    monkeypatch.setattr(dashboard, "load_paper_state", lambda: (None, None))
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=bogus")
    assert resp.status_code == 400


def test_summary_row_has_all_expected_keys():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    if not body["books"]:
        return  # no paper state in this environment
    row = body["books"][0]
    for key in ("book", "equity", "return", "last_run", "retired_at", "family",
                "color", "introduced", "return_today", "monitor_only", "sparkline"):
        assert key in row


def test_summary_row_color_matches_book_colors_helper():
    client = TestClient(app)
    body = client.get("/api/books/summary?sort=recent").json()
    if not body["books"]:
        return
    psum, _phist = dashboard.load_paper_state()
    expected = dashboard.book_colors(psum["book"].tolist())
    for row in body["books"]:
        assert row["color"] == expected[row["book"]]


def test_summary_show_monitor_only_false_excludes_monitor_only_books():
    client = TestClient(app)
    all_body = client.get("/api/books/summary?sort=recent&show_monitor_only=true").json()
    filtered_body = client.get("/api/books/summary?sort=recent&show_monitor_only=false").json()
    filtered_names = {r["book"] for r in filtered_body["books"]}
    for row in all_body["books"]:
        if row["monitor_only"]:
            assert row["book"] not in filtered_names


def test_summary_loads_each_ledger_at_most_once_per_request(monkeypatch):
    """Final-review finding 1/3: books_summary()'s per-row loop used to call
    dashboard.book_family(name) with no pre-loaded ledger, so each row re-read
    generated_templates.csv/pipeline_ideas.csv from disk -- fine at dozens of live
    books today, the same regression class that made research_verdicts() ~1.5s at 487
    graveyard rows. Confirm the two (deliberately uncached) loaders are each called at
    most once per request, regardless of how many books are in psum."""
    psum, _phist = dashboard.load_paper_state()
    if psum is None or psum.empty:
        return  # no local paper state in this environment -- nothing to assert

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
    resp = client.get("/api/books/summary?sort=recent")
    assert resp.status_code == 200
    assert calls["generated"] <= 1
    assert calls["pipeline"] <= 1


def test_summary_nan_fields_become_json_null_not_nan_token():
    """A book with < 2 distinct calendar days of history has NaN return_today --
    the response body must be valid JSON (null), never the bare NaN token FastAPI's
    default json.dumps(allow_nan=True) would otherwise emit."""
    client = TestClient(app)
    resp = client.get("/api/books/summary?sort=recent")
    assert "NaN" not in resp.text
    body = resp.json()
    for row in body["books"]:
        if row["return_today"] is not None:
            assert math.isfinite(row["return_today"])
