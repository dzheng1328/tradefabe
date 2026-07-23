"""
carry_backtest.py — crypto funding-rate carry (the one strategy that predicts NOTHING).

Delta-neutral cash-and-carry: long spot + short perpetual, same notional. Price moves cancel;
you collect the funding rate the longs pay the shorts every 8h. Return per period ~= funding
rate received. Market-neutral, so the benchmark is cash (absolute return), not SPY.

Data: OKX public funding-rate-history (free, reachable). Honest costs + the real risks named.
"""
from __future__ import annotations
import time, os, json, datetime
import requests, numpy as np, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts live in research/, artifacts at repo root
H = {"User-Agent": "Mozilla/5.0 tradefabe-research"}
SYMBOLS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
PERIODS_YEAR = 3 * 365          # funding every 8h
FEE_DRAG_YR  = 0.015            # ~1.5%/yr for entry/exit/roll/slippage (pessimistic for a hold book)


def fetch_funding(inst, max_pages=60):
    base = "https://www.okx.com/api/v5/public/funding-rate-history"
    out, after = [], ""
    for _ in range(max_pages):
        url = f"{base}?instId={inst}&limit=100" + (f"&after={after}" if after else "")
        try:
            d = requests.get(url, headers=H, timeout=30).json().get("data", [])
        except Exception as e:
            print(f"  [warn] {inst} page failed: {str(e)[:50]}"); break
        if not d:
            break
        out += d
        after = d[-1]["fundingTime"]
        time.sleep(0.25)
    df = pd.DataFrame(out)
    df["t"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms")
    df["f"] = df["fundingRate"].astype(float)
    return df.set_index("t")["f"].sort_index()


def stats(r):
    r = r.dropna()
    eq = (1 + r).cumprod()
    yrs = len(r) / PERIODS_YEAR
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    sharpe = r.mean() / r.std() * np.sqrt(PERIODS_YEAR) if r.std() > 0 else np.nan
    maxdd = (eq / eq.cummax() - 1).min()
    return cagr, sharpe, maxdd, eq


def main():
    print("pulling OKX funding-rate history (8h) ...")
    series = {}
    for s in SYMBOLS:
        f = fetch_funding(s)
        if len(f) > 100:
            series[s] = f
            print(f"  {s:16s} {len(f)} periods  {f.index.min().date()} -> {f.index.max().date()}")
    fund = pd.DataFrame(series).dropna(how="all")
    # equal-weight book collecting funding across perps; per-period fee drag
    fee = FEE_DRAG_YR / PERIODS_YEAR
    port = fund.mean(axis=1) - fee
    fund_gross = fund.mean(axis=1)

    print("\n=== FUNDING CARRY (delta-neutral, market-neutral) ===")
    print(f"  window {fund.index.min().date()} -> {fund.index.max().date()}  ({len(fund)} funding periods)")
    for s in series:
        cg, sh, dd, _ = stats(fund[s].dropna())
        pos = (fund[s] > 0).mean()
        print(f"  {s:16s} yield {cg:6.1%}/yr  Sharpe {sh:5.2f}  MaxDD {dd:6.1%}  funding+ {pos:.0%} of time")
    cg, sh, dd, eq = stats(port)
    cgg, shg, *_ = stats(fund_gross)
    print(f"  {'PORTFOLIO (net)':16s} yield {cg:6.1%}/yr  Sharpe {sh:5.2f}  MaxDD {dd:6.1%}")
    print(f"  {'  (gross)':16s} yield {cgg:6.1%}/yr  Sharpe {shg:5.2f}")
    print(f"  funding positive {(fund_gross>0).mean():.0%} of all periods "
          f"(when negative, the carry pays YOU-out — regime risk)")

    os.makedirs(os.path.join(BASE, "artifacts"), exist_ok=True)
    (1 + port).cumprod().rename("carry_net").to_csv(os.path.join(BASE, "artifacts", "carry_curve.csv"))
    with open(os.path.join(BASE, "artifacts", "carry_meta.json"), "w") as fh:
        json.dump({"window": [str(fund.index.min().date()), str(fund.index.max().date())],
                   "net_yield": round(float(cg), 4), "net_sharpe": round(float(sh), 3),
                   "net_maxdd": round(float(dd), 4), "gross_yield": round(float(cgg), 4),
                   "pct_funding_positive": round(float((fund_gross > 0).mean()), 3),
                   "fee_drag_yr": FEE_DRAG_YR,
                   "generated_at": datetime.datetime.now().isoformat(timespec="seconds")}, fh, indent=2)
    print("\nwrote artifacts/carry_curve.csv + carry_meta.json")
    print("RISK NOTE: return is real but the risks are structural, not 'no edge' —")
    print("  counterparty (exchange/FTX-style blowup), funding flipping negative in bears,")
    print("  liquidation of the short leg on a violent pump, and stablecoin/depeg risk.")


if __name__ == "__main__":
    main()
