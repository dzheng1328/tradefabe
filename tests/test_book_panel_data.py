"""book_panel_data()'s three-source backtest-curve resolution (#28b) -- regression
coverage for a real bug hit while building the strategy factory: a promoted book with
no entry in EITHER full_returns.csv or piggyback_returns.csv crashed with a KeyError
trying to look up a backtest curve that was never persisted anywhere for factory/
generated candidates. factory_returns.csv (loaded as `factory_bt`) is the fix. Requires
pyproject.toml's [tool.pytest.ini_options] pythonpath=["."] so `import app` resolves."""
import numpy as np
import pandas as pd
import pytest

import app


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
    data = app.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
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
    data = app.book_panel_data(name, _phist(name, dates, [100_000, 99_950, 99_900]),
                               full, _meta(), _gy_last_row(name), None, None,
                               piggy=piggy, factory_bt=factory_bt)
    assert data["kind"] == "equity"
    assert len(data["bt_curve"]) > 0


def test_book_panel_data_falls_back_to_full_when_neither_piggy_nor_factory_bt_has_it():
    name = "tsmom_12m"
    full = _returns_frame(name)
    dates = pd.bdate_range("2026-01-01", periods=3)
    data = app.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
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
        app.book_panel_data(name, _phist(name, dates, [100_000, 100_100, 100_050]),
                            full, _meta(), _gy_last_row(name), None, None)
