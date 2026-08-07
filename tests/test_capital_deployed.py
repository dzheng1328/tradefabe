"""Dashboard: the midnight V-notch repair, honest unpriceable figures, trade-log frame (#109).

Three separate ways the panel lied, all silent:
  * a bare-date history row parsed to MIDNIGHT and sorted to the START of the day it
    belonged at the END of, drawing a one-minute V-notch on every chart;
  * `Series.sum()` skips NaN, so an entirely unpriceable book summed to 0.0 and rendered
    "$0 gross, $-0 equity" for a fully-deployed $100k book;
  * the caption blamed vol-targeted sizing for cash above 100% of equity, on books that
    are deliberately NOT vol-targeted, when the real cause is short proceeds.
"""
import numpy as np
import pandas as pd
import pytest

app = pytest.importorskip("app")
dashboard = pytest.importorskip("tradefabe.dashboard")


# ------------------------------------------------------------------ money()
def test_money_renders_an_unknown_value_as_a_dash_not_a_number():
    """`f"${nan:,.0f}"` renders "$nan" and `f"${-0.08:,.0f}"` renders "$-0" — both read as
    "this book is empty" when the truth is "we could not price it"."""
    assert app.money(float("nan")) == "—"
    assert app.money(None) == "—"
    assert app.money(float("inf")) == "—"


def test_money_renders_real_values_normally():
    assert app.money(145_417.89) == "$145,418"
    assert app.money(-47_481.0) == "$-47,481"
    assert app.money(0.0) == "$0"


# ------------------------------------------------------------------ bare-date repair
def write_history(tmp_path, rows):
    p = tmp_path / "state" / "paper"
    p.mkdir(parents=True)
    pd.DataFrame(rows, columns=["date", "book", "equity"]).to_csv(
        p / "history.csv", index=False)
    pd.DataFrame([{"book": "b", "equity": 1.0}]).to_csv(p / "summary.csv", index=False)
    return p


def test_a_bare_date_row_sorts_to_the_END_of_its_day(tmp_path, monkeypatch):
    """The whole bug. The daily cycle never runs before 22:00 UTC, so its row belongs after
    that day's marks — not 23 hours before them at midnight."""
    write_history(tmp_path, [
        ("2026-07-27T13:30", "b", 100_000.0),
        ("2026-07-27T23:03", "b", 100_000.0),
        ("2026-07-27", "b", 99_955.13),            # the daily cycle's post-rebalance row
        ("2026-07-28T02:37", "b", 99_955.13),
    ])
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    _, phist = app.load_paper_state()
    s = phist.set_index("date")["equity"].sort_index()

    assert s.index[0] == pd.Timestamp("2026-07-27 13:30")     # NOT the bare row
    assert s.index[2] == pd.Timestamp("2026-07-27 23:59")     # repaired to end of day
    # and the series no longer goes down-then-straight-back-up inside one minute
    assert s.iloc[0] == s.iloc[1] == 100_000.0
    assert s.iloc[2] == s.iloc[3] == pytest.approx(99_955.13)


def test_minute_stamped_rows_are_left_exactly_alone(tmp_path, monkeypatch):
    """The repair must key on the ORIGINAL string having no time part. Shifting a real
    23:03 mark to 23:59 would invent data."""
    write_history(tmp_path, [("2026-07-27T23:03", "b", 1.0)])
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    _, phist = app.load_paper_state()
    assert phist["date"].iloc[0] == pd.Timestamp("2026-07-27 23:03")


def test_the_repair_is_monotonic_across_a_day_boundary(tmp_path, monkeypatch):
    """Regression guard on the visible symptom: after sorting, equity must never travel
    backwards in time within a day."""
    write_history(tmp_path, [
        ("2026-07-26", "b", 1.0), ("2026-07-26T09:00", "b", 2.0),
        ("2026-07-27", "b", 3.0), ("2026-07-27T09:00", "b", 4.0),
    ])
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    _, phist = app.load_paper_state()
    s = phist.set_index("date")["equity"].sort_index()
    assert s.index.is_monotonic_increasing
    assert s.tolist() == [2.0, 1.0, 4.0, 3.0]     # each day's cycle row lands last


# ------------------------------------------------------------------ trades_frame
def test_trades_frame_is_empty_not_none_for_a_book_with_no_log():
    """Empty-vs-None is the distinction between "nothing traded yet" and "cannot trade"."""
    df = app.trades_frame({"name": "b"})
    assert df is not None and df.empty
    assert list(df.columns) == ["ts", "ticker", "side", "shares", "price", "notional",
                                "position_after"]


def test_trades_frame_is_newest_first():
    df = app.trades_frame({"trades": [
        {"ts": "2026-07-20T22:00", "ticker": "AAA", "side": "BUY", "shares": 1.0,
         "price": 1.0, "notional": 1.0, "position_after": 1.0},
        {"ts": "2026-07-27T22:00", "ticker": "BBB", "side": "SELL", "shares": -1.0,
         "price": 2.0, "notional": 2.0, "position_after": 0.0},
    ]})
    assert df["ticker"].tolist() == ["BBB", "AAA"]


def test_trades_frame_tolerates_a_row_from_an_older_schema():
    """The ledger is long-lived and written by the cloud; a missing column must not take
    the dashboard down the way the bare `full[name]` KeyError once did."""
    df = app.trades_frame({"trades": [{"ts": "2026-07-27T22:00", "ticker": "AAA"}]})
    assert len(df) == 1
    assert pd.isna(df["notional"].iloc[0])


def test_trades_frame_handles_a_mixed_stamp_format():
    """Bare-date and minute-stamped rows coexist in ledgers written across the #109 fix."""
    df = app.trades_frame({"trades": [
        {"ts": "2026-07-27", "ticker": "AAA", "side": "BUY", "shares": 1.0,
         "price": 1.0, "notional": 1.0, "position_after": 1.0},
        {"ts": "2026-07-28T02:37", "ticker": "BBB", "side": "BUY", "shares": 1.0,
         "price": 1.0, "notional": 1.0, "position_after": 1.0},
    ]})
    assert df["ticker"].tolist() == ["BBB", "AAA"]
    assert df["ts"].notna().all()
