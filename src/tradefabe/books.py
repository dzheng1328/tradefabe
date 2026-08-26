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

# Trade log depth (#109). Capped for the same reason backfill_marks() caps: these ledgers
# are committed to git every cycle by the Action, so an unbounded list grows the repo
# forever. 500 fills is months of history for a monthly book and weeks for a daily one.
MAX_TRADES = 500

# A share delta below this is rounding, not a fill. Vol-targeted weights drift by tiny
# fractions every rebalance; logging those would bury the real trades in noise.
MIN_FILL_SHARES = 1e-9


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


def record_prices(book: dict, px: pd.Series, when: str) -> None:
    """Remember the prices this book was actually valued at, inside the ledger itself.

    The dashboard used to price open positions from `data/prices.csv`, which is (a)
    gitignored, so it is local-only and can be arbitrarily stale while the ledger arrives
    fresh from the Action every cycle, and (b) the DAILY equity universe only -- it has no
    BTC-USD or ETH-USD, so `crypto_reversal_1h`'s positions all priced to NaN and the
    Capital-deployed panel rendered `$-0` for a fully-deployed $100k book (#109).

    Storing them here makes the ledger self-describing: whatever source priced the book is
    the source the UI reports, with no second data path to keep in sync. Only held names
    are kept, so this does not grow with the universe.
    """
    keep = {}
    for t in book["positions"]:
        v = px.get(t, None)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            keep[t] = round(v, 6)
    book["last_prices"] = keep
    book["last_prices_at"] = when


def log_trades(book: dict, new_pos: dict, px: pd.Series, when: str) -> list[dict]:
    """Append one record per fill implied by moving `positions` -> `new_pos` (#109).

    `rebalance_to()` computed target shares, turnover, and cost and then threw all of it
    away, leaving only the resulting position -- so there was no way to see WHAT was traded
    or WHEN. Each record is self-contained (price and notional included) so the log stays
    readable without re-deriving anything from a price frame that may no longer exist.

    Sides are named from the position's perspective, not the order's, because that is what
    a reader of a long/short book actually wants to know: BUY/SELL open or grow a long,
    SHORT/COVER open or reduce a short, and a sign flip is reported as the side it ends in.
    """
    old = dict(book.get("positions", {}))
    trades = []
    for t in sorted(set(old) | set(new_pos)):
        before, after = float(old.get(t, 0.0)), float(new_pos.get(t, 0.0))
        delta = after - before
        if abs(delta) < MIN_FILL_SHARES:
            continue
        p = _px(px, t)
        if p <= 0:                      # unpriceable: turnover already skipped it
            continue
        if after >= 0 and before >= 0:
            side = "BUY" if delta > 0 else "SELL"
        elif after <= 0 and before <= 0:
            side = "SHORT" if delta < 0 else "COVER"
        else:                            # crossed zero -- name it by where it landed
            side = "BUY" if after > 0 else "SHORT"
        trades.append({"ts": when, "ticker": t, "side": side,
                       "shares": round(delta, 6), "price": round(p, 6),
                       "notional": round(abs(delta) * p, 2),
                       "position_after": round(after, 6)})
    if trades:
        book["trades"] = (book.get("trades", []) + trades)[-MAX_TRADES:]
    return trades


# ---------------------------------------------------------------- retirement (#113)
# Retirement is MANUAL-ONLY, by Dave's explicit call. There is deliberately no performance
# trigger, no drawdown threshold, and no code path anywhere in the engine that sets this
# key on its own -- only retire() does, and only the CLI reaches it.
#
# The reason is in DOCTRINE.md's v1.2 retirement clause: a monitor-only book exists to
# accumulate forward evidence, and auto-retiring the losers would filter that record on
# results. That is survivorship bias in the ONE dataset in this lab that doesn't have any,
# and it would quietly turn the honest forward record into a curated one.
#
# Guard: tests/test_retirement.py asserts a full run_daily()/run_mark() cycle never writes
# this key on any book, so the property survives future engine changes.
RETIRE_REASON_MAX = 300


def is_retired(book: dict) -> bool:
    return bool(book.get("retired"))


def retire(name: str, reason: str, when: str | None = None) -> dict:
    """Freeze a book: no further rebalances, no further marks, history preserved exactly.

    Refuses a book with no ledger on disk. load() synthesizes a fresh $100k book for any
    unknown name, so without this check a typo would CREATE a retired phantom book that
    then shows up in the dashboard forever."""
    if not _path(name).exists():
        raise KeyError(f"no ledger at {_path(name)} -- nothing to retire")
    book = load(name)
    if is_retired(book):
        return book
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("a retirement needs a reason -- it is a human decision on the "
                         "record, not a status flag")
    book["retired"] = {"at": when or utc_stamp(), "reason": reason[:RETIRE_REASON_MAX]}
    save(book)
    return book


def unretire(name: str) -> dict:
    """Reverse a retirement. The book resumes on the next cycle; its history was never
    touched, so the gap between the retire and un-retire stamps is visible on the chart
    rather than papered over."""
    if not _path(name).exists():
        raise KeyError(f"no ledger at {_path(name)} -- nothing to un-retire")
    book = load(name)
    book.pop("retired", None)
    save(book)
    return book


def utc_stamp(when=None) -> str:
    """The ONE clock every history key uses: naive UTC, minute resolution.

    The paper engine runs in a UTC container and owns the ledger, so its wall-clock marks
    were already UTC while a local `tradefabe mark` wrote PDT -- and hourly bars arrived
    tz-AWARE. Three representations in one series made it non-monotonic, which no amount
    of sorting fixes because the values genuinely disagree about what time it is."""
    if when is None:
        return dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(timespec="minutes")
    ts = pd.Timestamp(when)
    ts = ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts
    return ts.isoformat(timespec="minutes")


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
    book["last_run"] = dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    book["last_price_bar"] = bar_date(px) or book.get("last_price_bar")
    # Self-describing ledger (#109): whatever priced this book is what the dashboard shows,
    # instead of a second, gitignored, equity-only cache that silently NaN'd crypto books.
    record_prices(book, px, date)
    return True


def backfill_marks(book: dict, px: pd.DataFrame, cap: int = 400) -> int:
    """Append one mark per price bar since this book's last recorded mark. Returns how
    many were added.

    Positions are constant between rebalances, so valuing them at each intervening bar's
    real close is ordinary mark-to-market, just computed late -- NOT invented data. This
    is what decouples chart resolution from GitHub's erratic cron: a cycle that fires 2.5h
    after the previous one still lands every hourly point in between.

    Marks strictly forward in time and never rewrites an existing key, so running it twice
    is a no-op. `cap` bounds a first run on a long-idle book from appending thousands of
    rows in one go."""
    if px is None or px.empty:
        return 0
    # A brand-new book (just promoted, empty history) has no inception to bound against --
    # the loop below would then happily backfill every one of the price source's ~30 days
    # of bars as fabricated flat-equity history the book never held (caught 2026-08-26:
    # every freshly-promoted book's "first mark" was silently backdated 6-8 weeks). Refuse
    # outright and let the caller's mark() fallback write the true first entry at the real
    # current time, which becomes tomorrow's inception.
    if not book["history"]:
        return 0
    # Tracked separately from history keys ON PURPOSE. The keys written by mark() are
    # WALL-CLOCK stamps ("2026-07-26T20:59"), while these are BAR times (Friday's close,
    # if the market has been shut since). Comparing the two key spaces made backfill go
    # permanently silent the moment a wall-clock mark landed after the last bar.
    last_bar = book.get("last_backfill_bar")
    # NEVER backfill before the book existed. The price source carries 30 days of bars,
    # but a book opened three days ago did not hold these positions three weeks ago --
    # writing marks for that window would be inventing a history it never had, which is
    # the one thing this ledger must not do.
    inception = book["history"][0][0]
    added = 0
    for ts, row in px.iloc[-cap:].iterrows():
        key = utc_stamp(ts)
        if key < inception:
            continue
        if last_bar is not None and key <= last_bar:
            continue
        if any(r[0] == key for r in book["history"]):
            continue
        eq = equity(book, row)
        if not math.isfinite(eq):
            continue
        book["history"].append([key, round(eq, 2)])
        book["last_backfill_bar"] = key
        added += 1
    if added:
        book["history"].sort(key=lambda r: r[0])   # bar times interleave with wall-clock
        # Deliberately does NOT touch `last_price_bar`. That field guards the DAILY-frame
        # mark path against regressing to an older close; hourly bars are a different
        # clock, and setting it here made every daily mark look like a step backwards in
        # time, so mark() correctly refused all of them and no equity book marked at all.
        book["last_run"] = dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    return added


def _finite(v) -> bool:
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def rebalance_to(book: dict, weights: pd.Series, date: str, px: pd.Series,
                 cost_bps: float, stamp: str | None = None) -> bool:
    """Trade to target weights at today's close; charge cost on turnover.

    Returns False without trading if the book or any target name can't be priced. Note
    `p <= 0` does NOT screen NaN (`nan <= 0` is False), so a partial price bar would
    otherwise size positions off a NaN and corrupt the book permanently.

    `date` is the PRICE BAR's date and is what `last_rebalance` records -- "which bar did
    we trade on". `stamp` is the minute-resolution clock key for the history and trade log
    (#109); it defaults to `date` only so existing callers keep working. The two are
    genuinely different questions, and conflating them is what put a bare date into a
    minute-stamped history and produced a midnight V-notch on every chart."""
    stamp = stamp or date
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
    # Log BEFORE positions are replaced -- the fill is the difference between the two, and
    # once `book["positions"]` is overwritten that difference is unrecoverable.
    log_trades(book, new_pos, px, stamp)
    book["positions"] = new_pos
    book["last_rebalance"] = date
    mark(book, stamp, px)
    return True


def _px(px: pd.Series, t: str) -> float:
    """Price for turnover/valuation arithmetic, 0.0 when unusable."""
    v = px.get(t, 0)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0
