import json
import os

import pandas as pd

from tradefabe import dashboard, remote


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


def test_load_carry_risk_returns_none_when_the_file_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    assert dashboard.load_carry_risk() is None


def test_load_carry_risk_reads_the_persisted_report(monkeypatch, tmp_path):
    paper_dir = tmp_path / "state" / "paper"
    paper_dir.mkdir(parents=True)
    report = {"generated_at": "2026-08-13T00:00:00", "coins": {"BTC": {"funding_7d": 0.001}}}
    with open(paper_dir / "carry_risk.json", "w") as fh:
        json.dump(report, fh)
    monkeypatch.setattr(dashboard, "BASE", str(tmp_path))
    monkeypatch.setattr(remote, "REPO_ROOT", tmp_path)
    assert dashboard.load_carry_risk() == report


def test_growth_series_leaves_nan_before_the_series_starts():
    # 2026-08-14: a series that starts partway through the chart (a factory/pipeline
    # curve, kronos, hourly) used to get fillna(0)'d across the WHOLE index, holding it
    # flat at 1.0 before it existed rather than simply not drawing a line there yet.
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    r = pd.Series([None, None, 0.01, -0.005, 0.02], index=idx)
    growth = dashboard.growth_series(r)
    assert growth.iloc[:2].isna().all()
    assert growth.iloc[2:].notna().all()


def test_growth_series_leaves_nan_after_the_series_ends():
    # The 2026-08-14 "glitched growth chart" bug: a stale one-time snapshot's last
    # value was extended flat for years via fillna(0).cumprod() over the full range.
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    r = pd.Series([0.01, 0.02, -0.01, None, None], index=idx)
    growth = dashboard.growth_series(r)
    assert growth.iloc[:3].notna().all()
    assert growth.iloc[3:].isna().all()


def test_growth_series_fills_internal_gaps_as_zero_return():
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    r = pd.Series([0.01, None, 0.02, None, 0.01], index=idx)
    growth = dashboard.growth_series(r)
    assert growth.notna().all()
    assert growth.iloc[1] == growth.iloc[0]   # a gap day carries the prior value forward


def test_growth_series_all_nan_returns_all_nan():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    r = pd.Series([None, None, None], index=idx)
    growth = dashboard.growth_series(r)
    assert growth.isna().all()


def test_all_candidate_returns_sorts_the_index_after_concat(monkeypatch):
    # 2026-08-15: family L/M (hourly/kronos) trade weekends, unlike the business-day
    # index everything else in `combined` uses. pd.concat(..., sort=False)'s union of
    # those two index shapes appends the weekend-only dates AFTER the whole business-day
    # range instead of merging them chronologically, leaving `combined.index`
    # non-monotonic. Plotly's mode="lines" draws points in ARRAY order, not sorted by x,
    # so an unsorted index made the growth chart's own line jump backward across years
    # mid-trace -- rendered as the long straight "horizontal line" artifacts reported
    # live on the Research Lab overview and Piggyback Lab charts.
    business_idx = pd.date_range("2018-01-01", periods=2000, freq="B")
    # A week in the middle of business_idx's own span, including its weekend --
    # business_idx has no weekend dates at all, so those two days are genuinely new to
    # the union, not already present in a different frame.
    hourly_idx = pd.date_range("2023-06-05", periods=7, freq="D")

    full = pd.DataFrame({"a": 0.001, "bench_6040": 0.0005, "spy": 0.0004}, index=business_idx)
    meta = {"oos_start": business_idx[0].isoformat()}
    hourly = pd.DataFrame({"b": 0.002}, index=hourly_idx)

    monkeypatch.setattr(dashboard, "load_backtest", lambda: (full, meta, None, None))
    monkeypatch.setattr(dashboard, "load_factory_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pipeline_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_hourly_backtest", lambda: hourly)
    monkeypatch.setattr(dashboard, "load_kronos_backtest", lambda: None)
    monkeypatch.setattr(dashboard, "load_pairs_backtest", lambda: None)

    combined, _bench = dashboard._all_candidate_returns()
    assert combined.index.is_monotonic_increasing


def test_unique_strategy_universe_excludes_stale_one_time_snapshots(monkeypatch):
    # 2026-08-14: factory_returns.csv carried columns whose data stopped dead years
    # ago (a one-time snapshot from whenever that candidate was promoted, never
    # refreshed) -- near-zero date overlap with anything current, so they can't be
    # meaningfully compared/plotted alongside the live roster.
    idx = pd.date_range("2018-01-01", periods=2200, freq="B")
    rng = pd.Series(range(len(idx)), index=idx)
    combined = pd.DataFrame({
        "fresh_a": 0.0001 * (rng % 7 - 3),
        "fresh_b": 0.0001 * (rng % 11 - 5),
        "stale_old": pd.Series(0.0001 * (rng % 5 - 2), index=idx).where(rng < 400),
    })
    bench = pd.DataFrame({"bench_6040": 0.0002 * (rng % 13 - 6)}, index=idx)
    monkeypatch.setattr(dashboard, "_all_candidate_returns", lambda: (combined, bench))

    gy_last = pd.DataFrame({"oos_sharpe": [0.5, 0.6, 0.9]},
                           index=["fresh_a", "fresh_b", "stale_old"])
    kept, oos = dashboard.unique_strategy_universe(gy_last, corr_threshold=2.0)
    assert "stale_old" not in kept
    assert set(kept) == {"fresh_a", "fresh_b"}
    assert "stale_old" not in oos.columns


def test_sort_books_flat_sharpe_sorts_descending_by_backtest_oos_sharpe():
    psum = pd.DataFrame({
        "book": ["low_sharpe_book", "high_sharpe_book", "no_verdict_book"],
        "equity": [100_000.0, 100_000.0, 100_000.0],
        "return": [0.0, 0.0, 0.0],
        "last_run": ["2026-08-14"] * 3,
        "retired_at": [None, None, None],
    })
    phist = pd.DataFrame({
        "book": ["low_sharpe_book", "high_sharpe_book", "no_verdict_book"],
        "date": pd.to_datetime(["2026-08-14"] * 3),
        "equity": [100_000.0, 100_000.0, 100_000.0],
    })
    gy_last = pd.DataFrame(
        {"oos_sharpe": [0.2, 1.5], "verdict": ["DEAD", "DEAD"]},
        index=["low_sharpe_book", "high_sharpe_book"],
    )
    rows = dashboard.sort_books_flat(psum, phist, gy_last, sort_key="sharpe")
    assert [r["book"] for r in rows] == ["high_sharpe_book", "low_sharpe_book", "no_verdict_book"]
