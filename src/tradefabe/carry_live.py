"""Live paper carry book: accrues real Hyperliquid funding (BTC+ETH) on a delta-neutral
notional. Delta-neutral means price moves are ignored by construction; what the book earns
is funding minus a fee drag. If funding goes negative (bear regimes), the book BLEEDS —
that's the point of watching it live."""
from __future__ import annotations
import time
import datetime as dt
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
    per_coin = []
    for c in COINS:
        pts = _funding_since(c, start + 1)
        per_coin.append(sum(f for _, f in pts))
    days = max((now_ms - start) / (24 * 3600 * 1000), 1e-9)
    accrual = (sum(per_coin) / len(COINS)) - FEE_DRAG_YR / 365 * days
    eq = book.get("equity", books.START_CASH) if "equity" in book else books.START_CASH
    book["equity"] = round(eq * (1 + accrual), 2)
    book["last_ts"] = now_ms
    # Minute-resolution stamp, same key shape books.mark() uses for the equity books.
    # This used to key on the bare DATE, which collapsed every 30min mark cron call into
    # a single overwritten row per day -- the accrual was already being computed every
    # cycle, it just wasn't being RECORDED, so the dashboard's short ranges (5H/1D) had
    # exactly one point to draw and rendered a bare dot.
    stamp = dt.datetime.now().isoformat(timespec="minutes")
    if not book["history"] or book["history"][-1][0] != stamp:
        book["history"].append([stamp, book["equity"]])
    else:
        book["history"][-1][1] = book["equity"]
    book["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    books.save(book)
    return book
