from fastapi.testclient import TestClient

from tradefabe.api.main import app
from tradefabe import dashboard


def test_up_for_review_matches_the_dashboard_helper():
    client = TestClient(app)
    resp = client.get("/api/books/up_for_review")
    assert resp.status_code == 200
    body = resp.json()
    assert "books" in body

    psum, phist = dashboard.load_paper_state()
    if psum is None:
        assert body["books"] == []
        return
    expected = dashboard.books_up_for_review(psum, phist)
    assert len(body["books"]) == len(expected)


def test_up_for_review_rows_carry_a_verdict_field():
    client = TestClient(app)
    body = client.get("/api/books/up_for_review").json()
    for row in body["books"]:
        assert "verdict" in row
        assert "days_live" in row
        assert "introduced" in row
