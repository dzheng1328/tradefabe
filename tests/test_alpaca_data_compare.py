"""Pure comparison logic for issue #135 (Alpaca vs yfinance hourly data) -- the parts
that don't need real network access. fetch_alpaca_bars() itself (real API calls) is
deliberately untested here, same convention as cost_check.py's round_trip()."""
import numpy as np
import pandas as pd

import alpaca_data_compare as m
# _to_alpaca_symbol moved to alpaca_fetch.py (#156) so hourly_backtest.py's equity-leg
# swap can share fetch_alpaca_bars without a circular import with alpaca_data_compare.py.
import alpaca_fetch


def test_to_alpaca_symbol_converts_crypto_dash_to_slash():
    assert alpaca_fetch._to_alpaca_symbol("BTC-USD") == "BTC/USD"
    assert alpaca_fetch._to_alpaca_symbol("ETH-USD") == "ETH/USD"


def test_to_alpaca_symbol_leaves_equity_tickers_unchanged():
    assert alpaca_fetch._to_alpaca_symbol("SPY") == "SPY"


def test_compare_overlap_matches_bars_offset_by_the_real_30min_alignment_gap():
    # #135's actual finding: yfinance aligns equity bars to the market open (:30),
    # Alpaca aligns to the wall-clock hour (:00) -- an exact-timestamp join found ZERO
    # overlap despite both sources covering the same calendar period. merge_asof with
    # a tolerance is what recovers a real comparison.
    yf_idx = pd.date_range("2024-01-02 14:30", periods=5, freq="h")
    al_idx = pd.date_range("2024-01-02 14:00", periods=5, freq="h")
    yf_px = pd.DataFrame({"SPY": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=yf_idx)
    al_px = pd.DataFrame({"SPY": [100.1, 101.1, 102.1, 103.1, 104.1]}, index=al_idx)

    agree = m.compare_overlap(yf_px, al_px)
    row = agree.iloc[0]
    assert row["ticker"] == "SPY"
    assert row["overlap_rows"] == 5   # every bar found a nearest match within tolerance
    assert row["mean_abs_pct_delta"] > 0   # the 0.1 offset is real disagreement, not 0


def test_compare_overlap_reports_zero_overlap_beyond_the_tolerance_window():
    # bars an hour apart (not 30min) are too far apart to be "the same bar, different
    # alignment" -- must NOT be silently matched as if they agreed.
    yf_idx = pd.date_range("2024-01-02 14:00", periods=3, freq="h")
    al_idx = pd.date_range("2024-01-03 14:00", periods=3, freq="h")   # a full day later
    yf_px = pd.DataFrame({"SPY": [100.0, 101.0, 102.0]}, index=yf_idx)
    al_px = pd.DataFrame({"SPY": [200.0, 201.0, 202.0]}, index=al_idx)

    agree = m.compare_overlap(yf_px, al_px)
    row = agree.iloc[0]
    assert row["overlap_rows"] == 0
    assert np.isnan(row["mean_abs_pct_delta"])


def test_compare_overlap_only_considers_tickers_present_in_both_sources():
    yf_px = pd.DataFrame({"SPY": [100.0], "ONLY_YF": [1.0]},
                         index=pd.date_range("2024-01-02 14:30", periods=1))
    al_px = pd.DataFrame({"SPY": [100.0], "ONLY_ALPACA": [1.0]},
                         index=pd.date_range("2024-01-02 14:00", periods=1))
    agree = m.compare_overlap(yf_px, al_px)
    assert list(agree["ticker"]) == ["SPY"]


def test_report_extra_depth_prints_regime_coverage(capsys):
    yf_px = pd.DataFrame({"SPY": [1.0]}, index=[pd.Timestamp("2023-08-25")])
    al_px = pd.DataFrame({"SPY": [1.0]}, index=[pd.Timestamp("2016-01-01")])
    m.report_extra_depth(al_px, yf_px, "equity")
    out = capsys.readouterr().out
    assert "2793" in out or "more day" in out
    assert "COVERS" in out   # Alpaca starting 2016 covers every REGIME_MARKERS entry


def test_report_extra_depth_handles_an_empty_source_without_raising(capsys):
    m.report_extra_depth(pd.DataFrame(), pd.DataFrame({"SPY": [1.0]}, index=[pd.Timestamp("2023-01-01")]), "equity")
    out = capsys.readouterr().out
    assert "no data to compare depth" in out
