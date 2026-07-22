"""
harness.py — the reusable evaluation harness that enforces DOCTRINE.md v1.0.

Plug in a strategy (a function `prices -> signal matrix`) and the harness judges it
out-of-sample against:
  1. a DATA-DERIVED noise floor (hundreds of random strategies through the same machinery),
  2. a fair 60/40 benchmark, and
  3. the pre-registered kill rule.
Every verdict — alive or dead — is appended to graveyard.csv.
"""
from __future__ import annotations
import os
import datetime
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tsmom_backtest import (load_prices, stats, ANN, VOL_WINDOW, TARGET_VOL,
                            MAX_LEG, MAX_GROSS, COST_BPS, LOOKBACK, BASE)

# ---- frozen doctrine parameters (see DOCTRINE.md v1.0) ----
OOS_START   = pd.Timestamp("2018-01-01")
NULL_TRIALS = 500
NULL_PCTILE = 95
BENCH_W     = {"SPY": 0.60, "IEF": 0.40}
CORR_DIV    = 0.30
DD_MULT     = 1.5
GRAVEYARD   = os.path.join(BASE, "graveyard.csv")


# ---------- shared sizing + engine (identical for every strategy, incl. the null) ----------
def size_and_rebalance(prices, signal):
    rets  = prices.pct_change()
    rv    = rets.rolling(VOL_WINDOW).std() * np.sqrt(ANN)
    raw   = (signal * (TARGET_VOL / rv)).clip(-MAX_LEG, MAX_LEG)
    w     = raw / prices.shape[1]
    gross = w.abs().sum(axis=1)
    scale = (MAX_GROSS / gross).clip(upper=1.0).replace([np.inf, -np.inf], 1.0)
    w = w.mul(scale, axis=0)
    per   = pd.Series(prices.index.to_period("M"), index=prices.index)
    reb   = per.ne(per.shift(1))
    mask  = pd.DataFrame(np.tile(reb.values.reshape(-1, 1), (1, w.shape[1])),
                         index=w.index, columns=w.columns)
    return w.where(mask).ffill().fillna(0.0)


def net_returns(prices, w):
    rets   = prices.pct_change()
    w_exec = w.shift(1)                        # execute next day: no lookahead
    gross  = (w_exec * rets).sum(axis=1)
    cost   = w_exec.diff().abs().sum(axis=1) * (COST_BPS / 1e4)
    return (gross - cost).dropna()


def calmar(s):
    m = s["MaxDD"]
    return s["CAGR"] / abs(m) if (m and np.isfinite(m) and m != 0) else np.nan


# ---------- strategies: prices -> signal matrix ----------
def sig_tsmom(prices):
    return np.sign(prices / prices.shift(LOOKBACK) - 1)


def sig_random(prices, rng):
    return pd.DataFrame(rng.choice([-1.0, 1.0], size=prices.shape),
                        index=prices.index, columns=prices.columns)


# ---------- fair benchmark (60/40) ----------
def benchmark_returns(prices):
    cols = [c for c in BENCH_W if c in prices.columns]
    tot  = sum(BENCH_W[c] for c in cols)
    w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for c in cols:
        w[c] = BENCH_W[c] / tot
    per  = pd.Series(prices.index.to_period("M"), index=prices.index)
    reb  = per.ne(per.shift(1))
    mask = pd.DataFrame(np.tile(reb.values.reshape(-1, 1), (1, w.shape[1])),
                        index=w.index, columns=w.columns)
    w = w.where(mask).ffill().fillna(0.0)
    return net_returns(prices, w)


# ---------- the data-derived noise floor ----------
def noise_floor(prices, trials=NULL_TRIALS):
    rng = np.random.default_rng(0)
    out = []
    for _ in range(trials):
        r = net_returns(prices, size_and_rebalance(prices, sig_random(prices, rng)))
        v = stats(r[r.index >= OOS_START])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


# ---------- doctrine verdict ----------
def evaluate(name, sig_fn, prices, null):
    r_oos = (lambda r: r[r.index >= OOS_START])(net_returns(prices, size_and_rebalance(prices, sig_fn(prices))))
    b_all = benchmark_returns(prices)
    b_oos = b_all[b_all.index >= OOS_START]
    s, b  = stats(r_oos), stats(b_oos)
    both  = pd.concat([r_oos, b_oos], axis=1).dropna()
    corr  = both.iloc[:, 0].corr(both.iloc[:, 1])
    null_bar = float(np.percentile(null, NULL_PCTILE))

    beats_luck = s["Sharpe"] > null_bar
    earns      = (calmar(s) > calmar(b)) or (abs(corr) < CORR_DIV and s["Sharpe"] >= b["Sharpe"])
    dd_ok      = s["MaxDD"] >= DD_MULT * b["MaxDD"]        # both negative
    alive      = bool(beats_luck and earns and dd_ok)

    print(f"\n=== DOCTRINE v1.0 verdict: {name} ===")
    print(f"  strategy  Sharpe {s['Sharpe']:.2f} | Sortino {s['Sortino']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr->bench {corr:.2f}")
    print(f"  benchmark Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}   (60/40)")
    print(f"  noise floor: random p{NULL_PCTILE} Sharpe = {null_bar:.2f}  (mean {null.mean():.2f}, max {null.max():.2f})")
    print(f"  gate 1  beats luck  : {beats_luck}   ({s['Sharpe']:.2f} > {null_bar:.2f})")
    print(f"  gate 2  earns place : {earns}   (Calmar {calmar(s):.2f} vs {calmar(b):.2f}; |corr| {abs(corr):.2f})")
    print(f"  gate 3  not painful : {dd_ok}   (MaxDD {s['MaxDD']:.1%} vs limit {DD_MULT * b['MaxDD']:.1%})")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if alive else 'DEAD -> graveyard, no rescue'}")

    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "oos_sharpe": round(s["Sharpe"], 3),
           "oos_sortino": round(s["Sortino"], 3), "oos_calmar": round(calmar(s), 3),
           "oos_maxdd": round(s["MaxDD"], 3), "corr_bench": round(corr, 3),
           "null_p95": round(null_bar, 3), "bench_sharpe": round(b["Sharpe"], 3),
           "bench_calmar": round(calmar(b), 3), "verdict": "ALIVE" if alive else "DEAD"}
    pd.DataFrame([row]).to_csv(GRAVEYARD, mode="a", header=not os.path.exists(GRAVEYARD), index=False)
    return s, null_bar


def main():
    prices, source = load_prices()
    print(f"data: {source} | {prices.index.min().date()} -> {prices.index.max().date()} | {prices.shape[1]} assets")
    print(f"computing noise floor from {NULL_TRIALS} random strategies (this is the honest pass bar)...")
    null = noise_floor(prices)
    s, null_bar = evaluate("TSMOM_12m_xasset", sig_tsmom, prices, null)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(null, bins=40, color="steelblue", alpha=0.75, label=f"{len(null)} random strategies")
    ax.axvline(null_bar, color="k", ls="--", lw=1, label=f"p{NULL_PCTILE} noise floor = {null_bar:.2f}")
    ax.axvline(s["Sharpe"], color="crimson", lw=2, label=f"TSMOM = {s['Sharpe']:.2f}")
    ax.set_title("Is the strategy distinguishable from luck?  (out-of-sample Sharpe)")
    ax.set_xlabel("OOS Sharpe"); ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(BASE, "noise_floor.png"), dpi=110)
    print("\nwrote noise_floor.png and appended to graveyard.csv")


if __name__ == "__main__":
    main()
