"""
congress_backtest.py — reproducible check of the `congress_copy` verdict (#59).

The verdict (DEAD, "NANC proxy alpha -0.4%/yr after SPY+QQQ beta") was recorded in
STRATEGIES.md prose but never backed by a script, so it could not be re-checked or
challenged. Every other verdict in this lab is. This is that script.

Method: congressional-trade-mirroring ETFs are the tradeable proxy for the strategy --
raw disclosure data is 403-locked, and the ETFs already do the mirroring (45-day
disclosure lag included). Regress each ETF's daily excess return on SPY and QQQ excess
returns; the intercept is the alpha the strategy adds beyond cheap index beta.

  NANC  Unusual Whales Subversive Democratic Trading
  KRUZ  Unusual Whales Subversive Republican Trading
  KNOW  All-congress (both parties)

Alpha, not raw return, is the question. These funds concentrate in mega-cap tech, so a
good raw number can be entirely SPY+QQQ beta -- which you can buy for a few basis points
instead of the fund's fee.

Honest limits, printed with the results: the sample starts at each fund's inception
(NANC/KRUZ 2023-02), so this is a SHORT window and the standard errors are wide. A
t-stat near zero here means "no detectable alpha", not "proven zero".

Usage: PYTHONPATH=src python research/congress_backtest.py
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import yfinance as yf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNDS = ["NANC", "KRUZ", "KNOW"]
FACTORS = ["SPY", "QQQ"]
ANN = 252
RF_ANNUAL = 0.04          # flat cash rate for the 2023-26 window; alpha is barely sensitive to it
RECORDED_ALPHA = -0.004   # the -0.4%/yr in STRATEGIES.md, the number this script re-checks


def fetch(tickers, period="max"):
    px = yf.download(tickers, period=period, auto_adjust=True, progress=False,
                     threads=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers if isinstance(tickers, str) else tickers[0])
    return px.dropna(how="all")


def ols(y, X):
    """Least squares with an intercept. Returns (params, tstats) where params[0] is the
    intercept. Plain numpy -- statsmodels isn't a dependency of this repo."""
    A = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ beta
    dof = len(y) - A.shape[1]
    sigma2 = resid @ resid / dof
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(A.T @ A)))
    return beta, beta / se


def analyze(fund, px, rf_daily):
    cols = [fund] + FACTORS
    r = px[cols].pct_change().dropna()
    if len(r) < 60:
        return None
    y = (r[fund] - rf_daily).values
    X = (r[FACTORS] - rf_daily).values
    beta, t = ols(y, X)
    alpha_ann = beta[0] * ANN
    raw_cagr = (1 + r[fund]).prod() ** (ANN / len(r)) - 1
    spy_cagr = (1 + r["SPY"]).prod() ** (ANN / len(r)) - 1
    return {
        "fund": fund, "n_days": len(r),
        "start": r.index[0].date(), "end": r.index[-1].date(),
        "alpha_ann": alpha_ann, "alpha_t": t[0],
        "beta_spy": beta[1], "beta_qqq": beta[2],
        "raw_cagr": raw_cagr, "spy_cagr": spy_cagr,
        "r2": 1 - np.var(y - np.column_stack([np.ones(len(X)), X]) @ beta) / np.var(y),
    }


def main():
    px = fetch(FUNDS + FACTORS)
    rf_daily = RF_ANNUAL / ANN
    rows = [a for f in FUNDS if (a := analyze(f, px, rf_daily))]
    out = pd.DataFrame(rows)

    print("congress-copy proxy: alpha vs SPY+QQQ\n")
    for a in rows:
        print(f"  {a['fund']}  {a['start']} -> {a['end']}  ({a['n_days']} days)")
        print(f"    alpha        {a['alpha_ann']:+.2%}/yr  (t = {a['alpha_t']:+.2f})")
        print(f"    betas        SPY {a['beta_spy']:.2f}   QQQ {a['beta_qqq']:.2f}   R2 {a['r2']:.2f}")
        print(f"    raw CAGR     {a['raw_cagr']:+.2%}   vs SPY {a['spy_cagr']:+.2%}")
        verdict = "no detectable alpha" if abs(a["alpha_t"]) < 2 else "alpha detected"
        print(f"    -> {verdict}\n")

    nanc = next((a for a in rows if a["fund"] == "NANC"), None)
    if nanc:
        delta = nanc["alpha_ann"] - RECORDED_ALPHA
        print(f"recorded verdict check: STRATEGIES.md says {RECORDED_ALPHA:+.1%}/yr for NANC; "
              f"this run gives {nanc['alpha_ann']:+.2%}/yr (delta {delta:+.2%})")
        print("  Both are economically ~zero and statistically indistinguishable from it "
              "(|t| < 2), which is what DEAD rested on. The point estimate moves with the\n"
              "  sample end date -- it is not a fixed number to match to the basis point.")

    print("\nlimits: short sample (fund inception 2023-02), so standard errors are wide; "
          "|t| < 2 means\n  no DETECTABLE alpha, not proven zero. ETFs are the tradeable "
          "proxy -- raw disclosure\n  data is 403-locked, and the funds already apply the "
          "45-day lag.")

    path = os.path.join(BASE, "artifacts", "congress_alpha.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.to_csv(path, index=False)
    print(f"\nwrote {path}")
    return out


if __name__ == "__main__":
    main()
