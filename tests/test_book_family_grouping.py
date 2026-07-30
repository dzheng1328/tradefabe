"""Dashboard: Book Status grouped by family (#30) -- the pure grouping/filtering logic
behind render_book_status(), split out into group_books_by_family()/_is_monitor_only()
specifically so it's testable without a Streamlit runtime (both are plain pandas/dict
code, no st.* calls). Requires pyproject.toml's [tool.pytest.ini_options]
pythonpath=["."] so `import app` (a repo-root script) resolves under pytest."""
import json

import numpy as np
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


def _phist(rows):
    """rows: list of (book, date_str, equity). Parsed to real datetimes, matching
    load_paper_state()'s contract -- book_introduced_dates()/book_return_today()/
    sort_books_flat() all expect an already-parsed `date` column, not raw CSV strings."""
    df = pd.DataFrame(rows, columns=["book", "date", "equity"])
    # format="mixed": real history.csv mixes bare-date and full-timestamp rows (see
    # load_paper_state()'s own comment on this), and so do these fixtures on purpose.
    df["date"] = pd.to_datetime(df["date"], format="mixed")
    return df


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


def test_book_family_resolves_a_generated_name_via_the_ledger_fallback(monkeypatch):
    # #28b: a generated candidate's family can't have a static dict entry (the
    # parameter is drawn fresh each cycle) -- must resolve via generated_templates.csv.
    monkeypatch.setattr(app, "_load_generated_ledger",
                        lambda: {"tsmom_gen_147d": {"family": "A", "rationale": "..."}})
    assert app.book_family("tsmom_gen_147d") == "A"
    assert app.book_family("some_other_unmapped_name") == "?"   # ledger miss still falls through


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


# ---------------------------------------------------------------- sortable list (#141)
def test_book_introduced_dates_is_the_earliest_mark_per_book():
    phist = _phist([
        ("a", "2026-07-20", 100_000), ("a", "2026-07-22", 101_000),
        ("b", "2026-07-25", 100_000),
    ])
    dates = app.book_introduced_dates(phist)
    assert dates["a"] == pd.Timestamp("2026-07-20")
    assert dates["b"] == pd.Timestamp("2026-07-25")


def test_book_introduced_dates_empty_for_no_history():
    assert app.book_introduced_dates(pd.DataFrame(columns=["book", "date", "equity"])) == {}
    assert app.book_introduced_dates(None) == {}


def test_book_return_today_compares_to_the_previous_calendar_days_close():
    phist = _phist([
        ("a", "2026-07-28", 100_000),
        ("a", "2026-07-29T10:00", 100_500),
        ("a", "2026-07-29T15:00", 101_000),   # today's latest
    ])
    rt = app.book_return_today(phist)
    assert rt["a"] == pytest.approx(101_000 / 100_000 - 1)


def test_book_return_today_is_nan_for_a_book_with_only_one_calendar_day():
    # just opened today -- there IS no "previous close" yet.
    phist = _phist([("a", "2026-07-29T10:00", 100_000), ("a", "2026-07-29T15:00", 100_500)])
    rt = app.book_return_today(phist)
    assert np.isnan(rt["a"])


def test_book_return_today_empty_for_no_history():
    assert app.book_return_today(pd.DataFrame(columns=["book", "date", "equity"])) == {}
    assert app.book_return_today(None) == {}


def test_sort_books_flat_recent_orders_newest_first():
    psum = _psum(["a", "b", "c"])
    phist = _phist([("a", "2026-07-20", 100_000), ("b", "2026-07-25", 100_000),
                    ("c", "2026-07-22", 100_000)])
    rows = app.sort_books_flat(psum, phist, sort_key="recent")
    assert [r["book"] for r in rows] == ["b", "c", "a"]


def test_sort_books_flat_recent_puts_a_book_missing_from_phist_entirely_last():
    # no crash, no None-vs-Timestamp comparison error -- NaT sorts last.
    psum = _psum(["a", "never_marked"])
    phist = _phist([("a", "2026-07-20", 100_000)])
    rows = app.sort_books_flat(psum, phist, sort_key="recent")
    assert [r["book"] for r in rows] == ["a", "never_marked"]


def test_sort_books_flat_return_today_orders_highest_first_and_nan_last():
    psum = _psum(["a", "b", "c"])
    phist = _phist([
        ("a", "2026-07-28", 100_000), ("a", "2026-07-29", 100_500),   # +0.5%
        ("b", "2026-07-28", 100_000), ("b", "2026-07-29", 102_000),   # +2.0%
        ("c", "2026-07-29T10:00", 100_000), ("c", "2026-07-29T15:00", 100_100),  # NaN, 1 day only
    ])
    rows = app.sort_books_flat(psum, phist, sort_key="return_today")
    assert [r["book"] for r in rows] == ["b", "a", "c"]


def test_sort_books_flat_total_return_matches_psums_own_return_column():
    # _psum()'s return column is 0.01*i for names in input order -- c > b > a here.
    psum = _psum(["a", "b", "c"])
    rows = app.sort_books_flat(psum, phist=None, sort_key="total_return")
    assert [r["book"] for r in rows] == ["c", "b", "a"]


def test_sort_books_flat_respects_the_monitor_only_filter():
    names = ["tsmom_12m", "carry_btc_eth"]
    gy = _gy_last({"tsmom_12m": "DEAD"})
    rows = app.sort_books_flat(_psum(names), phist=None, gy_last=gy,
                               show_monitor_only=False, sort_key="total_return")
    assert [r["book"] for r in rows] == ["carry_btc_eth"]


# ---------------------------------------------------------------- accrual-only books (#143)
def test_accrual_only_books_names_the_three_funding_accrual_books():
    # a regression guard: these three update equity via a direct multiplicative funding
    # accrual (kronos_live.run_carry_kronos, hourly.run_funding_timing, carry_live.run_carry)
    # and never call books.rebalance_to()/log_trades(), so they can NEVER populate `trades`
    # -- the trade-log caption must special-case exactly this set, not a superset or subset.
    assert app.ACCRUAL_ONLY_BOOKS == {"carry_btc_eth", "carry_kronos_vol", "funding_timing_1h"}


def test_accrual_only_books_excludes_a_normal_rebalancing_book():
    # kronos_wick_agg DOES call books.rebalance_to() -- it just may have zero target
    # weights on a given day. It must keep the generic "no fills yet" caption, which is
    # still accurate for it (a fill may still show up next cycle).
    assert "kronos_wick_agg" not in app.ACCRUAL_ONLY_BOOKS


# ---------------------------------------------------------------- promotion cap / up for review (#147)
@pytest.fixture
def scratch_promotions(monkeypatch, tmp_path):
    """Points app.factory's promotion-registry paths at a scratch dir, same technique
    tests/test_factory_run.py's scratch_graveyard fixture uses -- so factory_owned_names()
    reads test data instead of the real (git-tracked) state/paper/ registries."""
    monkeypatch.setattr(app.factory, "PROMOTED_PATH", tmp_path / "promoted.json")
    monkeypatch.setattr(app.factory, "PROMOTED_GENERATED_PATH", tmp_path / "promoted_generated.json")
    monkeypatch.setattr(app.factory, "PROMOTED_COMBOS_PATH", tmp_path / "promoted_combos.json")
    (tmp_path / "promoted.json").write_text(json.dumps([]))
    (tmp_path / "promoted_generated.json").write_text(json.dumps([]))
    (tmp_path / "promoted_combos.json").write_text(json.dumps([]))
    return tmp_path


def test_factory_owned_names_unions_all_three_registries(scratch_promotions):
    (scratch_promotions / "promoted.json").write_text(json.dumps(["tsmom_3m"]))  # real TEMPLATES key
    (scratch_promotions / "promoted_generated.json").write_text(
        json.dumps([{"name": "turn_of_month_gen_5_5", "family": "C", "freq": "D", "params": {}}]))
    (scratch_promotions / "promoted_combos.json").write_text(
        json.dumps([{"name": "factory_combo_a_b", "freq": "D", "legs": []}]))
    assert app.factory_owned_names() == {"tsmom_3m", "turn_of_month_gen_5_5", "factory_combo_a_b"}


def test_factory_owned_names_empty_when_nothing_promoted(scratch_promotions):
    assert app.factory_owned_names() == set()


def _days_ago(n):
    return (pd.Timestamp.now() - pd.Timedelta(days=n)).strftime("%Y-%m-%d")


def test_books_up_for_review_surfaces_an_old_factory_owned_book(scratch_promotions):
    (scratch_promotions / "promoted.json").write_text(json.dumps(["tsmom_3m"]))
    # carry_btc_eth is hand-picked, not factory-owned -- must never appear here even
    # though it's just as old, since the factory never touches its accumulation.
    psum = _psum(["tsmom_3m", "carry_btc_eth"])
    phist = _phist([("tsmom_3m", _days_ago(90), 100_000), ("carry_btc_eth", _days_ago(90), 100_000)])

    rows = app.books_up_for_review(psum, phist)
    assert [r["book"] for r in rows] == ["tsmom_3m"]
    assert rows[0]["days_live"] >= 90


def test_books_up_for_review_excludes_a_book_under_the_age_threshold(scratch_promotions):
    (scratch_promotions / "promoted.json").write_text(json.dumps(["tsmom_3m"]))
    psum = _psum(["tsmom_3m"])
    phist = _phist([("tsmom_3m", _days_ago(5), 100_000)])
    assert app.books_up_for_review(psum, phist) == []


def test_books_up_for_review_excludes_an_already_retired_book(scratch_promotions):
    # #147 is explicitly not a retirement mechanism, but a book that's ALREADY been
    # retired by hand has already had its review -- listing it again would be noise.
    (scratch_promotions / "promoted.json").write_text(json.dumps(["tsmom_3m"]))
    psum = _psum(["tsmom_3m"])
    psum["retired_at"] = ["2026-07-01"]
    phist = _phist([("tsmom_3m", _days_ago(90), 100_000)])
    assert app.books_up_for_review(psum, phist) == []


def test_books_up_for_review_sorts_oldest_first(scratch_promotions):
    (scratch_promotions / "promoted.json").write_text(json.dumps(["tsmom_3m", "tsmom_6m"]))
    psum = _psum(["tsmom_3m", "tsmom_6m"])
    phist = _phist([("tsmom_3m", _days_ago(65), 100_000), ("tsmom_6m", _days_ago(120), 100_000)])
    rows = app.books_up_for_review(psum, phist)
    assert [r["book"] for r in rows] == ["tsmom_6m", "tsmom_3m"]
