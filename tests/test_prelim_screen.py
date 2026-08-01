"""harness.prelim_screen() (#175): the calibration-only prelim firewall for the daily
automated research pipeline (#174). Three properties matter more than any single verdict:
the screen can never see anything dated after CALIB_END, it can never write
graveyard.csv, and it can never move family_n_tested()'s count -- an idea that fails here
must be indistinguishable, after the fact, from one that was never proposed."""
import os

import numpy as np
import pandas as pd
import pytest

import harness


def _prices(n=3600, seed=1, oos_regime="flat"):
    """A + B from 2007-01-01 through well past CALIB_END (2017-12-31). A trends up
    strongly and cleanly through the calibration window; B stays flat throughout
    calibration. `oos_regime` controls what A does AFTER CALIB_END -- "flat" (unchanged
    drift) vs. "crash" (a sharp reversal) -- used only by the calibration-blindness test
    to prove the choice never reaches prelim_screen()'s decision."""
    idx = pd.bdate_range(harness.CALIB_START, periods=n)
    calib_mask = idx <= harness.CALIB_END
    n_calib = int(calib_mask.sum())
    rng = np.random.default_rng(seed)

    a_calib = np.cumsum(rng.normal(0.0012, 0.004, n_calib))
    if oos_regime == "crash":
        a_oos = a_calib[-1] + np.cumsum(rng.normal(-0.02, 0.01, n - n_calib))
    else:
        a_oos = a_calib[-1] + np.cumsum(rng.normal(0.0012, 0.004, n - n_calib))
    log_a = np.concatenate([a_calib, a_oos])
    log_b = np.cumsum(rng.normal(0.0, 0.003, n))

    return pd.DataFrame({"A": 100 * np.exp(log_a), "B": 100 * np.exp(log_b)}, index=idx)


def _long_a_short_b(prices):
    return pd.DataFrame({"A": 1.0, "B": -1.0}, index=prices.index)


def _short_a_long_b(prices):
    return pd.DataFrame({"A": -1.0, "B": 1.0}, index=prices.index)


@pytest.fixture
def scratch_prelim(monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "GRAVEYARD", str(tmp_path / "graveyard.csv"))
    monkeypatch.setattr(harness, "PRELIM_LOG", str(tmp_path / "prelim_log.csv"))
    monkeypatch.setattr(harness, "GENERATED_LEDGER", str(tmp_path / "generated_templates.csv"))
    return tmp_path


def test_a_clear_calibration_winner_passes(scratch_prelim, monkeypatch):
    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(), "SYNTHETIC (test)"))
    passed = harness.prelim_screen({"name": "winner", "sig_fn": _long_a_short_b, "freq": "D"})
    assert passed is True


def test_a_clear_calibration_loser_fails(scratch_prelim, monkeypatch):
    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(), "SYNTHETIC (test)"))
    passed = harness.prelim_screen({"name": "loser", "sig_fn": _short_a_long_b, "freq": "D"})
    assert passed is False


# ---------------------------------------------------------------- calibration blindness
def test_verdict_is_unchanged_by_what_happens_after_calib_end(scratch_prelim, monkeypatch):
    """The core safety property (#175): two price histories, IDENTICAL through
    CALIB_END, that diverge wildly afterwards (A keeps trending vs. A crashes) must
    produce the EXACT SAME prelim verdict and the EXACT SAME logged calibration Sharpe --
    proving the OOS portion was never read, not merely that it didn't happen to matter."""
    spec = {"name": "winner", "sig_fn": _long_a_short_b, "freq": "D"}

    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(oos_regime="flat"), "SYNTHETIC (test)"))
    passed_flat = harness.prelim_screen(spec)
    log_flat = pd.read_csv(scratch_prelim / "prelim_log.csv").iloc[-1]

    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(oos_regime="crash"), "SYNTHETIC (test)"))
    passed_crash = harness.prelim_screen(spec)
    log_crash = pd.read_csv(scratch_prelim / "prelim_log.csv").iloc[-1]

    assert passed_flat == passed_crash is True
    assert log_flat["calib_sharpe"] == pytest.approx(log_crash["calib_sharpe"])
    assert log_flat["calib_null_p50"] == pytest.approx(log_crash["calib_null_p50"])


def test_calib_slice_drops_every_row_after_calib_end():
    prices = _prices()
    sliced = harness._calib_slice(prices)
    assert sliced.index.max() <= harness.CALIB_END
    assert sliced.index.min() >= harness.CALIB_START
    assert len(sliced) < len(prices)   # confirms the OOS tail actually existed to drop


# ---------------------------------------------------------------- firewall properties
def test_prelim_screen_never_writes_graveyard(scratch_prelim, monkeypatch):
    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(), "SYNTHETIC (test)"))
    harness.prelim_screen({"name": "winner", "sig_fn": _long_a_short_b, "freq": "D"})
    harness.prelim_screen({"name": "loser", "sig_fn": _short_a_long_b, "freq": "D"})
    assert not os.path.exists(harness.GRAVEYARD)


def test_prelim_screen_does_not_move_family_n_tested(scratch_prelim, monkeypatch):
    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(), "SYNTHETIC (test)"))
    before = harness.family_n_tested(["some_hand_picked_candidate"])
    harness.prelim_screen({"name": "winner", "sig_fn": _long_a_short_b, "freq": "D"})
    harness.prelim_screen({"name": "loser", "sig_fn": _short_a_long_b, "freq": "D"})
    after = harness.family_n_tested(["some_hand_picked_candidate"])
    assert before == after


def test_prelim_screen_logs_every_call_pass_or_fail(scratch_prelim, monkeypatch):
    monkeypatch.setattr(harness, "load_prices", lambda: (_prices(), "SYNTHETIC (test)"))
    harness.prelim_screen({"name": "winner", "sig_fn": _long_a_short_b, "freq": "D"})
    harness.prelim_screen({"name": "loser", "sig_fn": _short_a_long_b, "freq": "D"})

    log = pd.read_csv(scratch_prelim / "prelim_log.csv")
    assert list(log["strategy"]) == ["winner", "loser"]
    assert list(log["passed"]) == [True, False]
    assert log["calib_sharpe"].notna().all()
    assert log["calib_null_p50"].notna().all()
