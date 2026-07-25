"""Daily paper cycle: refresh data, retarget books on their schedule, mark to market,
and write a tidy summary for the dashboard. Deterministic — no LLM anywhere in the loop."""
from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf
from . import books, signals, piggyback, factory
from .carry_live import run_carry
from .carry_risk import check_carry_risk
from .engine import sized_weights
from .paths import STATE_DIR

EQUITY_BOOKS = list(signals.REGISTRY)
# Only the 3 backtest-ALIVE piggyback constructions (piggyback.REGISTRY already excludes
# the DEAD piggyback_2b -- see STRATEGIES.md family H / graveyard.csv).
PIGGYBACK_BOOKS = list(piggyback.REGISTRY)
# Factory templates (#28) auto-promoted (#29/#28b) after clearing the full doctrine
# gate -- factory.load_promoted() reads state/paper/promoted.json, written by
# research/factory_run.py, so this list can grow between runner.py processes without a
# code change. Re-read at IMPORT time -- a book promoted after this process started
# won't appear until the next `tradefabe run`/`tradefabe mark` invocation, same as any
# other module-level registry here.
FACTORY_BOOKS = factory.load_promoted()
# Promoted LIVE-GENERATED candidates (#28b) -- these don't live in factory.TEMPLATES (no
# importable module-level entry survives across processes), so each entry carries its
# own family+params and factory.rebuild_signal() reconstructs the exact signal function
# fresh every process, same determinism guarantee TEMPLATES gets "for free" from being
# source code.
GENERATED_BOOKS = factory.load_promoted_generated()
ALL_BOOKS = EQUITY_BOOKS + PIGGYBACK_BOOKS + FACTORY_BOOKS + [g["name"] for g in GENERATED_BOOKS]


def _prices() -> pd.DataFrame:
    px = yf.download(signals.UNIVERSE, period="420d", auto_adjust=True,
                     progress=False, threads=False)["Close"]
    return px.dropna(how="all")


def _make_generated_get_weights(sig_fn):
    """A get_weights(px, name)-shaped callable for a promoted GENERATED book -- unlike
    signals.target_weights()/piggyback.target_weights()/factory.target_weights(), a
    generated candidate has no name-keyed static registry to look `name` up in, so this
    closes over the already-reconstructed sig_fn directly instead."""
    def get_weights(px, name):
        return sized_weights(px, sig_fn(px)).iloc[-1].fillna(0.0)
    return get_weights


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
    for name in FACTORY_BOOKS:
        _, freq, _, _ = factory.TEMPLATES[name]
        _run_book(name, freq, factory.target_weights, px, today, last, verbose)
    for g in GENERATED_BOOKS:
        sig_fn = factory.rebuild_signal(g["family"], g["params"])
        get_weights = _make_generated_get_weights(sig_fn)
        _run_book(g["name"], g["freq"], get_weights, px, today, last, verbose)
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
