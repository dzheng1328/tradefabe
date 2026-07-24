"""Turn-of-month calendar window edges. Two variants exist on purpose (see
signals.py docstring): the research signal counts TRADING days, the live signal counts
CALENDAR days. These tests (a) pin each variant's own boundary spec independently, and
(b) construct a concrete case where they disagree, which is the whole reason the split
exists."""
import numpy as np
import pandas as pd

from tradefabe import signals


def test_research_variant_flags_first_3_and_last_4_trading_days():
    # one full month's trading days only -> idx[:3] and idx[-4:] are unambiguously the
    # first 3 / last 4 trading days of that (only) month
    idx = pd.bdate_range("2026-03-01", "2026-03-31")
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    sig = signals.sig_turn_of_month_research(px)["A"]

    in_window = set(idx[:3]) | set(idx[-4:])
    for d in idx:
        expected = 1.0 if d in in_window else 0.0
        assert sig.loc[d] == expected, f"{d.date()}: expected {expected}, got {sig.loc[d]}"


def test_live_variant_boundaries_31_day_month():
    idx = pd.date_range("2026-01-01", "2026-01-31", freq="D")   # January, 31 days
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    sig = signals.sig_turn_of_month_live(px)["A"]
    assert sig.loc["2026-01-04"] == 1.0     # day <= 4
    assert sig.loc["2026-01-05"] == 0.0     # first day outside the window
    assert sig.loc["2026-01-25"] == 0.0     # 31 - 6 = 25, boundary: NOT included
    assert sig.loc["2026-01-26"] == 1.0     # day > 25


def test_live_variant_boundaries_30_day_month():
    idx = pd.date_range("2026-04-01", "2026-04-30", freq="D")   # April, 30 days
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    sig = signals.sig_turn_of_month_live(px)["A"]
    assert sig.loc["2026-04-24"] == 0.0     # 30 - 6 = 24, boundary excluded
    assert sig.loc["2026-04-25"] == 1.0


def test_live_variant_boundaries_28_day_february():
    idx = pd.date_range("2026-02-01", "2026-02-28", freq="D")   # 2026 is not a leap year
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    sig = signals.sig_turn_of_month_live(px)["A"]
    assert sig.loc["2026-02-22"] == 0.0     # 28 - 6 = 22, boundary excluded
    assert sig.loc["2026-02-23"] == 1.0


def test_research_and_live_variants_can_disagree():
    """The concrete divergence case: a month whose 1st falls on a Saturday. The live
    (calendar) variant flags calendar day 5 as OUTSIDE the window (day > 4), but the
    research (trading-day) variant flags it INSIDE, because the first two calendar days
    are a weekend and never appear as trading days -- so day 5 is only the 3rd trading
    day of the month."""
    month_start = None
    for year in range(2024, 2030):
        for month in range(1, 13):
            cand = pd.Timestamp(year=year, month=month, day=1)
            if cand.dayofweek == 5:            # Saturday
                month_start = cand
                break
        if month_start is not None:
            break
    assert month_start is not None, "no Saturday-starting month found in the search range"

    month_end = month_start + pd.offsets.MonthEnd(0)
    idx = pd.bdate_range(month_start, month_end)     # trading days only: 1st, 2nd (weekend) excluded
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)

    day5 = month_start + pd.Timedelta(days=4)
    assert day5 in idx  # the 5th is a weekday here by construction (Sat+4=Wed)

    live_sig = signals.sig_turn_of_month_live(px)["A"]
    research_sig = signals.sig_turn_of_month_research(px)["A"]

    assert live_sig.loc[day5] == 0.0        # calendar day 5 > 4 -> outside
    assert research_sig.loc[day5] == 1.0    # 3rd trading day of the month -> inside
    assert not np.array_equal(live_sig.values, research_sig.values)
