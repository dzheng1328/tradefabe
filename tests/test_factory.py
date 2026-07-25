"""The strategy factory's template library and pure selection logic (#28) -- signal
math on synthetic prices with known expected output (same style as test_signals.py),
plus select_diverse_sample()/complementary_pairs() unit tests. Requires
pyproject.toml's [tool.pytest.ini_options] pythonpath=["."] so `import harness`-style
repo-root imports resolve (factory itself lives in the installed tradefabe package)."""
import numpy as np
import pandas as pd
import pytest

from tradefabe import factory

N = 260
IDX = pd.bdate_range("2020-01-02", periods=N)


def trend_prices():
    up = np.linspace(50.0, 150.0, N)
    down = np.linspace(150.0, 50.0, N)
    flat = np.full(N, 100.0)
    return pd.DataFrame({"UP": up, "DOWN": down, "FLAT": flat}, index=IDX)


# ---------------------------------------------------------------- TEMPLATES shape
def test_templates_have_the_expected_shape_and_valid_freq():
    for name, spec in factory.TEMPLATES.items():
        assert len(spec) == 4, name
        sig_fn, freq, rationale, family = spec
        assert callable(sig_fn), name
        assert freq in ("D", "W", "M"), name
        assert isinstance(rationale, str) and len(rationale) > 20, name
        assert isinstance(family, str) and len(family) == 1, name


def test_templates_are_genuinely_new_names_not_existing_graveyard_entries():
    # the whole point of the factory is NEW candidates, not re-tests of the roster
    # already in STRATEGIES.md/graveyard.csv under the same name.
    existing = {"tsmom_12m", "tsmom_ensemble", "xsec_momentum", "green_line_200d",
               "str_reversal_5d", "low_vol_xsec", "turn_of_month",
               "insider_buying_21d", "piggyback_2a", "piggyback_2b",
               "piggyback_3", "piggyback_4"}
    assert existing.isdisjoint(factory.TEMPLATES.keys())


# ---------------------------------------------------------------- template signal math
def test_tsmom_variant_signs_match_trend_direction():
    px = trend_prices()
    sig_fn = factory.TEMPLATES["tsmom_6m"][0]
    last = sig_fn(px).iloc[-1]
    assert last["UP"] == 1.0
    assert last["DOWN"] == -1.0
    assert last["FLAT"] == 0.0


def test_str_reversal_variant_fades_the_move():
    px = trend_prices()
    sig_fn = factory.TEMPLATES["str_reversal_10d"][0]
    last = sig_fn(px).iloc[-1]
    assert last["UP"] == -1.0     # rising -> fade -> short
    assert last["DOWN"] == 1.0    # falling -> fade -> long
    assert last["FLAT"] == 0.0


def test_low_vol_xsec_variant_favors_the_calmer_asset():
    # 4 assets so the calm one's percentile rank sits strictly below 0.5 (with only 2
    # assets the calmer one lands exactly at the 0.5 rank boundary -> sign(0) = 0, not +1
    # -- an artifact of percentile ranking at small N, not a template bug).
    idx = IDX
    calm = np.full(N, 100.0)
    mid1 = 100.0 * np.cumprod(1 + 0.01 * np.where(np.arange(N) % 2 == 0, 1, -1))
    mid2 = 100.0 * np.cumprod(1 + 0.03 * np.where(np.arange(N) % 2 == 0, 1, -1))
    wild = 100.0 * np.cumprod(1 + 0.05 * np.where(np.arange(N) % 2 == 0, 1, -1))
    px = pd.DataFrame({"CALM": calm, "MID1": mid1, "MID2": mid2, "WILD": wild}, index=idx)
    sig_fn = factory.TEMPLATES["low_vol_xsec_30d"][0]
    last = sig_fn(px).iloc[-1]
    assert last["CALM"] == 1.0
    assert last["WILD"] == -1.0


def test_turn_of_month_variant_only_fires_in_its_window():
    sig_fn = factory.TEMPLATES["turn_of_month_narrow"][0]
    idx = pd.bdate_range("2024-01-01", "2024-02-29")
    px = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    sig = sig_fn(px)
    jan = sig.loc["2024-01"]
    per = jan.index.to_period("M")
    pos = pd.Series(range(1, len(jan) + 1), index=jan.index)
    tot = len(jan)
    in_window = (pos <= 2) | ((tot - pos) < 2)
    assert (jan["A"][in_window] == 1.0).all()
    assert (jan["A"][~in_window] == 0.0).all()


def test_donchian_breakout_goes_long_on_a_new_high_short_on_a_new_low():
    idx = pd.bdate_range("2024-01-02", periods=30)
    # flat at 100 for the lookback, then a sharp new high on the last day
    px = pd.DataFrame({"A": [100.0] * 29 + [200.0]}, index=idx)
    sig_fn = factory.TEMPLATES["donchian_20d"][0]
    last = sig_fn(px).iloc[-1]
    assert last["A"] == 1.0

    px2 = pd.DataFrame({"A": [100.0] * 29 + [50.0]}, index=idx)
    last2 = sig_fn(px2).iloc[-1]
    assert last2["A"] == -1.0


# ---------------------------------------------------------------- select_diverse_sample
def test_select_diverse_sample_respects_k():
    rng = np.random.default_rng(0)
    out = factory.select_diverse_sample(factory.TEMPLATES, k=5, rng=rng)
    assert len(out) == 5
    assert len(set(out)) == 5     # no duplicates


def test_select_diverse_sample_spans_multiple_families_when_k_allows():
    rng = np.random.default_rng(0)
    out = factory.select_diverse_sample(factory.TEMPLATES, k=8, rng=rng)
    families = {factory.TEMPLATES[name][3] for name in out}
    # round-robin construction: 8 draws across 5 families must touch at least 4 of them,
    # never pure luck landing all 8 in one family.
    assert len(families) >= 4


def test_select_diverse_sample_honors_exclude():
    rng = np.random.default_rng(0)
    exclude = set(factory.TEMPLATES.keys()) - {"tsmom_3m", "donchian_20d"}
    out = factory.select_diverse_sample(factory.TEMPLATES, k=5, rng=rng, exclude=exclude)
    assert set(out) == {"tsmom_3m", "donchian_20d"}


def test_select_diverse_sample_caps_at_available_pool_size():
    rng = np.random.default_rng(0)
    out = factory.select_diverse_sample(factory.TEMPLATES, k=1000, rng=rng)
    assert len(out) == len(factory.TEMPLATES)
    assert set(out) == set(factory.TEMPLATES.keys())


def test_select_diverse_sample_is_deterministic_given_a_seed():
    out1 = factory.select_diverse_sample(factory.TEMPLATES, k=6, rng=np.random.default_rng(7))
    out2 = factory.select_diverse_sample(factory.TEMPLATES, k=6, rng=np.random.default_rng(7))
    assert out1 == out2


# ---------------------------------------------------------------- complementary_pairs
def test_complementary_pairs_picks_the_least_correlated_pair_first():
    # "least correlated" means |corr| closest to zero -- NOT most negative. b is
    # independent noise (~0 corr with a and c); c is a plus a tiny nudge (~+1 corr with
    # a) -- the most-correlated pair must involve both a and c, and sorted ascending by
    # |corr| the first pair must be strictly less correlated than the last.
    idx = pd.bdate_range("2020-01-02", periods=300)
    rng = np.random.default_rng(0)
    a = rng.normal(0, 0.01, 300)
    b = rng.normal(0, 0.01, 300)             # independent of a
    c = a + rng.normal(0, 0.0005, 300)       # strongly correlated with a
    returns = pd.DataFrame({"a": a, "b": b, "c": c}, index=idx)
    pairs = factory.complementary_pairs(returns, ["a", "b", "c"], top_k=3)
    assert set(pairs[-1][:2]) == {"a", "c"}          # most correlated pair, sorted last
    assert abs(pairs[0][2]) < abs(pairs[-1][2])


def test_complementary_pairs_respects_top_k():
    idx = pd.bdate_range("2020-01-02", periods=100)
    rng = np.random.default_rng(1)
    returns = pd.DataFrame({n: rng.normal(0, 0.01, 100) for n in ("a", "b", "c", "d")}, index=idx)
    pairs = factory.complementary_pairs(returns, ["a", "b", "c", "d"], top_k=2)
    assert len(pairs) == 2


# ---------------------------------------------------------------- target_weights
def test_target_weights_matches_sized_weights_last_row():
    from tradefabe.engine import sized_weights
    px = trend_prices()
    sig_fn = factory.TEMPLATES["tsmom_6m"][0]
    got = factory.target_weights(px, "tsmom_6m")
    expected = sized_weights(px, sig_fn(px)).iloc[-1].fillna(0.0)
    pd.testing.assert_series_equal(got, expected)


# ---------------------------------------------------------------- promotion registry (#29)
def test_promote_writes_and_load_promoted_reads_back(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    assert factory.load_promoted() == []
    factory.promote("donchian_20d")
    assert factory.load_promoted() == ["donchian_20d"]


def test_promote_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    factory.promote("donchian_20d")
    factory.promote("donchian_20d")
    assert factory.load_promoted() == ["donchian_20d"]


def test_promote_appends_without_clobbering_existing_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    factory.promote("donchian_20d")
    factory.promote("tsmom_3m")
    assert set(factory.load_promoted()) == {"donchian_20d", "tsmom_3m"}


def test_promote_rejects_a_name_not_in_templates(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    with pytest.raises(ValueError):
        factory.promote("not_a_real_template")


def test_load_promoted_filters_out_stale_names_no_longer_in_templates(monkeypatch, tmp_path):
    p = tmp_path / "promoted.json"
    p.write_text('["donchian_20d", "a_template_that_got_removed_later"]')
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", p)
    assert factory.load_promoted() == ["donchian_20d"]


def test_load_promoted_empty_when_file_does_not_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(factory, "STATE_DIR", tmp_path)
    monkeypatch.setattr(factory, "PROMOTED_PATH", tmp_path / "does_not_exist.json")
    assert factory.load_promoted() == []
