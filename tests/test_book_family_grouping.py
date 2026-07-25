"""Dashboard: Book Status grouped by family (#30) -- the pure grouping/filtering logic
behind render_book_status(), split out into group_books_by_family()/_is_monitor_only()
specifically so it's testable without a Streamlit runtime (both are plain pandas/dict
code, no st.* calls). Requires pyproject.toml's [tool.pytest.ini_options]
pythonpath=["."] so `import app` (a repo-root script) resolves under pytest."""
import pandas as pd
import pytest

import app


def _psum(names):
    return pd.DataFrame({
        "book": names,
        "equity": [100_000.0 + i for i in range(len(names))],
        "return": [0.01 * i for i in range(len(names))],
        "last_run": ["2026-07-24"] * len(names),
    })


def _gy_last(verdicts):
    """verdicts: dict of strategy -> 'ALIVE'/'DEAD', shaped like app.py's gy_last
    (drop_duplicates('strategy').set_index('strategy'))."""
    return pd.DataFrame({"verdict": list(verdicts.values())}, index=list(verdicts.keys()))


def test_book_family_resolves_known_names_from_the_static_dict():
    assert app.book_family("tsmom_12m") == "A"
    assert app.book_family("carry_btc_eth") == "E"


def test_book_family_resolves_any_factory_combo_name_via_pattern_fallback():
    # combo names vary run to run (whichever pair factory_run.py picked that cycle) --
    # a static dict entry can never cover them all, so this must be pattern-based.
    assert app.book_family("factory_combo_tsmom_3m_donchian_55d") == "H"
    assert app.book_family("factory_combo_anything_at_all") == "H"


def test_book_family_falls_back_to_unmapped_marker_for_anything_else():
    assert app.book_family("some_totally_new_strategy") == "?"


def test_is_monitor_only_true_for_a_dead_verdict():
    gy = _gy_last({"tsmom_12m": "DEAD"})
    assert app._is_monitor_only("tsmom_12m", gy) is True


def test_is_monitor_only_false_for_an_alive_verdict():
    gy = _gy_last({"some_winner": "ALIVE"})
    assert app._is_monitor_only("some_winner", gy) is False


def test_is_monitor_only_false_when_no_graveyard_row_at_all():
    # carry_btc_eth's real situation -- never run through the bare-strategy gate,
    # so it must NOT be flagged monitor-only just for being absent from the ledger.
    gy = _gy_last({"tsmom_12m": "DEAD"})
    assert app._is_monitor_only("carry_btc_eth", gy) is False


def test_is_monitor_only_false_when_gy_last_is_none():
    assert app._is_monitor_only("anything", None) is False


def test_grouping_matches_current_live_roster_families():
    names = ["tsmom_12m", "tsmom_ensemble", "green_line_200d", "turn_of_month",
             "piggyback_2a", "piggyback_3", "piggyback_4", "carry_btc_eth"]
    groups = app.group_books_by_family(_psum(names))
    got = {label: sorted(r["book"] for r in rows) for _, label, rows in groups}
    assert got == {
        "Trend / momentum": ["green_line_200d", "tsmom_12m", "tsmom_ensemble"],
        "Calendar / seasonality": ["turn_of_month"],
        "Carry / structural": ["carry_btc_eth"],
        "Piggyback / combined": ["piggyback_2a", "piggyback_3", "piggyback_4"],
    }


def test_grouping_preserves_family_letter_order_not_input_order():
    # input order is H, A, C, E -- output should come back A, C, E, H (BOOK_FAMILIES order)
    names = ["piggyback_2a", "tsmom_12m", "turn_of_month", "carry_btc_eth"]
    groups = app.group_books_by_family(_psum(names))
    labels_in_order = [label for _, label, _ in groups]
    assert labels_in_order == ["Trend / momentum", "Calendar / seasonality",
                               "Carry / structural", "Piggyback / combined"]


def test_grouping_puts_unmapped_books_in_an_other_group_last():
    names = ["tsmom_12m", "some_brand_new_factory_strategy"]
    groups = app.group_books_by_family(_psum(names))
    assert [label for _, label, _ in groups] == ["Trend / momentum", "Other"]
    other_rows = groups[-1][2]
    assert [r["book"] for r in other_rows] == ["some_brand_new_factory_strategy"]


def test_grouping_omits_empty_families():
    groups = app.group_books_by_family(_psum(["carry_btc_eth"]))
    assert len(groups) == 1
    assert groups[0][1] == "Carry / structural"


def test_show_monitor_only_false_filters_out_dead_books():
    names = ["tsmom_12m", "carry_btc_eth"]
    gy = _gy_last({"tsmom_12m": "DEAD"})
    groups = app.group_books_by_family(_psum(names), gy, show_monitor_only=False)
    all_books = [r["book"] for _, _, rows in groups for r in rows]
    assert all_books == ["carry_btc_eth"]     # tsmom_12m (monitor-only DEAD) filtered out


def test_show_monitor_only_true_keeps_everything_default_behavior():
    names = ["tsmom_12m", "carry_btc_eth"]
    gy = _gy_last({"tsmom_12m": "DEAD"})
    groups = app.group_books_by_family(_psum(names), gy, show_monitor_only=True)
    all_books = sorted(r["book"] for _, _, rows in groups for r in rows)
    assert all_books == ["carry_btc_eth", "tsmom_12m"]


def test_grouping_with_no_gy_last_never_filters():
    # gy_last=None (e.g. the backtest_ok=False fallback path) -- can't compute
    # monitor-only, so nothing is ever hidden regardless of show_monitor_only.
    names = ["tsmom_12m", "carry_btc_eth"]
    groups = app.group_books_by_family(_psum(names), gy_last=None, show_monitor_only=False)
    all_books = sorted(r["book"] for _, _, rows in groups for r in rows)
    assert all_books == ["carry_btc_eth", "tsmom_12m"]
