"""ONE-TIME repair for #235/#236 (run 2026-08-26). Before #236's fix, books.backfill_marks()
fabricated up to ~45 days of flat-$100k history for every freshly-promoted book, because its
"never backfill before the book existed" guard did nothing when a book's history was empty
-- see #235's writeup. This strips those fabricated pre-promotion rows from each affected
book's own state/paper/{name}.json, then regenerates summary.csv/history.csv from the
corrected books via runner.write_summary() -- the same function every normal cycle already
uses, so this produces byte-identical formatting rather than hand-rolled CSV/JSON writing.

CUTOFFS were derived from git history, not a heuristic: each is the timestamp of the commit
that actually first added that name to its promotion registry (state/paper/
promoted_pipeline.json or promoted_combos.json/promoted_generated.json), e.g.:

    git log --format="%ad" --date=iso-strict -S '"factory_combo_donchian_gen_93d_turn_of_month_gen_3_1"' \
        -- state/paper/promoted_combos.json | tail -1

Every factory-combo cutoff below landed on a "paper engine: factory" daily commit, one day
apart -- consistent with the factory's documented one-promotion-per-cycle behavior, and
strong confirmation this is the real promotion moment, not a guess.

Run once via `gh workflow run "paper engine" -f job=repair_history` so the Action itself
commits the fix -- state/ is Action-owned (CLAUDE.md); a local commit here would be a
second writer. Idempotent: rerunning finds nothing left below any cutoff to strip.
"""
from tradefabe import books, runner

CUTOFFS = {
    "rp_asset_class_trend_hedge_SPY_IEF_252_63": "2026-08-08T04:37:02",
    "rp_asset_class_trend_hedge_QQQ_GLD_90_60": "2026-08-24T15:22:04",
    "turn_of_month_gen_7_3": "2026-07-30T05:28:08",
    "factory_combo_donchian_gen_93d_turn_of_month_gen_3_1": "2026-08-01T22:03:25",
    "factory_combo_donchian_gen_109d_turn_of_month_gen_1_2": "2026-08-02T22:03:14",
    "factory_combo_str_reversal_gen_36d_turn_of_month_gen_5_8": "2026-08-03T22:14:50",
    "factory_combo_str_reversal_gen_25d_low_vol_xsec_gen_112d": "2026-08-04T22:20:06",
    "factory_combo_donchian_gen_115d_turn_of_month_gen_1_4": "2026-08-05T22:18:04",
    "factory_combo_turn_of_month_gen_2_4_donchian_gen_94d": "2026-08-07T01:02:42",
    "factory_combo_donchian_gen_28d_tsmom_gen_120d": "2026-08-07T21:49:40",
    "factory_combo_tsmom_gen_69d_low_vol_xsec_gen_79d": "2026-08-08T21:39:15",
    "factory_combo_turn_of_month_gen_4_3_donchian_gen_107d": "2026-08-09T21:41:10",
    "factory_combo_low_vol_xsec_gen_126d_tsmom_gen_43d": "2026-08-10T21:52:15",
    "factory_combo_donchian_gen_45d_tsmom_gen_164d": "2026-08-11T21:57:58",
    "factory_combo_tsmom_gen_86d_low_vol_xsec_gen_53d": "2026-08-12T21:56:29",
    "factory_combo_tsmom_gen_108d_donchian_gen_18d": "2026-08-13T21:56:12",
    "factory_combo_tsmom_gen_70d_low_vol_xsec_gen_100d": "2026-08-14T21:33:39",
    "factory_combo_low_vol_xsec_gen_56d_tsmom_gen_87d": "2026-08-15T21:29:38",
    "factory_combo_tsmom_gen_140d_donchian_gen_99d": "2026-08-16T21:28:45",
    "factory_combo_tsmom_gen_137d_donchian_gen_106d": "2026-08-17T21:33:42",
    "factory_combo_tsmom_gen_67d_low_vol_xsec_gen_28d": "2026-08-18T21:31:51",
    "factory_combo_low_vol_xsec_gen_60d_tsmom_gen_85d": "2026-08-19T21:33:45",
    "factory_combo_tsmom_gen_92d_low_vol_xsec_gen_27d": "2026-08-20T21:36:42",
    "factory_combo_tsmom_gen_51d_low_vol_xsec_gen_121d": "2026-08-21T21:32:39",
    "factory_combo_low_vol_xsec_gen_113d_tsmom_gen_30d": "2026-08-22T21:29:42",
    "factory_combo_low_vol_xsec_gen_71d_tsmom_gen_55d": "2026-08-23T21:29:16",
    "factory_combo_tsmom_gen_347d_tsmom_gen_22d": "2026-08-24T21:37:33",
    "factory_combo_tsmom_gen_26d_tsmom_gen_237d": "2026-08-25T21:37:11",
}


def strip_fabricated_rows(book: dict, cutoff: str) -> int:
    """Drop every history row dated before cutoff. Returns how many were removed. Pure
    function of (book, cutoff) so the repair logic is testable without touching disk."""
    before = len(book["history"])
    book["history"] = [row for row in book["history"] if row[0] >= cutoff]
    return before - len(book["history"])


def repair() -> None:
    for name, cutoff in CUTOFFS.items():
        book = books.load(name)
        removed = strip_fabricated_rows(book, cutoff)
        if removed:
            books.save(book)
        print(f"{name}: removed {removed} fabricated rows (kept {len(book['history'])})")

    last_px = runner._prices().iloc[-1]
    runner.write_summary(last_px)
    print("summary.csv / history.csv regenerated from corrected books")


if __name__ == "__main__":
    repair()
