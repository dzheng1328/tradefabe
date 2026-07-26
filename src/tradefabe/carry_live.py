"""Live paper carry book: accrues real Hyperliquid funding (BTC+ETH) on a delta-neutral
notional. Delta-neutral means price moves are ignored by construction; what the book earns
is funding minus a fee drag. If funding goes negative (bear regimes), the book BLEEDS —
that's the point of watching it live."""
from __future__ import annotations
import time
import datetime as dt
import pandas as pd
import requests
from .paths import STATE_DIR
from . import books

COINS = ["BTC", "ETH"]
FEE_DRAG_YR = 0.015
API = "https://api.hyperliquid.xyz/info"


def _funding_since(coin: str, start_ms: int) -> list[tuple[int, float]]:
    out, t = [], start_ms
    for _ in range(40):
        r = None
        for attempt in range(3):
            try:
                r = requests.post(API, json={"type": "fundingHistory", "coin": coin,
                                             "startTime": t}, timeout=30).json()
                if isinstance(r, list):
                    break
            except Exception:
                pass
            time.sleep(1 + attempt)
        if not isinstance(r, list) or not r:
            break
        out += [(int(x["time"]), float(x["fundingRate"])) for x in r]
        last = int(r[-1]["time"])
        if last <= t or len(r) < 500:
            break
        t = last + 1
        time.sleep(0.15)
    return out


def run_carry(name: str = "carry_btc_eth") -> dict:
    book = books.load(name)
    now_ms = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start = book.get("last_ts") or (now_ms - 24 * 3600 * 1000)
    # Hyperliquid pays funding EVERY HOUR, so accrue and stamp per hourly point rather
    # than collapsing the whole gap into one row at cycle time. GitHub's cron fires only
    # ~every 2.2h despite an hourly schedule, so one row per cycle left the 5H chart with
    # a single point -- the accrual was always computed correctly, it just wasn't being
    # RECORDED at the resolution the data already had.
    per_coin = {c: dict(_funding_since(c, start + 1)) for c in COINS}
    stamps = sorted(set().union(*(set(v) for v in per_coin.values())))
    eq = book.get("equity", books.START_CASH)
    prev_ms = start
    for ts in stamps:
        rates = [per_coin[c][ts] for c in COINS if ts in per_coin[c]]
        if not rates:
            continue
        days = max((ts - prev_ms) / (24 * 3600 * 1000), 0.0)
        eq *= 1 + (sum(rates) / len(rates)) - FEE_DRAG_YR / 365 * days
        prev_ms = ts
        # Minute-resolution key, same shape books.mark() uses. Stamped at the FUNDING
        # point's own time, not wall-clock, so the series is evenly hourly regardless of
        # when the cycle happened to run.
        key = books.utc_stamp(pd.Timestamp(ts, unit="ms"))
        if not any(row[0] == key for row in book["history"]):
            book["history"].append([key, round(eq, 2)])

    book["equity"] = round(eq, 2)
    book["last_ts"] = stamps[-1] if stamps else now_ms
    book["last_run"] = dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    books.save(book)
    return book
