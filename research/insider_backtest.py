"""
insider_backtest.py — real trade-level backtest of corporate insider BUYING (SEC Form 4).

Data: openinsider.com (free aggregator of Form 4 open-market purchases).
Strategy: on each insider purchase, enter the stock the day AFTER the filing is public
(honest disclosure lag), hold H trading days equal-weighted, net of pessimistic costs.
Judged vs SPY/QQQ and vs a permutation null (same event timing, RANDOM tickers from the
same pool) — the honest luck floor for a stock-picking signal.

Caveats it prints: survivorship (delisted tickers absent from yfinance bias results UP),
and small-cap concentration (real spreads/impact far exceed the modeled cost).
"""
from __future__ import annotations
import io, time, os, json, datetime
import numpy as np, pandas as pd, requests
import yfinance as yf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts live in research/, artifacts at repo root
UA   = {"User-Agent": "Mozilla/5.0 tradefabe-research"}
HOLD_DAYS = 21          # research: insider-buy edge is front-loaded in ~days 5-21
COST_BPS  = 20.0        # per-side; small-caps are pricey — deliberately pessimistic
VAL_MIN_K = 100         # only purchases >= $100k (meaningful, higher-signal)
YEARS     = range(2018, 2026)
LIQ_DVOL  = 5e6         # "liquid" = median daily $volume > $5M (tradeable-universe test)
NPERM     = 50
ANN = 252


def fetch_purchases(y0, y1):
    """openinsider screener, purchases only, value>=VAL_MIN_K, quarter by quarter."""
    rows = []
    for y in range(y0, y1):
        for (m0, d0, m1, d1) in [(1,1,3,31),(4,1,6,30),(7,1,9,30),(10,1,12,31)]:
            fdr = f"{m0:02d}%2F{d0:02d}%2F{y}-{m1:02d}%2F{d1:02d}%2F{y}"
            url = ("http://openinsider.com/screener?s=&o=&pl=&ph=&ll=&lh=&fd=0"
                   f"&fdr={fdr}&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&xs="
                   f"&vl={VAL_MIN_K}&vh=&ocl=&och=&sic1=-1&sicl=&sich=&grp=0"
                   "&nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h="
                   "&sortcol=0&cnt=5000&page=1")
            try:
                r = requests.get(url, headers=UA, timeout=60)
                t = pd.read_html(io.StringIO(r.text), attrs={"class": "tinytable"})[0]
                t.columns = [str(c).replace("\xa0", " ").strip() for c in t.columns]
                rows.append(t)
            except Exception as e:
                print(f"  [warn] {y}Q fetch/parse failed: {str(e)[:60]}")
            time.sleep(0.4)
    df = pd.concat(rows, ignore_index=True)
    df = df[df["Trade Type"].astype(str).str.contains("P - Purchase", na=False)].copy()
    df["filing"] = pd.to_datetime(df["Filing Date"], errors="coerce").dt.normalize()
    df["ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
    df["value"]  = (df["Value"].astype(str).str.replace(r"[^0-9.]", "", regex=True)
                    .replace("", np.nan).astype(float))
    df = df.dropna(subset=["filing", "ticker", "value"])
    df = df[df["ticker"].str.fullmatch(r"[A-Z.\-]{1,6}")]
    return df[["filing", "ticker", "value"]].reset_index(drop=True)


def download(tickers, start):
    out = {}
    tickers = list(tickers)
    for i in range(0, len(tickers), 60):
        chunk = tickers[i:i+60]
        try:
            raw = yf.download(chunk, start=start, auto_adjust=True, progress=False, threads=False)
            close = raw["Close"] if "Close" in raw else raw
            vol   = raw["Volume"] if "Volume" in raw else None
            if isinstance(close, pd.Series):
                close = close.to_frame(chunk[0])
            for c in close.columns:
                s = close[c].dropna()
                if len(s) > 250:
                    dv = (close[c] * vol[c]).median() if vol is not None and c in vol else np.nan
                    out[c] = (close[c], dv)
        except Exception as e:
            print(f"  [warn] price chunk failed: {str(e)[:60]}")
        print(f"  priced {min(i+60,len(tickers))}/{len(tickers)}")
    return out


def stats(r):
    r = r.dropna()
    if len(r) < 60:
        return dict(CAGR=np.nan, Sharpe=np.nan, MaxDD=np.nan)
    eq = (1 + r).cumprod()
    return dict(CAGR=eq.iloc[-1] ** (ANN/len(r)) - 1,
                Sharpe=r.mean()/r.std()*np.sqrt(ANN) if r.std() > 0 else np.nan,
                MaxDD=(eq/eq.cummax() - 1).min())


def book_returns(events, rets, tick_idx, dates):
    """overlapping equal-weight book: each event holds its ticker for HOLD_DAYS."""
    T, N = len(dates), rets.shape[1]
    pos = np.zeros((T, N))
    for e_start, e_tk in zip(events["start_i"].values, tick_idx):
        pos[e_start:e_start+HOLD_DAYS, e_tk] += 1.0
    rowsum = pos.sum(axis=1, keepdims=True)
    w = np.divide(pos, rowsum, out=np.zeros_like(pos), where=rowsum > 0)
    wl = np.vstack([np.zeros((1, N)), w[:-1]])              # yesterday's weights: no lookahead
    gross = np.nansum(wl * rets.values, axis=1)
    cost  = np.abs(np.vstack([w[:1], np.diff(w, axis=0)])).sum(axis=1) * (COST_BPS/1e4)
    return pd.Series(gross - cost, index=dates)


def main():
    print("fetching insider purchases from openinsider (2018-2025, >=$100k)...")
    ev = fetch_purchases(2018, 2026)
    print(f"  {len(ev)} purchases, {ev['ticker'].nunique()} unique tickers")
    top = ev.groupby("ticker")["value"].sum().sort_values(ascending=False)
    keep = list(top.index[:700])                            # bound yfinance work
    ev = ev[ev["ticker"].isin(keep)]

    print("downloading prices (many small-caps; delisted names will be missing)...")
    px = download(set(ev["ticker"]) | {"SPY", "QQQ"}, start="2017-06-01")
    have = set(px) - {"SPY", "QQQ"}
    miss = ev["ticker"].nunique() - len(have)
    print(f"  priced {len(have)} tickers; {miss} missing (survivorship — biases results UP)")

    prices = pd.DataFrame({t: px[t][0] for t in px}).sort_index()
    rets_all = prices.pct_change()
    dates = prices.index
    universe = sorted(have)
    col = {t: i for i, t in enumerate(universe)}
    rets = rets_all[universe]

    ev = ev[ev["ticker"].isin(have)].copy()
    entry = ev["filing"].values.astype("datetime64[ns]")
    ev["start_i"] = dates.searchsorted(entry, side="right")  # first trading day AFTER filing
    ev = ev[ev["start_i"] < len(dates)-HOLD_DAYS]
    tick_idx = ev["ticker"].map(col).values
    print(f"  {len(ev)} usable events")

    net = book_returns(ev, rets, tick_idx, dates).dropna()
    spy = rets_all["SPY"].reindex(net.index); qqq = rets_all["QQQ"].reindex(net.index)

    # liquid-only variant (tradeable): tickers with median $vol > LIQ_DVOL
    liq = {t for t in universe if px[t][1] is not None and px[t][1] > LIQ_DVOL}
    ev_l = ev[ev["ticker"].isin(liq)]
    net_l = book_returns(ev_l, rets, ev_l["ticker"].map(col).values, dates).dropna()

    # permutation null: same event timing, RANDOM tickers from the pool
    rng = np.random.default_rng(0); nullsh = []
    allidx = np.arange(len(universe))
    for _ in range(NPERM):
        perm = rng.choice(allidx, size=len(ev))
        v = stats(book_returns(ev, rets, perm, dates).dropna())["Sharpe"]
        if np.isfinite(v): nullsh.append(v)
    nbar = float(np.percentile(nullsh, 95))

    S, Sl = stats(net), stats(net_l)
    B, Q = stats(spy.reindex(net.index)), stats(qqq.reindex(net.index))
    print("\n=== INSIDER BUYING — trade-level backtest ===")
    print(f"  window {net.index.min().date()} -> {net.index.max().date()}  | hold {HOLD_DAYS}d | cost {COST_BPS:.0f}bps/side")
    def row(n, s): print(f"  {n:26s} CAGR {s['CAGR']:6.1%}  Sharpe {s['Sharpe']:5.2f}  MaxDD {s['MaxDD']:6.1%}")
    row("insider (all buys)", S)
    row("insider (liquid only)", Sl)
    row("SPY", B); row("QQQ", Q)
    print(f"  permutation luck floor (random tickers, same timing) p95 Sharpe = {nbar:.2f}")
    beat = S["Sharpe"] > nbar and S["Sharpe"] > B["Sharpe"]
    print(f"  VERDICT (all):    {'BEATS luck & SPY' if beat else 'does NOT clear the bar'}")
    beatl = Sl["Sharpe"] > nbar and Sl["Sharpe"] > B["Sharpe"]
    print(f"  VERDICT (liquid): {'BEATS luck & SPY' if beatl else 'does NOT clear the bar'}  <- the tradeable one")

    os.makedirs(os.path.join(BASE, "artifacts"), exist_ok=True)
    pd.DataFrame({"insider_all": (1+net).cumprod(),
                  "insider_liquid": (1+net_l).cumprod().reindex(net.index),
                  "SPY": (1+spy.reindex(net.index).fillna(0)).cumprod(),
                  "QQQ": (1+qqq.reindex(net.index).fillna(0)).cumprod()}).to_csv(
                      os.path.join(BASE, "artifacts", "insider_curves.csv"))
    with open(os.path.join(BASE, "artifacts", "insider_meta.json"), "w") as f:
        json.dump({"events": int(len(ev)), "tickers_priced": len(have), "tickers_missing": int(miss),
                   "null_p95": round(nbar, 3), "hold_days": HOLD_DAYS, "cost_bps": COST_BPS,
                   "all": {k: round(float(v), 4) for k, v in S.items()},
                   "liquid": {k: round(float(v), 4) for k, v in Sl.items()},
                   "spy": {k: round(float(v), 4) for k, v in B.items()},
                   "generated_at": datetime.datetime.now().isoformat(timespec="seconds")}, f, indent=2)
    print("\nwrote artifacts/insider_curves.csv + insider_meta.json")


if __name__ == "__main__":
    main()
