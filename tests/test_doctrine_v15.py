"""DOCTRINE v1.5 (#112): segregated n_tested + the duty-cycle null as default.

The #98 council decided this and it sat unimplemented while `family_n_tested()` kept
returning the all-time union — 139, of which 121 were factory-origin. Every automated draw
raised the bar for every hand-picked candidate, permanently, taking the required Sharpe from
1.58 to 2.52 and heading for 3.63.

These tests pin the rule, not the numbers: the classifier reads ledgers that change every
cycle, so they assert RELATIONSHIPS ("a factory draw does not inflate a hand-picked
candidate") rather than counts that would go stale in a day.
"""
import numpy as np
import pandas as pd
import pytest

import harness


@pytest.fixture
def ledgers(monkeypatch, tmp_path):
    """A synthetic graveyard + factory ledger, so these never depend on the real ones."""
    gy = {"hand_a", "hand_b", "hand_c",
          "tmpl_x", "tmpl_y",                       # factory TEMPLATES
          "trend_gen_10d", "trend_gen_20d", "trend_gen_30d",   # live-generated
          "combo_ab",                                # combo
          "promoted_gen_99d"}                        # generated AND promoted
    monkeypatch.setattr(harness, "graveyard_strategy_names", lambda: set(gy))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "gen.csv"))
    pd.DataFrame({"name": ["trend_gen_10d", "trend_gen_20d", "trend_gen_30d",
                           "promoted_gen_99d"]}).to_csv(tmp_path / "gen.csv", index=False)

    import tradefabe.factory as factory
    monkeypatch.setattr(factory, "TEMPLATES", {"tmpl_x": (), "tmpl_y": ()}, raising=False)
    monkeypatch.setattr(factory, "load_promoted", lambda: [], raising=False)
    monkeypatch.setattr(factory, "load_promoted_generated",
                        lambda: [{"name": "promoted_gen_99d"}], raising=False)
    monkeypatch.setattr(factory, "load_promoted_combos", lambda: [], raising=False)
    return gy


# ------------------------------------------------------------------ origin classification
def test_every_factory_signal_is_recognized(ledgers):
    """All four are recorded at GENERATION time, before any verdict — which is what stops
    origin from being assigned after the fact to flatter a result."""
    fac = harness.factory_origin_names()
    assert {"tmpl_x", "tmpl_y"} <= fac                      # factory.TEMPLATES
    assert {"trend_gen_10d", "trend_gen_20d"} <= fac        # _gen_ convention + ledger
    assert "combo_ab" in fac                                # combo
    assert not ({"hand_a", "hand_b", "hand_c"} & fac)       # hand-picked stay out


# ------------------------------------------------------------------ the core rule
def test_a_factory_draw_does_not_inflate_a_hand_picked_candidate(ledgers):
    """The whole point of #112. Adding automated draws must leave the hand-picked bar
    untouched, or an unbounded search prices out every real strategy."""
    before = harness.family_n_tested(["hand_a"])
    ledgers.update({f"trend_gen_{i}d" for i in range(100, 140)})
    after = harness.family_n_tested(["hand_a"])
    assert after == before


def test_a_factory_candidate_still_bears_the_full_search_cost(ledgers):
    """Segregation is not amnesty. A draw competing inside the search is corrected against
    every other draw — otherwise the factory would get a free pass, which is the opposite
    of the problem being fixed."""
    hand = harness.family_n_tested(["hand_a"])
    fac = harness.family_n_tested(["tmpl_x"])
    assert fac > hand


def test_a_promoted_factory_candidate_joins_the_hand_picked_family(ledgers):
    """Promotion IS selection-on-result — exactly what a multiple-testing correction exists
    to price. A draw nobody acted on is search; the one that got a live book is a
    hypothesis."""
    assert harness.family_n_tested(["promoted_gen_99d"]) == \
        harness.family_n_tested(["hand_a"])


def test_a_promoted_name_is_not_double_counted_in_the_factory_family(ledgers):
    """It moved families; it did not join both."""
    fac_family = harness.family_n_tested(["tmpl_x"])
    assert "promoted_gen_99d" not in ((harness.graveyard_strategy_names()
                                       & harness.factory_origin_names())
                                      - harness.promoted_names())
    assert fac_family == len(((harness.graveyard_strategy_names()
                               & harness.factory_origin_names())
                              - harness.promoted_names()) | {"tmpl_x"})


def test_a_mixed_candidate_set_gets_the_conservative_union(ledgers):
    """When a run evaluates both kinds at once, take the LARGER family. A convenient
    reading would pick whichever bucket flattered the result."""
    mixed = harness.family_n_tested(["hand_a", "tmpl_x"])
    assert mixed >= harness.family_n_tested(["tmpl_x"])
    assert mixed >= harness.family_n_tested(["hand_a"])


def test_a_first_run_counts_itself(ledgers):
    """Preserved from the pre-v1.5 contract: a strategy's own first evaluation is part of
    its own family, and a re-run of a logged strategy does not double-count."""
    assert harness.family_n_tested(["brand_new"]) == harness.family_n_tested(["hand_a"]) + 1
    assert harness.family_n_tested(["hand_a"]) == harness.family_n_tested(["hand_a", "hand_a"])


def test_segregation_actually_lowers_the_hand_picked_bar(ledgers):
    """The measured motivation: the all-time union was 139 with 121 factory rows. If this
    ever stops being true, the fix has silently regressed to the pre-v1.5 behaviour."""
    all_time = len(harness.graveyard_strategy_names() | {"hand_a"})
    assert harness.family_n_tested(["hand_a"]) < all_time


# ------------------------------------------------------------------ the duty-cycle null
def test_the_rotated_null_preserves_the_candidates_turnover():
    """Why the null must be per-STRATEGY, not per-frequency. A per-bar random signal flips
    at nearly every rebalance while a real trend signal holds — measured at 3.7x the
    turnover monthly and 19.9x daily — so the null paid a cost the candidate never did and
    gate 1 came out systematically lenient. A rotation preserves the sequence exactly."""
    idx = pd.bdate_range("2020-01-01", periods=300)
    sig = pd.DataFrame({"A": np.sign(np.sin(np.linspace(0, 6, 300))),
                        "B": np.sign(np.cos(np.linspace(0, 6, 300)))}, index=idx)
    rot = harness.sig_rotated(sig, np.random.default_rng(0))

    flips_sig = sig.diff().abs().sum().sum()
    flips_rot = rot.diff().abs().sum().sum()
    # a circular shift can differ by at most the single wrap-around seam per column
    assert abs(flips_rot - flips_sig) <= 2 * sig.shape[1]


def test_a_rotated_null_is_a_real_reordering_not_the_signal_itself():
    idx = pd.bdate_range("2020-01-01", periods=200)
    sig = pd.DataFrame({"A": np.arange(200.0)}, index=idx)
    rot = harness.sig_rotated(sig, np.random.default_rng(3))
    assert not rot["A"].equals(sig["A"])
    assert sorted(rot["A"].tolist()) == sorted(sig["A"].tolist())   # same values, moved


def test_noise_floor_with_like_differs_from_the_legacy_per_bar_null():
    """If these ever coincided, `like=` would be a no-op and v1.5(b) would be cosmetic."""
    idx = pd.bdate_range("2021-01-01", periods=400)
    rng = np.random.default_rng(0)
    px = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
                       for c in ("A", "B", "C")}, index=idx)
    sig = np.sign(px / px.shift(60) - 1).fillna(0.0)
    legacy = harness.noise_floor(px, "M", 25)
    duty = harness.noise_floor(px, "M", 25, like=sig)
    assert len(legacy) and len(duty)
    assert not np.allclose(np.median(legacy), np.median(duty))


def test_a_brand_new_candidate_is_classified_before_it_has_a_graveyard_row(ledgers):
    """Regression guard on a real bug caught by tests/test_factory_run.py.

    The `_gen_`/`combo` conventions were first written as a FILTER over rows already in
    graveyard.csv. But classification happens at EVALUATION time, when a first-time
    candidate has no row yet — so every brand-new factory candidate was silently misfiled
    into the hand-picked family and corrected against the wrong, much smaller bar."""
    assert harness.is_factory_origin("factory_combo_never_seen_before")
    assert harness.is_factory_origin("trend_gen_777d")
    assert not harness.is_factory_origin("some_hand_picked_idea")

    unseen_combo = "factory_combo_brand_new_a_brand_new_b"
    assert unseen_combo not in harness.graveyard_strategy_names()
    # it must be corrected against the FACTORY family, not the hand-picked one
    assert harness.family_n_tested([unseen_combo]) > harness.family_n_tested(["hand_a"])
