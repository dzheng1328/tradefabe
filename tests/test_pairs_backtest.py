"""Family N mechanics (#172).

The verdict rests on three things being right: the cointegration filter actually
distinguishing a real relationship from two independent series (fit_pair), the
stateful entry/exit/stop logic doing what its z-score thresholds say (pair_position),
and the sizing dilution bug found and fixed while building this (#172's own
debugging) staying fixed -- a signal frame padded with inactive tickers silently
shrinks every position by dividing by the wrong denominator in engine.sized_weights().
"""
import numpy as np
import pandas as pd
import pytest

import pairs_backtest as pb


def _log_walk(n, seed, drift=0.0, vol=0.01):
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(drift, vol, n))


# ---------------------------------------------------------------- fit_pair
def test_fit_pair_recovers_a_known_hedge_ratio_on_a_truly_cointegrated_pair():
    """B is A's log-price times a known beta plus small mean-reverting noise -- the
    textbook cointegrated construction. fit_pair() must recover beta close to the
    true value and the ADF test must reject the unit root (low p-value)."""
    idx = pd.bdate_range(pb.CALIB_START, periods=3000)
    log_a = _log_walk(len(idx), seed=1, drift=0.0002, vol=0.01)
    true_beta = 1.7
    noise = np.random.default_rng(2).normal(0, 0.005, len(idx))
    # mean-reverting noise (AR(1), phi<1), not a random walk, or the residual itself
    # would be nonstationary and no beta could make this pair pass ADF.
    resid = np.zeros(len(idx))
    for i in range(1, len(idx)):
        resid[i] = 0.9 * resid[i - 1] + noise[i]
    log_b = (log_a - resid) / true_beta
    prices = pd.DataFrame({"A": np.exp(log_a), "B": np.exp(log_b)}, index=idx)

    beta, alpha, adf_p = pb.fit_pair(prices, "A", "B")
    assert beta == pytest.approx(true_beta, rel=0.1)
    assert adf_p < 0.05


def test_fit_pair_fails_two_independent_random_walks():
    """Two independent random walks are the textbook NON-cointegrated case -- any
    linear combination is itself a random walk, so ADF must NOT reject the unit root
    (spurious regression, Granger & Newbold 1974)."""
    idx = pd.bdate_range(pb.CALIB_START, periods=3000)
    log_a = _log_walk(len(idx), seed=30)
    log_b = _log_walk(len(idx), seed=40)
    prices = pd.DataFrame({"A": np.exp(log_a), "B": np.exp(log_b)}, index=idx)

    _, _, adf_p = pb.fit_pair(prices, "A", "B")
    assert adf_p > 0.05


def test_fit_pair_only_uses_the_calibration_window():
    """A relationship that holds ONLY after the calibration window ends must not be
    picked up -- fit_pair() must be blind to OOS data, the same discipline every other
    family's calibration/OOS split already follows."""
    idx = pd.bdate_range("2007-01-01", periods=6000)   # spans well past CALIB_END
    calib_end_i = idx.get_indexer([pd.Timestamp(pb.CALIB_END)], method="nearest")[0]
    log_a = _log_walk(len(idx), seed=1)
    log_b = _log_walk(len(idx), seed=2)
    # force perfect cointegration (identical series) starting ONLY after calibration ends
    log_b[calib_end_i:] = log_a[calib_end_i:]
    prices = pd.DataFrame({"A": np.exp(log_a), "B": np.exp(log_b)}, index=idx)

    _, _, adf_p = pb.fit_pair(prices, "A", "B")
    # the two series are still independent random walks THROUGH the calibration window,
    # so this must fail exactly like the independent-walks case -- the post-calibration
    # relationship must be invisible to the fit.
    assert adf_p > 0.05


# ---------------------------------------------------------------- pair_position
def test_pair_position_enters_long_the_spread_below_negative_entry():
    z = pd.Series([0.0, -1.0, -2.5, -2.5, -2.5])
    pos = pb.pair_position(z)
    assert list(pos) == [0.0, 0.0, 1.0, 1.0, 1.0]


def test_pair_position_enters_short_the_spread_above_positive_entry():
    z = pd.Series([0.0, 1.0, 2.5, 2.5])
    pos = pb.pair_position(z)
    assert list(pos) == [0.0, 0.0, -1.0, -1.0]


def test_pair_position_exits_a_long_when_z_crosses_back_through_zero():
    z = pd.Series([-2.5, -2.5, -1.0, 0.0, 0.5])
    pos = pb.pair_position(z)
    assert list(pos) == [1.0, 1.0, 1.0, 0.0, 0.0]


def test_pair_position_force_flattens_a_long_past_the_stop():
    z = pd.Series([-2.5, -3.0, -4.5, -5.0])
    pos = pb.pair_position(z)
    assert list(pos) == [1.0, 1.0, 0.0, 0.0]


def test_pair_position_does_not_re_enter_between_entry_and_exit_thresholds():
    """Inside (-Z_ENTRY, +Z_ENTRY) with no open position, nothing happens -- the
    threshold is an ENTRY trigger, not a continuous signal."""
    z = pd.Series([0.0, 1.5, -1.5, 0.5, -0.5])
    pos = pb.pair_position(z)
    assert list(pos) == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_pair_position_treats_nan_as_flat():
    z = pd.Series([-2.5, np.nan, -2.5])
    pos = pb.pair_position(z)
    assert list(pos) == [1.0, 0.0, 1.0]   # NaN forces flat; re-enters fresh after


# ---------------------------------------------------------------- sizing dilution (#172)
def test_padding_the_signal_with_inactive_tickers_silently_shrinks_the_position():
    """The bug found while building this: engine.sized_weights() divides by
    prices.shape[1], and every OTHER family densely populates every column, so that
    normalization naturally spreads capital across the whole universe. A pairs signal
    is structurally sparse -- one active pair's two columns nonzero, the rest zero.
    Passing the FULL 12-ticker candidate universe through regardless of how many pairs
    actually cleared the filter divides by 12 when only 2 are ever active, silently
    shrinking the position to a fraction of what the same signal, sized against ONLY
    the active tickers, would produce. This proves the mechanism main() must avoid by
    narrowing `px` to just the kept pairs' tickers before sizing -- not main() itself,
    since it isn't factored into a separately-callable function, but the same
    sized_weights() call it makes."""
    from tradefabe.engine import sized_weights

    idx = pd.bdate_range("2018-01-01", periods=300)
    rng = np.random.default_rng(0)
    prices_full = pd.DataFrame(
        {t: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))
         for t in ["LQD", "HYG", "GLD", "SLV", "TLT", "IEF", "EFA", "EEM",
                  "SPY", "QQQ", "USO", "DBC"]}, index=idx)
    only_active = prices_full[["LQD", "HYG"]]

    pos = pd.Series(1.0, index=idx)
    signal_padded = pd.DataFrame(0.0, index=idx, columns=prices_full.columns)
    signal_padded["LQD"] = pos
    signal_padded["HYG"] = -pos
    signal_narrow = pd.DataFrame({"LQD": pos, "HYG": -pos}, index=idx)

    w_padded = sized_weights(prices_full, signal_padded)
    w_narrow = sized_weights(only_active, signal_narrow)

    # same direction, same underlying prices for LQD/HYG -- only the denominator
    # (prices.shape[1]: 12 vs 2) differs, so the padded version must be smaller by
    # exactly that ratio, not merely "different."
    ratio = (w_narrow["LQD"] / w_padded["LQD"]).dropna()
    assert ratio.to_numpy() == pytest.approx(6.0, rel=0.01)
