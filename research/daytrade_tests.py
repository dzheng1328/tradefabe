"""
daytrade_tests.py — two honest tests of day-trading lore on daily bars.

Caveat up front: true 1-minute "wick" scalping can't be backtested cleanly with free data
(yfinance gives only ~60 days of minute bars) AND intraday costs/spread dominate — which is
exactly why ~97% of day traders lose. What we CAN test on daily OHLC:
  A) Stop-losses: do fixed/trailing stops on SPY beat just holding? (they're risk mgmt, not alpha)
  B) Wicks: does buying after a bullish "hammer" (long lower wick) beat the unconditional baseline?
"""
from __future__ import annotations
import numpy as np, pandas as pd, yfinance as yf

ANN, COST_BPS = 252, 5.0


def stat(r):
    r = r.dropna(); eq = (1+r).cumprod()
    return (eq.iloc[-1]**(ANN/len(r))-1, r.mean()/r.std()*np.sqrt(ANN), (eq/eq.cummax()-1).min())


# ---------------- A) stop-loss study on SPY ----------------
def stop_study():
    px = yf.download("SPY", start="2000-01-01", auto_adjust=True, progress=False)["Close"].dropna()
    px = px.iloc[:, 0] if hasattr(px, "columns") else px
    ret = px.pct_change()
    idx = px.index
    ms = pd.Series(idx.to_period("M"), index=idx).ne(pd.Series(idx.to_period("M"), index=idx).shift(1)).values
    P = px.values

    def run(stop=None, trail=None):
        inmkt = np.zeros(len(P)); entry = P[0]; peak = P[0]; live = True
        for t in range(len(P)):
            if live:
                inmkt[t] = 1; peak = max(peak, P[t])
                if (stop and P[t] <= entry*(1-stop)) or (trail and P[t] <= peak*(1-trail)):
                    live = False
            elif ms[t]:                       # re-enter at next month start
                live = True; entry = P[t]; peak = P[t]; inmkt[t] = 1
        w = pd.Series(inmkt, index=idx)
        r = w.shift(1)*ret - w.diff().abs()*(COST_BPS/1e4)
        return stat(r.dropna())

    print(f"A) STOP-LOSSES on SPY buy-and-hold ({idx.min().date()}->{idx.max().date()})")
    print(f"   {'rule':<22}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}")
    rows = [("no stop (buy & hold)", run()), ("fixed -10%", run(stop=.10)),
            ("fixed -20%", run(stop=.20)), ("trailing -10%", run(trail=.10)),
            ("trailing -20%", run(trail=.20))]
    for name, (cg, sh, dd) in rows:
        print(f"   {name:<22}{cg:>7.1%}{sh:>8.2f}{dd:>8.1%}")


# ---------------- B) "wick"/hammer signal ----------------
def wick_study():
    tk = ["SPY","QQQ","NVDA","AMD","AAPL","MSFT","TSLA","AMZN","META","MU","AVGO","JPM","XOM","WMT"]
    raw = yf.download(tk, start="2010-01-01", auto_adjust=True, progress=False, threads=False)
    o, h, l, c = raw["Open"], raw["High"], raw["Low"], raw["Close"]
    all_sig, all_base = [], []
    for t in tk:
        if t not in c: continue
        O, H, L, C = o[t], h[t], l[t], c[t]
        body = (C-O).abs(); rng = (H-L).replace(0, np.nan)
        lower_wick = np.minimum(O, C) - L
        downtrend = C < C.shift(5)                          # after a pullback
        hammer = (lower_wick > 2*body) & ((C-L)/rng > 0.66) & downtrend
        fwd5 = C.shift(-5)/C - 1
        all_sig.append(fwd5[hammer].dropna())
        all_base.append(fwd5.dropna())
    sig = pd.concat(all_sig); base = pd.concat(all_base)
    print(f"\nB) WICK / HAMMER signal — forward 5-day return (pooled across {len(tk)} names)")
    print(f"   after a hammer : {sig.mean():+.3%}   (n={len(sig)})")
    print(f"   any random day : {base.mean():+.3%}   (n={len(base)})")
    print(f"   edge over baseline: {sig.mean()-base.mean():+.3%}  <- ~0 means the wick tells you nothing")


if __name__ == "__main__":
    stop_study()
    wick_study()
