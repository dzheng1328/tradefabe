"""Paper ledgers: JSON state per book under state/paper/. Fills are simulated at the
latest close with a per-side cost — a local paper broker. (Alpaca swap-in is on the roadmap.)"""
from __future__ import annotations
import json
import math
import sys
import datetime as dt
import pandas as pd
from .paths import STATE_DIR

START_CASH = 100_000.0


def _path(name):
    return STATE_DIR / f"{name}.json"


def load(name: str) -> dict:
    p = _path(name)
    if p.exists():
        return json.loads(p.read_text())
    return {"name": name, "cash": START_CASH, "positions": {}, "history": [],
            "last_run": None, "last_rebalance": None}


def save(book: dict) -> None:
    """allow_nan=False on purpose: Python happily emits a bare `NaN` token, which is not
    valid JSON -- `JSON.parse` and jq both reject the file outright. mark() already
    refuses to record a non-finite equity; this is the backstop that makes any future
    route to the same bug fail loudly at the write instead of silently on read."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(book["name"]).write_text(json.dumps(book, indent=1, allow_nan=False))


def equity(book: dict, px: pd.Series) -> float:
    """Cash + position value. Returns NaN if any held name has a non-finite price.

    NaN is deliberately allowed to propagate rather than being coerced to 0: a position
    priced at 0 is a silent 100% loss on that leg, which would look like a real drawdown.
    Callers must check `math.isfinite` -- see mark() and rebalance_to()."""
    pos_val = 0.0
    for t, sh in book["positions"].items():
        p = px.get(t, 0)
        try:
            p = float(p)
        except (TypeError, ValueError):
            return float("nan")
        if not math.isfinite(p):
            return float("nan")
        pos_val += sh * p
    return book["cash"] + pos_val


def bar_date(px: pd.Series):
    """The date of the price bar this Series came from, or None if unlabelled."""
    name = getattr(px, "name", None)
    if name is None:
        return None
    try:
        return pd.Timestamp(name).date().isoformat()
    except (ValueError, TypeError):
        return None


def _regressed(book: dict, px: pd.Series) -> str | None:
    """The bar we'd be marking against, if it is OLDER than the last one used.

    yfinance's most recent row comes and goes: a complete Friday bar in one call, an
    incomplete one in the next, absent in a third. Marking against whatever arrives makes
    equity jump backwards to an earlier close and back again -- the two-value square wave
    seen on the dashboard 2026-07-26. Equity may stand still, but it must never travel
    back in time."""
    bar, prev = bar_date(px), book.get("last_price_bar")
    return bar if (bar and prev and bar < prev) else None


def mark(book: dict, date: str, px: pd.Series) -> bool:
    """Append an equity mark. Returns False (and writes nothing) if the book can't be
    priced -- a NaN written into the ledger is permanent and silently poisons every
    downstream chart and return series (hit for real 2026-07-26, 8 books in one cycle) --
    or if the price bar is older than the one already marked against."""
    stale = _regressed(book, px)
    if stale:
        print(f"[warn] {book['name']}: skipping mark at {date} — price bar {stale} is older "
              f"than {book['last_price_bar']} already used", file=sys.stderr)
        return False
    eq = equity(book, px)
    if not math.isfinite(eq):
        unpriced = [t for t in book["positions"]
                    if not _finite(px.get(t, float("nan")))]
        print(f"[warn] {book['name']}: skipping mark at {date} — no usable price for "
              f"{unpriced or 'held positions'}", file=sys.stderr)
        return False
    # A key already recorded is never rewritten -- the first valuation of a bar is the
    # record. But the check has to scan the WHOLE history, not just history[-1]:
    # run_daily() keys on a bare date and run_mark() on a full timestamp, so the two
    # interleave, and a repeated bare date that wasn't the last entry got appended a
    # second time (25 duplicate keys accumulated before this was caught).
    if not any(row[0] == date for row in book["history"]):
        book["history"].append([date, round(eq, 2)])
    book["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    book["last_price_bar"] = bar_date(px) or book.get("last_price_bar")
    return True


def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def rebalance_to(book: dict, weights: pd.Series, date: str, px: pd.Series,
                 cost_bps: float) -> bool:
    """Trade to target weights at today's close; charge cost on turnover.

    Returns False without trading if the book or any target name can't be priced. Note
    `p <= 0` does NOT screen NaN (`nan <= 0` is False), so a partial price bar would
    otherwise size positions off a NaN and corrupt the book permanently."""
    stale = _regressed(book, px)
    if stale:
        print(f"[warn] {book['name']}: skipping rebalance at {date} — price bar {stale} is "
              f"older than {book['last_price_bar']} already used", file=sys.stderr)
        return False
    eq = equity(book, px)
    if not math.isfinite(eq):
        print(f"[warn] {book['name']}: skipping rebalance at {date} — book not priceable",
              file=sys.stderr)
        return False
    wanted = [t for t, w in weights.items() if abs(w) > 1e-9]
    unpriced = [t for t in wanted if not _finite(px.get(t, float("nan")))]
    if unpriced:
        print(f"[warn] {book['name']}: skipping rebalance at {date} — no usable price for "
              f"{unpriced}", file=sys.stderr)
        return False

    turnover = 0.0
    new_pos = {}
    for t, w in weights.items():
        p = float(px.get(t, 0) or 0)
        if not math.isfinite(p) or p <= 0:
            continue
        tgt_sh = (w * eq) / p
        cur_sh = book["positions"].get(t, 0.0)
        turnover += abs(tgt_sh - cur_sh) * p
        if abs(tgt_sh) > 1e-9:
            new_pos[t] = tgt_sh
    for t, cur_sh in book["positions"].items():          # closed names count in turnover
        if t not in weights.index:
            turnover += abs(cur_sh) * _px(px, t)
    cost = turnover * (cost_bps / 1e4)
    pos_val = sum(sh * _px(px, t) for t, sh in new_pos.items())
    book["cash"] = eq - pos_val - cost
    book["positions"] = new_pos
    book["last_rebalance"] = date
    mark(book, date, px)
    return True


def _px(px: pd.Series, t: str) -> float:
    """Price for turnover/valuation arithmetic, 0.0 when unusable."""
    v = px.get(t, 0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0
