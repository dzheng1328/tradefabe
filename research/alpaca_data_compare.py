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

Run: PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" .venv/bin/python research/alpaca_data_compare.py
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

from tradefabe import broker
from tradefabe.engine import UNIVERSE
from tradefabe.hourly import CRYPTO_TICKERS
from tradefabe.paths import ARTIFACTS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hourly_backtest import fetch_bars as yf_fetch_bars  # noqa: E402

# Alpaca's hourly bars empirically start ~2016 for equities, ~2021 for crypto on this
# account (confirmed again by fetch_alpaca_bars() below) -- fetching from a bit before
# that costs nothing (an empty response) and avoids hardcoding an exact cutover date.
ALPACA_START = {"equity": dt.datetime(2016, 1, 1), "crypto": dt.datetime(2020, 1, 1)}

# The three regimes family L's own docstring names as missing from every hourly source
# reachable today -- the actual question this script exists to answer.
REGIME_MARKERS = {
    "2018 vol spike": dt.datetime(2018, 2, 1),
    "COVID crash": dt.datetime(2020, 3, 1),
    "2022 bear market": dt.datetime(2022, 1, 1),
}

ALPACA_CACHE = os.path.join(ARTIFACTS, "alpaca_hourly_{tag}.csv")


def _to_alpaca_symbol(yf_symbol: str) -> str:
    """yfinance's crypto convention is "BTC-USD"; Alpaca's is "BTC/USD". Equity tickers
    are identical on both sources."""
    return yf_symbol.replace("-", "/") if "-" in yf_symbol else yf_symbol


def fetch_alpaca_bars(tickers: list[str], tag: str, start: dt.datetime) -> pd.DataFrame:
    """Alpaca's full available hourly history per ticker, from `start` to now.
    Snapshotted to artifacts/ (same convention as fetch_bars()'s yfinance cache) -- one
    real pull is enough evidence for this diagnostic; a re-run shouldn't re-hit the API.
    Fetches ONE TICKER AT A TIME deliberately: a single multi-symbol request over a
    decade of hourly bars was still running after several minutes in testing, while
    single-ticker requests reliably took ~30-40s each -- slower in aggregate, but
    predictable and each ticker's failure can't take the others down with it."""
    path = ALPACA_CACHE.format(tag=tag)
    if os.path.exists(path):
        px = pd.read_csv(path, index_col=0, parse_dates=True)
        print(f"[alpaca] {tag}: {len(px)} hourly bars from snapshot {path}")
        return px

    key_id, secret_key = broker.credentials()
    # This account's subscription tier can't query SIP (stock) data inside roughly the
    # last 15 minutes -- `end=now()` failed on EVERY equity ticker with "subscription
    # does not permit querying recent SIP data". A 20-minute buffer clears it; crypto
    # has no such restriction, so this costs it nothing.
    end = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(minutes=20)
    cols = {}
    for t in tickers:
        asym = _to_alpaca_symbol(t)
        try:
            if tag == "crypto":
                from alpaca.data.historical import CryptoHistoricalDataClient
                from alpaca.data.requests import CryptoBarsRequest
                from alpaca.data.timeframe import TimeFrame
                client = CryptoHistoricalDataClient(key_id, secret_key)
                req = CryptoBarsRequest(symbol_or_symbols=asym, timeframe=TimeFrame.Hour,
                                        start=start, end=end)
                df = client.get_crypto_bars(req).df
            else:
                from alpaca.data.historical import StockHistoricalDataClient
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame
                client = StockHistoricalDataClient(key_id, secret_key)
                req = StockBarsRequest(symbol_or_symbols=asym, timeframe=TimeFrame.Hour,
                                       start=start, end=end)
                df = client.get_stock_bars(req).df
        except Exception as e:  # noqa: BLE001 -- one ticker's API hiccup must not sink the run
            print(f"  [alpaca] {t}: ERROR {type(e).__name__}: {e}")
            continue
        if df.empty:
            print(f"  [alpaca] {t}: no data")
            continue
        close = df["close"]
        if isinstance(close.index, pd.MultiIndex):
            close = close.droplevel("symbol")
        close.index = pd.to_datetime(close.index).tz_localize(None)
        close = close[~close.index.duplicated(keep="last")].sort_index()
        cols[t] = close
        print(f"  [alpaca] {t}: {len(close)} bars, {close.index.min().date()} -> "
              f"{close.index.max().date()}")

    px = pd.DataFrame(cols).sort_index()
    os.makedirs(ARTIFACTS, exist_ok=True)
    px.to_csv(path)
    print(f"[alpaca] {tag}: wrote {len(px)} row(s) -> {path}")
    return px


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
