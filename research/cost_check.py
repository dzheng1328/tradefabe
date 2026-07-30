"""cost_check.py — empirical slippage check against COST_BPS, via real Alpaca paper fills.

NOT a strategy study. It renders no verdict, touches no graveyard row, and evaluates no
strategy. It measures one thing: how far a real Alpaca PAPER market order's fill price
lands from the reference price quoted immediately before submitting it, in basis points,
and compares that against `engine.COST_BPS` -- the flat per-side turnover cost every
strategy in this lab is charged (`engine.py:29`, currently 5.0bps, "pessimistic").

DOCTRINE.md's "Paper-testing verdicts" section already names "cost realism -- do live fill
costs resemble the backtest's cost assumption" as evidence a paper book can surface from
month 1. This script is that check, run directly against a real (paper) order instead of
waiting months for it to show up as a side effect of a live book.

**This places real Alpaca PAPER orders.** Small notional (default $50/leg), a single
liquid name (SPY), refuses to run at all if the market is closed (a market order queued
outside market hours won't fill on this call, defeating the point). No real money moves --
see CLAUDE.md's hard rule -- but it is genuine order-matching on Alpaca's side, not a
simulation layered on top of one.

**Does not change COST_BPS.** That constant is read by every gate in this lab; if the
measured cost here says it should move, that is a separate, explicit, pre-registered
doctrine amendment (same discipline as every DOCTRINE.md amendment), not a side effect of
running this script. This script's job ends at reporting the number.

Every trial is appended to `artifacts/cost_check.csv` -- a permanent ledger, same
convention as `graveyard.csv`/`generated_templates.csv`, so evidence accumulates across
runs instead of being thrown away between them.

Run (market hours only):
    PYTHONPATH="$(pwd)/src" .venv/bin/python research/cost_check.py
    PYTHONPATH="$(pwd)/src" .venv/bin/python research/cost_check.py --trials 10 --notional 100
"""
from __future__ import annotations

import argparse
import datetime
import os

import numpy as np
import pandas as pd

from tradefabe import broker
from tradefabe.engine import COST_BPS
from tradefabe.paths import ARTIFACTS

LEDGER = os.path.join(ARTIFACTS, "cost_check.csv")
SYMBOL = "SPY"


def _reference_price(symbol: str) -> float:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest
    key_id, secret_key = broker.credentials()
    dc = StockHistoricalDataClient(key_id, secret_key)
    trade = dc.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
    return float(trade[symbol].price)


def round_trip(symbol: str, notional: float) -> dict:
    """One buy-then-sell round trip. Returns a row: reference price at decision time, both
    fill prices, and the round-trip cost in bps relative to twice the reference price (a
    buy AND a sell, matching how engine.py charges turnover cost on both legs)."""
    ref = _reference_price(symbol)

    buy = broker.submit_market_order(symbol, notional, "buy")
    buy_fill = broker.await_fill(buy.id)

    sell = broker.submit_market_order(symbol, notional, "sell")
    sell_fill = broker.await_fill(sell.id)

    # Cost = how much worse than "trade at the reference price with zero friction" this
    # round trip was, as bps of the notional traded -- same units as COST_BPS.
    buy_slip = (buy_fill - ref) / ref
    sell_slip = (ref - sell_fill) / ref
    round_trip_bps = (buy_slip + sell_slip) * 1e4

    return {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol, "notional": notional, "reference_price": round(ref, 4),
        "buy_fill": round(buy_fill, 4), "sell_fill": round(sell_fill, 4),
        "round_trip_bps": round(round_trip_bps, 3),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--notional", type=float, default=50.0)
    ap.add_argument("--symbol", default=SYMBOL)
    args = ap.parse_args()

    if not broker.market_is_open():
        raise SystemExit(
            "Market is closed -- refusing to run. A market order submitted now would "
            "queue instead of filling, and this script needs a same-call fill."
        )

    print(f"[cost_check] {args.trials} round trips on {args.symbol} at "
          f"${args.notional:.0f}/leg (real Alpaca PAPER orders)")
    rows = []
    for i in range(args.trials):
        row = round_trip(args.symbol, args.notional)
        rows.append(row)
        print(f"  trial {i+1}/{args.trials}: ref {row['reference_price']:.2f} | "
              f"buy {row['buy_fill']:.2f} | sell {row['sell_fill']:.2f} | "
              f"round-trip {row['round_trip_bps']:+.2f}bps")

    os.makedirs(ARTIFACTS, exist_ok=True)
    pd.DataFrame(rows).to_csv(LEDGER, mode="a", header=not os.path.exists(LEDGER), index=False)

    bps = np.array([r["round_trip_bps"] for r in rows])
    mean_side_bps = bps.mean() / 2   # round trip = two sides, COST_BPS is per side
    print(f"\n[cost_check] this run: round-trip mean {bps.mean():+.2f}bps "
          f"(std {bps.std(ddof=1):.2f}, n={len(bps)}) -> ~{mean_side_bps:+.2f}bps/side")
    print(f"[cost_check] engine.COST_BPS assumes {COST_BPS:.1f}bps/side -- measured is "
          f"{'inside' if mean_side_bps <= COST_BPS else 'OUTSIDE'} that pessimistic bound "
          f"(this run only; see {LEDGER} for the accumulated ledger across runs).")
    print(f"[cost_check] wrote {len(rows)} row(s) to {LEDGER} -- no COST_BPS or graveyard.csv "
          f"change made. A constant change is a separate, pre-registered doctrine decision.")


if __name__ == "__main__":
    main()
