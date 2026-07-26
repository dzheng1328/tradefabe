"""Risk register (#10): measured stats and entry integrity.

The point of the register is that no number is invented, so the structural tests here
matter as much as the math: every cited entry must carry a source, and the measured
entries must actually be derived from data."""
import numpy as np
import pandas as pd
import pytest

from tradefabe import risk_register as rr


def _curve(daily_returns):
    """Equity curve whose pct_change() recovers exactly `daily_returns` — note the
    leading 1.0, without which the first return is swallowed by cumprod."""
    idx = pd.date_range("2023-05-11", periods=len(daily_returns) + 1, freq="D")
    return pd.Series(np.cumprod([1.0] + [1 + r for r in daily_returns]), index=idx)


def test_every_cited_entry_has_a_real_source_and_url():
    for r in rr.CITED:
        assert r["source"], f"{r['key']} has no source"
        assert r["url"] and r["url"].startswith("http"), f"{r['key']} has no URL"
        assert not r["measured"], f"{r['key']} is cited, must not claim measured"


def test_every_entry_has_a_known_severity():
    for r in rr.build():
        assert r["category"] in rr.SEVERITY, f"{r['key']} has unknown severity"


def test_negative_day_fraction_and_longest_run_are_measured_correctly():
    # 3 up, 4 consecutive down, 3 up -> 40% negative, longest run 4
    rets = [0.001] * 3 + [-0.001] * 4 + [0.001] * 3
    m = rr.measured_funding_risk(_curve(rets))
    assert m["pct_days_negative"] == pytest.approx(4 / 10, abs=1e-9)
    assert m["longest_negative_run"] == 4
    assert m["worst_day"] == pytest.approx(-0.001, rel=1e-6)


def test_longest_run_takes_the_max_not_the_last_run():
    # runs of 2 then 5 -- a bug that returns the final run would report 2
    rets = [-0.001] * 2 + [0.001] * 3 + [-0.001] * 5 + [0.001] * 2
    assert rr.measured_funding_risk(_curve(rets))["longest_negative_run"] == 5


def test_max_drawdown_is_negative_for_a_curve_that_falls():
    m = rr.measured_funding_risk(_curve([0.01] * 10 + [-0.02] * 5))
    assert m["max_drawdown"] < 0


def test_build_omits_the_funding_entry_when_there_is_no_curve():
    keys = {r["key"] for r in rr.build(None)}
    assert "negative_funding" not in keys
    assert "venue_failure" in keys and "operational" in keys


def test_build_includes_the_funding_entry_when_a_curve_is_supplied():
    rng = np.random.default_rng(0)
    curve = _curve(rng.normal(0.0003, 0.0005, 400))
    entry = next(r for r in rr.build(curve) if r["key"] == "negative_funding")
    assert entry["measured"] is True
    assert "%" in entry["likelihood"]


def test_liquidation_risk_reads_the_requested_posture():
    rj = {"coins": {"BTC": {"postures": {"25%": {"leverage": 10.0, "liq_distance": 0.0875}}}}}
    out = rr.measured_liquidation_risk(rj, "25%")
    assert out["BTC"]["liq_distance"] == pytest.approx(0.0875)


def test_liquidation_risk_is_none_when_the_monitor_has_no_report():
    assert rr.measured_liquidation_risk(None) is None
    assert rr.measured_liquidation_risk({}) is None
    assert rr.measured_liquidation_risk({"coins": {"BTC": {"postures": {}}}}) is None
