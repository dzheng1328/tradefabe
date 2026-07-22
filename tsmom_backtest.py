"""
tsmom_backtest.py — Honest first-slice backtest: cross-asset time-series momentum.

This is the "Executor's step" from our planning: ONE documented strategy, run
through an honest pipeline, before any platform gets built.

Discipline baked in on purpose:
  * Canonical parameters (12-month lookback) — NOT optimized, to avoid overfitting.
  * Signal at day t is applied to returns t -> t+1 (positions shifted 1 day): no lookahead.
  * Monthly rebalance + pessimistic slippage: costs are not hand-waved.
  * In-sample / out-of-sample split with a KILL RULE written before results are seen.
  * Benchmarked against just-buy-SPY, the honest bar to beat.

Run:    python tsmom_backtest.py
Output: prints a metrics table + writes equity_curve.png and results.csv (next to this file).
"""

from __future__ import annotations
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------------------------ CONFIG
UNIVERSE   = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
              "GLD", "SLV", "DBC", "USO", "VNQ", "UUP"]  # ~15 markets for real breadth
START      = "2007-01-01"
LOOKBACK   = 252        # ~12 months, the canonical TSMOM signal (do NOT tune this)
VOL_WINDOW = 60         # trailing window for volatility targeting
TARGET_VOL = 0.10       # annualized vol budget per sleeve
MAX_LEG    = 2.0        # cap per-asset leverage
MAX_GROSS  = 3.0        # cap total gross exposure
COST_BPS   = 5.0        # per-side slippage in bps, charged on turnover (pessimistic)
LONG_SHORT = True       # canonical TSMOM is long/short
SPLIT_DATE = "2018-01-01"   # everything on/after this date is OUT-OF-SAMPLE
BENCH      = "SPY"

# KILL RULE — written before results are seen:
#   The strategy is DEAD unless, out-of-sample and after costs, it delivers
#   Sharpe >= 1.0 AND beats buy-&-hold SPY on Sharpe. No tweaking to rescue it.
KILL_OOS_SHARPE = 1.0

ANN  = 252
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_CACHE = os.path.join(BASE, "data", "prices.csv")


def load_prices():
    """cache -> yfinance -> synthetic fallback. Returns (prices, source_label)."""
    os.makedirs(os.path.dirname(DATA_CACHE), exist_ok=True)
    if os.path.exists(DATA_CACHE):
        px = pd.read_csv(DATA_CACHE, index_col=0, parse_dates=True)
        return px.dropna(how="all"), "cache"
    try:
        import yfinance as yf
        raw = yf.download(UNIVERSE, start=START, auto_adjust=True, progress=False, threads=False)
        px = raw["Close"]
        px = px[[c for c in UNIVERSE if c in px.columns]]
        px = px.dropna(axis=1, how="all")          # drop tickers that failed to download...
        dropped = [t for t in UNIVERSE if t not in px.columns]
        if dropped:                                # ...loudly, so N is sized to real data
            print(f"[warn] no data for {dropped}; proceeding with {list(px.columns)}", file=sys.stderr)
        px = px.dropna(how="all")
        if px.shape[0] < 500 or px.shape[1] < 4:
            raise RuntimeError("insufficient data returned from yfinance")
        px.to_csv(DATA_CACHE)
        return px, "yfinance"
    except Exception as e:  # offline / sandbox fallback so the pipeline still runs end-to-end
        print(f"[warn] live data unavailable ({e}); generating SYNTHETIC data.", file=sys.stderr)
        return _synthetic_prices(), "SYNTHETIC (do not trust the numbers)"


def _synthetic_prices():
    """Correlated GBM so the machinery can be smoke-tested with no network."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(START, periods=ANN * 17)
    n = len(UNIVERSE)
    drift = rng.uniform(0.02, 0.09, n) / ANN
    vol   = rng.uniform(0.10, 0.25, n) / np.sqrt(ANN)
    mkt   = rng.normal(0, 1, len(idx))            # shared factor -> realistic correlation
    beta  = rng.uniform(0.2, 1.0, n)
    rets  = np.zeros((len(idx), n))
    for i in range(n):
        idio = rng.normal(0, 1, len(idx))
        rets[:, i] = drift[i] + vol[i] * (beta[i] * mkt + np.sqrt(max(1 - beta[i] ** 2, 0)) * idio)
    return pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx, columns=UNIVERSE)


def stats(r):
    r = r.dropna()
    if len(r) < 30:
        return {k: np.nan for k in ["CAGR", "Vol", "Sharpe", "Sortino", "MaxDD"]}
    eq = (1 + r).cumprod()
    cagr    = eq.iloc[-1] ** (ANN / len(r)) - 1
    vol     = r.std() * np.sqrt(ANN)
    sharpe  = r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan
    dn      = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(ANN) if dn > 0 else np.nan
    maxdd   = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": maxdd}


def build_weights(prices):
    rets = prices.pct_change()
    # --- signal: sign of trailing 12-month return (canonical TSMOM) ---
    trailing = prices / prices.shift(LOOKBACK) - 1
    signal = np.sign(trailing)
    if not LONG_SHORT:
        signal = signal.clip(lower=0)
    # --- volatility targeting per sleeve ---
    rv  = rets.rolling(VOL_WINDOW).std() * np.sqrt(ANN)
    raw = (signal * (TARGET_VOL / rv)).clip(-MAX_LEG, MAX_LEG)
    w   = raw / prices.shape[1]                      # equal-weight the sleeves
    # --- cap total gross exposure ---
    gross = w.abs().sum(axis=1)
    scale = (MAX_GROSS / gross).clip(upper=1.0).replace([np.inf, -np.inf], 1.0)
    w = w.mul(scale, axis=0)
    # --- monthly rebalance: only change weights on the first trading day of a month ---
    per      = pd.Series(prices.index.to_period("M"), index=prices.index)
    reb_mask = per.ne(per.shift(1))
    mask = pd.DataFrame(np.tile(reb_mask.values.reshape(-1, 1), (1, w.shape[1])),
                        index=w.index, columns=w.columns)
    return w.where(mask).ffill().fillna(0.0)


def main():
    prices, source = load_prices()
    print(f"data source: {source}  |  {prices.index.min().date()} -> {prices.index.max().date()}  |  {prices.shape[1]} assets")
    rets   = prices.pct_change()
    w      = build_weights(prices)
    w_exec = w.shift(1)                                    # execute next day: no lookahead
    gross  = (w_exec * rets).sum(axis=1)
    cost   = w_exec.diff().abs().sum(axis=1) * (COST_BPS / 1e4)
    net    = (gross - cost).dropna()
    bench  = rets[BENCH].reindex(net.index)

    split = pd.Timestamp(SPLIT_DATE)
    seg = {
        "FULL":                       net,
        f"IN-SAMPLE  (<{split.date()})":  net[net.index < split],
        f"OUT-SAMPLE (>={split.date()})": net[net.index >= split],
    }
    print("\n=== TSMOM (net of costs) ===")
    hdr = f"{'segment':<26}{'CAGR':>8}{'Vol':>8}{'Sharpe':>8}{'Sortino':>9}{'MaxDD':>8}"
    print(hdr); print("-" * len(hdr))
    rows = {}
    for name, r in seg.items():
        s = stats(r); rows[name] = s
        print(f"{name:<26}{s['CAGR']:>7.1%}{s['Vol']:>8.1%}{s['Sharpe']:>8.2f}{s['Sortino']:>9.2f}{s['MaxDD']:>8.1%}")

    b_oos = stats(bench[bench.index >= split])
    s_oos = rows[f"OUT-SAMPLE (>={split.date()})"]
    print(f"{'buy&hold ' + BENCH + ' (OOS)':<26}{b_oos['CAGR']:>7.1%}{b_oos['Vol']:>8.1%}{b_oos['Sharpe']:>8.2f}{b_oos['Sortino']:>9.2f}{b_oos['MaxDD']:>8.1%}")

    print("\n=== KILL RULE (written before results) ===")
    passes = (s_oos["Sharpe"] >= KILL_OOS_SHARPE) and (s_oos["Sharpe"] > b_oos["Sharpe"])
    print(f"  need: OOS Sharpe >= {KILL_OOS_SHARPE:.2f}  AND  > buy&hold {BENCH} OOS Sharpe ({b_oos['Sharpe']:.2f})")
    print(f"  got : OOS Sharpe  = {s_oos['Sharpe']:.2f}")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if passes else 'DEAD -> do not tweak to rescue'}")
    if source.startswith("SYNTHETIC"):
        print("  (NOTE: synthetic data — this is a pipeline smoke-test, not a real result.)")

    # artifacts
    eq  = (1 + net).cumprod()
    beq = (1 + bench.reindex(net.index).fillna(0)).cumprod()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7),
                                   gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    ax1.plot(eq.index, eq, label="TSMOM (net)", lw=1.5)
    ax1.plot(beq.index, beq, label=f"buy&hold {BENCH}", lw=1.0, alpha=0.7)
    ax1.axvline(split, color="k", ls="--", lw=0.8)
    ax1.set_yscale("log"); ax1.set_title(f"Cross-asset TSMOM   [source: {source}]")
    ax1.legend(); ax1.grid(alpha=0.3)
    dd = eq / eq.cummax() - 1
    ax2.fill_between(dd.index, dd, 0, color="crimson", alpha=0.4)
    ax2.set_ylabel("drawdown"); ax2.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(BASE, "equity_curve.png"), dpi=110)
    pd.DataFrame(rows).T.to_csv(os.path.join(BASE, "results.csv"))
    print("\nwrote equity_curve.png and results.csv")


if __name__ == "__main__":
    main()
