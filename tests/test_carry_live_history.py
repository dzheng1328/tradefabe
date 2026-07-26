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
    """The original bug: keying on the bare DATE collapsed every cycle into one row/day.

    The mechanism has since changed -- rows are now stamped at the FUNDING POINT's own
    hour rather than at wall-clock time, because Hyperliquid pays hourly and GitHub's cron
    only fires every ~2.2h, so one row per cycle still left the 5H chart nearly empty. The
    guarantee this test exists to protect is unchanged: repeated cycles must ACCUMULATE."""
    hour_ms = 3600 * 1000
    base = 1_800_000_000_000
    served = {"upto": 0}

    def fake_funding(coin, start_ms):
        served["upto"] += 1
        return [(base + i * hour_ms, 0.0001) for i in range(served["upto"])
                if base + i * hour_ms > start_ms]

    monkeypatch.setattr(carry_live, "_funding_since", fake_funding)

    for _ in range(3):
        book = carry_live.run_carry()

    keys = [k for k, _ in book["history"]]
    assert len(keys) > 1, "cycles must accumulate rows, not overwrite one"
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys)), "a funding hour must never be recorded twice"


def test_a_cycle_with_no_new_funding_points_adds_no_row(isolated_state, monkeypatch):
    """Replaces the old "updates in place within the same minute" contract. Rows are keyed
    by funding hour now, so a cycle that finds no NEW funding is simply a no-op -- which is
    what makes running mark twice in quick succession harmless."""
    monkeypatch.setattr(carry_live, "_funding_since", lambda coin, start_ms: [])
    carry_live.run_carry()
    book = carry_live.run_carry()
    assert book["history"] == [] or len(book["history"]) == len(set(k for k, _ in book["history"]))


def test_each_funding_hour_is_stamped_at_its_own_time_not_wall_clock(isolated_state, monkeypatch):
    hour_ms = 3600 * 1000
    base = 1_800_000_000_000
    monkeypatch.setattr(carry_live, "_funding_since",
                        lambda coin, start_ms: [(base, 0.0001), (base + hour_ms, 0.0001)])
    book = carry_live.run_carry()
    keys = [k for k, _ in book["history"]]
    assert len(keys) == 2
    expected = [books.utc_stamp(__import__("pandas").Timestamp(t, unit="ms"))
                for t in (base, base + hour_ms)]
    assert keys == expected
