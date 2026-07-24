"""
harness.py — the reusable evaluation harness that enforces DOCTRINE.md.

Plug in a strategy (a function `prices -> signal matrix` plus a rebalance frequency)
and the harness judges it out-of-sample against:
  1. a DATA-DERIVED noise floor (random strategies through the SAME machinery at the
     SAME rebalance frequency, so fast strategies face a luck bar that pays fast costs),
  2. a fair 60/40 benchmark, and
  3. the pre-registered kill rule.
Every verdict — alive or dead — is appended to graveyard.csv, and render-ready
artifacts are written to artifacts/ for the dashboard (app.py).

Engine core (data, sizing, returns, stats) and signal functions now live in the
installed package (tradefabe.engine / tradefabe.signals); this file keeps only the
doctrine: the noise floor, the fair benchmark, and the three-gate verdict.
"""
from __future__ import annotations
import os
import json
import datetime
import numpy as np
import pandas as pd
from tradefabe.engine import (load_prices, stats, ANN, VOL_WINDOW, TARGET_VOL,
                              MAX_LEG, MAX_GROSS, COST_BPS, LOOKBACK, BASE, BENCH_W,
                              realized_vol, _reb_mask, size_and_rebalance,
                              net_returns, calmar)
from tradefabe.signals import (sig_tsmom_12m as sig_tsmom, sig_tsmom_ensemble,
                               sig_xsec_momentum, sig_green_line_200d as sig_green_line,
                               sig_str_reversal, sig_low_vol,
                               sig_turn_of_month_research as sig_turn_of_month, sig_random)

# ---- frozen doctrine parameters (see DOCTRINE.md) ----
OOS_START   = pd.Timestamp("2018-01-01")
NULL_TRIALS = 500
NULL_PCTILE = 95
CORR_DIV    = 0.30
DD_MULT     = 1.5
GRAVEYARD   = os.path.join(BASE, "graveyard.csv")
ART         = os.path.join(BASE, "artifacts")


# name -> (signal_fn, rebalance freq). Freq is part of the strategy spec, pre-registered.
# turn_of_month uses the research (trading-day) variant; the live paper book uses the
# calendar variant — see tradefabe.signals for why they differ.
STRATEGIES = {
    "tsmom_12m":       (sig_tsmom,          "M"),
    "tsmom_ensemble":  (sig_tsmom_ensemble, "M"),
    "xsec_momentum":   (sig_xsec_momentum,  "M"),
    "green_line_200d": (sig_green_line,     "M"),
    "str_reversal_5d": (sig_str_reversal,   "W"),
    "low_vol_xsec":    (sig_low_vol,        "M"),
    "turn_of_month":   (sig_turn_of_month,  "D"),
}


# ---------- fair benchmark (60/40) ----------
def benchmark_returns(prices):
    cols = [c for c in BENCH_W if c in prices.columns]
    tot  = sum(BENCH_W[c] for c in cols)
    w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    for c in cols:
        w[c] = BENCH_W[c] / tot
    m = _reb_mask(prices.index, "M")
    mask = pd.DataFrame(np.tile(m.values.reshape(-1, 1), (1, w.shape[1])),
                        index=w.index, columns=w.columns)
    w = w.where(mask).ffill().fillna(0.0)
    return net_returns(prices, w)


# ---------- the data-derived noise floor (per rebalance frequency) ----------
def noise_floor(prices, freq, trials=NULL_TRIALS, rv=None):
    if rv is None:
        rv = realized_vol(prices)
    rng = np.random.default_rng(0)
    out = []
    for _ in range(trials):
        r = net_returns(prices, size_and_rebalance(prices, sig_random(prices, rng), freq, rv))
        v = stats(r[r.index >= OOS_START])["Sharpe"]
        if np.isfinite(v):
            out.append(v)
    return np.array(out)


# ---------- doctrine verdict ----------
def evaluate(name, r_full, bench_full, null, freq):
    r_oos = r_full[r_full.index >= OOS_START]
    b_oos = bench_full[bench_full.index >= OOS_START]
    s, b  = stats(r_oos), stats(b_oos)
    both  = pd.concat([r_oos, b_oos], axis=1).dropna()
    corr  = both.iloc[:, 0].corr(both.iloc[:, 1])
    null_bar = float(np.percentile(null, NULL_PCTILE))

    beats_luck = s["Sharpe"] > null_bar
    earns      = (calmar(s) > calmar(b)) or (abs(corr) < CORR_DIV and s["Sharpe"] >= b["Sharpe"])
    dd_ok      = s["MaxDD"] >= DD_MULT * b["MaxDD"]        # both negative
    alive      = bool(beats_luck and earns and dd_ok)

    print(f"\n=== DOCTRINE verdict: {name} (reb {freq}) ===")
    print(f"  strategy  Sharpe {s['Sharpe']:.2f} | Sortino {s['Sortino']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr->bench {corr:.2f}")
    print(f"  benchmark Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}   (60/40)")
    print(f"  noise floor ({freq}-rebalanced random): p{NULL_PCTILE} Sharpe = {null_bar:.2f}")
    print(f"  gate 1  beats luck  : {beats_luck}   ({s['Sharpe']:.2f} > {null_bar:.2f})")
    print(f"  gate 2  earns place : {earns}   (Calmar {calmar(s):.2f} vs {calmar(b):.2f}; |corr| {abs(corr):.2f})")
    print(f"  gate 3  not painful : {dd_ok}   (MaxDD {s['MaxDD']:.1%} vs limit {DD_MULT * b['MaxDD']:.1%})")
    print(f"  VERDICT: {'ALIVE -> promote to forward paper-testing' if alive else 'DEAD -> graveyard, no rescue'}")

    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "strategy": name, "freq": freq, "oos_sharpe": round(s["Sharpe"], 3),
           "oos_sortino": round(s["Sortino"], 3), "oos_calmar": round(calmar(s), 3),
           "oos_maxdd": round(s["MaxDD"], 3), "corr_bench": round(corr, 3),
           "null_p95": round(null_bar, 3), "bench_sharpe": round(b["Sharpe"], 3),
           "bench_calmar": round(calmar(b), 3), "verdict": "ALIVE" if alive else "DEAD"}
    pd.DataFrame([row]).to_csv(GRAVEYARD, mode="a", header=not os.path.exists(GRAVEYARD), index=False)
    return s


def main():
    prices, source = load_prices()
    print(f"data: {source} | {prices.index.min().date()} -> {prices.index.max().date()} | {prices.shape[1]} assets")
    rv    = realized_vol(prices)
    bench = benchmark_returns(prices)

    freqs = sorted({f for _, f in STRATEGIES.values()})
    nulls = {}
    for f in freqs:
        print(f"computing {f}-rebalanced noise floor ({NULL_TRIALS} random strategies)...")
        nulls[f] = noise_floor(prices, f, NULL_TRIALS, rv)

    returns_full = {}
    for name, (fn, freq) in STRATEGIES.items():
        r = net_returns(prices, size_and_rebalance(prices, fn(prices), freq, rv))
        returns_full[name] = r
        evaluate(name, r, bench, nulls[freq], freq)

    # ---- artifacts for the dashboard ----
    os.makedirs(ART, exist_ok=True)
    full = pd.DataFrame(returns_full)
    full["bench_6040"] = bench
    full["spy"] = prices["SPY"].pct_change()
    full = full.dropna(how="all")
    full.to_csv(os.path.join(ART, "full_returns.csv"))
    np.savez(os.path.join(ART, "nulls.npz"), **nulls)
    meta = {"source": source,
            "start": str(prices.index.min().date()), "end": str(prices.index.max().date()),
            "n_assets": int(prices.shape[1]), "universe": list(prices.columns),
            "oos_start": str(OOS_START.date()),
            "null_bars": {f: round(float(np.percentile(v, NULL_PCTILE)), 3) for f, v in nulls.items()},
            "strategy_freq": {k: v[1] for k, v in STRATEGIES.items()},
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(ART, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"\nwrote artifacts/ (full_returns.csv, nulls.npz, meta.json) and appended to graveyard.csv")


if __name__ == "__main__":
    main()
