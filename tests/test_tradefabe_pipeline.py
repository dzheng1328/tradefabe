"""src/tradefabe/pipeline.py (#177, #180): the package-side primitive vocabulary and the
promotion registry for OOS-ALIVE pipeline candidates.

build_signal()/PRIMITIVES moved here from research/pipeline_ideas.py (#180) so runner.py
-- part of the INSTALLED package, invoked as `tradefabe run` with no research/-relative
PYTHONPATH -- can rebuild a promoted candidate's signal directly, the same way
factory.rebuild_signal() already does for factory candidates. Coverage for build_signal()
itself stays in test_pipeline_ideas.py (which re-imports it); this file covers the
promotion registry, which is new.
"""
import numpy as np
import pandas as pd
import pytest

from tradefabe import pipeline
from tradefabe.engine import UNIVERSE


SPEC = {"name": "rp_single_asset_trend_SPY_90", "primitive": "single_asset_trend",
        "freq": "M", "params": {"ticker": "SPY", "lookback": 90}}


def test_promote_pipeline_writes_full_spec_and_load_reads_it_back(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROMOTED_PIPELINE_PATH", tmp_path / "promoted_pipeline.json")
    pipeline.promote_pipeline(SPEC)
    entries = pipeline.load_promoted_pipeline()
    assert len(entries) == 1
    assert entries[0] == SPEC


def test_promote_pipeline_is_idempotent_by_name(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROMOTED_PIPELINE_PATH", tmp_path / "promoted_pipeline.json")
    pipeline.promote_pipeline(SPEC)
    pipeline.promote_pipeline(SPEC)
    assert len(pipeline.load_promoted_pipeline()) == 1


def test_load_promoted_pipeline_empty_when_file_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROMOTED_PIPELINE_PATH", tmp_path / "does_not_exist.json")
    assert pipeline.load_promoted_pipeline() == []


def test_a_second_distinct_candidate_lands_alongside_the_first(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "PROMOTED_PIPELINE_PATH", tmp_path / "promoted_pipeline.json")
    other = {"name": "rp_pair_zscore_GLD_TLT", "primitive": "pair_zscore", "freq": "D",
             "params": {"ticker_a": "GLD", "ticker_b": "TLT", "z_window": 60,
                       "z_entry": 2.0, "z_stop": 4.0}}
    pipeline.promote_pipeline(SPEC)
    pipeline.promote_pipeline(other)
    names = {e["name"] for e in pipeline.load_promoted_pipeline()}
    assert names == {SPEC["name"], other["name"]}


def test_build_signal_rejects_an_unknown_primitive():
    with pytest.raises(ValueError):
        pipeline.build_signal("not_a_real_primitive", {})


# ---------------------------------------------------------------- asset_class_trend_hedge (#194)
def test_asset_class_covers_the_full_universe_exactly():
    """Guards against UNIVERSE drifting out of sync with ASSET_CLASS -- a ticker missing
    from the table would KeyError inside legs_differ_by_asset_class() the first time the
    LLM proposed it, not at review time."""
    assert set(pipeline.ASSET_CLASS) == set(UNIVERSE)


def test_build_signal_produces_a_valid_frame_for_asset_class_trend_hedge():
    idx = pd.bdate_range("2015-01-02", periods=400)
    rng = np.random.default_rng(1)
    px = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 400)))
                       for t in UNIVERSE}, index=idx)
    params = {"ticker_a": "TLT", "ticker_b": "SPY", "lookback_a": 90, "lookback_b": 60}
    sig = pipeline.build_signal("asset_class_trend_hedge", params)(px)
    assert sig.shape == px.shape
    assert set(sig.columns) == set(px.columns)
    assert set(sig.columns[(sig != 0).any()]) == {"TLT", "SPY"}
    assert sig.dropna().abs().to_numpy().max() <= 1.0 + 1e-9


def test_legs_differ_by_asset_class():
    assert pipeline.legs_differ_by_asset_class({"ticker_a": "TLT", "ticker_b": "SPY"})
    assert not pipeline.legs_differ_by_asset_class({"ticker_a": "SPY", "ticker_b": "QQQ"})
    # a ticker paired with itself always shares its own asset class -- no separate
    # identical-ticker check is needed for this primitive
    assert not pipeline.legs_differ_by_asset_class({"ticker_a": "SPY", "ticker_b": "SPY"})


def test_calibration_corr_cap_is_a_no_op_for_other_primitives():
    assert pipeline.legs_pass_calibration_corr_cap("single_asset_trend", {}, None)


def test_calibration_corr_cap_passes_genuinely_decorrelated_legs():
    idx = pd.bdate_range("2007-01-01", periods=2000)
    rng = np.random.default_rng(3)
    calib_prices = pd.DataFrame({
        "TLT": 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 2000))),
        "SPY": 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 2000))),
    }, index=idx)
    params = {"ticker_a": "TLT", "ticker_b": "SPY", "lookback_a": 60, "lookback_b": 60}
    assert pipeline.legs_pass_calibration_corr_cap("asset_class_trend_hedge", params, calib_prices)


def test_calibration_corr_cap_rejects_legs_that_move_together():
    """The claimed-relationship guard's whole reason to exist: two legs whose trend
    signals are perfectly correlated on calibration data are NOT a hedge, whatever the
    citation says."""
    idx = pd.bdate_range("2007-01-01", periods=2000)
    rng = np.random.default_rng(3)
    identical = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 2000)))
    calib_prices = pd.DataFrame({"TLT": identical, "SPY": identical}, index=idx)
    params = {"ticker_a": "TLT", "ticker_b": "SPY", "lookback_a": 60, "lookback_b": 60}
    assert not pipeline.legs_pass_calibration_corr_cap("asset_class_trend_hedge", params, calib_prices)
