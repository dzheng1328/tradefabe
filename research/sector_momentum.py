"""
sector_momentum.py — the decisive test of "double down on winners" on a NON-hindsight universe.

Same momentum-concentration rule, but on the 9 SPDR sectors since 1999 — a universe you could
actually rotate forward, and one that INCLUDES the crashes the semis basket conveniently skipped
(dot-com 2000-02, GFC 2008, 2022). If doubling-down-on-winners is real, it survives here. If it
was just NVDA in a hand-picked basket, it reverts to the mean.
"""
from __future__ import annotations
import numpy as np, pandas as pd, yfinance as yf

SECTORS = ["XLK","XLF","XLE","XLV","XLI","XLP","XLU","XLB","XLY"]  # SPDR sectors, ~1999
START, COST_BPS, MOM, ANN = "1999-01-01", 10.0, 63, 252


def stats(r):
    r = r.dropna(); eq = (1+r).cumprod()
    return (eq.iloc[-1]**(ANN/len(r))-1, r.mean()/r.std()*np.sqrt(ANN), (eq/eq.cummax()-1).min())


def main():
    px = yf.download(SECTORS+["SPY"], start=START, auto_adjust=True, progress=False, threads=False)["Close"].dropna(how="all")
    sec = [c for c in SECTORS if c in px.columns]
    prices = px[sec]; rets = prices.pct_change(); N = len(sec)
    per = pd.Series(prices.index.to_period("M"), index=prices.index); ms = per.ne(per.shift(1))

    def rebal(w):
        mask = pd.DataFrame(np.tile(ms.values.reshape(-1,1),(1,w.shape[1])), index=w.index, columns=w.columns)
        w = w.where(mask).ffill().fillna(0.0)
        return ((w.shift(1)*rets).sum(axis=1) - w.diff().abs().sum(axis=1)*(COST_BPS/1e4)).dropna()

    mom = prices/prices.shift(MOM) - 1
    def top_n(n):
        w = (mom.rank(axis=1, ascending=False) <= n).astype(float)
        return rebal(w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0))

    strat = {
        "buyhold_9sectors": rebal(pd.DataFrame(1.0/N, index=prices.index, columns=sec)),
        "top3_momentum":    top_n(3),
        "top1_momentum":    top_n(1),
        "SPY":              px["SPY"].pct_change().dropna(),
    }

    def cal(r, y):
        rr = r[r.index.year == y]; return (1+rr).prod()-1 if len(rr) else np.nan

    print(f"{N} SPDR sectors | {prices.index.min().date()} -> {prices.index.max().date()}\n")
    hdr = f"{'strategy':<20}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'2000':>7}{'2001':>7}{'2002':>7}{'2008':>7}{'2022':>7}"
    print(hdr); print("-"*len(hdr))
    for name, r in strat.items():
        cg, sh, dd = stats(r)
        cells = "".join(f"{cal(r,y):>7.0%}" if np.isfinite(cal(r,y)) else f"{'—':>7}" for y in (2000,2001,2002,2008,2022))
        print(f"{name:<20}{cg:>7.1%}{sh:>8.2f}{dd:>8.1%}{cells}")
    print("\nThe crash columns are the point: this is where concentrated momentum is supposed to break.")


if __name__ == "__main__":
    main()
