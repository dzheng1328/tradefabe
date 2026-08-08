import pandas as pd

from tradefabe import dashboard


def test_book_colors_assigns_by_position_cycling_through_slots():
    names = ["a", "b", "c"]
    colors = dashboard.book_colors(names)
    assert colors == {
        "a": dashboard.SLOTS[0], "b": dashboard.SLOTS[1], "c": dashboard.SLOTS[2],
    }


def test_book_colors_wraps_around_when_more_names_than_slots():
    names = [f"book_{i}" for i in range(len(dashboard.SLOTS) + 2)]
    colors = dashboard.book_colors(names)
    assert colors[f"book_{len(dashboard.SLOTS)}"] == dashboard.SLOTS[0]
    assert colors[f"book_{len(dashboard.SLOTS) + 1}"] == dashboard.SLOTS[1]


def test_latest_verdicts_keeps_last_row_per_strategy_indexed_by_name():
    gy = pd.DataFrame({
        "strategy": ["a", "a", "b"],
        "verdict": ["DEAD", "ALIVE", "DEAD"],
    })
    out = dashboard.latest_verdicts(gy)
    assert out.loc["a", "verdict"] == "ALIVE"
    assert out.loc["b", "verdict"] == "DEAD"
    assert list(out.index) == ["a", "b"]


def test_available_windows_excludes_windows_wider_than_the_live_span():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    live_hist = pd.Series([100_000, 100_100, 100_050], index=idx)
    windows = dashboard.available_windows(live_hist)
    assert windows[-1] == "ALL"
    assert "1Y" not in windows
    assert "1D" in windows


def test_available_windows_includes_all_when_span_covers_everything():
    idx = pd.date_range("2020-01-01", periods=800, freq="D")
    live_hist = pd.Series(range(800), index=idx)
    windows = dashboard.available_windows(live_hist)
    assert windows == ["5H", "1D", "1W", "1M", "3M", "1Y", "ALL"]
