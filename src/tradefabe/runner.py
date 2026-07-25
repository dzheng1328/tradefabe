"""Daily paper cycle: refresh data, retarget books on their schedule, mark to market,
and write a tidy summary for the dashboard. Deterministic — no LLM anywhere in the loop."""
from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf
from . import books, signals, piggyback
from .carry_live import run_carry
from .carry_risk import check_carry_risk
from .paths import STATE_DIR

EQUITY_BOOKS = list(signals.REGISTRY)
# Only the 3 backtest-ALIVE piggyback constructions (piggyback.REGISTRY already excludes
# the DEAD piggyback_2b -- see STRATEGIES.md family H / graveyard.csv).
PIGGYBACK_BOOKS = list(piggyback.REGISTRY)
ALL_BOOKS = EQUITY_BOOKS + PIGGYBACK_BOOKS


def _prices() -> pd.DataFrame:
    px = yf.download(signals.UNIVERSE, period="420d", auto_adjust=True,
                     progress=False, threads=False)["Close"]
    return px.dropna(how="all")


def _run_book(name, freq, get_weights, px, today, last, verbose):
    book = books.load(name)
    fresh = not book["positions"] and book["last_rebalance"] is None
    due = fresh or freq == "D" or signals.is_month_first_trading_day(px.index)
    if due:
        books.rebalance_to(book, get_weights(px, name), today, last, signals.COST_BPS)
    else:
        books.mark(book, today, last)
    books.save(book)
    if verbose:
        print(f"  {name:<18} equity ${books.equity(book, last):>12,.0f}"
              f"  ({'rebalanced' if due else 'marked'})")


def run_mark(verbose: bool = True) -> pd.DataFrame:
    """Lighter sibling of run_daily(): marks every book to market at the current price
    WITHOUT rebalancing, so the live-equity chart gets more than one point per day. Meant
    for a tighter cron (e.g. every 30min) alongside the once-daily run_daily(), which still
    owns the actual rebalance -- each strategy's registered M/W/D frequency is untouched.
    books.mark()'s dedup key is a full timestamp here (vs. run_daily()'s bare date), so the
    two interleave in the same history list without colliding."""
    px = _prices()
    now = dt.datetime.now().isoformat(timespec="minutes")
    last = px.iloc[-1]
    for name in ALL_BOOKS:
        book = books.load(name)
        books.mark(book, now, last)
        books.save(book)
        if verbose:
            print(f"  {name:<18} equity ${books.equity(book, last):>12,.0f}  (marked)")
    carry = run_carry()
    if verbose:
        print(f"  {'carry_btc_eth':<18} equity ${carry['equity']:>12,.0f}  (funding accrued)")
    return write_summary(last)


def run_daily(verbose: bool = True) -> pd.DataFrame:
    px = _prices()
    today = str(px.index[-1].date())
    last = px.iloc[-1]
    for name in EQUITY_BOOKS:
        _, freq = signals.REGISTRY[name]
        _run_book(name, freq, signals.target_weights, px, today, last, verbose)
    for name in PIGGYBACK_BOOKS:
        _, freq = piggyback.REGISTRY[name]
        _run_book(name, freq, piggyback.target_weights, px, today, last, verbose)
    carry = run_carry()
    if verbose:
        print(f"  {'carry_btc_eth':<18} equity ${carry['equity']:>12,.0f}  (funding accrued)")
    check_carry_risk()   # writes state/paper/carry_risk.json; never raises, dashboard-only surface
    return write_summary(last)


def write_summary(last_px: pd.Series) -> pd.DataFrame:
    rows, hist = [], []
    for name in ALL_BOOKS + ["carry_btc_eth"]:
        b = books.load(name)
        eq = b.get("equity") or books.equity(b, last_px)
        rows.append({"book": name, "equity": round(eq, 2),
                     "return": round(eq / books.START_CASH - 1, 4),
                     "last_run": b.get("last_run")})
        for d, e in b["history"]:
            hist.append({"date": d, "book": name, "equity": e})
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows)
    summary.to_csv(STATE_DIR / "summary.csv", index=False)
    pd.DataFrame(hist).to_csv(STATE_DIR / "history.csv", index=False)
    return summary
