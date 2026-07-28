"""Family M pure signals on hand-built forecast frames — no torch, no weights, no network.

That this file runs in CI at all is the point of splitting inference from signal logic in
`tradefabe.kronos`: the functions the live books would call are testable without a 400MB
download, and there is exactly one copy of them shared with the study.
"""
import numpy as np
import pandas as pd
import pytest

from tradefabe import kronos

IDX = pd.bdate_range("2025-07-01", periods=12)   # deliberately AFTER the pretrain cutoff
TICKERS = ["AAA", "BBB", "CCC"]


def fc_frame(**fields):
    """Forecast frame with columns (ticker, field). Each kwarg is field -> {ticker: value},
    broadcast down the index unless a list is given."""
    data = {}
    for field, per_ticker in fields.items():
        for tkr, val in per_ticker.items():
            data[(tkr, field)] = val if isinstance(val, list) else [val] * len(IDX)
    df = pd.DataFrame(data, index=IDX)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df.sort_index(axis=1)


# ------------------------------------------------------------------ sig_kronos_dir
def test_dir_signal_is_the_sign_of_the_forecast_return():
    fc = fc_frame(fc_ret={"AAA": 0.03, "BBB": -0.02, "CCC": 0.0})
    sig = kronos.sig_kronos_dir(fc)
    assert sig.iloc[-1]["AAA"] == 1.0
    assert sig.iloc[-1]["BBB"] == -1.0
    assert sig.iloc[-1]["CCC"] == 0.0


def test_dir_signal_ignores_forecast_magnitude():
    """Pre-registered as the SIGN of the forecast return. A magnitude-weighted variant is a
    different strategy and would need its own row (roster rule 2)."""
    small = kronos.sig_kronos_dir(fc_frame(fc_ret={"AAA": 0.0001}))
    huge = kronos.sig_kronos_dir(fc_frame(fc_ret={"AAA": 5.0}))
    assert small.iloc[-1]["AAA"] == huge.iloc[-1]["AAA"] == 1.0


def test_dir_signal_treats_a_missing_forecast_as_flat():
    sig = kronos.sig_kronos_dir(fc_frame(fc_ret={"AAA": np.nan}))
    assert sig.iloc[-1]["AAA"] == 0.0


# ------------------------------------------------------------------ sig_kronos_wick
def falling(start=100.0):
    """Strictly falling prices, so the HAMMER_PULLBACK precondition holds everywhere."""
    return list(np.linspace(start, start * 0.7, len(IDX)))


def rising(start=100.0):
    return list(np.linspace(start, start * 1.3, len(IDX)))


def test_wick_fires_only_when_a_majority_of_paths_show_a_hammer():
    """fc_hammer is a FRACTION of sampled futures; the 0.5 majority threshold is the signal
    decision. 0.49 must not fire, 0.51 must."""
    px = pd.DataFrame({t: falling() for t in ["AAA", "BBB"]}, index=IDX)
    below = kronos.sig_kronos_wick(fc_frame(fc_hammer={"AAA": 0.49, "BBB": 0.0}), px)
    above = kronos.sig_kronos_wick(fc_frame(fc_hammer={"AAA": 0.51, "BBB": 0.0}), px)
    assert below.iloc[-1]["AAA"] == 0.0
    assert above.iloc[-1]["AAA"] == 1.0


def test_wick_requires_the_pullback_precondition():
    """Same hammer forecast, one name falling and one rising. Only the pullback fires —
    this is the precondition inherited verbatim from daytrade_tests.wick_study."""
    px = pd.DataFrame({"AAA": falling(), "BBB": rising()}, index=IDX)
    sig = kronos.sig_kronos_wick(fc_frame(fc_hammer={"AAA": 1.0, "BBB": 1.0}), px)
    assert sig.iloc[-1]["AAA"] > 0.0
    assert sig.iloc[-1]["BBB"] == 0.0


def test_wick_is_long_only_and_never_shorts():
    px = pd.DataFrame({t: falling() for t in TICKERS}, index=IDX)
    sig = kronos.sig_kronos_wick(
        fc_frame(fc_hammer={"AAA": 1.0, "BBB": 0.0, "CCC": 0.0}), px)
    assert (sig.to_numpy() >= 0).all()


def test_wick_gross_is_exactly_one_when_any_name_fires_and_zero_otherwise():
    """The pre-registered aggression: gross 1.0, equal weight, flat when nothing triggers.
    No vol targeting and no MAX_LEG cap — sized_weights must NOT be layered on top."""
    px = pd.DataFrame({t: falling() for t in TICKERS}, index=IDX)
    two = kronos.sig_kronos_wick(
        fc_frame(fc_hammer={"AAA": 1.0, "BBB": 1.0, "CCC": 0.0}), px)
    gross = two.abs().sum(axis=1)
    assert gross.iloc[-1] == pytest.approx(1.0)
    assert two.iloc[-1]["AAA"] == pytest.approx(0.5)
    assert two.iloc[-1]["CCC"] == 0.0

    none = kronos.sig_kronos_wick(fc_frame(fc_hammer={t: 0.0 for t in TICKERS}), px)
    assert none.abs().sum(axis=1).iloc[-1] == 0.0


def test_wick_holds_a_trigger_for_hold_bars_then_releases():
    """A 5-bar forecast acted on for one bar and re-decided daily would pay 5x the turnover
    for one forecast's worth of information. The trigger is carried HOLD_BARS bars."""
    px = pd.DataFrame({"AAA": falling()}, index=IDX)
    # Fire at bar 5, not earlier: the HAMMER_PULLBACK lookback is still NaN for the first
    # 5 bars, so nothing CAN trigger during that warm-up however strong the forecast is.
    fire = 5
    fires_once = [0.0] * len(IDX)
    fires_once[fire] = 1.0
    sig = kronos.sig_kronos_wick(fc_frame(fc_hammer={"AAA": fires_once}), px)["AAA"]

    assert (sig.iloc[:fire] == 0.0).all()                              # before the trigger
    assert (sig.iloc[fire:fire + kronos.HOLD_BARS] == 1.0).all()       # held through horizon
    assert sig.iloc[fire + kronos.HOLD_BARS] == 0.0                    # released after


# ------------------------------------------------------------------ vol_scale
def test_vol_scale_is_target_over_forecast_vol():
    got = kronos.vol_scale(pd.Series([0.20, 0.40]), target_vol=0.10)
    assert got.tolist() == pytest.approx([0.5, 0.25])


def test_vol_scale_never_levers_past_always_on_carry():
    """Capped at 1.0. Uncapped, a calm-vol forecast would let the book beat its always-on
    carry benchmark on LEVERAGE rather than on timing — answering a different question than
    the one pre-registered."""
    got = kronos.vol_scale(pd.Series([0.001, 0.02, 0.10]), target_vol=0.10)
    assert (got <= kronos.VOL_SCALE_CAP).all()
    assert got.iloc[0] == pytest.approx(1.0)


def test_an_unusable_forecast_falls_back_to_full_size_not_flat():
    """NaN/zero/negative vol means the model gave us nothing. Full size reproduces always-on
    carry; going flat would be an ACTIVE bet the forecast never made. Also guards the NaN
    traps CLAUDE.md records: `nan <= 0` is False and `nan or 0` is nan."""
    got = kronos.vol_scale(pd.Series([np.nan, 0.0, -1.0]), target_vol=0.10)
    assert got.tolist() == pytest.approx([1.0, 1.0, 1.0])
    assert np.isfinite(got).all()


# ------------------------------------------------------------------ summarize_paths
def paths_from(closes, opens=None, highs=None, lows=None):
    """(n_paths, pred_len, 5) OHLCV block built from explicit closes."""
    c = np.asarray(closes, dtype=float)
    o = np.asarray(opens, dtype=float) if opens is not None else c
    h = np.asarray(highs, dtype=float) if highs is not None else np.maximum(o, c)
    l = np.asarray(lows, dtype=float) if lows is not None else np.minimum(o, c)
    return np.stack([o, h, l, c, np.ones_like(c)], axis=-1)


def test_fc_vol_measures_disagreement_across_paths_not_along_one():
    """The distinction the module docstring is built around. Paths that each wander a lot
    but all LAND in the same place carry no forecast uncertainty about the destination —
    fc_vol must be ~0. Reading SD along a single path would report a large number."""
    wandering = paths_from([[100, 130, 70, 120, 110]] * 8)
    assert kronos.summarize_paths(wandering, last_close=100.0)["fc_vol"] == pytest.approx(0.0)

    disagreeing = paths_from([[100, 100, 100, 100, end] for end in
                              (80, 90, 100, 110, 120, 95, 105, 115)])
    assert kronos.summarize_paths(disagreeing, last_close=100.0)["fc_vol"] > 0.5


def test_fc_ret_is_the_mean_terminal_return_over_paths():
    paths = paths_from([[100, 100, 100, 100, 110], [100, 100, 100, 100, 90]])
    assert kronos.summarize_paths(paths, last_close=100.0)["fc_ret"] == pytest.approx(0.0)


def test_fc_hammer_counts_the_fraction_of_paths_containing_one():
    """One path with a textbook hammer (long lower wick, close at the top), one without."""
    hammer = paths_from(closes=[[100, 100, 100, 100, 99]], opens=[[100, 100, 100, 100, 100]],
                        highs=[[100, 100, 100, 100, 100]], lows=[[100, 100, 100, 100, 90]])
    plain = paths_from(closes=[[100, 100, 100, 100, 100]])
    both = np.concatenate([hammer, plain])
    assert kronos.summarize_paths(both, last_close=100.0)["fc_hammer"] == pytest.approx(0.5)


# ------------------------------------------------------------------ contamination guard
def test_the_clean_window_guard_rejects_pre_cutoff_bars():
    """A verdict scored on the model's own training data looks GOOD — that is exactly why
    this is a raise and not a comment."""
    with pytest.raises(ValueError, match="pretraining cutoff"):
        kronos.assert_clean_window(pd.bdate_range("2024-01-01", periods=10))


def test_the_clean_window_guard_passes_post_cutoff_bars():
    kronos.assert_clean_window(pd.bdate_range("2025-07-01", periods=10))


def test_the_family_oos_start_is_not_the_default_doctrine_one():
    """Regression guard on the whole premise of family M: if someone ever 'fixes' this to
    engine.OOS_START, every verdict in the family silently becomes contaminated."""
    from tradefabe import engine
    assert kronos.KRONOS_OOS_START == pd.Timestamp("2025-06-05")
    assert kronos.KRONOS_OOS_START > pd.Timestamp(getattr(engine, "OOS_START", "2018-01-01"))
