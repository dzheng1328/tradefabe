"""The strategy factory (#28): a pre-registered TEMPLATE LIBRARY of parametrized,
economically-motivated signal generators across diverse families, plus the pure
selection logic (diverse sampling, correlation-based combo picking) a daily driver
(research/factory_run.py) uses to feed candidates through the SAME doctrine gate
(harness.evaluate(), DSR/CPCV-gated per DOCTRINE v1.4) every hand-tested strategy goes
through -- no lighter bar for being machine-generated.

Why a template library, not free-form generation: "keep searching until you find a
winner" is, unconstrained, the textbook way to manufacture false positives -- this
project's whole identity is refusing to do that. The fix is the same one DOCTRINE.md
already applies to hand-picked candidates: pre-register the search space BEFORE any
result is seen. TEMPLATES below is that pre-registration -- fixed at review time, not
generated at runtime from whatever looks good. Each template has a one-line economic
RATIONALE (same bar STRATEGIES.md holds hand-picked candidates to), not just a
parameter sweep for its own sake.

Every template is a genuinely new, distinct spec (not a re-test of an existing
graveyard.csv name) so family_n_tested() counts each one exactly once. Two families
already in STRATEGIES.md (trend, mean-reversion, defensive, calendar) get new
PARAMETER variants; one new family (breakout/channel, "I") is added for genuine
diversity. ICT/Smart-Money-Concepts (#24) deliberately do NOT appear here: this
project's price cache is Close-only (see engine.load_prices) -- Fair Value Gaps, order
blocks, and liquidity sweeps all need High/Low (or better, intraday) data this repo
doesn't fetch yet. Faking them off Close-only data would mislabel an arbitrary
Close-price heuristic as an ICT concept -- exactly the "honest > convenient" line this
project holds elsewhere. #24 already anticipates this class of blocker for a different
reason (data recency); this is the same blocker for a different field.
"""
from __future__ import annotations
import json
from itertools import combinations

import numpy as np
import pandas as pd

from .paths import STATE_DIR
from .engine import sized_weights


# ---------- template signal generators (parametrized, closures over one config value) ----------
def _make_tsmom(lookback_days):
    def sig(prices):
        return np.sign(prices / prices.shift(lookback_days) - 1)
    return sig


def _make_str_reversal(days):
    def sig(prices):
        return -np.sign(prices / prices.shift(days) - 1)
    return sig


def _make_low_vol_xsec(vol_window):
    def sig(prices):
        vol = prices.pct_change().rolling(vol_window).std()
        pr = vol.rank(axis=1, pct=True)
        return np.sign(0.5 - pr)
    return sig


def _make_turn_of_month(first_n, last_n):
    def sig(prices):
        df = pd.DataFrame(index=prices.index)
        df["g"] = prices.index.to_period("M")
        df["one"] = 1
        pos = df.groupby("g").cumcount() + 1
        tot = df.groupby("g")["one"].transform("size")
        in_tom = (pos <= first_n) | ((tot - pos) < last_n)
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out.loc[in_tom.values, :] = 1.0
        return out
    return sig


def _make_donchian_breakout(window):
    """Long on a new `window`-day high, short on a new `window`-day low, flat
    otherwise -- classic channel-breakout (Donchian/"Turtle Trader" style), a distinct
    edge source from moving-average trend (reacts to a price EXTREME, not an average)."""
    def sig(prices):
        hi = prices.rolling(window).max()
        lo = prices.rolling(window).min()
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[prices >= hi] = 1.0
        out[prices <= lo] = -1.0
        return out
    return sig


# name -> (signal_fn, rebalance freq, one-line economic rationale, family letter).
# Same shape as harness.STRATEGIES (fn, freq) plus the two fields the factory driver and
# the dashboard need that a hand-picked strategy gets from STRATEGIES.md prose instead.
TEMPLATES = {
    "tsmom_3m":  (_make_tsmom(63),  "M",
                  "Trend: sign of the trailing 3-month return -- a faster lookback than "
                  "tsmom_12m, testing whether the underreaction edge shows up sooner.", "A"),
    "tsmom_6m":  (_make_tsmom(126), "M",
                  "Trend: sign of the trailing 6-month return, between tsmom_3m and "
                  "tsmom_12m's lookbacks.", "A"),
    "tsmom_9m":  (_make_tsmom(189), "M",
                  "Trend: sign of the trailing 9-month return.", "A"),
    "tsmom_18m": (_make_tsmom(378), "M",
                  "Trend: sign of the trailing 18-month return -- slower than tsmom_12m, "
                  "testing whether a longer lookback filters more noise than signal.", "A"),
    "tsmom_24m": (_make_tsmom(504), "M",
                  "Trend: sign of the trailing 24-month return, the slowest trend variant "
                  "tested so far.", "A"),
    "str_reversal_3d":  (_make_str_reversal(3),  "W",
                         "Mean reversion: fade the trailing 3-day move -- faster than the "
                         "already-tested 5-day fade.", "B"),
    "str_reversal_10d": (_make_str_reversal(10), "W",
                         "Mean reversion: fade the trailing 10-day move.", "B"),
    "str_reversal_15d": (_make_str_reversal(15), "W",
                         "Mean reversion: fade the trailing 15-day move.", "B"),
    "str_reversal_20d": (_make_str_reversal(20), "W",
                         "Mean reversion: fade the trailing 20-day move -- slower than the "
                         "already-tested 5-day fade, closer to a monthly reversal.", "B"),
    "turn_of_month_narrow": (_make_turn_of_month(2, 2), "D",
                             "Calendar: narrower turn-of-month window (first 2 + last 2 "
                             "trading days) than the already-tested 3+4.", "C"),
    "turn_of_month_wide":   (_make_turn_of_month(5, 5), "D",
                             "Calendar: wider turn-of-month window (first 5 + last 5 trading "
                             "days) than the already-tested 3+4.", "C"),
    "low_vol_xsec_30d":  (_make_low_vol_xsec(30),  "M",
                          "Defensive anomaly: BAB-lite long-calm/short-wild split using a "
                          "faster 30-day vol window than the already-tested 60-day one.", "D"),
    "low_vol_xsec_120d": (_make_low_vol_xsec(120), "M",
                          "Defensive anomaly: BAB-lite split using a slower 120-day vol "
                          "window than the already-tested 60-day one.", "D"),
    "donchian_20d": (_make_donchian_breakout(20), "D",
                     "Breakout: long a new 20-day high, short a new 20-day low -- a "
                     "distinct edge source from moving-average trend (reacts to a price "
                     "EXTREME, not an average); the faster of the two classic Turtle "
                     "Trader channel lengths.", "I"),
    "donchian_55d": (_make_donchian_breakout(55), "D",
                     "Breakout: long a new 55-day high, short a new 55-day low -- the "
                     "slower classic Turtle Trader channel length.", "I"),
}

FAMILY_LABELS = {"I": "Breakout / channel"}   # new family this module introduces


def select_diverse_sample(templates, k, rng, exclude=()):
    """Draw up to `k` template names from `templates`, round-robining across families
    so a single research cycle can't accidentally exhaust one family before ever trying
    another (the "diverse portfolio" requirement -- diversity by construction, not luck).
    `exclude` skips names already logged to graveyard.csv (a re-run of this module
    shouldn't keep re-drawing the same already-tested template forever). Deterministic
    given `rng`; returns fewer than k if the (post-exclude) pool is smaller than k."""
    by_family = {}
    for name, (_, _, _, family) in templates.items():
        if name in exclude:
            continue
        by_family.setdefault(family, []).append(name)
    for names in by_family.values():
        rng.shuffle(names)

    families = list(by_family)
    rng.shuffle(families)
    out = []
    i = 0
    while len(out) < k and any(by_family.values()):
        family = families[i % len(families)]
        if by_family[family]:
            out.append(by_family[family].pop())
        i += 1
        if i > 10_000:      # every family pool exhausted; avoid an infinite loop
            break
    return out


def complementary_pairs(returns, names, top_k=3):
    """Rank every pair among `names` (columns of the `returns` DataFrame) by ascending
    |correlation| -- the "correlation analysis to pick genuinely complementary pairs, not
    every subset" approach #24/#28 both call for, generalizing piggyback.py's
    combinations search beyond one fixed leg pool. Returns up to `top_k` (name_a, name_b,
    corr) tuples, least-correlated first -- candidates for a piggyback-style construction,
    not automatically blended/evaluated here (that's the existing piggyback.py machinery,
    reusable as-is once a pair is chosen)."""
    cm = returns[list(names)].corr()
    pairs = []
    for a, b in combinations(names, 2):
        c = cm.loc[a, b]
        if np.isfinite(c):
            pairs.append((a, b, float(c)))
    pairs.sort(key=lambda t: abs(t[2]))
    return pairs[:top_k]


def target_weights(prices, name):
    """Today's vol-targeted, capped portfolio weights for a promoted template -- same
    contract as signals.target_weights()/piggyback.target_weights(), so runner.py can
    call whichever registry a book came from identically (#29's "zero special-casing"
    requirement)."""
    sig_fn, _, _, _ = TEMPLATES[name]
    return sized_weights(prices, sig_fn(prices)).iloc[-1].fillna(0.0)


# ---------- promotion registry (#29): which factory candidates run.py should treat as
# real live books. A plain JSON list of names, not the templates/signal functions
# themselves -- those already live in TEMPLATES (an importable module-level dict), so the
# only thing that needs to persist ACROSS PROCESSES (factory_run.py's cycle exits; the
# next `tradefabe run` is a fresh process) is which names were promoted. ----------
PROMOTED_PATH = STATE_DIR / "promoted.json"


def load_promoted():
    """Every currently-promoted template name, filtered to ones still present in
    TEMPLATES (defensive: if a template is ever removed from the library, a stale
    promoted.json entry shouldn't crash runner.py -- it just stops being a live book)."""
    if not PROMOTED_PATH.exists():
        return []
    with open(PROMOTED_PATH) as fh:
        names = json.load(fh)
    return [n for n in names if n in TEMPLATES]


def promote(name):
    """Registers `name` (must be a TEMPLATES key) as a live paper book, idempotently --
    calling this again for an already-promoted name is a no-op, not a duplicate entry.
    Does NOT open the book's state file itself: the next `tradefabe run` naturally
    creates it at $100k on first encounter, exactly like any other new book (books.load()
    on a name with no existing state/paper/<name>.json file already does this)."""
    if name not in TEMPLATES:
        raise ValueError(f"{name} is not a registered template -- only a TEMPLATES key "
                         "can be promoted, no ad-hoc names")
    promoted = load_promoted()
    if name in promoted:
        return
    promoted.append(name)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROMOTED_PATH, "w") as fh:
        json.dump(promoted, fh, indent=1)
