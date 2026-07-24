"""Signal functions on synthetic prices with known expected output — no live data, no
randomness (except sig_random itself, which is trivially exempt from a "known output"
test by definition)."""
import numpy as np
import pandas as pd
import pytest

from tradefabe import signals

N = 260  # > LOOKBACK (252) so every trailing-window signal has real values on the last row
IDX = pd.bdate_range("2020-01-02", periods=N)


def trend_prices():
    """Three columns with unambiguous, hand-verifiable 12-mo and 200d-MA trends:
    UP is strictly increasing (last value > any trailing window's mean or start),
    DOWN mirrors it, FLAT never moves at all."""
    up = np.linspace(50.0, 150.0, N)
    down = np.linspace(150.0, 50.0, N)
    flat = np.full(N, 100.0)
    return pd.DataFrame({"UP": up, "DOWN": down, "FLAT": flat}, index=IDX)


def test_sig_tsmom_12m_signs():
    px = trend_prices()
    sig = signals.sig_tsmom_12m(px)
    last = sig.iloc[-1]
    assert last["UP"] == 1.0
    assert last["DOWN"] == -1.0
    assert last["FLAT"] == 0.0


def test_sig_tsmom_ensemble_signs():
    px = trend_prices()
    sig = signals.sig_tsmom_ensemble(px)
    last = sig.iloc[-1]
    # every one of the 3/6/12-month lookbacks agrees on a strictly monotonic series,
    # so the ensemble average is exactly +-1.0, not just same-signed
    assert last["UP"] == 1.0
    assert last["DOWN"] == -1.0
    assert last["FLAT"] == 0.0


def test_sig_green_line_200d_signs():
    px = trend_prices()
    sig = signals.sig_green_line_200d(px)
    last = sig.iloc[-1]
    assert last["UP"] == 1.0     # strictly rising series sits above its own trailing mean
    assert last["DOWN"] == -1.0
    assert last["FLAT"] == 0.0   # price - its own trailing mean is exactly 0 when flat


def test_sig_str_reversal_fades_the_trend():
    px = trend_prices()
    sig = signals.sig_str_reversal(px)
    last = sig.iloc[-1]
    # reversal is the NEGATIVE of the 5-day trend: an UP series has a positive 5-day
    # return, so the fade signal is short, and vice versa
    assert last["UP"] == -1.0
    assert last["DOWN"] == 1.0
    assert last["FLAT"] == 0.0


def test_sig_xsec_momentum_ranks_by_relative_return():
    idx = IDX
    # four distinct, strictly ordered 12-month returns: -30%, -10%, +10%, +30%
    worst = np.linspace(100.0, 70.0, N)
    low = np.linspace(100.0, 90.0, N)
    high = np.linspace(100.0, 110.0, N)
    best = np.linspace(100.0, 130.0, N)
    px = pd.DataFrame({"worst": worst, "low": low, "high": high, "best": best}, index=idx)
    sig = signals.sig_xsec_momentum(px)
    last = sig.iloc[-1]
    # pct rank of 4 distinct values -> .25/.5/.75/1.0; sign(pr - 0.5) -> -1/0/+1/+1
    assert last["worst"] == -1.0
    assert last["low"] == 0.0
    assert last["high"] == 1.0
    assert last["best"] == 1.0


def test_sig_low_vol_ranks_calmest_long_wildest_short():
    n = 80
    idx = pd.bdate_range("2020-01-02", periods=n)
    t = np.arange(n)
    # deterministic alternating +-amp daily returns -> realized vol scales with amp,
    # cleanly separated so pct-rank ordering is unambiguous
    amps = {"calm": 0.001, "mild": 0.01, "brisk": 0.03, "wild": 0.06}
    data = {}
    for name, amp in amps.items():
        rets = amp * np.where(t % 2 == 0, 1.0, -1.0)
        data[name] = 100.0 * np.cumprod(1 + rets)
    px = pd.DataFrame(data, index=idx)
    sig = signals.sig_low_vol(px)
    last = sig.iloc[-1]
    # ascending vol -> pct rank .25/.5/.75/1.0 -> sign(0.5 - pr) -> +1/0/-1/-1
    assert last["calm"] == 1.0
    assert last["mild"] == 0.0
    assert last["brisk"] == -1.0
    assert last["wild"] == -1.0


def test_tsmom_and_green_line_genuinely_diverge():
    """Pins the CLAUDE.md gotcha: tsmom_12m and green_line_200d paper books opened
    identical-to-the-cent on 2026-07-22. Plausible in a uniform uptrend, but the two
    signals CAN and DO disagree — this constructs the exact disagreement case (a price
    that fell then partially recovered) and checks live target_weights() differ."""
    n = 300   # chosen so iloc[-1-252] == index 47, exactly the flat/drop boundary below
    idx = pd.bdate_range("2020-01-02", periods=n)
    px = np.empty(n)
    px[:47] = 100.0                                    # flat run; this is the 12-mo-ago level
    px[47:100] = np.linspace(100.0, 60.0, 100 - 47)     # sharp drop
    px[100:] = np.linspace(60.0, 90.0, n - 100)         # partial recovery, still < 100
    prices = pd.DataFrame({"X": px, "PAD": np.full(n, 100.0)}, index=idx)

    # hand-check the disagreement before trusting the library call
    ref_12mo_ago = prices["X"].iloc[-1 - 252]
    last_price = prices["X"].iloc[-1]
    assert last_price < ref_12mo_ago                    # tsmom_12m: SHORT
    ma200 = prices["X"].rolling(200).mean().iloc[-1]
    assert last_price > ma200                            # green_line_200d: LONG

    w_tsmom = signals.target_weights(prices, "tsmom_12m")
    w_green = signals.target_weights(prices, "green_line_200d")
    assert np.sign(w_tsmom["X"]) == -1.0
    assert np.sign(w_green["X"]) == 1.0
    assert np.sign(w_tsmom["X"]) != np.sign(w_green["X"])


def test_registry_covers_all_live_books():
    assert set(signals.REGISTRY) == {"tsmom_12m", "tsmom_ensemble", "green_line_200d", "turn_of_month"}
    for fn, freq in signals.REGISTRY.values():
        assert callable(fn)
        assert freq in ("D", "W", "M")


def test_is_month_first_trading_day():
    idx = pd.DatetimeIndex(["2024-01-30", "2024-01-31"])
    assert signals.is_month_first_trading_day(idx) is False
    idx2 = pd.DatetimeIndex(["2024-01-31", "2024-02-01"])
    assert signals.is_month_first_trading_day(idx2) is True
    assert signals.is_month_first_trading_day(pd.DatetimeIndex(["2024-01-01"])) is True
