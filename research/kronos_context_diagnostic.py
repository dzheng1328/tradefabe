"""kronos_context_diagnostic.py — is Kronos forecasting, or reverting to its own window mean?

NOT a strategy study. It renders no verdict, touches no graveyard row, and evaluates no
returns. It is a diagnostic on the MODEL, run deliberately before family M's study so that
a defect in the pre-registered spec is found before a verdict exists rather than after.

## The finding

`KronosPredictor.predict()` normalizes its context window in-place:

    x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
    x = (x - x_mean) / (x_std + 1e-5)

and generates in that normalized space. On a strongly trending DAILY series the final bar
sits far above (or below) the mean of a long context window, and autoregressive generation
drifts back toward zero — which denormalizes into a large spurious return.

Measured 2026-07-27, `Kronos-base`, 8 tickers, 5-bar horizon, 30 sampled paths:

    context   corr(z_last, fc_ret)   R^2    slope
    128            +0.642            0.41   +0.88% per z
    512            -0.939            0.88   -7.44% per z

At the 512-bar context, **88% of the variance in the forecast is explained by a single
number — where the last bar sits in its own normalization window.** The slope is -7.4% of
forecast 5-day return per z-unit. That is not a forecast; it is normalization drift, and it
would have made `sig_kronos_dir` a dressed-up mean-reversion factor.

Corroborating detail from the same run: SPY daily at context 512 forecast -11.7% while the
realized move was -0.06%, and BTC-USD daily — whose last price sits BELOW its 512-day mean —
forecast +13.3%. Same mechanism, opposite sign, tracking the trend direction.

## Why this is out of the authors' tested regime rather than a bug in their code

Every published Kronos example is intraday: 5-minute A-share bars, an hourly BTC/USDT demo.
Over 512 intraday bars a price barely moves relative to the window mean, so `z_last` stays
small and the artifact is negligible — reproduced here (H3): BTC 1h forecast +0.09% against
a realized +0.17%. The pathology is specific to feeding long contexts of trending daily
bars, which is what family M's pre-registration asked for.

It also suggests the paper's headline metric would not surface this. RankIC is a
cross-sectional RANK correlation, and this artifact ranks assets by how far each sits below
its own trailing mean — a coherent mean-reversion factor that can score respectably on rank
correlation while being useless as a return forecast.

Run:
    PYTHONPATH="$(pwd)/src:$(pwd):$(pwd)/research" .venv/bin/python \
      research/kronos_context_diagnostic.py
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
import yfinance as yf

from tradefabe import kronos

TICKERS = ["SPY", "QQQ", "TLT", "GLD", "XLE", "EEM", "BTC-USD", "IWM"]
CONTEXTS = (128, 512)
N_PATHS = 30
HORIZON = 5


def frame(raw: pd.DataFrame, tkr: str) -> pd.DataFrame:
    """yfinance hands back MultiIndex columns; flatten one ticker to plain OHLCV."""
    return pd.DataFrame({
        "open": raw["Open"][tkr], "high": raw["High"][tkr], "low": raw["Low"][tkr],
        "close": raw["Close"][tkr], "volume": raw["Volume"][tkr],
    }).dropna()


def z_last(ctx: pd.DataFrame) -> float:
    """The last bar's z-score in its own context window — precisely the quantity
    `predict()` normalizes by, and the one that turns out to drive the forecast."""
    return float((ctx["close"].iloc[-1] - ctx["close"].mean()) / ctx["close"].std())


def main():
    if not kronos.is_available():
        raise SystemExit("needs the optional extra: pip install -e '.[kronos]'")
    kronos.predictor("cpu")

    raw = yf.download(TICKERS, start="2022-06-01", auto_adjust=True, progress=False)
    rows = []
    for tkr in TICKERS:
        df = frame(raw, tkr)
        for ctx_len in CONTEXTS:
            end_i = len(df) - 10
            ctx = df.iloc[end_i - ctx_len:end_i]
            y_ts = pd.bdate_range(ctx.index[-1] + pd.Timedelta(days=1), periods=HORIZON)
            t0 = time.time()
            paths = kronos.forecast_paths(ctx, y_ts, n_paths=N_PATHS, seed=1)
            secs = time.time() - t0
            fc = kronos.summarize_paths(paths, float(ctx["close"].iloc[-1]))["fc_ret"]
            actual = float(df["close"].iloc[end_i + HORIZON - 1] / ctx["close"].iloc[-1] - 1)
            rows.append({"ticker": tkr, "context": ctx_len, "z_last": z_last(ctx),
                         "fc_ret": fc, "actual": actual, "secs": secs})
            print(f"  {tkr:8s} ctx={ctx_len:3d}  z_last {rows[-1]['z_last']:+6.2f}   "
                  f"fc {fc:+7.2%}   actual {actual:+6.2%}   ({secs:.1f}s)")

    d = pd.DataFrame(rows)
    print("\n=== does the forecast just track the last bar's position in its window? ===")
    for ctx_len, g in d.groupby("context"):
        r = float(np.corrcoef(g["z_last"], g["fc_ret"])[0, 1])
        slope = float(np.polyfit(g["z_last"], g["fc_ret"], 1)[0])
        print(f"  context={ctx_len:3d}: corr {r:+.3f}   R^2 {r**2:.2f}   "
              f"slope {slope:+.2%} per z   |mean fc| {g['fc_ret'].abs().mean():.2%}   "
              f"|mean actual| {g['actual'].abs().mean():.2%}")

    print("\n  A large NEGATIVE corr means the model walks back toward the context mean.")
    print("  R^2 near 1 means that is essentially ALL the forecast contains.")
    return d


if __name__ == "__main__":
    main()
