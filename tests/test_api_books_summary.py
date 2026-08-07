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


def test_nan_retired_at_becomes_json_null():
    """Directly verify that NaN in retired_at (non-retired books) becomes JSON null.

    This test is independent of the endpoint's transform: it loads the raw data,
    finds a book with NaN retired_at, makes the API call, and asserts that the
    response actually contains retired_at: None (JSON null), not NaN. This would
    fail if the astype(object).fillna(None) transform had a latent bug.
    """
    # Find a non-retired book (one with NaN retired_at) in the raw data
    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        return  # no paper state in this environment

    non_retired = psum[pd.isna(psum["retired_at"])]
    if non_retired.empty:
        return  # all books are retired in this environment

    # Pick the first non-retired book
    book_name = non_retired.iloc[0]["book"]

    # Make the API call
    client = TestClient(app)
    resp = client.get("/api/books/summary")
    assert resp.status_code == 200
    body = resp.json()

    # Find that book in the response (not by re-deriving it, but by looking it up)
    for row in body:
        if row["book"] == book_name:
            # Assert retired_at is None, not NaN or anything else
            assert row["retired_at"] is None, (
                f"Expected retired_at to be None for {book_name}, "
                f"got {row['retired_at']}"
            )
            break
    else:
        raise AssertionError(f"Book {book_name} not found in API response")
