"""DOCTRINE v1.5 (#112): segregated n_tested + the duty-cycle null as default. Extended by
v1.10 (#176) to a THIRD bucket for the research pipeline (#174), tested in the same file
since both amendments exercise the same `family_n_tested()` mechanism.

The #98 council decided v1.5 and it sat unimplemented while `family_n_tested()` kept
returning the all-time union — 139, of which 121 were factory-origin. Every automated draw
raised the bar for every hand-picked candidate, permanently, taking the required Sharpe from
1.58 to 2.52 and heading for 3.63. v1.10 applies the identical argument to a second,
independent search (genuinely new strategy families, not parameter variants) that must be
segregated from BOTH the factory's bucket and the hand-picked one, not folded into either.

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
    """A synthetic graveyard + factory + pipeline ledger, so these never depend on the
    real ones. Pipeline entries (#176) added alongside the original factory ones rather
    than in a separate fixture -- both origins need to coexist in the SAME graveyard for
    the three-way segregation tests below to mean anything."""
    gy = {"hand_a", "hand_b", "hand_c",
          "tmpl_x", "tmpl_y",                       # factory TEMPLATES
          "trend_gen_10d", "trend_gen_20d", "trend_gen_30d",   # live-generated
          "combo_ab",                                # combo
          "promoted_gen_99d",                        # generated AND promoted
          "rp_pairs_a", "rp_pairs_b", "rp_vrp_c", "rp_vrp_d",  # pipeline-proposed --
          "rp_carry_e", "rp_carry_f", "rp_swap_g",             # (7, matching the
          "promoted_rp_h"}                           # factory's own 6-vs-5 margin below)
    monkeypatch.setattr(harness, "graveyard_strategy_names", lambda: set(gy))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "gen.csv"))
    pd.DataFrame({"name": ["trend_gen_10d", "trend_gen_20d", "trend_gen_30d",
                           "promoted_gen_99d"]}).to_csv(tmp_path / "gen.csv", index=False)
    monkeypatch.setattr(harness, "PIPELINE_LEDGER", str(tmp_path / "pipeline.csv"))
    pd.DataFrame({"name": ["rp_pairs_a", "rp_pairs_b", "rp_vrp_c", "rp_vrp_d",
                           "rp_carry_e", "rp_carry_f", "rp_swap_g",
                           "promoted_rp_h"]}).to_csv(tmp_path / "pipeline.csv", index=False)

    import tradefabe.factory as factory
    monkeypatch.setattr(factory, "TEMPLATES", {"tmpl_x": (), "tmpl_y": ()}, raising=False)
    monkeypatch.setattr(factory, "load_promoted", lambda: [], raising=False)
    # promoted_names() currently only knows the factory's three registries -- #180 hasn't
    # given the pipeline its own yet, so a promoted PIPELINE candidate is simulated via
    # the same registry the way it will actually work in production until #180 lands.
    monkeypatch.setattr(factory, "load_promoted_generated",
                        lambda: [{"name": "promoted_gen_99d"}, {"name": "promoted_rp_h"}],
                        raising=False)
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


# ------------------------------------------------------------ the third bucket (v1.10, #176)
def test_every_pipeline_signal_is_recognized(ledgers):
    """Both markers -- the rp_ naming convention and the proposal-time ledger -- are fixed
    before any candidate is drawn, the same before-the-result guarantee the factory's own
    markers carry."""
    pipe = harness.pipeline_origin_names()
    assert {"rp_pairs_a", "rp_pairs_b", "rp_vrp_c"} <= pipe    # naming convention
    assert "promoted_rp_h" in pipe                              # ledger only, no rp_ prefix
    assert not ({"hand_a", "hand_b", "hand_c"} & pipe)         # hand-picked stay out
    assert not ({"tmpl_x", "tmpl_y", "trend_gen_10d", "combo_ab"} & pipe)   # factory stays out


def test_a_pipeline_name_is_never_also_factory_origin(ledgers):
    """The two conventions (rp_ prefix vs. _gen_/combo) are disjoint by construction --
    if #177 ever proposes a name that collides with the factory's markers, the prefix is
    what must change, not this check."""
    for name in ("rp_pairs_a", "rp_vrp_c", "rp_pairs_lookalike"):
        assert harness.is_pipeline_origin(name)
        assert not harness.is_factory_origin(name)
    for name in ("trend_gen_10d", "factory_combo_x_y", "tmpl_x"):
        assert harness.is_factory_origin(name)
        assert not harness.is_pipeline_origin(name)


def test_a_pipeline_draw_does_not_inflate_a_hand_picked_candidate(ledgers):
    """The core rule (#176), same as #112's for the factory bucket: an automated search's
    draws must never raise the bar for a hand-picked candidate."""
    before = harness.family_n_tested(["hand_a"])
    ledgers.update({f"rp_backtest_{i}" for i in range(100, 140)})
    after = harness.family_n_tested(["hand_a"])
    assert after == before


def test_a_pipeline_draw_does_not_inflate_the_factory_bucket(ledgers):
    """The reason #176 needs a THIRD bucket rather than reusing the factory's: two
    different searches over two different spaces must not correct against each other,
    the same way neither may correct against hand-picked."""
    fac_before = harness.family_n_tested(["tmpl_x"])
    ledgers.update({f"rp_backtest_{i}" for i in range(200, 240)})
    assert harness.family_n_tested(["tmpl_x"]) == fac_before


def test_a_factory_draw_does_not_inflate_the_pipeline_bucket(ledgers):
    """The other direction of the same guarantee."""
    pipe_before = harness.family_n_tested(["rp_pairs_a"])
    ledgers.update({f"trend_gen_{i}d" for i in range(200, 240)})
    assert harness.family_n_tested(["rp_pairs_a"]) == pipe_before


def test_a_pipeline_candidate_still_bears_the_full_search_cost(ledgers):
    """Segregation is not amnesty: a draw competing inside the pipeline's own search is
    corrected against every other pipeline draw."""
    hand = harness.family_n_tested(["hand_a"])
    pipe = harness.family_n_tested(["rp_pairs_a"])
    assert pipe > hand


def test_a_promoted_pipeline_candidate_joins_the_hand_picked_family(ledgers):
    """Promotion is selection-on-result regardless of which automated origin found the
    candidate -- same logic v1.5 applied to a promoted factory draw."""
    assert harness.family_n_tested(["promoted_rp_h"]) == \
        harness.family_n_tested(["hand_a"])


def test_a_mixed_three_way_candidate_set_gets_the_conservative_union(ledgers):
    """A run spanning all three origins at once corrects against the union of all three
    families -- the same conservative reading v1.5 applied to a two-way mix."""
    three_way = harness.family_n_tested(["hand_a", "tmpl_x", "rp_pairs_a"])
    assert three_way >= harness.family_n_tested(["tmpl_x"])
    assert three_way >= harness.family_n_tested(["hand_a"])
    assert three_way >= harness.family_n_tested(["rp_pairs_a"])


def test_a_brand_new_pipeline_candidate_is_classified_before_it_has_a_graveyard_row(ledgers):
    """Same regression shape as the factory's own brand-new-candidate guard: a first-time
    pipeline candidate must be corrected against the PIPELINE family, not misfiled into
    hand-picked for lack of a graveyard row yet."""
    unseen = "rp_never_seen_before"
    assert unseen not in harness.graveyard_strategy_names()
    assert harness.family_n_tested([unseen]) > harness.family_n_tested(["hand_a"])


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
