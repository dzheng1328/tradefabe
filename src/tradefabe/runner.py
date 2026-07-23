"""Daily paper cycle: refresh data, retarget books on their schedule, mark to market,
and write a tidy summary for the dashboard. Deterministic — no LLM anywhere in the loop."""
from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf
from . import books, signals
from .carry_live import run_carry
from .paths import STATE_DIR

EQUITY_BOOKS = list(signals.REGISTRY)


def _prices() -> pd.DataFrame:
    px = yf.download(signals.UNIVERSE, period="420d", auto_adjust=True,
                     progress=False, threads=False)["Close"]
    return px.dropna(how="all")


def run_daily(verbose: bool = True) -> pd.DataFrame:
    px = _prices()
    today = str(px.index[-1].date())
    last = px.iloc[-1]
    for name in EQUITY_BOOKS:
        _, freq = signals.REGISTRY[name]
        book = books.load(name)
        fresh = not book["positions"] and book["last_rebalance"] is None
        due = fresh or freq == "D" or signals.is_month_first_trading_day(px.index)
        if due:
            w = signals.target_weights(px, name)
            books.rebalance_to(book, w, today, last, signals.COST_BPS)
        else:
            books.mark(book, today, last)
        books.save(book)
        if verbose:
            print(f"  {name:<18} equity ${books.equity(book, last):>12,.0f}"
                  f"  ({'rebalanced' if due else 'marked'})")
    carry = run_carry()
    if verbose:
        print(f"  {'carry_btc_eth':<18} equity ${carry['equity']:>12,.0f}  (funding accrued)")
    return write_summary(last)


def write_summary(last_px: pd.Series) -> pd.DataFrame:
    rows, hist = [], []
    for name in EQUITY_BOOKS + ["carry_btc_eth"]:
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
