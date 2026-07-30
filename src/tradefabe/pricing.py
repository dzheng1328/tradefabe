"""Modular per-book price sourcing for mark-to-market.

Every book declares WHERE its marks come from; the mark loop fetches each distinct source
once per cycle and marks every book against its own. Adding a future book means one entry
in BOOK_SOURCE (or nothing at all, if it uses the default equity universe) rather than a
new bespoke branch in runner.py -- which is how the engine ended up with three separate
hand-rolled mark paths (daily equity, hourly crypto, funding) before this.

WHY HOURLY BARS, NOT THE DAILY FRAME
------------------------------------
GitHub's scheduled cron is best-effort and heavily throttled: an `0 * * * *` mark schedule
actually delivered 03:00, 06:38, 09:13, 11:20, 13:25, 15:06, 17:03, 19:13, 20:59 on
2026-07-26 -- roughly one every 2.2h, only one of them on the hour. One mark per firing
therefore left multi-hour holes in every chart, and a freshly-opened book showed a single
dot.

Rather than fight the scheduler (more cron entries cost Actions minutes and GitHub
throttles them anyway), each cycle BACKFILLS one mark per hourly bar since the book's last
mark. This is not invented data: positions are constant between rebalances, and the prices
are the real historical hourly closes for that window. It is ordinary mark-to-market,
computed slightly late. The result is a dense, evenly-spaced hourly series whose resolution
does not depend on when the scheduler happened to fire.
"""
from __future__ import annotations

import pandas as pd

from .engine import UNIVERSE

CRYPTO_TICKERS = ["BTC-USD", "ETH-USD"]
# Family M's wick book trades 14 single names, none of them in UNIVERSE (#105). Imported
# from kronos.py rather than duplicated so the marked universe and the traded universe are
# the same list -- kronos.py's torch imports are lazy, so this costs nothing here.
from .kronos import WICK_UNIVERSE                                   # noqa: E402
LIVE_PERIOD = "30d"          # comfortably covers any realistic gap between cycles

# source name -> tickers priced by it
SOURCES = {
    "equity_hourly": list(UNIVERSE),
    "crypto_hourly": CRYPTO_TICKERS,
    "wick_hourly": list(WICK_UNIVERSE),
}

# book -> source. A book absent from here uses DEFAULT_SOURCE, so a future factory
# promotion on the standard ETF universe needs no entry at all.
BOOK_SOURCE = {
    "crypto_reversal_1h": "crypto_hourly",
    "kronos_wick_agg": "wick_hourly",
}
DEFAULT_SOURCE = "equity_hourly"

# Books whose equity is NOT a function of prices -- funding accrual books own their own
# marking (carry_live.run_carry / hourly.run_funding_timing / kronos_live.run_carry_kronos)
# and must be left alone here.
NON_PRICED = {"carry_btc_eth", "funding_timing_1h", "carry_kronos_vol"}


def source_for(book_name: str) -> str:
    return BOOK_SOURCE.get(book_name, DEFAULT_SOURCE)


def fetch(source: str) -> pd.DataFrame:
    """Hourly closes for one source. Trailing partial bars are dropped for the same reason
    engine.drop_incomplete_tail() drops them: a row that exists but is not a complete
    cross-section is not a close."""
    import yfinance as yf
    tickers = SOURCES[source]
    raw = yf.download(tickers, period=LIVE_PERIOD, interval="1h", progress=False,
                      threads=False, auto_adjust=True)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        px.columns = list(tickers)
    px = px[[t for t in tickers if t in px.columns]].dropna(how="all")
    if px.index.tz is not None:
        px.index = px.index.tz_convert(None)
    complete = px.notna().all(axis=1)
    if complete.any() and not complete.iloc[-1]:
        px = px.loc[:complete[complete].index[-1]]
    return px


def fetch_for_books(names) -> dict[str, pd.DataFrame]:
    """One fetch per DISTINCT source needed by `names`, not one per book."""
    out = {}
    for src in {source_for(n) for n in names if n not in NON_PRICED}:
        try:
            out[src] = fetch(src)
        except Exception as e:                    # a dead source must not kill the cycle
            print(f"[warn] hourly source {src} unavailable: {str(e)[:80]}")
    return out
