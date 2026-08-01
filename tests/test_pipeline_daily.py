"""research/pipeline_daily.py (#178): the pipeline's daily driver.

Deliberately thin, per #178's own design questions: propose_idea() (#177) already
returns something prelim_screen() (#175) can run with no translation, and
prelim_screen() already logs every outcome for audit. There's no new mechanism to test
here, only that the wiring calls the right thing at the right time -- and, just as
important, does NOT call prelim_screen() on a day nothing was proposed.
"""
import pipeline_daily as pd_


def test_nothing_proposed_means_nothing_screened():
    def fake_propose():
        return None

    def fake_screen(idea):
        raise AssertionError("prelim_screen must not be called when nothing was proposed")

    result = pd_.run_daily_cycle(propose_fn=fake_propose, screen_fn=fake_screen)
    assert result == {"proposed": False, "name": None, "passed": None}


def test_a_proposal_is_screened_with_the_exact_object_propose_returned():
    idea = {"name": "rp_single_asset_trend_SPY_90", "sig_fn": lambda prices: prices, "freq": "M"}
    seen = {}

    def fake_propose():
        return idea

    def fake_screen(candidate):
        seen["candidate"] = candidate
        return True

    result = pd_.run_daily_cycle(propose_fn=fake_propose, screen_fn=fake_screen)
    assert seen["candidate"] is idea
    assert result == {"proposed": True, "name": idea["name"], "passed": True}


def test_a_failed_screen_is_reported_not_raised():
    idea = {"name": "rp_loser", "sig_fn": lambda prices: prices, "freq": "D"}
    result = pd_.run_daily_cycle(propose_fn=lambda: idea, screen_fn=lambda c: False)
    assert result == {"proposed": True, "name": "rp_loser", "passed": False}


def test_defaults_wire_to_the_real_propose_idea_and_prelim_screen():
    """No stand-ins snuck into the default wiring -- an unpatched call must reach the
    real #177/#175 functions, not a private copy."""
    import inspect
    src = inspect.getsource(pd_.run_daily_cycle)
    assert "pipeline_ideas.propose_idea" in src
    assert "harness.prelim_screen" in src
