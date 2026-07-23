"""
concentrate.py — "double down on the winners." Instead of holding the whole basket, concentrate
into the momentum leaders. Testable version of Dave's idea (double down on what's ALREADY winning;
predicting future winners by judgment is un-backtestable).

Reports full-period risk-adjusted stats AND the 2018 & 2022 tech drawdowns — because the whole
question with concentration is what it does when leadership breaks, not during the bull.
"""
from __future__ import annotations
import numpy as np, pandas as pd, yfinance as yf

BASKET = ["NVDA","AMD","INTC","MU","AVGO","QCOM","TXN","AMAT","LRCX","KLAC",
          "ADI","MRVL","TSM","ASML","MCHP","NXPI"]
START, COST_BPS, MOM, ANN = "2015-01-01", 10.0, 63, 252


def stats(r):
    r = r.dropna(); eq = (1+r).cumprod()
    return (eq.iloc[-1]**(ANN/len(r))-1, r.mean()/r.std()*np.sqrt(ANN), (eq/eq.cummax()-1).min())


def main():
    px = yf.download(BASKET, start=START, auto_adjust=True, progress=False, threads=False)["Close"].dropna(how="all")
    names = [c for c in BASKET if c in px.columns and px[c].notna().sum() > 500]
    prices = px[names]; rets = prices.pct_change(); N = len(names)
    per = pd.Series(prices.index.to_period("M"), index=prices.index); ms = per.ne(per.shift(1))

    def rebal(w):
        mask = pd.DataFrame(np.tile(ms.values.reshape(-1,1),(1,w.shape[1])), index=w.index, columns=w.columns)
        w = w.where(mask).ffill().fillna(0.0)
        return ((w.shift(1)*rets).sum(axis=1) - w.diff().abs().sum(axis=1)*(COST_BPS/1e4)).dropna()

    mom = prices/prices.shift(MOM) - 1

    def top_n(n):
        rank = mom.rank(axis=1, ascending=False)
        w = (rank <= n).astype(float)
        return rebal(w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0))

    momw = mom.clip(lower=0)
    strat = {
        "buyhold_basket (16)": rebal(pd.DataFrame(1.0/N, index=prices.index, columns=names)),
        "top6_momentum":       top_n(6),
        "top3_momentum":       top_n(3),
        "top1_momentum":       top_n(1),
        "momentum_weighted":   rebal(momw.div(momw.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)),
    }

    def cal(r, y):
        rr = r[r.index.year == y]; return (1+rr).prod()-1 if len(rr) else np.nan

    print(f"basket {N} names | {prices.index.min().date()} -> {prices.index.max().date()}\n")
    hdr = f"{'strategy':<22}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'2018':>8}{'2022':>8}"
    print(hdr); print("-"*len(hdr))
    for name, r in strat.items():
        cg, sh, dd = stats(r)
        print(f"{name:<22}{cg:>7.1%}{sh:>8.2f}{dd:>8.1%}{cal(r,2018):>8.0%}{cal(r,2022):>8.0%}")
    print("\n2018 and 2022 are the leadership-break years — that's where concentration is supposed to hurt.")


if __name__ == "__main__":
    main()
