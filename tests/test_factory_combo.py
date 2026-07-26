"""Factory combo promotion (#64).

Before this, the factory could promote a single-strategy candidate it discovered but not
a COMBO it discovered, because piggyback.REGISTRY is a fixed hand-picked dict. These
cover the new registry, the weight construction, and the leg-rebuild path that has to
work in a fresh process."""
import json

import numpy as np
import pandas as pd
import pytest

from tradefabe import factory


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_COMBOS_PATH", tmp_path / "promoted_combos.json")
    return tmp_path


def _generated_leg(name="tsmom_gen_100d", family="A", params=None):
    # family keys are the STRATEGIES.md letters; family A (trend) takes lookback_days
    return {"name": name, "family": family, "params": params or {"lookback_days": 100}}


def _spec(name="factory_combo_a_b", freq="D", legs=None):
    return {"name": name, "freq": freq,
            "legs": legs or [_generated_leg(), _generated_leg("tsmom_gen_200d",
                                                              params={"lookback_days": 200})]}


def _prices(n=400, cols=("SPY", "IEF", "QQQ")):
    idx = pd.bdate_range("2024-01-02", periods=n)
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {c: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n))) for c in cols}, index=idx)


# ---------------------------------------------------------------- registry
def test_promote_combo_persists_the_full_leg_specs(isolated):
    factory.promote_combo(_spec())
    saved = json.loads((isolated / "promoted_combos.json").read_text())
    assert len(saved) == 1
    # legs must carry family+params, not just names -- a fresh process cannot rebuild
    # a generated signal function from a name alone
    for leg in saved[0]["legs"]:
        assert leg["family"] and leg["params"]


def test_promote_combo_is_idempotent(isolated):
    factory.promote_combo(_spec())
    factory.promote_combo(_spec())
    assert len(factory.load_promoted_combos()) == 1


def test_promote_combo_accumulates_distinct_names(isolated):
    factory.promote_combo(_spec("factory_combo_a_b"))
    factory.promote_combo(_spec("factory_combo_c_d"))
    assert {c["name"] for c in factory.load_promoted_combos()} == {
        "factory_combo_a_b", "factory_combo_c_d"}


def test_load_is_empty_when_nothing_promoted(isolated):
    assert factory.load_promoted_combos() == []


# ---------------------------------------------------------------- weights
def test_combo_weights_are_70pct_core_plus_30pct_sleeve(isolated):
    px = _prices()
    w = factory.combo_target_weights(px, _spec())
    # the 60/40 core is 70% of the book, so SPY alone carries at least 0.7*0.6 minus
    # whatever the sleeve shorts -- the invariant that must hold is the total split
    assert w.index.equals(px.columns)
    assert not w.isna().any()
    assert factory.COMBO_SLEEVE == pytest.approx(0.30)


def test_combo_weights_match_a_hand_computed_blend(isolated):
    from tradefabe.engine import BENCH_W, sized_weights
    px = _prices()
    spec = _spec()
    legs = [factory.rebuild_signal(l["family"], l["params"]) for l in spec["legs"]]
    sleeve = sum(sized_weights(px, f(px)).iloc[-1].fillna(0.0) for f in legs) / len(legs)
    bench = pd.Series(BENCH_W).reindex(px.columns).fillna(0.0)
    expected = 0.7 * bench + 0.3 * sleeve
    pd.testing.assert_series_equal(factory.combo_target_weights(px, spec), expected)


def test_a_template_leg_needs_no_params(isolated):
    name = next(iter(factory.TEMPLATES))
    spec = _spec(legs=[{"name": name, "family": None, "params": None}, _generated_leg()])
    w = factory.combo_target_weights(_prices(), spec)
    assert not w.isna().any()


def test_an_unknown_leg_raises_rather_than_silently_dropping(isolated):
    spec = _spec(legs=[{"name": "not_a_thing", "family": None, "params": None},
                       _generated_leg()])
    with pytest.raises(KeyError):
        factory.combo_target_weights(_prices(), spec)
