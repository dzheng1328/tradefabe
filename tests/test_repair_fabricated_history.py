"""ops/repair_fabricated_history.py's pure trimming logic (#235/#236 one-time repair).
Doesn't touch disk or CUTOFFS -- those are exercised by running the real script once,
manually, via the paper-engine workflow's repair_history job."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
from repair_fabricated_history import strip_fabricated_rows  # noqa: E402


def test_drops_rows_strictly_before_the_cutoff():
    book = {"history": [["2026-07-14T13:30", 100000.0], ["2026-08-24T15:40", 100000.0],
                         ["2026-08-24T16:39", 100021.48]]}
    removed = strip_fabricated_rows(book, "2026-08-24T15:40")
    assert removed == 1
    assert book["history"] == [["2026-08-24T15:40", 100000.0], ["2026-08-24T16:39", 100021.48]]


def test_keeps_the_row_exactly_at_the_cutoff():
    book = {"history": [["2026-08-24T15:40", 100000.0]]}
    assert strip_fabricated_rows(book, "2026-08-24T15:40") == 0
    assert len(book["history"]) == 1


def test_no_op_when_nothing_is_before_the_cutoff():
    book = {"history": [["2026-08-25T00:00", 100000.0], ["2026-08-26T00:00", 100100.0]]}
    assert strip_fabricated_rows(book, "2026-08-01T00:00") == 0
    assert len(book["history"]) == 2


def test_empty_history_is_a_no_op():
    book = {"history": []}
    assert strip_fabricated_rows(book, "2026-08-01T00:00") == 0
    assert book["history"] == []


def test_every_cutoff_is_a_real_iso_timestamp_string():
    """Guards against a typo'd cutoff silently comparing as a no-op or dropping everything
    -- string comparison only sorts correctly if every value is the same ISO shape."""
    from repair_fabricated_history import CUTOFFS
    import datetime as dt

    for name, cutoff in CUTOFFS.items():
        assert dt.datetime.fromisoformat(cutoff), f"{name}: {cutoff!r} isn't a valid ISO timestamp"
        assert len(cutoff) == len("2026-08-24T15:22:04"), f"{name}: {cutoff!r} has an unexpected shape"
