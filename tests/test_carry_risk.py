"""Pure risk-math for the carry monitor: maintenance margin, liquidation distance,
margin usage under a pump, and the funding-flip alert logic. Deliberately does NOT test
fetch_max_leverage/trailing_funding themselves -- those hit Hyperliquid's live API, and
this suite pins math, not network availability."""
import pytest

from tradefabe import carry_risk


def test_maintenance_margin_fraction_is_half_of_initial():
    # Hyperliquid's documented convention: maintenance = half of initial margin (1/leverage)
    assert carry_risk.maintenance_margin_fraction(40) == pytest.approx(1 / 80)
    assert carry_risk.maintenance_margin_fraction(25) == pytest.approx(1 / 50)
    assert carry_risk.maintenance_margin_fraction(10) == pytest.approx(0.05)


def test_liquidation_distance_matches_hand_derivation():
    # L=10x, mmr=5% (=1/(2*10)) -> 1/10 - 0.05 = 0.05 (a 5% pump liquidates)
    assert carry_risk.liquidation_distance(10, 0.05) == pytest.approx(0.05)
    # L=4x (10% of a 40x max), mmr=1/80=0.0125 -> 1/4 - 0.0125 = 0.2375
    lev = 40 * 0.10
    mmr = carry_risk.maintenance_margin_fraction(40)
    assert carry_risk.liquidation_distance(lev, mmr) == pytest.approx(0.2375)


def test_margin_usage_at_pump_scales_linearly_and_caps_at_one():
    dist = carry_risk.liquidation_distance(10, 0.05)   # 0.05, from above
    assert carry_risk.margin_usage_at_pump(0.025, 10, 0.05) == pytest.approx(0.5)
    assert carry_risk.margin_usage_at_pump(dist, 10, 0.05) == pytest.approx(1.0)
    # a pump well past the liquidation distance still caps at 1.0, not > 1.0
    assert carry_risk.margin_usage_at_pump(0.50, 10, 0.05) == pytest.approx(1.0)


def test_margin_usage_handles_non_positive_distance():
    # dist = 1/1 - 0.5 = 0.5 here -- a small pump uses a small fraction of it
    assert carry_risk.margin_usage_at_pump(0.01, 1, 0.5) == pytest.approx(0.02)
    # a degenerate leverage/mmr combo giving zero or negative liquidation room
    assert carry_risk.margin_usage_at_pump(0.01, 1, 1.5) == 1.0   # dist = 1 - 1.5 < 0 -> capped


def test_check_carry_risk_funding_flip_and_high_risk_logic(monkeypatch, tmp_path):
    """Isolate the orchestration logic from the network by monkeypatching the two
    live-data fetchers -- pins the alert/report-shape contract without touching
    Hyperliquid or the real state/paper/ directory."""
    def fake_trailing_funding(coin, days=carry_risk.FUNDING_ALERT_WINDOW_DAYS):
        return {"BTC": 0.004, "ETH": -0.002}[coin]

    def fake_max_leverage(coin):
        return {"BTC": 40.0, "ETH": 25.0}[coin]

    monkeypatch.setattr(carry_risk, "trailing_funding", fake_trailing_funding)
    monkeypatch.setattr(carry_risk, "fetch_max_leverage", fake_max_leverage)
    monkeypatch.setattr(carry_risk, "STATE_DIR", tmp_path)

    report = carry_risk.check_carry_risk()

    assert report["coins"]["BTC"]["funding_flip_alert"] is False
    assert report["coins"]["ETH"]["funding_flip_alert"] is True
    assert report["blended_funding_7d"] == pytest.approx((0.004 - 0.002) / 2)
    assert report["blended_funding_flip_alert"] is False   # blended is still positive

    # headline posture (25% of max) exists for both coins with the live-fetched leverage
    for coin, max_lev in (("BTC", 40.0), ("ETH", 25.0)):
        posture = report["coins"][coin]["postures"]["25%"]
        expected_lev = max_lev * 0.25
        expected_mmr = carry_risk.maintenance_margin_fraction(max_lev)
        assert posture["leverage"] == pytest.approx(expected_lev)
        assert posture["liq_distance"] == pytest.approx(
            carry_risk.liquidation_distance(expected_lev, expected_mmr))

    # persisted to the (monkeypatched, isolated) state dir
    assert (carry_risk.STATE_DIR / "carry_risk.json").exists()


def test_check_carry_risk_survives_total_network_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(carry_risk, "trailing_funding", lambda coin, days=7: None)
    monkeypatch.setattr(carry_risk, "fetch_max_leverage", lambda coin: None)
    monkeypatch.setattr(carry_risk, "STATE_DIR", tmp_path)

    report = carry_risk.check_carry_risk()   # must not raise

    assert report["blended_funding_7d"] is None
    assert report["blended_funding_flip_alert"] is False
    for coin in carry_risk.COINS:
        assert report["coins"][coin]["postures"] == {}
        assert report["high_risk_alert"][coin] is False
