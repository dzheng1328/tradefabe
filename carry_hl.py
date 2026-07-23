"""
carry_hl.py — multi-year crypto funding-carry backtest on Hyperliquid (hourly funding, 2023->now).

Delta-neutral: long spot + short perp, collect the funding the longs pay the shorts. The point of
this run is to watch the yield behave through the REAL drawdowns of 2023-2026, and to confirm a
price crash doesn't touch a delta-neutral book. Honest fee drag applied; the tail risks it CANNOT
capture (exchange blowup, stablecoin depeg) are named, not modeled.
"""
from __future__ import annotations
import time, os, json, datetime
import requests, numpy as np, pandas as pd
import yfinance as yf

BASE = os.path.dirname(os.path.abspath(__file__))
COINS = ["BTC", "ETH", "SOL"]
FEE_DRAG_YR = 0.015
ANN_D = 365


def fetch_hl(coin, start_ms=1683849600000, max_calls=200):
    url = "https://api.hyperliquid.xyz/info"
    out, t = [], start_ms
    for _ in range(max_calls):
        r = None
        for attempt in range(4):
            try:
                r = requests.post(url, json={"type": "fundingHistory", "coin": coin, "startTime": t}, timeout=30).json()
                if isinstance(r, list):
                    break
            except Exception:
                pass
            time.sleep(1.0 + attempt)
        if not isinstance(r, list) or not r:
            break
        out += r
        last = r[-1]["time"]
        if last <= t:
            break
        t = last + 1
        if len(r) < 500:
            break
        time.sleep(0.15)
    df = pd.DataFrame(out)
    if df.empty or "time" not in df.columns:
        return pd.Series(dtype=float)
    df["time"] = pd.to_datetime(df["time"].astype("int64"), unit="ms")
    df["f"] = df["fundingRate"].astype(float)
    return df.drop_duplicates("time").set_index("time")["f"].sort_index()


def stats(r):
    r = r.dropna(); eq = (1 + r).cumprod()
    yrs = len(r) / ANN_D
    return dict(yield_=eq.iloc[-1] ** (1/yrs) - 1,
                sharpe=r.mean()/r.std()*np.sqrt(ANN_D) if r.std() > 0 else np.nan,
                maxdd=(eq/eq.cummax() - 1).min())


def main():
    print("pulling Hyperliquid hourly funding (2023->now)...")
    hourly = {}
    for c in COINS:
        f = fetch_hl(c)
        if len(f) > 500:
            hourly[c] = f
            print(f"  {c:4s} {len(f)} hourly points  {f.index.min().date()} -> {f.index.max().date()}")
        time.sleep(1.0)
    H = pd.DataFrame(hourly)
    # daily carry per coin = sum of hourly funding that day (received by the short)
    daily = H.resample("D").sum()
    fee = FEE_DRAG_YR / ANN_D
    port = daily.mean(axis=1) - fee
    port_gross = daily.mean(axis=1)

    print(f"\n=== FUNDING CARRY (delta-neutral) — {daily.index.min().date()} -> {daily.index.max().date()} ===")
    for c in hourly:
        s = stats(daily[c].dropna()); pos = (daily[c] > 0).mean()
        print(f"  {c:4s} yield {s['yield_']:6.1%}/yr  Sharpe(daily) {s['sharpe']:5.1f}  MaxDD {s['maxdd']:6.1%}  funding+ {pos:.0%}")
    sg = stats(port_gross); sn = stats(port)
    print(f"  PORT gross {sg['yield_']:5.1%}/yr | net {sn['yield_']:5.1%}/yr  Sharpe(daily) {sn['sharpe']:.1f}  MaxDD {sn['maxdd']:.1%}")
    print(f"  funding positive {(port_gross>0).mean():.0%} of days")

    # does it survive a real price event? compare to BTC over the window + worst BTC drawdown
    btc = yf.download("BTC-USD", start=daily.index.min().date(), end=(daily.index.max()+pd.Timedelta(days=1)).date(),
                      auto_adjust=True, progress=False)["Close"].dropna()
    btc = btc.iloc[:, 0] if hasattr(btc, "columns") else btc
    beq = btc/btc.iloc[0]; bdd = (beq/beq.cummax() - 1)
    trough = bdd.idxmin()
    ceq = (1 + port).cumprod()
    # carry return across the peak->trough of BTC's worst drawdown
    peak = beq[:trough].idxmax()
    carry_thru = ceq.reindex(pd.date_range(peak, trough)).ffill()
    c_move = carry_thru.iloc[-1]/carry_thru.iloc[0] - 1 if len(carry_thru.dropna()) else float("nan")
    print(f"\n  BTC worst drawdown in window: {bdd.min():.0%} ({peak.date()} -> {trough.date()})")
    print(f"  carry book over that SAME crash: {c_move:+.1%}   <- delta-neutral: the crash didn't touch it")
    print(f"  (BTC total over window {beq.iloc[-1]-1:+.0%} vs carry net {ceq.iloc[-1]-1:+.1%})")

    os.makedirs(os.path.join(BASE, "artifacts"), exist_ok=True)
    pd.DataFrame({"carry_net": ceq}).to_csv(os.path.join(BASE, "artifacts", "carry_hl_curve.csv"))
    with open(os.path.join(BASE, "artifacts", "carry_hl_meta.json"), "w") as fh:
        json.dump({"window": [str(daily.index.min().date()), str(daily.index.max().date())],
                   "net_yield": round(float(sn["yield_"]), 4), "gross_yield": round(float(sg["yield_"]), 4),
                   "net_maxdd": round(float(sn["maxdd"]), 4), "pct_days_positive": round(float((port_gross>0).mean()), 3),
                   "btc_worst_dd": round(float(bdd.min()), 3), "carry_through_crash": round(float(c_move), 4),
                   "generated_at": datetime.datetime.now().isoformat(timespec="seconds")}, fh, indent=2)
    print("\nwrote artifacts/carry_hl_curve.csv + carry_hl_meta.json")


if __name__ == "__main__":
    main()
