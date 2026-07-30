"""Integration test for the strategy factory's daily driver (research/factory_run.py,
#28) -- runs a full cycle (individual templates + one correlation-picked combo) against
a small synthetic price panel, with graveyard.csv monkeypatched to a scratch file in
both harness and piggyback_backtest (both write to it independently). Requires
pyproject.toml's pythonpath=[".", "research"] so `import factory_run` (which itself does
`from piggyback_backtest import ...`, a sibling repo-root-script-style import) resolves."""
import numpy as np
import pandas as pd
import pytest

import harness
import piggyback_backtest
import factory_run


def _synthetic_prices(n=1200, seed=3):
    """Enough history and enough assets for every template's longest lookback (24mo
    tsmom = 504 trading days) plus OOS_START (2018-01-01) to have real post-OOS data."""
    idx = pd.bdate_range("2015-01-02", periods=n)
    rng = np.random.default_rng(seed)
    cols = ["SPY", "QQQ", "IEF", "TLT", "GLD"]
    drift = rng.uniform(0.02, 0.08, len(cols)) / 252
    vol = rng.uniform(0.10, 0.20, len(cols)) / np.sqrt(252)
    rets = rng.normal(drift, vol, size=(n, len(cols)))
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=cols)


@pytest.fixture
def scratch_graveyard(monkeypatch, tmp_path):
    gy = tmp_path / "graveyard.csv"
    monkeypatch.setattr(harness, "GRAVEYARD", str(gy))
    monkeypatch.setattr(piggyback_backtest, "GRAVEYARD", str(gy))
    monkeypatch.setattr(factory_run, "load_prices", lambda: (_synthetic_prices(), "SYNTHETIC (test)"))
    monkeypatch.setattr(factory_run.factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory_run.factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    monkeypatch.setattr(factory_run.factory, "PROMOTED_GENERATED_PATH", tmp_path / "promoted_generated.json")
    monkeypatch.setattr(factory_run.factory, "PROMOTED_COMBOS_PATH", tmp_path / "promoted_combos.json")
    monkeypatch.setattr(factory_run.factory, "GENERATED_LEDGER", tmp_path / "generated_templates.csv")
    monkeypatch.setattr(factory_run, "FACTORY_RETURNS_PATH", tmp_path / "factory_returns.csv")
    return gy


def test_run_cycle_evaluates_n_templates_and_one_combo(scratch_graveyard, capsys):
    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    assert len(evaluated) == 5   # 4 individual templates + 1 combo

    gy = pd.read_csv(scratch_graveyard)
    assert set(gy["strategy"]) == set(evaluated)
    assert gy["verdict"].isin(["ALIVE", "DEAD"]).all()
    assert gy["dsr"].notna().all()

    combo_rows = gy[gy["strategy"].str.startswith("factory_combo_")]
    assert len(combo_rows) == 1
    # the combo's n_tested must be strictly greater than any individual's -- it's
    # evaluated AFTER the 4 individuals have already been logged to the same graveyard.
    assert combo_rows["n_tested"].iloc[0] > gy[~gy["strategy"].str.startswith("factory_combo_")]["n_tested"].min()


def test_run_cycle_never_redraws_an_already_tested_template(scratch_graveyard):
    first = factory_run.run_cycle(n=len(factory_run.factory.TEMPLATES), seed=1, verbose=False)
    individuals_first = {n for n in first if not n.startswith("factory_combo_")}
    assert individuals_first == set(factory_run.factory.TEMPLATES.keys())   # exhausted the pool


def test_run_cycle_falls_back_to_live_generation_once_templates_are_exhausted(scratch_graveyard):
    # exhaust the whole template pool first (#28's original behavior)...
    factory_run.run_cycle(n=len(factory_run.factory.TEMPLATES), seed=1, verbose=False)

    # ...a second cycle can no longer draw ANY template, so #28b's fallback kicks in:
    # every individual this cycle must be a live-generated one, logged to the ledger.
    second = factory_run.run_cycle(n=4, seed=2, verbose=False)
    assert second != []
    individuals_second = [n for n in second if not n.startswith("factory_combo_")]
    assert all(n not in factory_run.factory.TEMPLATES for n in individuals_second)
    assert set(individuals_second) <= factory_run.factory.generated_names()


def test_run_cycle_skips_the_combo_when_fewer_than_two_candidates_drawn(scratch_graveyard):
    evaluated = factory_run.run_cycle(n=1, seed=5, verbose=False)
    assert len(evaluated) == 1
    assert not evaluated[0].startswith("factory_combo_")


def test_generated_candidates_are_logged_to_the_ledger_before_evaluation(scratch_graveyard):
    factory_run.run_cycle(n=len(factory_run.factory.TEMPLATES), seed=1, verbose=False)  # exhaust templates
    factory_run.run_cycle(n=3, seed=2, verbose=False)
    ledger = pd.read_csv(factory_run.factory.GENERATED_LEDGER)
    assert len(ledger) >= 3
    for col in ("timestamp", "name", "family", "freq", "params", "rationale"):
        assert col in ledger.columns
    assert ledger["family"].isin(list(factory_run.factory.GENERATION_RANGES)).all()


# ---------------------------------------------------------------- promotion (#28b)
# #28b supersedes #29's "promote only if ALIVE" rule: the single best-ranked candidate
# this cycle is promoted regardless of verdict (Dave's explicit call). Real evaluate()
# outcomes are all DEAD for both real and this synthetic data (same as the actual
# project's track record) -- force a specific candidate's rank via rows_for() to test the
# RANKING/PROMOTION WIRING itself, decoupled from evaluate()'s own statistics (already
# covered by test_deflated_sharpe.py). Forces cpcv_sharpe_mean, not dsr (#145): dsr is no
# longer the promotion ranking key -- see rank_for_promotion()'s docstring for why.
def _force_winner(monkeypatch, winner_holder):
    real_rows_for = factory_run.rows_for

    def fake_rows_for(names):
        rows = real_rows_for(names)
        winner_holder["name"] = names[0]
        rows = rows.copy()
        rows.loc[rows["strategy"] == names[0], "cpcv_sharpe_mean"] = 99.0
        return rows
    monkeypatch.setattr(factory_run, "rows_for", fake_rows_for)


def test_run_cycle_promotes_the_best_ranked_candidate_regardless_of_verdict(scratch_graveyard, monkeypatch):
    winner = {}
    _force_winner(monkeypatch, winner)
    factory_run.run_cycle(n=4, seed=42, verbose=False)

    promoted_templates = set(factory_run.factory.load_promoted())
    promoted_generated = {g["name"] for g in factory_run.factory.load_promoted_generated()}
    assert (promoted_templates | promoted_generated) == {winner["name"]}


# #145: dsr saturates at exactly 1.0 for every daily-rebalanced candidate (families C and
# I) regardless of real quality -- see harness.dsr_gate1's docstring. Promotion used to
# rank on raw dsr, so a saturated tie was really decided by candidate list order
# (_fill_with_generated()'s unshuffled A,B,C,D,I round-robin), which is why 6/6 real
# promoted-generated books were turn_of_month before this fix despite generation being
# even across all 5 families. rank_for_promotion() must resolve a dsr tie by
# cpcv_sharpe_mean (a continuous, non-saturating, cross-frequency-comparable estimate),
# not by whichever candidate happens to come first.
def test_promotion_breaks_a_saturated_dsr_tie_by_cpcv_sharpe_not_row_order(scratch_graveyard, monkeypatch):
    real_rows_for = factory_run.rows_for
    winner = {}

    def fake_rows_for(names):
        rows = real_rows_for(names).copy()
        rows["dsr"] = 1.0             # saturate every candidate, same as the real bug
        rows["cpcv_sharpe_mean"] = -5.0
        winner["name"] = names[1]     # deliberately NOT names[0] -- the old idxmax(dsr)
        rows.loc[rows["strategy"] == winner["name"], "cpcv_sharpe_mean"] = 5.0
        return rows
    monkeypatch.setattr(factory_run, "rows_for", fake_rows_for)

    factory_run.run_cycle(n=4, seed=42, verbose=False)
    promoted = set(factory_run.factory.load_promoted()) | \
        {g["name"] for g in factory_run.factory.load_promoted_generated()}
    assert promoted == {winner["name"]}


def test_run_cycle_promotes_a_dead_best_candidate_not_just_alive_ones(scratch_graveyard, monkeypatch):
    winner = {}
    _force_winner(monkeypatch, winner)
    factory_run.run_cycle(n=4, seed=42, verbose=False)

    gy = pd.read_csv(scratch_graveyard)
    winner_verdict = gy[gy["strategy"] == winner["name"]].iloc[-1]["verdict"]
    assert winner_verdict == "DEAD"   # real synthetic data never clears gate 1 -- confirms
                                      # promotion happened DESPITE a DEAD verdict, not because of ALIVE
    promoted_names = set(factory_run.factory.load_promoted()) | \
        {g["name"] for g in factory_run.factory.load_promoted_generated()}
    assert winner["name"] in promoted_names


def test_run_cycle_promotes_a_generated_winner_via_promote_generated_with_full_spec(scratch_graveyard, monkeypatch):
    factory_run.run_cycle(n=len(factory_run.factory.TEMPLATES), seed=1, verbose=False)  # exhaust templates
    # that first (unforced) cycle already promoted its own best-of-batch, template-
    # sourced -- capture it so we can confirm the SECOND cycle doesn't add another one.
    promoted_before = set(factory_run.factory.load_promoted())
    assert len(promoted_before) == 1

    winner = {}
    _force_winner(monkeypatch, winner)
    factory_run.run_cycle(n=3, seed=2, verbose=False)

    assert factory_run.factory.load_promoted() == list(promoted_before)   # unchanged: this
                                                                          # cycle's winner was generated, not template-sourced
    generated_promoted = factory_run.factory.load_promoted_generated()
    assert len(generated_promoted) == 1
    entry = generated_promoted[0]
    assert entry["name"] == winner["name"]
    assert entry["family"] in factory_run.factory.GENERATION_RANGES
    assert isinstance(entry["params"], dict) and entry["params"]


def test_run_cycle_can_promote_the_combo_when_it_wins(scratch_graveyard, monkeypatch):
    # #64 reversed the old contract: the combo used to be excluded from the promotion
    # ranking entirely (piggyback.py's registry was a fixed dict, so a combo could not
    # become a live book). It now competes on equal terms. Force it to have the top rank
    # and confirm it is promoted -- into the COMBO registry, with its legs' full specs.
    real_rows_for = factory_run.rows_for

    def fake_rows_for(names):
        rows = real_rows_for(names).copy()
        combo = [n for n in names if n.startswith("factory_combo_")]
        assert combo, "the combo must be in the ranking pool now"
        rows.loc[rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 1.0
        rows.loc[~rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 0.0
        return rows
    monkeypatch.setattr(factory_run, "rows_for", fake_rows_for)

    evaluated = factory_run.run_cycle(n=4, seed=42, verbose=False)
    combo_names = [n for n in evaluated if n.startswith("factory_combo_")]
    assert combo_names

    promoted_combos = factory_run.factory.load_promoted_combos()
    assert {c["name"] for c in promoted_combos} & set(combo_names)
    spec = next(c for c in promoted_combos if c["name"] in combo_names)
    assert len(spec["legs"]) == 2
    assert spec["freq"] in ("D", "W", "M")


def test_combo_promotion_does_not_also_promote_an_individual(scratch_graveyard, monkeypatch):
    # one new book per cycle: when the combo wins it REPLACES the individual winner
    # rather than being promoted on top of it.
    real_rows_for = factory_run.rows_for

    def fake_rows_for(names):
        rows = real_rows_for(names).copy()
        combo = [n for n in names if n.startswith("factory_combo_")]
        rows.loc[rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 1.0
        rows.loc[~rows["strategy"].isin(combo), "cpcv_sharpe_mean"] = 0.0
        return rows
    monkeypatch.setattr(factory_run, "rows_for", fake_rows_for)

    factory_run.run_cycle(n=4, seed=42, verbose=False)
    individuals = set(factory_run.factory.load_promoted()) | \
        {g["name"] for g in factory_run.factory.load_promoted_generated()}
    assert not individuals, "combo won, so no individual should have been promoted"
def _all_promoted_names():
    # union across all three registries -- a cycle's winner can be a template, a
    # generated candidate, OR a combo (#64); this only cares that something new landed
    # SOMEWHERE, not which registry.
    return (set(factory_run.factory.load_promoted())
            | {g["name"] for g in factory_run.factory.load_promoted_generated()}
            | {c["name"] for c in factory_run.factory.load_promoted_combos()})


def test_run_cycle_promotion_accumulates_across_cycles(scratch_graveyard):
    factory_run.run_cycle(n=4, seed=1, verbose=False)
    first_promoted = _all_promoted_names()
    assert len(first_promoted) == 1   # exactly one best-of-cycle winner

    # a second cycle draws NEW candidates (already-tested excludes the first batch) --
    # Dave's explicit choice: promoted books ACCUMULATE, one per cycle, not a single
    # rotating slot.
    factory_run.run_cycle(n=4, seed=2, verbose=False)
    second_promoted = _all_promoted_names()
    assert len(second_promoted) == 2
    assert first_promoted < second_promoted


# ---------------------------------------------------------------- backtest curve persistence
# Regression coverage for a real bug hit while building this: a promoted book with no
# entry in EITHER full_returns.csv or piggyback_returns.csv crashed app.py's
# book_panel_data() trying to look up a backtest curve that was never persisted anywhere
# for factory/generated candidates.
def test_run_cycle_persists_a_backtest_curve_only_for_the_winner(scratch_graveyard, monkeypatch):
    winner = {}
    _force_winner(monkeypatch, winner)
    factory_run.run_cycle(n=4, seed=42, verbose=False)

    curve = pd.read_csv(factory_run.FACTORY_RETURNS_PATH, index_col=0, parse_dates=True)
    assert list(curve.columns) == [winner["name"]]   # only the winner, not all 4 candidates
    assert len(curve) > 0
    assert curve[winner["name"]].notna().any()


def test_run_cycle_persisted_curve_accumulates_columns_across_cycles(scratch_graveyard):
    factory_run.run_cycle(n=4, seed=1, verbose=False)
    factory_run.run_cycle(n=4, seed=2, verbose=False)
    curve = pd.read_csv(factory_run.FACTORY_RETURNS_PATH, index_col=0, parse_dates=True)
    assert curve.shape[1] == 2   # one column per cycle's winner, not overwritten
    assert set(curve.columns) == _all_promoted_names()
