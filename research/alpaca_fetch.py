"""alpaca_fetch.py — shared Alpaca hourly-bar fetcher.

Factored out of alpaca_data_compare.py (#135) so hourly_backtest.py can use the SAME
fetch function for its equity leg (#156) without alpaca_data_compare.py and
hourly_backtest.py importing from each other in a circle -- alpaca_data_compare.py
already imports hourly_backtest.fetch_bars (the yfinance path, still used for its
comparison and for family L's crypto leg), so hourly_backtest.py importing
fetch_alpaca_bars back from alpaca_data_compare.py would be circular.

Requires the optional `[alpaca]` extra and ALPACA_API_KEY_ID/ALPACA_SECRET_KEY (same
`.env`/broker.credentials() convention as everywhere else Alpaca is used). Imports are
lazy, inside the function body, matching the kronos.py/desktop.py optional-extra
pattern -- importing this module costs nothing when the extra isn't installed.
"""
from __future__ import annotations

import datetime as dt
import os

import pandas as pd

from tradefabe import broker
from tradefabe.paths import ARTIFACTS

# Alpaca's hourly bars empirically start ~2016 for equities, ~2021 for crypto on this
# account -- fetching from a bit before that costs nothing (an empty response) and
# avoids hardcoding an exact cutover date.
ALPACA_START = {"equity": dt.datetime(2016, 1, 1), "crypto": dt.datetime(2020, 1, 1)}

ALPACA_CACHE = os.path.join(ARTIFACTS, "alpaca_hourly_{tag}.csv")


def _to_alpaca_symbol(yf_symbol: str) -> str:
    """yfinance's crypto convention is "BTC-USD"; Alpaca's is "BTC/USD". Equity tickers
    are identical on both sources."""
    return yf_symbol.replace("-", "/") if "-" in yf_symbol else yf_symbol


def fetch_alpaca_bars(tickers: list[str], tag: str, start: dt.datetime) -> pd.DataFrame:
    """Alpaca's full available hourly history per ticker, from `start` to now.
    Snapshotted to artifacts/ (same convention as hourly_backtest.fetch_bars()'s
    yfinance cache) -- one real pull is enough evidence for this diagnostic; a re-run
    shouldn't re-hit the API. Fetches ONE TICKER AT A TIME deliberately: a single
    multi-symbol request over a decade of hourly bars was still running after several
    minutes in testing, while single-ticker requests reliably took ~30-40s each --
    slower in aggregate, but predictable and each ticker's failure can't take the
    others down with it."""
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
