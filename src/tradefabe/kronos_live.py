"""Family M's live monitor-only paper books (#105/#126).

Same relationship to `kronos.py` that `hourly.py` has to family L's study: **the signal
functions live in `kronos.py` and are imported here**, so the function that produced the
verdict and the function running the live book are literally the same object. Two copies
would drift and the live/backtest splice chart would be comparing two different strategies.

WHY THESE BOOKS EXIST AT ALL, given all three candidates are backtest-DEAD
--------------------------------------------------------------------------
Under DOCTRINE v1.2 a backtest-DEAD book is monitor-only forever and can never become
`paper-confirmed`. That is accepted and permanent here. The reason to run them anyway is
stated in STRATEGIES.md family M: this family's *backtest* window is short (288 bars) and
sits entirely inside one regime, whereas every day forward is guaranteed post-cutoff and
unselected. The forward record is the better evidence, and it is the only evidence about
Kronos that cannot be gamed. These books collect it.

Under DOCTRINE v1.6 they are never retired automatically -- see `books.retire`.

WHAT MAKES THIS DIFFERENT FROM EVERY OTHER BOOK SOURCE
------------------------------------------------------
1. **It needs torch and a ~400MB checkpoint.** Every other book is arithmetic on a price
   frame. `run_kronos()` therefore checks `kronos.is_available()` first and returns without
   touching a ledger when the extra is absent -- a machine or CI job without `[kronos]` runs
   a normal cycle and simply doesn't advance these three books. Never raises.
2. **Inference happens once per cycle, for the DAILY run only.** All three books rebalance
   at freq D, so `run_mark()` has nothing to gain from a forecast; it marks them from prices
   like any other book. This is what keeps the hourly job cheap.
3. **Every live forecast is appended to the same snapshot the study used**
   (`artifacts/kronos_forecasts.csv`). Kronos sampling is stochastic, so without the
   snapshot a live position could never be reproduced or audited after the fact. The live
   record and the research record are one file, growing forward.
"""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from . import books, kronos
from .engine import COST_BPS, UNIVERSE, sized_weights

# The three books, and the universe each one needs a forecast for.
DIR_BOOK = "kronos_dir_daily"
WICK_BOOK = "kronos_wick_agg"
CARRY_BOOK = "carry_kronos_vol"

# Which books are actually opened. Dave's criterion for putting family M on live books was
# "only the ones that are profitable" over the clean window, so kronos_dir_daily (Sharpe
# -1.17, negative return) is deliberately NOT here while the other two (+0.69, +3.10) are.
#
# The tension, recorded rather than hidden: selecting which books to OPEN on their backtest
# result is selection-on-result, and it does weaken STRATEGIES.md's claim that the forward
# record is "unselected by construction" -- the forward record is now of two pre-filtered
# books. It is the same kind of selection every promotion in this lab already makes (the
# factory promotes its best-ranked candidate), and it is Dave's explicit call, so it stands.
# Adding DIR_BOOK to this tuple is the one-line change that makes the record unfiltered.
LIVE_BOOKS = (WICK_BOOK, CARRY_BOOK)

# Forecast context: DAILY_CONTEXT bars of model input, plus slack for the signal's own
# lookbacks (HAMMER_PULLBACK) and, for the dir book, sized_weights' 60-bar vol warm-up.
FETCH_DAYS = 420

FORECAST_SNAPSHOT = os.path.join(kronos.ARTIFACT_DIR, "kronos_forecasts.csv")
SNAPSHOT_COLS = ["date", "ticker", "fc_ret", "fc_vol", "fc_hammer"]


def universe_for(name: str) -> list[str]:
    if name == DIR_BOOK:
        return list(UNIVERSE)
    if name == WICK_BOOK:
        return list(kronos.WICK_UNIVERSE)
    return list(kronos.CARRY_COINS)


def tickers_needed(names=LIVE_BOOKS) -> list[str]:
    """Union across the requested books -- SPY/QQQ appear in two universes and must be
    forecast ONCE per date, not once per book."""
    out: set[str] = set()
    for n in names:
        out.update(universe_for(n))
    return sorted(out)


# ----------------------------------------------------------------------------- data
def fetch_ohlcv(tickers: list[str], days: int = FETCH_DAYS) -> dict[str, pd.DataFrame]:
    """Per-ticker OHLCV. Kronos consumes all five columns -- that is what makes the wick
    book expressible -- so this cannot reuse runner._prices(), which is close-only."""
    import yfinance as yf
    raw = yf.download(tickers, period=f"{days}d", auto_adjust=True,
                      progress=False, threads=False)
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = pd.DataFrame({"open": raw["Open"][t], "high": raw["High"][t],
                               "low": raw["Low"][t], "close": raw["Close"][t],
                               "volume": raw["Volume"][t]})
        except KeyError:
            continue
        df = df.dropna()
        if len(df) > kronos.DAILY_CONTEXT:
            out[t] = df
    return out


def drop_current_day(hist: pd.DataFrame, today=None) -> pd.DataFrame:
    """Drop a bar dated TODAY (UTC). `engine.drop_incomplete_tail()` is not enough here.

    That guard trims a partial trailing bar by finding NaNs in the cross-section, which is the
    right test for the daily ETF frame. It cannot see this case: BTC-USD trades 24/7, so
    yfinance returns a row for the in-progress UTC day with all five OHLCV columns populated.
    Nothing is NaN, so the guard keeps it -- and the model gets an intraday snapshot fed to it
    as if it were a daily close.

    Found in production on 2026-07-30 (#126), not in testing: the first cloud cycle wrote
    forecasts dated 2026-07-30 built from a bar a few hours old. Not lookahead -- the price is
    the present, not the future -- but wrong in two ways that matter. It diverges from the
    study, which only ever fed complete daily bars, and forecast_today() skips any (date,
    ticker) already in the snapshot, so that row would have been frozen as THE 07-30 forecast
    and never recomputed once the day actually closed. The snapshot is the audit record.

    A no-op for equities, whose last bar is yesterday's close during a live cycle anyway."""
    if hist.empty:
        return hist
    today = pd.Timestamp(today or dt.datetime.now(dt.UTC).date())
    return hist[pd.DatetimeIndex(hist.index).normalize() < today]


def load_snapshot() -> pd.DataFrame:
    if not os.path.exists(FORECAST_SNAPSHOT):
        return pd.DataFrame(columns=SNAPSHOT_COLS)
    return pd.read_csv(FORECAST_SNAPSHOT, parse_dates=["date"])


def append_snapshot(rows: list[dict]) -> None:
    """Append live forecasts to the research snapshot. Header written only when creating."""
    if not rows:
        return
    os.makedirs(kronos.ARTIFACT_DIR, exist_ok=True)
    new = pd.DataFrame(rows)[SNAPSHOT_COLS]
    header = not os.path.exists(FORECAST_SNAPSHOT)
    new.to_csv(FORECAST_SNAPSHOT, mode="a", header=header, index=False)


def _seed_for(date) -> int:
    """Same date-derived seed the study uses, so a live forecast for a date reproduces
    identically whether it was made by the cycle or replayed by the study."""
    return int(pd.Timestamp(date).strftime("%Y%m%d"))


def forecast_today(ohlcv: dict[str, pd.DataFrame], snapshot: pd.DataFrame) -> list[dict]:
    """One forecast per ticker for the LATEST complete bar, skipping any already stored.

    Strictly causal by construction: the context ends at the last complete bar, so the
    forecast horizon is genuinely unseen. `drop_incomplete_tail` is the caller's job -- see
    run_kronos(), which trims before this is reached."""
    have = set()
    if len(snapshot):
        have = set(zip(pd.to_datetime(snapshot["date"]).dt.date, snapshot["ticker"]))
    rows = []
    for t, hist in sorted(ohlcv.items()):
        d = hist.index[-1]
        if (pd.Timestamp(d).date(), t) in have:
            continue
        ctx = kronos.trim_context(hist)
        horizon = pd.bdate_range(pd.Timestamp(d) + pd.Timedelta(days=1),
                                 periods=kronos.PRED_LEN)
        paths = kronos.forecast_paths(ctx, horizon, seed=_seed_for(d))
        summary = kronos.summarize_paths(paths, float(hist["close"].iloc[-1]))
        rows.append({"date": pd.Timestamp(d).normalize(), "ticker": t, **summary})
    return rows


def forecast_frame(snapshot: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Snapshot -> the (ticker, field) frame kronos.py's signals consume."""
    df = snapshot[snapshot["ticker"].isin(tickers)]
    if df.empty:
        return pd.DataFrame()
    return (df.pivot_table(index="date", columns="ticker",
                           values=["fc_ret", "fc_vol", "fc_hammer"])
              .swaplevel(axis=1).sort_index(axis=1).sort_index())


# ------------------------------------------------------------------------ the books
def dir_weights(fc: pd.DataFrame, px: pd.DataFrame) -> pd.Series:
    """kronos_dir_daily's live target: sign of the forecast return, vol-targeted and capped
    by engine.sized_weights, exactly as the study does and exactly as tsmom_12m does."""
    sig = kronos.sig_kronos_dir(fc).reindex(index=px.index, columns=px.columns)
    return sized_weights(px, sig).iloc[-1].fillna(0.0)


def wick_weights(fc: pd.DataFrame, px: pd.DataFrame) -> pd.Series:
    """kronos_wick_agg's live target. NO sized_weights: the frozen spec is long-only,
    equal-weight, gross 1.0 when any name fires and flat otherwise, with no vol targeting
    and no MAX_LEG cap. Applying sizing here would be running a different strategy than the
    one that was judged."""
    w = kronos.sig_kronos_wick(fc, px)
    if w.empty:
        return pd.Series(dtype=float)
    return w.reindex(columns=px.columns).iloc[-1].fillna(0.0)


def run_price_book(name: str, ohlcv: dict[str, pd.DataFrame], snapshot: pd.DataFrame,
                   verbose: bool = True) -> bool:
    """Rebalance one of the two FORECAST-DRIVEN equity books. Returns True if it advanced."""
    tickers = [t for t in universe_for(name) if t in ohlcv]
    px = pd.DataFrame({t: ohlcv[t]["close"] for t in tickers}).sort_index().dropna(how="all")
    fc = forecast_frame(snapshot, tickers)
    if fc.empty or px.empty:
        if verbose:
            print(f"  {name:<22} (SKIPPED — no forecasts available yet)")
        return False

    book = books.load(name)
    if books.is_retired(book):
        if verbose:
            print(f"  {name:<22} (retired — ledger frozen)")
        return False

    weights = dir_weights(fc, px) if name == DIR_BOOK else wick_weights(fc, px)
    last = px.iloc[-1]
    stamp = books.utc_stamp()
    ok = books.rebalance_to(book, weights, str(px.index[-1].date()), last, COST_BPS,
                            stamp=stamp)
    if ok:
        book["equity"] = round(books.equity(book, last), 2)
    books.save(book)
    if verbose:
        if ok:
            gross = float(np.abs(weights).sum())
            print(f"  {name:<22} equity ${book['equity']:>12,.0f}  "
                  f"(rebalanced, gross {gross:.0%})")
        else:
            print(f"  {name:<22} (SKIPPED — unpriceable, ledger untouched)")
    return ok


def run_carry_kronos(snapshot: pd.DataFrame, verbose: bool = True) -> dict | None:
    """carry_kronos_vol: the always-on carry book's accrual, scaled by the forecast vol.

    Reuses `carry_live._funding_since` rather than re-implementing Hyperliquid's paging --
    one funding fetcher in the codebase, so this book and `carry_btc_eth` can never disagree
    about what the funding actually was. Charges the round trip on BOTH legs whenever the
    scale moves, which is the honest penalty for a continuously-varying notional and is
    exactly what made this candidate lose to always-on carry in the backtest."""
    from .carry_live import _funding_since, FEE_DRAG_YR

    book = books.load(CARRY_BOOK)
    if books.is_retired(book):
        if verbose:
            print(f"  {CARRY_BOOK:<22} (retired — ledger frozen)")
        return None

    fc = snapshot[snapshot["ticker"].isin(kronos.CARRY_COINS)]
    if fc.empty:
        if verbose:
            print(f"  {CARRY_BOOK:<22} (SKIPPED — no crypto forecast yet)")
        return None
    latest = fc.sort_values("date").groupby("ticker").last()
    scale = float(kronos.vol_scale(pd.Series({"v": float(latest["fc_vol"].mean())})).iloc[0])

    now_ms = int(dt.datetime.now(dt.UTC).timestamp() * 1000)
    start = book.get("last_ts") or (now_ms - 24 * 3600 * 1000)
    per_coin = {c.replace("-USD", ""): dict(_funding_since(c.replace("-USD", ""), start + 1))
                for c in kronos.CARRY_COINS}
    stamps = sorted(set().union(*(set(v) for v in per_coin.values())) or set())
    if not stamps:
        if verbose:
            print(f"  {CARRY_BOOK:<22} (SKIPPED — no new funding points)")
        return None

    # First cycle charges NOTHING, matching the study exactly: kronos_backtest.carry_returns
    # computes `turn = pos.diff().abs().fillna(0.0)`, so its first bar pays no adjustment.
    # Defaulting prev_scale to VOL_SCALE_CAP instead billed the book for a 1.0 -> 0.50 move
    # it never made, opening it at $99,957 rather than $100,000 -- a live/backtest divergence
    # manufactured on day one, in the one book whose whole question is whether scaling beats
    # holding.
    prev_scale = float(book.get("vol_scale", scale))
    eq = book.get("equity", books.START_CASH)
    # The scale change is decided ONCE per cycle, so its cost is charged once here rather
    # than per funding point -- charging it per point would invent turnover the book never had.
    eq *= 1 - abs(scale - prev_scale) * 2 * (COST_BPS / 1e4)

    prev_ms = start
    for ts in stamps:
        rates = [per_coin[c][ts] for c in per_coin if ts in per_coin[c]]
        if not rates:
            continue
        days = max((ts - prev_ms) / (24 * 3600 * 1000), 0.0)
        eq *= 1 + scale * (sum(rates) / len(rates) - FEE_DRAG_YR / 365 * days)
        prev_ms = ts
        key = books.utc_stamp(pd.Timestamp(ts, unit="ms"))
        if not any(row[0] == key for row in book["history"]):
            book["history"].append([key, round(eq, 2)])

    book["equity"] = round(eq, 2)
    book["last_ts"] = stamps[-1]
    book["vol_scale"] = scale
    book["last_run"] = dt.datetime.now(dt.UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    books.save(book)
    if verbose:
        print(f"  {CARRY_BOOK:<22} equity ${book['equity']:>12,.0f}  "
              f"(funding accrued at {scale:.0%} notional)")
    return book


# --------------------------------------------------------------------------- entry point
def run_kronos(verbose: bool = True, names=LIVE_BOOKS) -> list[str]:
    """One family M cycle: forecast today, then advance each live book. NEVER RAISES.

    Called from `run_daily()` only, not `run_mark()` -- all three books are freq D, so a
    mark has nothing to gain from a forecast and would pay the whole inference cost for
    nothing. `run_mark()` marks them from prices like any other book.

    Returns the names that advanced, so a caller can tell "not installed" from "ran"."""
    if not names:
        return []
    if not kronos.is_available():
        if verbose:
            print("  [skip] family M books: the [kronos] extra is not installed "
                  "(pip install -e '.[kronos]'). No ledger touched.")
        return []
    try:
        from .engine import drop_incomplete_tail
        ohlcv = fetch_ohlcv(tickers_needed(names))
        # BOTH guards. drop_incomplete_tail catches a partial cross-section; drop_current_day
        # catches the 24/7 case it structurally cannot see. See drop_current_day's docstring.
        ohlcv = {t: drop_current_day(drop_incomplete_tail(d)) for t, d in ohlcv.items()}
        ohlcv = {t: d for t, d in ohlcv.items() if len(d) > kronos.DAILY_CONTEXT}

        snapshot = load_snapshot()
        fresh = forecast_today(ohlcv, snapshot)
        append_snapshot(fresh)
        if verbose and fresh:
            print(f"  [kronos] {len(fresh)} new forecasts on "
                  f"{pd.Timestamp(fresh[0]['date']).date()} "
                  f"(snapshot now {len(snapshot) + len(fresh)} rows)")
        snapshot = pd.concat([snapshot, pd.DataFrame(fresh)], ignore_index=True) \
            if fresh else snapshot

        done = []
        for name in names:
            if name == CARRY_BOOK:
                if run_carry_kronos(snapshot, verbose) is not None:
                    done.append(name)
            elif run_price_book(name, ohlcv, snapshot, verbose):
                done.append(name)
        return done
    except Exception as e:                        # noqa: BLE001 - deliberately broad
        # Same contract run_hourly() has: these are monitor-only books, and a torch OOM or a
        # HuggingFace outage must never take down the cycle that owns the real ledger.
        if verbose:
            print(f"  [warn] family M books skipped this cycle: {str(e)[:110]}")
        return []
