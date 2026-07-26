"""Live-equity panel chart: range slicing and y-axis scaling.

Two real dashboard bugs, pinned here:
  1. A book that records one mark per day (carry_btc_eth, before the carry_live.py
     timestamp fix) had exactly ONE row inside the 5H window, so the chart rendered a
     bare dot instead of a line. window_slice() now widens back to the last two marks.
  2. Every live-equity chart started its y-axis at $0 (a consequence of the tozeroy
     fill), which squashed a $100k book's real sub-percent moves into a flat line.
     padded_range() scales to the visible high/low with 30% headroom instead.

Requires pyproject.toml's [tool.pytest.ini_options] pythonpath=["."] so `import app`
resolves the repo-root script, not an installed package."""
import pandas as pd
import pytest

import app


def _daily(n=4, start="2026-07-22", equity=100_000.0, step=25.0):
    """A once-a-day-marked ledger, the carry book's shape."""
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.Series([equity + i * step for i in range(n)], index=idx)


def _half_hourly(n=12, start="2026-07-25 00:00", equity=100_000.0, step=5.0):
    """A 30min-mark-cron ledger, every equity book's shape."""
    idx = pd.date_range(start, periods=n, freq="30min")
    return pd.Series([equity + i * step for i in range(n)], index=idx)


# ------------------------------------------------------------------ window_slice
def test_5h_window_on_a_daily_marked_book_widens_instead_of_returning_one_point():
    # the exact carry_btc_eth bug: 4 daily marks, a 5H window contains only the last one
    hist = _daily()
    naive = hist[hist.index >= hist.index[-1] - app.RANGE_WINDOWS["5H"]]
    assert len(naive) == 1, "precondition: the naive slice is the single-dot case"

    win, widened = app.window_slice(hist, "5H")

    assert widened is True
    assert len(win) == app.MIN_CHART_POINTS
    assert list(win.values) == list(hist.tail(2).values)


def test_5h_window_is_honored_exactly_when_it_already_has_enough_points():
    hist = _half_hourly(n=24)                     # 12h of 30min marks
    win, widened = app.window_slice(hist, "5H")

    assert widened is False
    assert len(win) == 11                         # 5h back inclusive of the endpoint
    assert win.index[-1] == hist.index[-1]
    assert win.index[0] >= hist.index[-1] - app.RANGE_WINDOWS["5H"]


def test_all_returns_the_untouched_series():
    hist = _daily()
    win, widened = app.window_slice(hist, "ALL")

    assert widened is False
    assert len(win) == len(hist)


def test_a_single_mark_book_cannot_be_widened_and_is_not_flagged_as_such():
    # a book opened this cycle genuinely has one point -- there is nothing to widen TO,
    # and claiming otherwise in the caption would be a lie.
    hist = _daily(n=1)
    win, widened = app.window_slice(hist, "5H")

    assert widened is False
    assert len(win) == 1


# ------------------------------------------------------------------ padded_range
def test_padded_range_pads_30pct_of_span_on_each_end():
    lo, hi = app.padded_range([100.0, 200.0])
    assert lo == pytest.approx(100.0 - 30.0)
    assert hi == pytest.approx(200.0 + 30.0)


def test_padded_range_does_not_anchor_a_100k_book_at_zero():
    # the "everything looks flat" bug: a $100k book moving $400 must not be plotted
    # against a $0 baseline.
    lo, hi = app.padded_range([99_664.45, 100_067.99])
    assert lo > 90_000, "y-axis must open near the data, not at zero"
    assert lo < 99_664.45 < 100_067.99 < hi


def test_padded_range_gives_a_flat_series_a_non_degenerate_band():
    lo, hi = app.padded_range([99_955.25, 99_955.25, 99_955.25])
    assert hi > lo, "a dead-flat book still needs a drawable axis"
    assert lo < 99_955.25 < hi


def test_padded_range_is_none_for_an_empty_series():
    assert app.padded_range([]) is None


# ------------------------------------------------------------------ the figure itself
def test_live_equity_chart_never_plots_a_lone_point_for_a_daily_book():
    fig = app.live_equity_chart(_daily(), "#86b6ef", "5H")
    assert len(fig.data[0].x) >= app.MIN_CHART_POINTS


def test_live_equity_chart_sets_an_explicit_non_zero_based_y_range():
    hist = _daily(equity=100_000.0, step=25.0)
    fig = app.live_equity_chart(hist, "#86b6ef", "ALL")
    lo, hi = fig.layout.yaxis.range

    assert lo > 0, "regression: the axis used to start at $0 because of the tozeroy fill"
    assert lo < float(hist.min()) and hi > float(hist.max())
