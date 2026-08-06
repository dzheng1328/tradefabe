import pandas as pd
from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_books_summary_matches_load_paper_state():
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200

    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        assert resp.json() == []
    else:
        assert resp.json() == psum.astype(object).fillna(None).to_dict(orient="records")


def test_books_summary_is_a_list_of_dicts_with_expected_keys():
    client = TestClient(app)
    body = client.get("/api/books/summary").json()
    if not body:
        return  # no paper state in this environment -- nothing more to assert
    row = body[0]
    for key in ("book", "equity", "return", "last_run"):
        assert key in row
