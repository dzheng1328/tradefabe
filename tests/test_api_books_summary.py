import math

import pandas as pd
from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_summary_default_sort_groups_by_family():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "families" in body
    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        assert body["families"] == []
        return
    total_books = sum(len(f["books"]) for f in body["families"])
    assert total_books == len(psum)
    for fam in body["families"]:
        assert set(fam.keys()) == {"family", "label", "books"}


def test_summary_flat_sort_modes_return_a_flat_books_list():
    client = TestClient(app)
    for sort in ("recent", "return_today", "total_return"):
        resp = client.get(f"/api/books/summary?sort={sort}")
        assert resp.status_code == 200
        body = resp.json()
        assert "books" in body
        assert "families" not in body


def test_summary_unknown_sort_is_a_400():
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
