"""book_panel_data()'s three-source backtest-curve resolution (#28b) -- regression
coverage for a real bug hit while building the strategy factory: a promoted book with
no entry in EITHER full_returns.csv or piggyback_returns.csv crashed with a KeyError
trying to look up a backtest curve that was never persisted anywhere for factory/
generated candidates. factory_returns.csv (loaded as `factory_bt`) is the fix."""
import numpy as np
import pandas as pd
import pytest

import tradefabe.dashboard as dashboard


def _phist(name, dates, equities):
    return pd.DataFrame({"book": [name] * len(dates), "date": dates, "equity": equities})


def _gy_last_row(name, verdict="DEAD"):
    return pd.DataFrame({"verdict": [verdict], "corr_bench": [0.1], "null_p95": [0.5],
                        "freq": ["D"]}, index=[name])


def _meta():
    return {"oos_start": "2018-01-01"}


def _returns_frame(name, n=40):
    idx = pd.bdate_range("2018-01-02", periods=n)
    rng = np.random.default_rng(0)
    return pd.DataFrame({name: rng.normal(0.0005, 0.01, n)}, index=idx)


def test_book_panel_data_uses_piggyback_source_when_present():
    name = "some_piggy"
    piggy = _returns_frame(name)
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
                               full, _meta(), _gy_last_row(name), None, None, piggy=piggy)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


def test_book_panel_data_uses_factory_bt_source_when_no_piggyback_entry():
    # the exact bug scenario: a promoted factory/generated book, absent from both
    # full_returns.csv and piggyback_returns.csv.
    name = "turn_of_month_gen_5_7"
    factory_bt = _returns_frame(name)
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    piggy = pd.DataFrame({"other_piggy": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 99_950, 99_900]),
                               full, _meta(), _gy_last_row(name), None, None,
                               piggy=piggy, factory_bt=factory_bt)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


def test_book_panel_data_falls_back_to_full_when_neither_piggy_nor_factory_bt_has_it():
    name = "tsmom_12m"
    full = _returns_frame(name)
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
                               full, _meta(), _gy_last_row(name), None, None,
                               piggy=None, factory_bt=None)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


def test_book_panel_data_raises_a_clear_keyerror_when_no_source_has_the_name():
    # documents the ORIGINAL crash mode (before factory_bt existed, this was the only
    # outcome for a promoted factory book) -- still correct behavior for a name that
    # genuinely isn't backed by any artifact.
    name = "nowhere_to_be_found"
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    with pytest.raises(KeyError):
        dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
                            full, _meta(), _gy_last_row(name), None, None)


def test_book_panel_data_uses_hourly_source_for_family_l():
    """The same bug, recurred (2026-07-26). Family L's hourly books (#86) became LIVE
    books whose curves live in a FOURTH artifact, hourly_returns.csv. The Research Lab
    lookup was extended and this one was not, so opening any of the three in Paper Books
    crashed the whole dashboard with a bare KeyError -- word for word the failure
    CLAUDE.md's Known-gaps entry describes."""
    name = "crypto_reversal_1h"
    hourly = _returns_frame(name)
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 99_950, 99_900]),
                               full, _meta(), _gy_last_row(name), None, None,
                               piggy=None, factory_bt=None, hourly_bt=hourly)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


def test_book_panel_data_uses_pipeline_bt_source_for_a_promoted_pipeline_candidate():
    """The same bug, a third time -- a promoted research-pipeline candidate (#180) has no
    entry in full/piggyback/factory/hourly/kronos_returns.csv either; pipeline_returns.csv
    is its own dedicated fifth (in this lookup) source, same only-promoted-gets-a-curve
    reasoning as factory_bt."""
    name = "rp_single_asset_trend_SPY_90"
    pipeline_bt = _returns_frame(name)
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_050, 100_100]),
                               full, _meta(), _gy_last_row(name), None, None,
                               piggy=None, factory_bt=None, hourly_bt=None, kronos_bt=None,
                               pipeline_bt=pipeline_bt)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


# ---------------------------------------------------------------- accrual-only deployment (#149)
# carry_kronos_vol/funding_timing_1h (ACCRUAL_ONLY_BOOKS, #143) never populate
# `positions`/`cash` -- their equity moves through kronos_live.run_carry_kronos()'s /
# hourly.run_funding_timing()'s direct multiplicative accrual instead. Computing
# "deployment" as cash+positions for them silently shows the frozen $100k starting cash
# forever, never the real accrued equity -- this is the regression guard for that fix.
def test_book_panel_data_skips_broken_deployment_math_for_an_accrual_only_book(monkeypatch):
    name = "carry_kronos_vol"
    fake_book = {"name": name, "cash": 100_000.0, "positions": {}, "equity": 100_009.43}
    monkeypatch.setattr(dashboard, "load_book_json", lambda n: fake_book)

    # family M's window is the model's pretraining cutoff (KRONOS_OOS_START), not
    # meta["oos_start"] -- dates before it slice to an empty bt_curve.
    rng = np.random.default_rng(0)
    kronos_idx = pd.bdate_range("2025-06-05", periods=40)
    kronos_bt = pd.DataFrame({name: rng.normal(0.0005, 0.01, len(kronos_idx))}, index=kronos_idx)
    full = pd.DataFrame({"unrelated": [0.0] * 5}, index=pd.bdate_range("2018-01-02", periods=5))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_005, 100_009.43]),
                               full, _meta(), _gy_last_row(name), None, None,
                               kronos_bt=kronos_bt)

    assert data["kind"] == "equity"          # still equity-kind for verdict/backtest sourcing
    assert data["deployment"] is None         # NOT {"cash": 100_000, "equity": 100_000, ...}
    assert data["positions_df"] is None


def test_book_panel_data_still_computes_deployment_for_a_normal_equity_book(monkeypatch):
    # regression guard the other direction: a book that DOES hold real positions must
    # keep the cash+positions math, not get swept into the accrual-only carve-out.
    name = "tsmom_12m"
    fake_book = {"name": name, "cash": 40_000.0,
                 "positions": {"SPY": 100.0}, "last_prices": {"SPY": 600.0}}
    monkeypatch.setattr(dashboard, "load_book_json", lambda n: fake_book)

    full = _returns_frame(name)
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_200]),
                               full, _meta(), _gy_last_row(name), None, None)

    assert data["deployment"] is not None
    assert data["deployment"]["cash"] == 40_000.0
    assert data["deployment"]["equity"] == 40_000.0 + 100.0 * 600.0
    assert data["positions_df"] is not None and len(data["positions_df"]) == 1


def test_book_panel_data_skips_positions_when_compute_positions_is_false():
    name = "some_book"
    full = pd.DataFrame({name: [0.001] * 40}, index=pd.bdate_range("2018-01-02", periods=40))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(
        name, _phist(name, dates, [100_000, 100_100, 100_050]),
        full, _meta(), _gy_last_row(name, verdict="ALIVE"), None, None,
        compute_positions=False,
    )
    assert data["positions_df"] is None
    assert data["deployment"] is None
    # everything else 2a actually needs is still populated
    assert data["stats"] is not None
    assert data["live_hist"] is not None


def test_book_panel_data_still_computes_positions_by_default():
    name = "some_book"
    full = pd.DataFrame({name: [0.001] * 40}, index=pd.bdate_range("2018-01-02", periods=40))
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = dashboard.book_panel_data(
        name, _phist(name, dates, [100_000, 100_100, 100_050]),
        full, _meta(), _gy_last_row(name, verdict="ALIVE"), None, None,
    )
    # book_json has no positions in this fixture, but the deployment dict itself
    # must still be built (not None) -- that's the default-True contract.
    assert data["deployment"] is not None


@pytest.mark.parametrize("name", ["crypto_reversal_1h", "equity_tsmom_1h", "funding_timing_1h"])
def test_every_live_book_on_disk_resolves_a_curve(name):
    """End-to-end guard: every book that actually exists in state/paper must resolve a
    backtest curve from the real artifacts, not just from a fixture. This is the check
    that would have caught the crash before it shipped."""
    import os
    from tradefabe.paths import STATE_DIR
    if not (STATE_DIR / f"{name}.json").exists():
        pytest.skip(f"{name} not opened in this checkout")
    # These loaders moved to dashboard.py undecorated (2a Task 1, same precedent as
    # load_carry_backtest in sub-project 1) -- no more @st.cache_data wrapper to unwrap.
    hourly = dashboard.load_hourly_backtest()
    piggy = dashboard.load_piggyback_backtest()
    factory_bt = dashboard.load_factory_backtest()
    full = pd.read_csv(os.path.join(dashboard.ART, "full_returns.csv"), index_col=0, parse_dates=True)
    sources = [d for d in (piggy, factory_bt, hourly) if d is not None]
    assert any(name in d.columns for d in sources) or name in full.columns, \
        f"{name} is a live book with no persisted backtest curve in ANY source"


def test_the_call_site_supplies_every_source_book_panel_data_accepts():
    """The crash had TWO halves: book_panel_data() didn't accept the hourly source, AND
    its caller didn't pass it. A test that only exercises the function would have gone
    green while the dashboard still died on the missing argument.

    So assert the structural invariant directly: the live call site (api/main.py's
    book_detail, the desktop-cutover-era replacement for app.py's render_paper_books)
    must supply EVERY parameter book_panel_data declares. Adding a fifth curve source
    then fails here until the call site is updated too.

    compute_positions (2a Task 1) is exempt: it's a behavior flag, not a curve source,
    and its whole contract is a default that preserves every existing caller's behavior
    with zero changes -- the opposite of what this invariant guards against."""
    import ast, inspect
    from tradefabe.api.main import book_detail

    params = inspect.signature(dashboard.book_panel_data).parameters
    n_params = len([p for p in params if p != "compute_positions"])
    tree = ast.parse(inspect.getsource(book_detail).lstrip())
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", None)) == "book_panel_data"]
    assert calls, "book_detail no longer calls book_panel_data -- update this test"
    for c in calls:
        supplied = len(c.args) + len([kw for kw in c.keywords if kw.arg != "compute_positions"])
        assert supplied == n_params, (
            f"book_panel_data accepts {n_params} params but the Paper Books call site "
            f"supplies {supplied}; a live book from the unpassed source crashes the "
            f"dashboard with a bare KeyError")
