"""src/tradefabe/pipeline.py (#177, #180): the package-side primitive vocabulary and the
promotion registry for OOS-ALIVE pipeline candidates.

build_signal()/PRIMITIVES moved here from research/pipeline_ideas.py (#180) so runner.py
-- part of the INSTALLED package, invoked as `tradefabe run` with no research/-relative
PYTHONPATH -- can rebuild a promoted candidate's signal directly, the same way
factory.rebuild_signal() already does for factory candidates. Coverage for build_signal()
itself stays in test_pipeline_ideas.py (which re-imports it); this file covers the
promotion registry, which is new.
"""
import pytest

from tradefabe import pipeline


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
