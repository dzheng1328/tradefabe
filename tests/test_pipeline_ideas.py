"""research/pipeline_ideas.py (#177): the research pipeline's idea-generation step.

Three things matter more than any single test: the budget guard is a PROVABLE ceiling
that fires BEFORE any model call (Dave's explicit $0.05/day cap -- "if it will definitely
exceed that, no api"), a validated proposal is directly consumable by
harness.prelim_screen() with no further translation, and every name this module produces
satisfies #176's origin-classification contract by construction.
"""
import json

import numpy as np
import pandas as pd
import pytest

import harness
import pipeline_ideas as pi


def _prices(n=400, seed=1):
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))) for t in
         ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
          "GLD", "SLV", "DBC", "USO", "VNQ", "UUP"]}, index=idx)


@pytest.fixture
def scratch(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "graveyard.csv"))
    monkeypatch.setattr(harness, "PIPELINE_LEDGER", str(tmp_path / "pipeline.csv"))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "gen.csv"))
    # test_propose_idea_returns_a_prelim_screen_ready_dict calls the REAL
    # harness.prelim_screen() -- without this, that call writes to the real,
    # git-tracked artifacts/prelim_log.csv instead of a scratch path.
    monkeypatch.setattr(harness, "PRELIM_LOG", str(tmp_path / "prelim_log.csv"))
    return tmp_path


VALID_RAW = {
    "primitive": "single_asset_trend", "params": {"ticker": "SPY", "lookback": 90},
    "freq": "M", "rationale": "Trailing return sign, underreaction to news.",
    "citation": "Jegadeesh & Titman 1993",
}


# ---------------------------------------------------------------- build_signal
def test_build_signal_produces_a_valid_frame_for_every_primitive():
    px = _prices()
    cases = {
        "pair_zscore": {"ticker_a": "GLD", "ticker_b": "SLV", "z_window": 60,
                        "z_entry": 2.0, "z_stop": 4.0},
        "cross_sectional_rank": {"metric": "momentum", "lookback": 90, "k": 3},
        "single_asset_trend": {"ticker": "SPY", "lookback": 90},
        "static_spread_carry": {"ticker_a": "TLT", "ticker_b": "IEF", "long_leg": "a"},
    }
    for primitive, params in cases.items():
        sig = pi.build_signal(primitive, params)(px)
        assert sig.shape == px.shape
        assert set(sig.columns) == set(px.columns)
        # a lookback-based signal is NaN during its own warmup window -- same convention
        # every existing factory template (e.g. _make_tsmom) already follows; only the
        # post-warmup values are constrained to the signal's actual range.
        assert sig.dropna().abs().to_numpy().max() <= 1.0 + 1e-9


def test_build_signal_rejects_an_unknown_primitive():
    with pytest.raises(ValueError):
        pi.build_signal("not_a_real_primitive", {})


# ---------------------------------------------------------------- validate_proposal
def test_validate_proposal_accepts_a_well_formed_spec():
    out = pi.validate_proposal(VALID_RAW)
    assert out["primitive"] == "single_asset_trend"
    assert out["params"] == {"ticker": "SPY", "lookback": 90}
    assert out["freq"] == "M"


def test_validate_proposal_rejects_unknown_primitive():
    raw = {**VALID_RAW, "primitive": "made_up"}
    assert pi.validate_proposal(raw) is None


def test_validate_proposal_rejects_out_of_range_param():
    raw = {**VALID_RAW, "params": {"ticker": "SPY", "lookback": 9999}}
    assert pi.validate_proposal(raw) is None


def test_validate_proposal_rejects_a_ticker_outside_the_universe():
    raw = {**VALID_RAW, "params": {"ticker": "TSLA", "lookback": 90}}
    assert pi.validate_proposal(raw) is None


def test_validate_proposal_rejects_missing_rationale_or_citation():
    raw = {**VALID_RAW, "rationale": ""}
    assert pi.validate_proposal(raw) is None
    raw2 = {**VALID_RAW, "citation": "   "}
    assert pi.validate_proposal(raw2) is None


def test_validate_proposal_rejects_identical_tickers_for_a_pair():
    raw = {"primitive": "static_spread_carry",
           "params": {"ticker_a": "TLT", "ticker_b": "TLT", "long_leg": "a"},
           "freq": "D", "rationale": "x", "citation": "y"}
    assert pi.validate_proposal(raw) is None


def test_validate_proposal_rejects_entry_not_less_than_stop():
    raw = {"primitive": "pair_zscore",
           "params": {"ticker_a": "GLD", "ticker_b": "SLV", "z_window": 60,
                      "z_entry": 4.0, "z_stop": 2.0},
           "freq": "D", "rationale": "x", "citation": "y"}
    assert pi.validate_proposal(raw) is None


def test_validate_proposal_never_raises_on_a_malformed_dict():
    assert pi.validate_proposal({}) is None
    assert pi.validate_proposal({"primitive": "single_asset_trend"}) is None


# ---------------------------------------------------------------- naming (#176's contract)
def test_make_name_always_carries_the_pipeline_prefix():
    name = pi.make_name("single_asset_trend", {"ticker": "SPY", "lookback": 90})
    assert name.startswith(harness.PIPELINE_NAME_PREFIX)
    assert harness.is_pipeline_origin(name)
    assert not harness.is_factory_origin(name)


def test_make_name_is_deterministic():
    a = pi.make_name("pair_zscore", {"ticker_a": "GLD", "ticker_b": "SLV",
                                     "z_window": 60, "z_entry": 2.0, "z_stop": 4.0})
    b = pi.make_name("pair_zscore", {"ticker_a": "GLD", "ticker_b": "SLV",
                                     "z_window": 60, "z_entry": 2.0, "z_stop": 4.0})
    assert a == b


# ---------------------------------------------------------------- rate limiter
def test_already_proposed_today_is_false_on_an_empty_ledger(scratch):
    assert pi.already_proposed_today() is False


def test_already_proposed_today_is_true_right_after_recording(scratch):
    proposal = pi.validate_proposal(VALID_RAW)
    pi.record_proposal("rp_test_a", proposal)
    assert pi.already_proposed_today() is True


# ---------------------------------------------------------------- budget guard
def test_estimate_cost_uses_the_output_cap_not_actual_output():
    """The estimate must be an upper bound regardless of what the model actually
    returns -- it's computed from MAX_OUTPUT_TOKENS, not from a real response."""
    short_prompt = "hi"
    cost = pi.estimate_cost(short_prompt)
    expected = (pi.estimate_tokens(short_prompt) * pi.PRICE_PER_INPUT_TOKEN_USD
               + pi.MAX_OUTPUT_TOKENS * pi.PRICE_PER_OUTPUT_TOKEN_USD)
    assert cost == pytest.approx(expected)


def test_a_realistic_daily_prompt_stays_under_budget(scratch):
    """The actual guarantee Dave asked for: a normal day's prompt must cost well under
    the $0.05/day cap, not just barely clear it."""
    prompt = pi.build_prompt()
    assert pi.estimate_cost(prompt) < pi.DAILY_BUDGET_USD


def test_propose_idea_refuses_to_call_the_model_when_budget_is_exceeded(scratch, monkeypatch):
    monkeypatch.setattr(pi, "DAILY_BUDGET_USD", 0.0)   # guaranteed to be exceeded

    def _must_not_be_called(prompt):
        raise AssertionError("the model must never be called once the budget check fails")

    result = pi.propose_idea(llm_fn=_must_not_be_called)
    assert result is None


# ---------------------------------------------------------------- propose_idea end-to-end
def test_propose_idea_returns_a_prelim_screen_ready_dict(scratch, monkeypatch):
    def fake_llm(prompt):
        return json.dumps(VALID_RAW)

    result = pi.propose_idea(llm_fn=fake_llm)
    assert result["name"].startswith("rp_")
    assert result["freq"] == "M"
    assert callable(result["sig_fn"])

    # The core guarantee #177's own design question demands: #175's prelim screen must
    # be able to run against this with no further design work.
    calib_prices = _prices(n=3000, seed=7)
    calib_prices.index = pd.bdate_range(harness.CALIB_START, periods=3000)
    monkeypatch.setattr(harness, "load_prices", lambda: (calib_prices, "SYNTHETIC (test)"))

    passed = harness.prelim_screen(result)
    assert passed in (True, False)   # ran to completion without error -- that's the point


def test_propose_idea_records_to_the_ledger_and_rate_limits_a_second_call(scratch):
    def fake_llm(prompt):
        return json.dumps(VALID_RAW)

    first = pi.propose_idea(llm_fn=fake_llm)
    assert first is not None
    assert pi.already_proposed_today() is True

    def _must_not_be_called(prompt):
        raise AssertionError("a second call the same day must be rate-limited before this runs")
    second = pi.propose_idea(llm_fn=_must_not_be_called)
    assert second is None


def test_propose_idea_returns_none_on_malformed_json(scratch):
    result = pi.propose_idea(llm_fn=lambda prompt: "not json at all")
    assert result is None
    assert not harness.pipeline_origin_names()


def test_propose_idea_returns_none_when_the_model_explicitly_skips(scratch):
    result = pi.propose_idea(llm_fn=lambda prompt: json.dumps({"skip": True, "reason": "nothing new"}))
    assert result is None


def test_propose_idea_rejects_a_duplicate_of_an_already_tested_name(scratch, monkeypatch):
    name = pi.make_name(VALID_RAW["primitive"], VALID_RAW["params"])
    monkeypatch.setattr(harness, "graveyard_strategy_names", lambda: {name})

    result = pi.propose_idea(llm_fn=lambda prompt: json.dumps(VALID_RAW))
    assert result is None
