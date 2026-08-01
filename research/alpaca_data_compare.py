"""
alpaca_data_compare.py — issue #135: does Alpaca's hourly market data beat yfinance's
for family L's backtest specifically?

`research/hourly_backtest.py`'s `fetch_bars()` is bottlenecked by yfinance's rolling
730-day intraday window -- its own docstring names the accepted REGIME LIMITATION this
causes: no hourly source it can reach today spans 2018's vol spike, COVID, or the 2022
bear. Alpaca's hourly bars go back further on this account -- confirmed empirically here
(again, reproducing the finding that scoped this issue): ~2016 for equities, ~2021 for
crypto. Alpaca's DAILY bars only start ~2016 too, too shallow for the 2007-2017 core
calibration window, so this is scoped to family L's HOURLY backtest specifically, not a
wholesale data-source swap (see the issue for the full reasoning).

**Scope: read-only measurement.** Does not touch `research/hourly_backtest.py`'s
`fetch_bars()`, the live path (`src/tradefabe/pricing.py`/`hourly.py`), or
`graveyard.csv`. Two things measured:

  1. AGREEMENT over the OVERLAPPING window (both sources have data) -- row counts,
     close-price deltas, gap counts. A genuine data-quality check, not just "more rows":
     if Alpaca disagrees with yfinance on price by more than a few bps, more history
     alone doesn't make it the better source.
  2. ALPACA'S EXTRA DEPTH -- how far its hourly bars reach beyond yfinance's rolling
     730-day window (read from the already-snapshotted `artifacts/hourly_bars_*.csv`,
     the SAME cache the real backtest consumes -- not a fresh yfinance pull), and
     whether that depth actually covers the three regimes family L is missing: 2018's
     vol spike, COVID (Mar 2020), and the 2022 bear.

**Decision checkpoint, not automatic (#135).** This script only measures and reports.
Swapping `fetch_bars()` to Alpaca, or re-running family L's doctrine evaluation on a
materially different backtest window, produces new `graveyard.csv` rows on a different
input and needs its own pre-registration (a STRATEGIES.md/DOCTRINE.md note) first --
same discipline as every prior doctrine amendment, not a side effect of running this.

**Decision made 2026-07-31 (#156): yes, for `equity_tsmom_1h` only** -- pre-registered
in STRATEGIES.md's family L section before `hourly_backtest.py`'s equity leg was
actually swapped. This script itself still only measures; the swap lives in
`hourly_backtest.py`, and `fetch_alpaca_bars` moved to `alpaca_fetch.py` so both files
can share it.

Run: PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" .venv/bin/python research/alpaca_data_compare.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

from tradefabe.engine import UNIVERSE
from tradefabe.hourly import CRYPTO_TICKERS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hourly_backtest import fetch_bars as yf_fetch_bars  # noqa: E402
# fetch_alpaca_bars/ALPACA_START moved to alpaca_fetch.py (#156) so hourly_backtest.py's
# equity-leg swap can import the same function without a circular import (hourly_backtest
# already gets imported BY this file, above).
from alpaca_fetch import fetch_alpaca_bars, ALPACA_START  # noqa: E402

# The three regimes family L's own docstring names as missing from every hourly source
# reachable today -- the actual question this script exists to answer.
REGIME_MARKERS = {
    "2018 vol spike": dt.datetime(2018, 2, 1),
    "COVID crash": dt.datetime(2020, 3, 1),
    "2022 bear market": dt.datetime(2022, 1, 1),
}

BAR_ALIGN_TOLERANCE = pd.Timedelta(minutes=35)


def compare_overlap(yf_px: pd.DataFrame, al_px: pd.DataFrame) -> pd.DataFrame:
    """Row counts, close-price agreement, and coverage over the window BOTH sources
    have data for -- per ticker. Matched via merge_asof (nearest, within
    BAR_ALIGN_TOLERANCE), NOT an exact-timestamp join: equity bars from the two
    sources are offset by exactly 30 minutes (yfinance aligns to the market open,
    e.g. 14:30/15:30; Alpaca aligns to the wall-clock hour, e.g. 14:00/15:00), so an
    exact join found ZERO overlapping rows despite both sources covering the same
    calendar period -- a real bar-alignment difference between the two sources,
    reported here rather than silently worked around by discarding the finding."""
    rows = []
    common = [t for t in yf_px.columns if t in al_px.columns]
    for t in common:
        y = yf_px[t].dropna().rename("yf").sort_index()
        a = al_px[t].dropna().rename("alpaca").sort_index()
        joined = pd.merge_asof(y.to_frame(), a.to_frame(), left_index=True,
                               right_index=True, direction="nearest",
                               tolerance=BAR_ALIGN_TOLERANCE).dropna()
        if joined.empty:
            rows.append({"ticker": t, "yf_rows": len(y), "alpaca_rows": len(a),
                        "overlap_rows": 0, "mean_abs_pct_delta": np.nan,
                        "max_abs_pct_delta": np.nan})
            continue
        pct_delta = (joined["alpaca"] - joined["yf"]).abs() / joined["yf"]
        rows.append({
            "ticker": t, "yf_rows": len(y), "alpaca_rows": len(a),
            "overlap_rows": len(joined),
            "mean_abs_pct_delta": float(pct_delta.mean()),
            "max_abs_pct_delta": float(pct_delta.max()),
        })
    return pd.DataFrame(rows)


def report_extra_depth(al_px: pd.DataFrame, yf_px: pd.DataFrame, tag: str) -> None:
    if al_px.empty or yf_px.empty:
        print(f"[{tag}] no data to compare depth (one source returned nothing)")
        return
    al_start, yf_start = al_px.index.min(), yf_px.index.min()
    extra_days = (yf_start - al_start).days
    print(f"\n[{tag}] Alpaca starts {al_start.date()}, yfinance (the cached backtest "
          f"input) starts {yf_start.date()} -- Alpaca reaches {extra_days} more day(s) "
          "back." if extra_days > 0 else
          f"\n[{tag}] Alpaca starts {al_start.date()}, no earlier than yfinance's "
          f"{yf_start.date()} -- no extra depth here.")
    for label, marker in REGIME_MARKERS.items():
        note = "COVERS" if al_start <= marker else "does NOT cover"
        print(f"    {label} ({marker.date()}): Alpaca {note} it")


def main():
    print("=== Alpaca vs yfinance hourly data comparison (#135) ===")
    print("Read-only measurement -- no fetch_bars()/graveyard.csv change made.\n")

    for tag, tickers in [("equity", UNIVERSE), ("crypto", CRYPTO_TICKERS)]:
        print(f"--- {tag} ({len(tickers)} tickers) ---")
        yf_px = yf_fetch_bars(tickers, tag)
        al_px = fetch_alpaca_bars(tickers, tag, ALPACA_START[tag])

        agree = compare_overlap(yf_px, al_px)
        print(f"\n[{tag}] agreement over the overlapping window:")
        with pd.option_context("display.float_format", "{:.5f}".format):
            print(agree.to_string(index=False))

        report_extra_depth(al_px, yf_px, tag)
        print()

    print("=== done -- findings above, no code or graveyard.csv changed ===")


if __name__ == "__main__":
    main()
