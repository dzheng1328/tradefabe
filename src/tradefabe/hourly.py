"""Family L: the hourly strategies (#86), as LIVE monitor-only paper books.

All three are backtest-DEAD (see STRATEGIES.md family L / graveyard.csv), so under
DOCTRINE v1.2 they are monitor-only forever and can never become `paper-confirmed`, no
matter what the live data does. Same status every factory promotion already carries.

**The signal functions and their parameters live HERE, not in research/hourly_backtest.py.**
The study imports them from this module, so the code that produced the verdict and the
code running the live book are literally the same function. Duplicating two-line signal
definitions across the two would be exactly how a live book silently drifts from the spec
it was judged on.

**Cadence caveat, stated plainly.** These were tested on a strict 1-hour clock. The paper
engine's tightest loop is `tradefabe mark`, scheduled hourly but in practice spaced ~2h by
GitHub's best-effort cron. So the live books rebalance on every mark cycle -- the closest
the engine can get -- and their realised cadence is SLOWER than the tested spec. Live
results will therefore diverge from the backtest for a reason that has nothing to do with
whether the edge is real. That is a known, accepted limitation of monitoring them at all,
not a bug to chase.
"""
from __future__ import annotations
import datetime as dt

import numpy as np
import pandas as pd

from . import books
from .engine import COST_BPS, UNIVERSE

# --- pre-registered parameters, frozen in STRATEGIES.md family L. DO NOT TUNE. ---
FUNDING_LOOKBACK_H = 24     # trailing hours of funding averaged for the on/off decision
REVERSAL_LOOKBACK_H = 6     # trailing hours faded
TSMOM_LOOKBACK_BARS = 24    # trailing bars (~5 sessions of ~4.8 usable hourly bars)

CRYPTO_TICKERS = ["BTC-USD", "ETH-USD"]
FUNDING_COINS = ["BTC", "ETH"]

# Enough history for the longest lookback with room to spare, without pulling 730 days
# on every cycle. 24-bar lookback needs ~5 sessions; 60d is generous.
LIVE_PERIOD = "60d"


# ---------------------------------------------------------------- signals
def sig_crypto_reversal(px: pd.DataFrame) -> pd.DataFrame:
    """Fade the trailing 6h move."""
    return -np.sign(px / px.shift(REVERSAL_LOOKBACK_H) - 1).fillna(0.0)


def sig_equity_tsmom(px: pd.DataFrame) -> pd.DataFrame:
    """Sign of the trailing 24-bar return."""
    return np.sign(px / px.shift(TSMOM_LOOKBACK_BARS) - 1).fillna(0.0)


def equal_weight(sig: pd.DataFrame) -> pd.DataFrame:
    """Equal weight across active names, as pre-registered. Deliberately NOT vol-targeted:
    engine.sized_weights()'s VOL_WINDOW/TARGET_VOL are calibrated for daily bars."""
    n = sig.abs().sum(axis=1).replace(0, np.nan)
    return sig.div(n, axis=0).fillna(0.0)


def funding_is_on(funding: pd.DataFrame) -> pd.Series:
    """The gate: carry runs at full notional when the trailing 24h mean funding is
    positive, flat when negative."""
    return (funding.rolling(FUNDING_LOOKBACK_H).mean() > 0).astype(float).mean(axis=1)


# ---------------------------------------------------------------- live books
BOOKS = {
    "crypto_reversal_1h": {"tickers": CRYPTO_TICKERS, "sig": sig_crypto_reversal},
    "equity_tsmom_1h":    {"tickers": list(UNIVERSE), "sig": sig_equity_tsmom},
}
PRICE_BOOK_NAMES = list(BOOKS)
ALL_NAMES = PRICE_BOOK_NAMES + ["funding_timing_1h"]


def fetch_hourly(tickers) -> pd.DataFrame:
    """Recent hourly closes for the live loop. Trailing partial bars are dropped for the
    same reason engine.drop_incomplete_tail() drops them: a row that exists but isn't a
    complete cross-section is not a close, and marking against it produced NaN equity and
    a phantom two-value square wave on the daily books (2026-07-26)."""
    import yfinance as yf
    raw = yf.download(tickers, period=LIVE_PERIOD, interval="1h", progress=False,
                      threads=False, auto_adjust=True)
    px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if not isinstance(raw.columns, pd.MultiIndex):
        px.columns = list(tickers)
    px = px[[t for t in tickers if t in px.columns]].dropna(how="all")
    complete = px.notna().all(axis=1)
    if complete.any() and not complete.iloc[-1]:
        px = px.loc[:complete[complete].index[-1]]
    return px


def target_weights(px: pd.DataFrame, name: str) -> pd.Series:
    """Latest equal-weight target for an hourly price book."""
    spec = BOOKS[name]
    return equal_weight(spec["sig"](px)).iloc[-1].fillna(0.0)


def run_funding_timing(name: str = "funding_timing_1h", verbose: bool = True) -> dict | None:
    """The gated carry book. Same delta-neutral accrual carry_live.run_carry() does, but
    the notional is ON only while the trailing 24h mean funding is positive.

    Reuses carry_live._funding_since() rather than re-implementing the paging -- one
    funding fetcher in the codebase, so the live gate and the live carry book can never
    disagree about what the funding actually was.

    Charges the round trip on both legs each time the gate flips, and charges the holding
    fee drag ONLY while on. A book that is flat is not paying to carry anything."""
    from .carry_live import _funding_since, FEE_DRAG_YR

    book = books.load(name)
    now_ms = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start = book.get("last_ts") or (now_ms - 24 * 3600 * 1000)

    # window long enough to both decide the gate (trailing 24h) and accrue since last_ts
    gate_from = min(start, now_ms - (FUNDING_LOOKBACK_H + 2) * 3600 * 1000)
    per_coin_recent, per_coin_accrue = [], []
    for c in FUNDING_COINS:
        pts = _funding_since(c, gate_from)
        if not pts:
            if verbose:
                print(f"  {name:<22} (SKIPPED — no funding data for {c})")
            return None
        cutoff = now_ms - FUNDING_LOOKBACK_H * 3600 * 1000
        per_coin_recent.append([f for t, f in pts if t >= cutoff])
        per_coin_accrue.append(sum(f for t, f in pts if t > start))

    means = [np.mean(v) for v in per_coin_recent if v]
    on = 1.0 if means and float(np.mean(means)) > 0 else 0.0
    was_on = float(book.get("gate_on", 0.0))

    days = max((now_ms - start) / (24 * 3600 * 1000), 1e-9)
    gross = float(np.mean(per_coin_accrue))
    flip_cost = abs(on - was_on) * 2 * (COST_BPS / 1e4)
    accrual = on * (gross - FEE_DRAG_YR / 365 * days) - flip_cost

    eq = book.get("equity", books.START_CASH)
    book["equity"] = round(eq * (1 + accrual), 2)
    book["last_ts"] = now_ms
    book["gate_on"] = on
    stamp = dt.datetime.now().isoformat(timespec="minutes")
    if not any(row[0] == stamp for row in book["history"]):
        book["history"].append([stamp, book["equity"]])
    book["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    books.save(book)
    if verbose:
        state = "ON" if on else "FLAT"
        print(f"  {name:<22} equity ${book['equity']:>12,.0f}  (funding gate {state})")
    return book


def run_price_books(verbose: bool = True) -> list[str]:
    """Rebalance + mark the two hourly PRICE books. Called from both run_daily() and
    run_mark(), so the realised cadence is the mark cadence -- see the module docstring's
    caveat about that being slower than the tested 1h spec."""
    done = []
    stamp = dt.datetime.now().isoformat(timespec="minutes")
    for name, spec in BOOKS.items():
        try:
            px = fetch_hourly(spec["tickers"])
        except Exception as e:                    # never kill a cycle over one book
            if verbose:
                print(f"  {name:<22} (SKIPPED — hourly data unavailable: {str(e)[:60]})")
            continue
        if len(px) <= TSMOM_LOOKBACK_BARS:
            if verbose:
                print(f"  {name:<22} (SKIPPED — only {len(px)} hourly bars)")
            continue
        book = books.load(name)
        last = px.iloc[-1]
        ok = books.rebalance_to(book, target_weights(px, name), stamp, last, COST_BPS)
        # Cache the equity ON the book, the way carry_live does. write_summary() values
        # every other book against the DAILY price frame, which has no BTC-USD/ETH-USD
        # column -- valuing this book there would price its holdings at 0 and silently
        # report cash only.
        if ok:
            book["equity"] = round(books.equity(book, last), 2)
        books.save(book)
        if verbose:
            if ok:
                print(f"  {name:<22} equity ${books.equity(book, last):>12,.0f}  (hourly rebalance)")
            else:
                print(f"  {name:<22} (SKIPPED — unpriceable, ledger untouched)")
        done.append(name)
    return done
