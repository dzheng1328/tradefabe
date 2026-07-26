"""
ict_backtest.py — ICT / Smart-Money-Concepts on hourly bars (#24).

Concepts read on HOURLY bars (where practitioners read them); P&L aggregated to DAILY
and judged with the existing daily doctrine machinery (harness.dsr_gate1, CPCV, ANN=252)
rather than a hand-rolled hourly variant. Signals keep their native timeframe; the verdict
uses vetted code.

Mechanical definitions, per the pre-registration in STRATEGIES.md family J. Practitioner
usage is discretionary; these are one deterministic reading of each concept, parametrized
and tested like anything else. ICT thresholds come from folklore, not published backtests
-- unlike TSMOM (Moskowitz-Ooi-Pedersen 2012) or BAB (Frazzini-Pedersen 2014) -- so they
get no benefit of the doubt.

  fvg             3-bar Fair Value Gap: bar1.high < bar3.low (bullish) / bar1.low >
                  bar3.high (bearish). Trade the gap direction, hold H bars.
  order_block     last opposite-direction bar before an impulse > K * ATR that also breaks
                  an N-bar swing. Trade the impulse direction, hold H bars.
  liquidity_sweep price pierces an N-bar swing extreme then closes back inside within M
                  bars. FADE it (the sweep is the trap), hold H bars.
  mss             market structure shift / CISD: close beyond an N-bar swing pivot. Trade
                  the break direction, hold H bars.
  power_of_3      NOT TESTABLE on this universe -- see note in main().

Honest limits, printed with the results: hourly history is ~2.9 years (yfinance's cap),
against the roster's 2018+ standard. Fewer observations and one macro regime means low
power: a DEAD verdict here is weaker evidence than a DEAD verdict on the daily roster,
and an ALIVE one would need replication before anyone believed it.

Usage: PYTHONPATH=src:. python research/ict_backtest.py [--trials 300]
"""
from __future__ import annotations
import argparse
import os
import numpy as np
import pandas as pd
import yfinance as yf

from tradefabe.engine import COST_BPS, stats, calmar
from harness import (dsr_gate1, bonferroni_bar, family_n_tested, CORR_DIV, DD_MULT,
                     GRAVEYARD, ART)

TICKERS = ["SPY", "QQQ", "IWM"]     # liquid index ETFs: where ICT is actually traded
PERIOD = "730d"                     # yfinance hourly cap
HOLD = 6                            # bars held per signal (~1 session)
SWING_N = 12                        # bars each side for a swing pivot
ATR_N = 24
IMPULSE_K = 1.5                     # impulse = move > K * ATR
SWEEP_M = 3                         # bars allowed to close back inside
NULL_TRIALS = 300


# ---------------------------------------------------------------- data
def fetch():
    raw = yf.download(TICKERS, period=PERIOD, interval="1h", auto_adjust=True,
                      progress=False, threads=False)
    out = {}
    for t in TICKERS:
        df = pd.DataFrame({f: raw[f][t] for f in ("Open", "High", "Low", "Close")}).dropna()
        if len(df) > 500:
            out[t] = df
    return out


def _atr(df, n=ATR_N):
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - df["Close"].shift()).abs(),
                    (df["Low"] - df["Close"].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _swings(df, n=SWING_N):
    """Confirmed pivots: an extreme that stands as the max/min of the surrounding 2n+1
    bars. Shifted forward n bars so the signal only uses information available at the
    time the pivot is CONFIRMED, not when it occurred."""
    hi = df["High"].rolling(2 * n + 1, center=True).max() == df["High"]
    lo = df["Low"].rolling(2 * n + 1, center=True).min() == df["Low"]
    last_hi = df["High"].where(hi).ffill().shift(n)
    last_lo = df["Low"].where(lo).ffill().shift(n)
    return last_hi, last_lo


def _hold(raw, h=HOLD):
    """Turn sparse entry marks into a held position, then lag one bar so a signal formed
    on bar t is only tradeable from t+1."""
    pos = raw.replace(0, np.nan).ffill(limit=h - 1).fillna(0.0)
    return pos.shift(1).fillna(0.0)


# ---------------------------------------------------------------- concepts
def sig_fvg(df):
    bull = df["High"].shift(2) < df["Low"]
    bear = df["Low"].shift(2) > df["High"]
    return _hold(np.sign(bull.astype(float) - bear.astype(float)))


def sig_order_block(df):
    atr = _atr(df)
    ret = df["Close"].diff()
    hi, lo = _swings(df)
    impulse_up = (ret > IMPULSE_K * atr) & (df["Close"] > hi)
    impulse_dn = (ret < -IMPULSE_K * atr) & (df["Close"] < lo)
    return _hold(np.sign(impulse_up.astype(float) - impulse_dn.astype(float)))


def sig_liquidity_sweep(df):
    hi, lo = _swings(df)
    pierced_hi = (df["High"] > hi) & (df["Close"] < hi)
    pierced_lo = (df["Low"] < lo) & (df["Close"] > lo)
    back_hi = pierced_hi.rolling(SWEEP_M).max().astype(bool) & (df["Close"] < hi)
    back_lo = pierced_lo.rolling(SWEEP_M).max().astype(bool) & (df["Close"] > lo)
    # fade: a sweep of highs is a bearish trap, and vice versa
    return _hold(np.sign(back_lo.astype(float) - back_hi.astype(float)))


def sig_mss(df):
    hi, lo = _swings(df)
    up = (df["Close"] > hi) & (df["Close"].shift() <= hi)
    dn = (df["Close"] < lo) & (df["Close"].shift() >= lo)
    return _hold(np.sign(up.astype(float) - dn.astype(float)))


CONCEPTS = {"ict_fvg": sig_fvg, "ict_order_block": sig_order_block,
            "ict_liquidity_sweep": sig_liquidity_sweep, "ict_mss": sig_mss}


# ---------------------------------------------------------------- returns
def daily_returns(data, sig_fn):
    """Position per ticker on hourly bars, equal-weighted, net of per-side cost on
    turnover; summed to a daily return series so the daily doctrine gates apply."""
    per = []
    for t, df in data.items():
        pos = sig_fn(df)
        bar_ret = df["Close"].pct_change().fillna(0.0)
        gross = pos * bar_ret
        cost = pos.diff().abs().fillna(0.0) * (COST_BPS / 1e4)
        per.append((gross - cost).rename(t))
    hourly = pd.concat(per, axis=1).mean(axis=1)
    return hourly.groupby(hourly.index.date).apply(lambda x: (1 + x).prod() - 1).pipe(
        lambda s: pd.Series(s.values, index=pd.DatetimeIndex(s.index)))


def matched_null(data, trials, rng):
    """Luck floor: random entry marks with the SAME trade frequency as the real concepts,
    run through the identical hold/cost/aggregation path. Anything else compares against
    the wrong distribution."""
    rate = np.mean([float((CONCEPTS[c](df) != 0).mean()) for c in CONCEPTS
                    for df in data.values()])
    out = []
    for _ in range(trials):
        def rand_sig(df, rng=rng, rate=rate):
            n = len(df)
            marks = np.where(rng.random(n) < rate / HOLD, rng.choice([-1.0, 1.0], n), 0.0)
            return _hold(pd.Series(marks, index=df.index))
        out.append(stats(daily_returns(data, rand_sig))["Sharpe"])
    return np.array(out)


def bench_daily(data):
    spy = data["SPY"]["Close"].pct_change().fillna(0.0)
    d = spy.groupby(spy.index.date).apply(lambda x: (1 + x).prod() - 1)
    return pd.Series(d.values, index=pd.DatetimeIndex(d.index))


# ---------------------------------------------------------------- verdict
def judge(name, r, bench, null, n_tested):
    s, b = stats(r), stats(bench)
    corr = float(pd.concat([r, bench], axis=1).dropna().corr().iloc[0, 1])
    g1 = dsr_gate1(r, null, n_tested)
    gate2 = (calmar(s) >= calmar(b)) or (abs(corr) < CORR_DIV and calmar(s) > 0)
    gate3 = s["MaxDD"] >= DD_MULT * b["MaxDD"]
    verdict = "ALIVE" if (g1["beats_luck"] and gate2 and gate3) else "DEAD"
    print(f"\n=== {name} ===")
    print(f"  Sharpe {s['Sharpe']:.2f} | Calmar {calmar(s):.2f} | MaxDD {s['MaxDD']:.1%} | corr {corr:+.2f}")
    print(f"  bench  Sharpe {b['Sharpe']:.2f} | Calmar {calmar(b):.2f} | MaxDD {b['MaxDD']:.1%}")
    bar, bar_method, _ = bonferroni_bar(null, n_tested)
    print(f"  DSR {g1['dsr']:.3f} vs SR* {g1['sr_star']:.2f} ({g1['cpcv_n_paths']} CPCV paths)"
          f" | Bonferroni bar {bar:.2f} ({bar_method}, logged only)")
    print(f"  gate1 luck {g1['beats_luck']} | gate2 place {gate2} | gate3 pain {gate3}"
          f"  -> {verdict}")
    return {"strategy": name, "verdict": verdict, "sharpe": s["Sharpe"],
            "calmar": calmar(s), "maxdd": s["MaxDD"], "corr_bench": corr, "dsr": g1["dsr"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trials", type=int, default=NULL_TRIALS)
    args = ap.parse_args()
    rng = np.random.default_rng(20260726)

    data = fetch()
    n_bars = len(next(iter(data.values())))
    span = next(iter(data.values())).index
    print(f"hourly data: {list(data)} | {n_bars} bars | {span.min().date()} -> {span.max().date()}")
    print("power warning: ~2.9yr of hourly history (yfinance cap) vs the roster's 2018+ "
          "standard.\n  One macro regime, few observations -- a DEAD verdict here is "
          "weaker evidence than\n  a DEAD verdict on the daily roster, and an ALIVE one "
          "would need replication.\n")
    print("power_of_3 (AMD): NOT TESTED. It is defined on Asian/London/NY sessions; "
          "US-listed\n  ETFs only trade 09:30-16:00 ET, so the Asian and London sessions "
          "do not exist in\n  this data at all. Testing it here would mean inventing a "
          "session mapping and\n  calling the result ICT. Left untested rather than faked.\n")

    bench = bench_daily(data)
    print(f"building matched null ({args.trials} trials)...")
    null = matched_null(data, args.trials, rng)
    print(f"  null Sharpe: mean {null.mean():.2f}, p95 {np.percentile(null, 95):.2f}")

    rets = {name: daily_returns(data, fn) for name, fn in CONCEPTS.items()}
    names = list(rets)
    n_tested = family_n_tested(names)
    rows = [judge(n, rets[n], bench, null, n_tested) for n in names]

    # complementary pair, not blind enumeration (see the issue's Bonferroni note)
    cm = pd.DataFrame(rets).corr()
    pairs = [(a, b, cm.loc[a, b]) for i, a in enumerate(names) for b in names[i + 1:]]
    a, b, c = min(pairs, key=lambda p: abs(p[2]))
    print(f"\nleast-correlated pair: {a} + {b} (corr {c:+.2f})")
    combo = pd.concat([rets[a], rets[b]], axis=1).dropna().mean(axis=1)
    rows.append(judge(f"ict_combo_{a}_{b}", combo, bench, null, n_tested + 1))

    allmix = pd.DataFrame(rets).dropna().mean(axis=1)
    rows.append(judge("ict_all_concepts", allmix, bench, null, n_tested + 2))

    out = pd.DataFrame(rows)
    os.makedirs(ART, exist_ok=True)
    pd.DataFrame(rets).to_csv(os.path.join(ART, "ict_returns.csv"))
    out.to_csv(os.path.join(ART, "ict_verdicts.csv"), index=False)
    print(f"\n{(out.verdict == 'DEAD').sum()}/{len(out)} DEAD")
    print(f"wrote {ART}/ict_returns.csv and ict_verdicts.csv")
    return out


if __name__ == "__main__":
    main()
