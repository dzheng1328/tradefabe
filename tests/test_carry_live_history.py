"""carry_live.run_carry()'s ledger-history keying.

The carry book used to append its history row keyed on the bare DATE, so the 30min
`tradefabe mark` cron overwrote one row per day instead of accumulating marks — the
funding accrual WAS being recomputed every cycle, it just wasn't recorded. The dashboard
then had a single point inside its 5H/1D windows and drew a dot. It now stamps to the
minute, the same key shape books.mark() uses for every equity book.

Network is monkeypatched out — this pins ledger shape, not Hyperliquid availability."""
import json

import pytest

from tradefabe import books, carry_live


@pytest.fixture
def isolated_state(monkeypatch, tmp_path):
    """books.save/_path resolve through books.STATE_DIR — point it at tmp_path so no test
    ever touches the real state/paper/ ledgers."""
    monkeypatch.setattr(books, "STATE_DIR", tmp_path)
    monkeypatch.setattr(carry_live, "_funding_since", lambda coin, start_ms: [(start_ms, 0.0001)])
    return tmp_path


def test_history_is_stamped_to_the_minute_not_the_bare_date(isolated_state):
    book = carry_live.run_carry()
    stamp = book["history"][-1][0]

    assert "T" in stamp, f"expected a minute-resolution timestamp, got {stamp!r}"
    assert len(stamp) == len("2026-07-25T12:34")


def test_repeated_cycles_accumulate_marks_instead_of_overwriting_one_daily_row(
        isolated_state, monkeypatch):
    # one wall-clock reading per CYCLE, not per call -- run_carry() reads the clock twice
    # (the history stamp and last_run), and both must see the same simulated minute.
    stamps = ["2026-07-25T12:00", "2026-07-25T12:30", "2026-07-25T13:00"]
    now = {"at": stamps[0]}

    class _FrozenClock(carry_live.dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:                       # the UTC now_ms call — real time is fine
                return super().now(tz)
            return cls.fromisoformat(now["at"])

    monkeypatch.setattr(carry_live.dt, "datetime", _FrozenClock)

    for stamp in stamps:
        now["at"] = stamp
        book = carry_live.run_carry()

    dates = [d for d, _ in book["history"]]
    assert dates == ["2026-07-25T12:00", "2026-07-25T12:30", "2026-07-25T13:00"]


def test_a_second_call_within_the_same_minute_updates_in_place(isolated_state, monkeypatch):
    class _FrozenClock(carry_live.dt.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return super().now(tz)
            return cls.fromisoformat("2026-07-25T12:00")

    monkeypatch.setattr(carry_live.dt, "datetime", _FrozenClock)

    carry_live.run_carry()
    book = carry_live.run_carry()

    assert len(book["history"]) == 1, "same-minute re-run must not duplicate the row"
    assert book["history"][0][1] == book["equity"]


def test_the_ledger_is_persisted_to_disk(isolated_state):
    carry_live.run_carry()
    saved = json.loads((isolated_state / "carry_btc_eth.json").read_text())

    assert saved["name"] == "carry_btc_eth"
    assert len(saved["history"]) == 1
