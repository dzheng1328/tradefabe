"""Family M: the Kronos learned-forecaster strategies (#105).

Kronos is a decoder-only transformer over tokenized OHLCV K-lines, pretrained on 12B bars
from 45 exchanges (AAAI 2026, MIT). We use it as a signal source, base weights frozen. The
model code is vendored at a pinned commit under `vendor/kronos_model/` -- see
`vendor/README.md` for why, and for the one patch applied to it.

**Every parameter in the FROZEN block below is pre-registered in STRATEGIES.md family M.
Changing one is a NEW strategy row and a NEW graveyard entry (roster rule 2), not a tweak.**

Three things about this module are load-bearing and easy to get wrong:

1.  **This family's OOS window is NOT 2018.** Kronos's pretraining corpus ends ~2025-06-05,
    so a backtest before that asks the model to predict bars already in its weights. That
    is leakage in the *parameters*, which no CPCV purge or embargo can undo. Use
    `KRONOS_OOS_START`, never `engine.OOS_START`, for any verdict in this family.
    `assert_clean_window()` exists to make the mistake loud.

2.  **The library throws away the sampled paths.** `auto_regressive_inference` ends with
    `np.mean(preds, axis=1)`, so `predict(sample_count=30)` returns a *smoothed point
    forecast*, not a distribution -- there is no spread left to measure. Anything needing
    uncertainty (the vol scale, the synthetic null) must go through `forecast_paths()`,
    which recovers independent draws by replicating the series across the batch dimension
    with `sample_count=1`. Reaching for `predict(...).std()` instead gives you the
    time-series SD of a smoothed path, a different and badly downward-biased quantity.

3.  **torch is imported lazily, inside functions.** The paper engine imports
    `tradefabe.runner`, which must keep working with no `[kronos]` extra installed. Note
    the trap CLAUDE.md records for `desktop.py`: a lazy import means `import tradefabe.kronos`
    SUCCEEDS while the model is unusable, so import alone verifies nothing. `is_available()`
    is the real check, and `tests/test_kronos_lazy_import.py` pins it.

The pure signal functions (`sig_*`, `vol_scale`) take a precomputed forecast frame and need
no torch at all. That split is deliberate: it keeps them cheap, testable in CI without a
400MB download, and identical between the study and any live book -- the drift failure mode
family L's docstring warns about.
"""
from __future__ import annotations

import functools
import os

import numpy as np
import pandas as pd

from .engine import ANN, TARGET_VOL

# ============================ FROZEN -- pre-registered in STRATEGIES.md family M ==========
# Provenance for each value is tabulated there. Do NOT tune. A different value is a new row.
MODEL_REPO = "NeoQuasar/Kronos-base"           # largest OPEN checkpoint (large is unreleased)
TOKENIZER_REPO = "NeoQuasar/Kronos-Tokenizer-base"
MAX_CONTEXT = 512        # hard architectural ceiling for `base` -- not a choice
CLIP = 5                 # library default
T_SAMPLING = 0.6         # authors' own backtest value (finetune/config.py: inference_T)
TOP_P = 0.9              # authors' own (inference_top_p)
TOP_K = 0                # authors' own (inference_top_k), 0 = disabled
SAMPLE_COUNT = 30        # n>=30 floor for an empirical quantile; authors' 5 suffices for a
                         # point forecast but not for the spread vol_scale/null consume
PRED_LEN = 5             # by analogy to existing 5-day specs (sig_str_reversal, wick fwd5)

# Kronos's pretraining corpus ends here (authors' finetune/config.py dataset_end_time, plus
# a test_time_range closing the same day). Everything before is contaminated FOR THIS FAMILY.
PRETRAIN_CUTOFF = pd.Timestamp("2025-06-05")
KRONOS_OOS_START = PRETRAIN_CUTOFF

# `kronos_wick_agg` is the direct successor to research/daytrade_tests.py's wick_study, so it
# inherits that study's universe and its exact hammer test -- applied to FORECAST bars rather
# than realized ones. Same test, different bars, is the whole experiment.
WICK_UNIVERSE = ["SPY", "QQQ", "NVDA", "AMD", "AAPL", "MSFT", "TSLA",
                 "AMZN", "META", "MU", "AVGO", "JPM", "XOM", "WMT"]
HAMMER_BODY_MULT = 2.0    # lower wick must exceed 2x the body
HAMMER_CLOSE_POS = 0.66   # close must sit in the top third of the bar's range
HAMMER_PULLBACK = 5       # only after a 5-bar pullback
HOLD_BARS = 5             # holding period once triggered

CARRY_COINS = ["BTC-USD", "ETH-USD"]
VOL_SCALE_CAP = 1.0       # may de-risk, may NEVER lever past always-on carry -- otherwise it
                          # beats its benchmark on leverage rather than on timing
# =========================================================================================

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "artifacts")

_OHLCV_COLS = ["open", "high", "low", "close", "volume"]


# ----------------------------------------------------------------- availability / loading
def is_available() -> bool:
    """True when the [kronos] extra is actually usable.

    Import of THIS module succeeds without torch by design, so `import tradefabe.kronos`
    proves nothing -- exactly the failure mode CLAUDE.md records for desktop.py, where
    omitting [desktop] left the import fine and the app dead. Call this instead.
    """
    try:
        import torch  # noqa: F401
        import einops  # noqa: F401
        import huggingface_hub  # noqa: F401
        from .vendor.kronos_model import KronosPredictor  # noqa: F401
    except ImportError:
        return False
    return True


def _require():
    if not is_available():
        raise RuntimeError(
            "Kronos needs the optional extra: pip install -e '.[kronos]'. "
            "tradefabe.kronos imports fine without it (torch is lazy), so an import check "
            "will not catch this -- use tradefabe.kronos.is_available()."
        )


def device() -> str:
    """mps on Apple silicon, cuda where present, else cpu."""
    _require()
    import torch
    if torch.cuda.is_available():
        return "cuda:0"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@functools.lru_cache(maxsize=1)
def predictor(dev: str | None = None):
    """The loaded KronosPredictor. Cached -- the weights are a ~400MB download and several
    seconds to materialize, and a walk-forward study calls this once per rebalance date."""
    _require()
    from .vendor.kronos_model import Kronos, KronosTokenizer, KronosPredictor
    tok = KronosTokenizer.from_pretrained(TOKENIZER_REPO)
    mdl = Kronos.from_pretrained(MODEL_REPO)
    mdl.eval()
    return KronosPredictor(mdl, tok, device=dev or device(),
                           max_context=MAX_CONTEXT, clip=CLIP)


def _seed(seed: int):
    """Kronos sampling is stochastic; a verdict has to be reproducible. Seeded per forecast
    date so a resumed or partially re-run study reproduces the same paths per date rather
    than depending on how many forecasts happened to precede it in the process."""
    import torch
    torch.manual_seed(seed)
    np.random.seed(seed % (2**32 - 1))


# ------------------------------------------------------------------------------ forecasting
def forecast_paths(hist: pd.DataFrame, y_timestamp: pd.DatetimeIndex,
                   n_paths: int = SAMPLE_COUNT, seed: int = 0) -> np.ndarray:
    """`n_paths` INDEPENDENT sampled futures, shape (n_paths, len(y_timestamp), 5).

    Columns are open/high/low/close/volume, in price units.

    Why not `predict(sample_count=n)`: that averages the draws away inside the library
    (`auto_regressive_inference` -> `np.mean(preds, axis=1)`) and hands back one smoothed
    path. To keep the distribution we replicate the series `n_paths` times across the BATCH
    dimension with `sample_count=1`, so each replica is sampled independently. Same public
    API, same compute, distribution preserved -- and no second patch to vendored code.
    """
    _require()
    _seed(seed)
    p = predictor()
    hist = hist[_OHLCV_COLS].astype(float)
    x_ts = pd.Series(hist.index)
    out = p.predict_batch(
        df_list=[hist] * n_paths,
        x_timestamp_list=[x_ts] * n_paths,
        y_timestamp_list=[pd.Series(y_timestamp)] * n_paths,
        pred_len=len(y_timestamp),
        T=T_SAMPLING, top_k=TOP_K, top_p=TOP_P, sample_count=1, verbose=False,
    )
    return np.stack([df[_OHLCV_COLS].to_numpy(dtype=float) for df in out])


def summarize_paths(paths: np.ndarray, last_close: float) -> dict:
    """Collapse sampled futures into the three quantities family M's signals consume.

    fc_ret    mean over paths of the PRED_LEN cumulative return -- the point forecast
    fc_vol    ANNUALIZED SD ACROSS PATHS of that same cumulative return. This is the
              model's own disagreement about where price lands, which is what a forward
              vol estimate should be. It is NOT the SD along a single path through time
              (that measures a smoothed trajectory and is biased badly low).
    fc_hammer fraction of paths whose forecast bars contain a hammer, by daytrade_tests.py's
              exact test. A fraction, not a bool, so the threshold stays a signal decision.
    """
    o, h, l, c = paths[:, :, 0], paths[:, :, 1], paths[:, :, 2], paths[:, :, 3]
    cum = c[:, -1] / last_close - 1.0

    horizon_years = paths.shape[1] / ANN
    fc_vol = float(np.std(cum, ddof=1) / np.sqrt(horizon_years)) if len(cum) > 1 else float("nan")

    body = np.abs(c - o)
    rng = np.where((h - l) == 0, np.nan, h - l)
    lower_wick = np.minimum(o, c) - l
    with np.errstate(invalid="ignore"):
        hammer = (lower_wick > HAMMER_BODY_MULT * body) & ((c - l) / rng > HAMMER_CLOSE_POS)
    per_path = np.nansum(hammer, axis=1) > 0

    return {"fc_ret": float(np.mean(cum)), "fc_vol": fc_vol,
            "fc_hammer": float(np.mean(per_path))}


# ----------------------------------------------------------- pure signals (NO torch needed)
# These take a forecast frame -- a DataFrame indexed by the date the forecast was MADE, with
# columns (ticker, field). Splitting them out from inference is what lets CI test the actual
# live-book code path without a 400MB download, and guarantees study and book share one
# function rather than two drifting copies.
def _field(fc: pd.DataFrame, field: str) -> pd.DataFrame:
    return fc.xs(field, axis=1, level=1)


def sig_kronos_dir(fc: pd.DataFrame) -> pd.DataFrame:
    """kronos_dir_daily: long/short on the sign of the forecast PRED_LEN-bar return.

    The vanilla use of the model, deliberately shaped like every other daily book here so
    the comparison is about the forecast and nothing else -- vol targeting and caps are
    applied downstream by engine.sized_weights, exactly as for tsmom_12m.
    """
    return np.sign(_field(fc, "fc_ret")).fillna(0.0)


def sig_kronos_wick(fc: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """kronos_wick_agg: long a name when the model expects a hammer and it has pulled back.

    The OHLC-only signal -- it cannot be expressed by any close-only forecaster, which is
    the entire reason this row exists rather than being a second copy of family A.

    AGGRESSIVE BY PRE-REGISTERED CONSTRUCTION: long-only, equal-weight across triggering
    names, gross 1.0 whenever at least one fires and flat otherwise. No vol targeting, no
    MAX_LEG cap -- unlike every other daily book in this repo. That is the frozen spec, not
    an oversight, and `sized_weights` must NOT be applied on top of it.

    A trigger is held HOLD_BARS bars, matching the forecast horizon: acting on a 5-bar
    forecast and re-deciding tomorrow would charge 5x the turnover for one forecast's worth
    of information.
    """
    hammer = _field(fc, "fc_hammer") > 0.5          # majority of sampled futures
    px = prices.reindex(index=fc.index, columns=hammer.columns)
    pullback = px < px.shift(HAMMER_PULLBACK)        # same precondition as the wick study
    trigger = (hammer & pullback).fillna(False)

    held = trigger.astype(float)
    for k in range(1, HOLD_BARS):                    # carry the trigger forward HOLD_BARS
        held = held + trigger.shift(k).fillna(False).astype(float)
    active = (held > 0).astype(float)

    n = active.sum(axis=1).replace(0, np.nan)        # equal weight, gross 1.0 when any fire
    return active.div(n, axis=0).fillna(0.0)


def vol_scale(fc_vol: pd.Series, target_vol: float = TARGET_VOL) -> pd.Series:
    """carry_kronos_vol: notional = min(1, target_vol / forecast_vol).

    Capped at VOL_SCALE_CAP so the book can de-risk but never lever past always-on carry --
    its benchmark. Without the cap it could beat that benchmark on leverage alone, which
    would answer a different question than the one pre-registered ("does timing beat
    holding?").

    A non-finite or non-positive forecast means the model gave us nothing usable; the
    honest response is full size (behave as always-on carry), not zero -- being flat is an
    active bet that the forecast never made.
    """
    v = pd.to_numeric(fc_vol, errors="coerce")
    scale = target_vol / v.where(np.isfinite(v) & (v > 0))
    return scale.clip(upper=VOL_SCALE_CAP).fillna(VOL_SCALE_CAP)


# ------------------------------------------------------------------------ doctrine guard
def assert_clean_window(index: pd.DatetimeIndex, name: str = "family M"):
    """Refuse to score a family-M verdict on contaminated bars.

    This is a hard guard rather than a comment because the mistake is silent and the result
    looks GOOD when you make it -- a model scored on its own training data produces exactly
    the confident backtest that would get a strategy promoted.
    """
    idx = pd.DatetimeIndex(index)
    bad = idx[idx < PRETRAIN_CUTOFF]
    if len(bad):
        raise ValueError(
            f"{name}: {len(bad)} bars before Kronos's pretraining cutoff "
            f"{PRETRAIN_CUTOFF.date()} (earliest {bad.min().date()}). Those bars are in the "
            f"model's weights -- a verdict on them is contaminated and may not be reported "
            f"as ALIVE. Slice to KRONOS_OOS_START, or label the run CONTAMINATED explicitly."
        )
