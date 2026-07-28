"""Daily paper cycle: refresh data, retarget books on their schedule, mark to market,
and write a tidy summary for the dashboard. Deterministic — no LLM anywhere in the loop."""
from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf
from . import books, signals, piggyback, factory, hourly, pricing
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
# Promoted correlation-picked COMBOS (#64). Same re-read-at-import contract as the two
# registries above; each entry carries its legs' full specs so the signal functions can be
# rebuilt in this process.
COMBO_BOOKS = factory.load_promoted_combos()
ALL_BOOKS = (EQUITY_BOOKS + PIGGYBACK_BOOKS + FACTORY_BOOKS
             + [g["name"] for g in GENERATED_BOOKS] + [c["name"] for c in COMBO_BOOKS])


def _prices() -> pd.DataFrame:
    px = yf.download(signals.UNIVERSE, period="420d", auto_adjust=True,
                     progress=False, threads=False)["Close"]
    return px.dropna(how="all")


def _make_combo_get_weights(spec):
    """get_weights(px, name)-shaped callable for a promoted combo -- closes over the spec
    so factory.combo_target_weights() can rebuild both legs."""
    def get_weights(px, name):
        return factory.combo_target_weights(px, spec)
    return get_weights


def _make_generated_get_weights(sig_fn):
    """A get_weights(px, name)-shaped callable for a promoted GENERATED book -- unlike
    signals.target_weights()/piggyback.target_weights()/factory.target_weights(), a
    generated candidate has no name-keyed static registry to look `name` up in, so this
    closes over the already-reconstructed sig_fn directly instead."""
    def get_weights(px, name):
        return sized_weights(px, sig_fn(px)).iloc[-1].fillna(0.0)
    return get_weights


def _run_book(name, freq, get_weights, px, today, last, verbose, stamp=None):
    """`today` is the price BAR's date (what `last_rebalance` means); `stamp` is the
    minute-resolution history key (#109).

    They used to be the same string, so run_daily() keyed history on a bare date while
    run_mark() keyed on a full timestamp. A bare date parses to MIDNIGHT, so once the
    dashboard sorted the series the daily run's post-rebalance equity -- written around
    22:00-23:10 UTC -- was drawn at the START of that same day, ~23h before it happened.
    The result was a one-minute-wide V-notch at every daily boundary on every chart."""
    stamp = stamp or books.utc_stamp()
    book = books.load(name)
    fresh = not book["positions"] and book["last_rebalance"] is None
    due = fresh or freq == "D" or signals.is_month_first_trading_day(px.index)
    if due:
        ok = books.rebalance_to(book, get_weights(px, name), today, last,
                                signals.COST_BPS, stamp=stamp)
    else:
        ok = books.mark(book, stamp, last)
    books.save(book)
    if verbose:
        if ok:
            print(f"  {name:<18} equity ${books.equity(book, last):>12,.0f}"
                  f"  ({'rebalanced' if due else 'marked'})")
        else:
            print(f"  {name:<18} {'':>19}  (SKIPPED — unpriceable, ledger untouched)")


def run_hourly(verbose: bool = True, prefetched: dict | None = None) -> None:
    """Family L's monitor-only books (#86). Called from BOTH run_daily() and run_mark(),
    like run_carry() -- these were tested on a 1h clock, so the mark cadence is the closest
    the engine gets. Never raises: a data outage on one hourly book must not take down a
    cycle that also owns the daily ledger."""
    try:
        hourly.run_price_books(verbose, prefetched)
        hourly.run_funding_timing(verbose=verbose)
    except Exception as e:                       # noqa: BLE001 - deliberately broad
        if verbose:
            print(f"  [warn] hourly books skipped this cycle: {str(e)[:90]}")


def run_mark(verbose: bool = True) -> pd.DataFrame:
    """Lighter sibling of run_daily(): marks every book to market at the current price
    WITHOUT rebalancing, so the live-equity chart gets more than one point per day. Meant
    for a tighter cron (e.g. every 30min) alongside the once-daily run_daily(), which still
    owns the actual rebalance -- each strategy's registered M/W/D frequency is untouched.
    Both cycles now key history on the SAME minute-resolution clock (#109); run_daily() used
    to key on a bare date, which parses to midnight and sorted its post-rebalance equity to
    the start of the day it belonged at the end of."""
    px = _prices()
    now = books.utc_stamp()
    last = px.iloc[-1]
    # One fetch per distinct hourly source, then backfill every bar since each book's last
    # mark. GitHub's cron actually fires ~every 2.2h despite an hourly schedule, so marking
    # once per firing left multi-hour holes; backfilling makes chart resolution independent
    # of when the scheduler happened to run. See pricing.py.
    hourly_px = pricing.fetch_for_books(ALL_BOOKS + hourly.PRICE_BOOK_NAMES)
    for name in ALL_BOOKS:
        book = books.load(name)
        filled = books.backfill_marks(book, hourly_px.get(pricing.source_for(name)))
        # The daily-frame mark is now only a FALLBACK, for when the hourly source was
        # unavailable. When backfill ran it has already marked through the latest complete
        # hourly bar, which is strictly fresher than the daily close.
        ok = bool(filled) or books.mark(book, now, last)
        books.save(book)
        if verbose:
            extra = f", +{filled} backfilled" if filled else ""
            if ok or filled:
                print(f"  {name:<18} equity ${books.equity(book, last):>12,.0f}"
                      f"  (marked{extra})")
            else:
                print(f"  {name:<18} {'':>19}  (SKIPPED — unpriceable, ledger untouched)")
    carry = run_carry()
    if verbose:
        print(f"  {'carry_btc_eth':<18} equity ${carry['equity']:>12,.0f}  (funding accrued)")
    run_hourly(verbose, hourly_px)
    return write_summary(last)


def run_daily(verbose: bool = True) -> pd.DataFrame:
    px = _prices()
    today = str(px.index[-1].date())
    # One clock for the whole cycle, minute resolution, matching run_mark() (#109). Every
    # book in this pass shares it, so a cycle is one point on the chart rather than a
    # smear -- and it can never sort to midnight the way a bare date did.
    stamp = books.utc_stamp()
    last = px.iloc[-1]
    for name in EQUITY_BOOKS:
        _, freq = signals.REGISTRY[name]
        _run_book(name, freq, signals.target_weights, px, today, last, verbose, stamp)
    for name in PIGGYBACK_BOOKS:
        _, freq = piggyback.REGISTRY[name]
        _run_book(name, freq, piggyback.target_weights, px, today, last, verbose, stamp)
    for name in FACTORY_BOOKS:
        _, freq, _, _ = factory.TEMPLATES[name]
        _run_book(name, freq, factory.target_weights, px, today, last, verbose, stamp)
    for g in GENERATED_BOOKS:
        sig_fn = factory.rebuild_signal(g["family"], g["params"])
        get_weights = _make_generated_get_weights(sig_fn)
        _run_book(g["name"], g["freq"], get_weights, px, today, last, verbose, stamp)
    for c in COMBO_BOOKS:
        _run_book(c["name"], c["freq"], _make_combo_get_weights(c), px, today, last, verbose, stamp)
    carry = run_carry()
    if verbose:
        print(f"  {'carry_btc_eth':<18} equity ${carry['equity']:>12,.0f}  (funding accrued)")
    check_carry_risk()   # writes state/paper/carry_risk.json; never raises, dashboard-only surface
    run_hourly(verbose)
    return write_summary(last)


def write_summary(last_px: pd.Series) -> pd.DataFrame:
    rows, hist = [], []
    # Family L's hourly books (#86) are included only once they exist on disk -- listing a
    # never-run book would report a phantom $100k with no history. They cache their own
    # `equity` because last_px is the DAILY frame and has no BTC-USD/ETH-USD column.
    hourly_live = [n for n in hourly.ALL_NAMES if (STATE_DIR / f"{n}.json").exists()]
    for name in ALL_BOOKS + ["carry_btc_eth"] + hourly_live:
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
