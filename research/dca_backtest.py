"""
dca_backtest.py — "modified double-down DCA" vs plain DCA (#25).

The claim (from an Instagram reel): hold back 25% of your annual investable amount in a
high-yield savings account, and deploy it in tiers when the ETF is far enough off its
52-week high. Extra buy at >=20% off, double extra at >=30% off.

  plain    100% of the monthly contribution into the ETF, always.
  tiered   75% baseline into the ETF; 25% into a reserve earning the real cash rate.
           >=20% off the 252-day high -> deploy 1x baseline extra from reserve.
           >=30% off                  -> deploy 2x baseline extra from reserve.

Both paths contribute the SAME total dollars on the same dates, so terminal wealth is
directly comparable. The reserve cannot go negative: a deploy is capped at its balance.

The question is cash drag. Markets spend most months near a high, and every such month
the held-back 25% earns cash instead of equity. A reserve strategy can look excellent in
a window built around one crash and still lose over a full history.

Methodology note that matters more than it looks: the reserve earns the ACTUAL 13-week
T-bill rate (^IRX), not a flat 4-5%. Rates were near zero from 2009 to 2015 -- assuming
today's yield across the whole sample would flatter the reserve by several thousand
dollars of interest that never existed.

Not evidence, stated plainly: the reel's "grew my portfolio from this to this" is an
unverified before/after graphic, and "comment stock to see what I'm buying" is a lead-gen
funnel. Neither counts either way. The mechanic is tested on its own merits.

Usage: PYTHONPATH=src:. python research/dca_backtest.py [--ticker QQQ]
"""
from __future__ import annotations
import argparse
import os
import numpy as np
import pandas as pd
import yfinance as yf

from harness import ART

ANNUAL = 12_000.0          # investable per year
BASELINE_FRAC = 0.75       # share that always goes straight in
DIP_1, DIP_2 = 0.20, 0.30  # drawdown-from-52wk-high tiers
HIGH_WINDOW = 252


def fetch(ticker, start="1999-01-01"):
    px = yf.download([ticker, "^IRX"], start=start, auto_adjust=True, progress=False,
                     threads=False)["Close"].dropna(how="all")
    px = px.ffill().dropna()
    return px[ticker], px["^IRX"]


def simulate(price, cash_rate, annual=ANNUAL, baseline_frac=BASELINE_FRAC):
    """One pass over the price history, running both strategies on identical dates and
    identical total contributions. Returns (per-strategy result dict, month-bucket log)."""
    monthly = annual / 12.0
    baseline = monthly * baseline_frac
    reserve_add = monthly - baseline

    high52 = price.rolling(HIGH_WINDOW, min_periods=HIGH_WINDOW).max()
    drawdown = price / high52 - 1.0
    # first trading day of each month
    months = price.groupby([price.index.year, price.index.month]).head(1).index
    months = months[high52.reindex(months).notna()]

    plain_sh = tiered_sh = 0.0
    reserve = 0.0
    contributed = 0.0
    flows_plain, flows_tiered, dates = [], [], []
    buckets = {"near_high": 0, "dip20": 0, "dip30": 0}
    starved = 0

    daily_cash = (cash_rate / 100.0 / 252.0).reindex(price.index).ffill().fillna(0.0)

    prev = None
    for d in months:
        if prev is not None:                       # accrue cash between contributions
            reserve *= float((1 + daily_cash.loc[prev:d].iloc[1:]).prod())
        p = float(price.loc[d])
        dd = float(drawdown.loc[d])

        plain_sh += monthly / p                    # plain: everything in
        tiered_sh += baseline / p                  # tiered: baseline in
        reserve += reserve_add

        if dd <= -DIP_2:
            want, buckets["dip30"] = 2 * baseline, buckets["dip30"] + 1
        elif dd <= -DIP_1:
            want, buckets["dip20"] = 1 * baseline, buckets["dip20"] + 1
        else:
            want, buckets["near_high"] = 0.0, buckets["near_high"] + 1
        deploy = min(want, reserve)
        if want > reserve + 1e-9:
            starved += 1
        reserve -= deploy
        tiered_sh += deploy / p

        contributed += monthly
        dates.append(d)
        flows_plain.append(-monthly)
        flows_tiered.append(-monthly)
        prev = d

    end_px = float(price.iloc[-1])
    plain_end = plain_sh * end_px
    tiered_end = tiered_sh * end_px + reserve
    flows_plain.append(plain_end)
    flows_tiered.append(tiered_end)
    dates.append(price.index[-1])

    return ({
        "plain": {"terminal": plain_end, "irr": xirr(flows_plain, dates)},
        "tiered": {"terminal": tiered_end, "irr": xirr(flows_tiered, dates),
                   "reserve_left": reserve, "months_starved": starved},
        "contributed": contributed, "months": len(months),
        "buckets": buckets,
        "start": months[0].date(), "end": price.index[-1].date(),
    })


def xirr(flows, dates):
    """Money-weighted return. Terminal wealth alone can't compare paths whose money went
    in at different times, which is the whole point of a dip-buying overlay."""
    t = np.array([(d - dates[0]).days / 365.25 for d in dates])
    f = np.array(flows, dtype=float)

    def npv(r):
        return float(np.sum(f / (1 + r) ** t))

    # bisection rather than scipy.brentq -- scipy is not a dependency of this repo
    lo, hi = -0.95, 5.0
    f_lo, f_hi = npv(lo), npv(hi)
    if np.isnan(f_lo) or np.isnan(f_hi) or f_lo * f_hi > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


WINDOWS = {
    "full history": "1999-01-01",
    "dot-com onset (2000)": "2000-01-01",
    "GFC onset (2007)": "2007-10-01",
    "covid onset (2020)": "2020-01-01",
    "2022 bear onset": "2022-01-01",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", default="QQQ")
    args = ap.parse_args()

    price, rate = fetch(args.ticker)
    print(f"{args.ticker}: {price.index.min().date()} -> {price.index.max().date()} "
          f"({len(price)} days). Reserve earns the real 13-week T-bill (^IRX), "
          f"mean {rate.mean():.2f}%/yr over the sample.\n")

    rows = []
    for label, start in WINDOWS.items():
        p = price[price.index >= start]
        if len(p) < HIGH_WINDOW + 260:
            continue
        res = simulate(p, rate)
        pl, ti = res["plain"], res["tiered"]
        gap = ti["terminal"] - pl["terminal"]
        b = res["buckets"]
        near = b["near_high"] / res["months"]
        print(f"{label}  ({res['start']} -> {res['end']}, {res['months']} months, "
              f"${res['contributed']:,.0f} contributed)")
        print(f"   plain   ${pl['terminal']:>12,.0f}   IRR {pl['irr']:6.2%}")
        print(f"   tiered  ${ti['terminal']:>12,.0f}   IRR {ti['irr']:6.2%}   "
              f"({gap:+,.0f}, {gap / pl['terminal']:+.2%})")
        print(f"   months near high {near:.0%} | >=20% off {b['dip20'] / res['months']:.0%}"
              f" | >=30% off {b['dip30'] / res['months']:.0%}"
              f" | reserve idle at end ${ti['reserve_left']:,.0f}"
              f" | months reserve too small {ti['months_starved']}")
        print(f"   -> {'tiered wins' if gap > 0 else 'PLAIN DCA WINS'}\n")
        rows.append({"window": label, "start": res["start"], "end": res["end"],
                     "months": res["months"], "contributed": res["contributed"],
                     "plain_terminal": pl["terminal"], "tiered_terminal": ti["terminal"],
                     "plain_irr": pl["irr"], "tiered_irr": ti["irr"],
                     "gap": gap, "pct_months_near_high": near,
                     "reserve_left": ti["reserve_left"]})

    out = pd.DataFrame(rows)
    wins = int((out["gap"] > 0).sum())
    print(f"tiered beats plain in {wins}/{len(out)} windows.")
    print("Cash drag is the mechanism: the reserve only helps in the months it is "
          "deployed, and\nit sits idle the rest of the time. Windows that START at a "
          "crash flatter it most --\nthat is survivorship of the entry date, not an edge.")
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, f"dca_{args.ticker.lower()}.csv")
    out.to_csv(path, index=False)
    print(f"\nwrote {path}")
    return out


if __name__ == "__main__":
    main()
