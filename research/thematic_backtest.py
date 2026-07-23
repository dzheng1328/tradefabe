"""
thematic_backtest.py — does "keep winners, cut losers, take profit at a target" actually beat
just BUYING AND HOLDING the hot basket?

We can't backtest "AI reads the news and picks the sector" (LLM lookahead + the sector was chosen
with hindsight). So we test the part that IS a clean price rule, on a semis/AI basket:
  - buyhold_basket : equal-weight the whole basket (the honest benchmark)
  - keep_winners   : each month hold only names with positive 3-mo momentum, equal weight (Dave's "keep winners / cut losers")
  - target_stop    : buy all; sell a name at +TARGET or -STOP; re-enter next month (Dave's "price target + cut losers")

Fair-comparison note: the basket is survivorship-picked (we KNOW semis won), so absolute returns
are inflated — but rule-vs-buyhold is apples-to-apples because both use the same basket.
"""
from __future__ import annotations
import numpy as np, pandas as pd, yfinance as yf

BASKET = ["NVDA","AMD","INTC","MU","AVGO","QCOM","TXN","AMAT","LRCX","KLAC",
          "ADI","MRVL","TSM","ASML","MCHP","NXPI"]
START, COST_BPS = "2015-01-01", 10.0
MOM_WIN = 63            # 3-mo momentum for keep_winners
TARGET, STOP = 0.25, 0.15   # +25% take-profit / -15% cut (arbitrary retail values; tuning them = overfit)
ANN = 252


def stats(r):
    r = r.dropna(); eq = (1+r).cumprod()
    return dict(CAGR=eq.iloc[-1]**(ANN/len(r))-1,
                Sharpe=r.mean()/r.std()*np.sqrt(ANN) if r.std()>0 else np.nan,
                MaxDD=(eq/eq.cummax()-1).min())


def month_start(idx):
    per = pd.Series(idx.to_period("M"), index=idx)
    return per.ne(per.shift(1))


def main():
    px = yf.download(BASKET+["SPY","SMH"], start=START, auto_adjust=True, progress=False, threads=False)["Close"]
    px = px.dropna(how="all")
    names = [c for c in BASKET if c in px.columns and px[c].notna().sum() > 500]
    print(f"basket: {len(names)} names | {px.index.min().date()} -> {px.index.max().date()}")
    prices = px[names]
    rets = prices.pct_change()
    ms = month_start(prices.index)
    N = len(names)

    def rebal(weight_df, cost=True):
        w = weight_df.where(pd.DataFrame(np.tile(ms.values.reshape(-1,1),(1,weight_df.shape[1])),
                            index=weight_df.index, columns=weight_df.columns)).ffill().fillna(0.0)
        r = (w.shift(1)*rets).sum(axis=1)
        c = w.diff().abs().sum(axis=1)*(COST_BPS/1e4) if cost else 0
        return (r - c).dropna()

    # 1) buy & hold equal weight
    bh = rebal(pd.DataFrame(1.0/N, index=prices.index, columns=names))

    # 2) keep winners: monthly, positive 3-mo momentum only, equal weight among them
    mom = prices/prices.shift(MOM_WIN) - 1
    sel = (mom > 0).astype(float)
    kw_w = sel.div(sel.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    kw = rebal(kw_w)

    # 3) target/stop: buy all; exit a name at +TARGET or -STOP; re-enter at next month start
    inmkt = np.zeros((len(prices), N))
    reenter = ms.values
    P = prices.values
    for j in range(N):
        entry = None
        for t in range(len(prices)):
            p = P[t, j]
            if np.isnan(p):
                continue
            if entry is None:
                if reenter[t]:
                    entry = p; inmkt[t, j] = 1
            else:
                inmkt[t, j] = 1
                chg = p/entry - 1
                if chg >= TARGET or chg <= -STOP:
                    entry = None
    ts_w = pd.DataFrame(inmkt*(1.0/N), index=prices.index, columns=names)
    # target/stop is a DAILY rule — compute directly, don't force it through the monthly mask
    ts = ((ts_w.shift(1)*rets).sum(axis=1) - ts_w.diff().abs().sum(axis=1)*(COST_BPS/1e4)).dropna()

    print("\n=== does the winner/loser/target machinery beat just holding the basket? ===")
    hdr = f"{'strategy':<22}{'CAGR':>9}{'Sharpe':>8}{'MaxDD':>9}"
    print(hdr); print("-"*len(hdr))
    rows = {"buyhold_basket": bh, "keep_winners": kw, f"target_stop (+{int(TARGET*100)}/-{int(STOP*100)})": ts,
            "SPY": yf_ret(px, "SPY"), "SMH": yf_ret(px, "SMH")}
    base = None
    for name, r in rows.items():
        s = stats(r);
        d = f"  (vs buyhold {s['CAGR']-base:+.1%} CAGR)" if base is not None and name!="buyhold_basket" else ""
        if name=="buyhold_basket": base = s["CAGR"]
        print(f"{name:<22}{s['CAGR']:>8.1%}{s['Sharpe']:>8.2f}{s['MaxDD']:>9.1%}{d}")
    print("\ncaveats: basket is hindsight-picked (absolute returns inflated); target/stop levels are")
    print("arbitrary — tuning them to win would be exactly the overfitting the doctrine forbids.")


def yf_ret(px, t):
    return px[t].pct_change().dropna()


if __name__ == "__main__":
    main()
