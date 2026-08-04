"""research/pipeline_register.py (#179): the fully-automatic pre-registration checkpoint.

Three things matter more than any single test: the STRATEGIES.md insertion never
clobbers content around it (the "Rules of the roster" marker must survive, and a second
candidate must land after the first, not overwrite it), pre-registration is idempotent
by name (a re-run must never duplicate a section), and every registration leaves a
durable, machine-readable trace (pipeline_preregistered.csv) independent of the prose.
"""
import pandas as pd
import pytest

import pipeline_register as pr

PROPOSAL_A = {
    "name": "rp_single_asset_trend_SPY_90", "primitive": "single_asset_trend",
    "params": {"ticker": "SPY", "lookback": 90}, "freq": "M",
    "rationale": "Trailing return sign, underreaction to news.",
    "citation": "Jegadeesh & Titman 1993",
}
PROPOSAL_B = {
    "name": "rp_pair_zscore_GLD_SLV", "primitive": "pair_zscore",
    "params": {"ticker_a": "GLD", "ticker_b": "SLV", "z_window": 60,
              "z_entry": 2.0, "z_stop": 4.0}, "freq": "D",
    "rationale": "Precious metals spread mean-reversion.",
    "citation": "n/a",
}

SCRATCH_STRATEGIES_MD = """# Strategy Roster

Some existing content above.

## Rules of the roster
1. A strategy's spec is frozen before its OOS verdict.
"""


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    md_path = tmp_path / "STRATEGIES.md"
    md_path.write_text(SCRATCH_STRATEGIES_MD)
    monkeypatch.setattr(pr, "STRATEGIES_PATH", str(md_path))
    monkeypatch.setattr(pr, "PREREGISTERED_LEDGER", str(tmp_path / "preregistered.csv"))
    return md_path


def test_format_preregistration_includes_every_field():
    text = pr.format_preregistration(PROPOSAL_A)
    assert "rp_single_asset_trend_SPY_90" in text
    assert "single_asset_trend" in text
    assert "ticker=SPY" in text and "lookback=90" in text
    assert "M" in text
    assert "underreaction to news" in text
    assert "Jegadeesh & Titman 1993" in text


def test_preregister_candidate_creates_the_section_on_first_use(scratch):
    result = pr.preregister_candidate(PROPOSAL_A)
    assert result is True

    text = scratch.read_text()
    assert pr.PREREG_SECTION_HEADER in text
    assert "rp_single_asset_trend_SPY_90" in text
    assert "## Rules of the roster" in text   # the marker survives
    assert "Some existing content above." in text   # nothing before it was clobbered
    # the new section must land BEFORE the marker, not after
    assert text.index(pr.PREREG_SECTION_HEADER) < text.index("## Rules of the roster")


def test_a_second_candidate_lands_after_the_first_within_the_same_section(scratch):
    pr.preregister_candidate(PROPOSAL_A)
    pr.preregister_candidate(PROPOSAL_B)

    text = scratch.read_text()
    assert text.count(pr.PREREG_SECTION_HEADER) == 1   # header not duplicated
    assert "rp_single_asset_trend_SPY_90" in text
    assert "rp_pair_zscore_GLD_SLV" in text
    # insertion order preserved, both still before the marker
    assert (text.index("rp_single_asset_trend_SPY_90")
            < text.index("rp_pair_zscore_GLD_SLV")
            < text.index("## Rules of the roster"))


def test_preregister_candidate_is_idempotent_for_the_same_name(scratch):
    first = pr.preregister_candidate(PROPOSAL_A)
    text_after_first = scratch.read_text()

    second = pr.preregister_candidate(PROPOSAL_A)
    text_after_second = scratch.read_text()

    assert first is True
    assert second is False
    assert text_after_first == text_after_second   # no duplicate section appended
    assert text_after_second.count("rp_single_asset_trend_SPY_90") == 1

    ledger = pd.read_csv(pr.PREREGISTERED_LEDGER)
    assert len(ledger) == 1   # one stamp, not two


def test_preregister_candidate_logs_to_the_ledger(scratch):
    pr.preregister_candidate(PROPOSAL_A)
    ledger = pd.read_csv(pr.PREREGISTERED_LEDGER)
    assert list(ledger["name"]) == ["rp_single_asset_trend_SPY_90"]
    assert ledger["timestamp"].notna().all()


def test_preregister_candidate_raises_if_the_marker_is_missing(monkeypatch, tmp_path):
    md_path = tmp_path / "STRATEGIES.md"
    md_path.write_text("# Strategy Roster\n\nNo rules-of-the-roster marker here.\n")
    monkeypatch.setattr(pr, "STRATEGIES_PATH", str(md_path))
    monkeypatch.setattr(pr, "PREREGISTERED_LEDGER", str(tmp_path / "preregistered.csv"))

    with pytest.raises(RuntimeError, match="missing"):
        pr.preregister_candidate(PROPOSAL_A)
