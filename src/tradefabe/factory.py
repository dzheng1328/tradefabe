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
import datetime
import json
import os
from itertools import combinations

import numpy as np
import pandas as pd

from .paths import STATE_DIR, REPO_ROOT
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


# ---------- live template generation (#28b) ----------
# TEMPLATES above is a fixed, hand-reviewed list -- it runs dry (15 entries). Rather than
# generating templates freely at runtime (which would reintroduce exactly the meta-level
# p-hacking DOCTRINE.md's own opening section warns against: tuning what gets tried
# based on what you've already seen), the PARAMETER RANGE per family is what's
# pre-registered here -- fixed once, reviewed like everything else in this file -- and
# only the SPECIFIC value drawn is randomized at runtime. Every draw is logged to
# GENERATED_LEDGER (git-tracked, append-only) at generation time, before its verdict is
# known, so there's no opportunity to selectively keep only favorable-looking generated
# candidates out of the record -- the same "the count IS the record" principle
# graveyard.csv already embodies, applied to the generation process itself.
#
# Ranges only cover families whose signal needs nothing but Close prices (this project's
# cache -- see engine.load_prices) and a single integer parameter: A/B/D/I from TEMPLATES
# above, plus C (two integers). E (carry), F (VRP), G (info) all need external data
# pipelines this repo doesn't have -- same boundary TEMPLATES itself already draws.
GENERATION_RANGES = {
    "A": {"lookback_days": (10, 504)},      # trend: ~2wk to 24mo
    "B": {"days": (2, 40)},                 # mean reversion: 2-40 day fade window
    "C": {"first_n": (1, 8), "last_n": (1, 8)},   # calendar: turn-of-month window width
    "D": {"vol_window": (10, 180)},         # defensive: vol-ranking window
    "I": {"window": (10, 120)},             # breakout: channel length
}
_GENERATION_MAKERS = {
    "A": _make_tsmom, "B": _make_str_reversal, "C": _make_turn_of_month,
    "D": _make_low_vol_xsec, "I": _make_donchian_breakout,
}
_GENERATION_FREQ = {"A": "M", "B": "W", "C": "D", "D": "M", "I": "D"}


def _generated_name(family, params):
    if family == "A":
        return f"tsmom_gen_{params['lookback_days']}d"
    if family == "B":
        return f"str_reversal_gen_{params['days']}d"
    if family == "C":
        return f"turn_of_month_gen_{params['first_n']}_{params['last_n']}"
    if family == "D":
        return f"low_vol_xsec_gen_{params['vol_window']}d"
    if family == "I":
        return f"donchian_gen_{params['window']}d"
    raise ValueError(f"no naming rule for family {family!r}")


def _generated_rationale(family, params):
    if family == "A":
        return f"Trend (generated): sign of the trailing {params['lookback_days']}-day return."
    if family == "B":
        return f"Mean reversion (generated): fade the trailing {params['days']}-day move."
    if family == "C":
        return (f"Calendar (generated): turn-of-month window, first {params['first_n']} + "
                f"last {params['last_n']} trading days.")
    if family == "D":
        return (f"Defensive anomaly (generated): BAB-lite split using a "
                f"{params['vol_window']}-day vol-ranking window.")
    if family == "I":
        return (f"Breakout (generated): long a new {params['window']}-day high, short a "
                f"new {params['window']}-day low.")
    raise ValueError(f"no rationale template for family {family!r}")


def generate_candidate(rng, family, exclude_names=()):
    """Draws a fresh parameter (or pair, for family C) for `family` from
    GENERATION_RANGES -- the pre-registered valid range, fixed here and not adjusted
    based on results -- and builds a full candidate spec, same shape as a TEMPLATES
    entry plus the params needed to reconstruct the signal fn in a later process (see
    rebuild_signal()). Retries on a name collision with `exclude_names` up to a bounded
    number of attempts (a fresh integer draw colliding is rare but not impossible);
    returns None if it can't find a fresh name in that many tries rather than looping
    forever on a near-exhausted range."""
    ranges = GENERATION_RANGES[family]
    maker = _GENERATION_MAKERS[family]
    for _ in range(50):
        params = {k: int(rng.integers(lo, hi + 1)) for k, (lo, hi) in ranges.items()}
        name = _generated_name(family, params)
        if name in exclude_names:
            continue
        return {"name": name, "sig_fn": maker(**params), "freq": _GENERATION_FREQ[family],
                "rationale": _generated_rationale(family, params), "family": family,
                "params": params, "source": "generated"}
    return None


def rebuild_signal(family, params):
    """Reconstructs the exact signal function for a generated candidate from its
    persisted family+params -- used by runner.py to rebalance a promoted generated book
    in a FRESH process (generate_candidate()'s own closure doesn't survive across
    processes; the maker+params fully and deterministically reproduce the same signal)."""
    return _GENERATION_MAKERS[family](**params)


GENERATED_LEDGER = REPO_ROOT / "generated_templates.csv"


def generated_names():
    """Every name ever logged to GENERATED_LEDGER -- so a later cycle doesn't re-generate
    (and re-log) the same exact spec, mirroring how graveyard_strategy_names() prevents
    re-testing an already-logged strategy."""
    if not os.path.exists(GENERATED_LEDGER):
        return set()
    return set(pd.read_csv(GENERATED_LEDGER)["name"].unique())


def log_generated(spec):
    """Appends a generated candidate's full spec to the git-tracked audit ledger --
    called at GENERATION time, before its backtest verdict is known, so every candidate
    ever generated is on the record whether it lives or dies (no file-drawer problem)."""
    row = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
           "name": spec["name"], "family": spec["family"], "freq": spec["freq"],
           "params": json.dumps(spec["params"]), "rationale": spec["rationale"]}
    pd.DataFrame([row]).to_csv(GENERATED_LEDGER, mode="a",
                               header=not os.path.exists(GENERATED_LEDGER), index=False)


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


# ---------- promotion registry for GENERATED candidates (#28b) ----------
# Separate from PROMOTED_PATH above: a generated candidate's signal function doesn't
# live in any importable module-level dict the way TEMPLATES entries do, so runner.py
# needs family+params (not just a name) to call rebuild_signal() in a fresh process.
PROMOTED_GENERATED_PATH = STATE_DIR / "promoted_generated.json"


def load_promoted_generated():
    """Every currently-promoted GENERATED candidate, as full {"name", "family", "freq",
    "params"} dicts -- unlike load_promoted() (TEMPLATES-name-only), runner.py needs
    family+params here to reconstruct the exact signal function via rebuild_signal()."""
    if not PROMOTED_GENERATED_PATH.exists():
        return []
    with open(PROMOTED_GENERATED_PATH) as fh:
        return json.load(fh)


def promote_generated(spec):
    """Registers a generated candidate (a dict shaped like generate_candidate()'s
    return value) as a live paper book, idempotent by name."""
    entries = load_promoted_generated()
    if any(e["name"] == spec["name"] for e in entries):
        return
    entries.append({"name": spec["name"], "family": spec["family"],
                    "freq": spec["freq"], "params": spec["params"]})
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROMOTED_GENERATED_PATH, "w") as fh:
        json.dump(entries, fh, indent=1)


# ---------- promotion registry for correlation-picked COMBOS (#64) ----------
# The third registry, and the reason it exists: factory_run.py builds one combo per cycle
# from the least-correlated pair, but until now it could never become a live book --
# piggyback.REGISTRY is a fixed hand-picked dict, so the factory could promote a
# single-strategy candidate it discovered and not a COMBO it discovered. That asymmetry
# was an unfinished wiring job, not a doctrine choice.
#
# A combo carries its legs' full specs (not just names) for the same reason
# PROMOTED_GENERATED_PATH does: a generated leg's signal function exists in no importable
# module-level dict, so a fresh `tradefabe run` process must reconstruct it.
PROMOTED_COMBOS_PATH = STATE_DIR / "promoted_combos.json"
COMBO_SLEEVE = 0.30   # same fixed sleeve piggyback.py uses -- pre-committed, not optimized


def load_promoted_combos():
    if not PROMOTED_COMBOS_PATH.exists():
        return []
    with open(PROMOTED_COMBOS_PATH) as fh:
        return json.load(fh)


def promote_combo(spec):
    """Registers a combo as a live paper book, idempotent by name. `spec` is
    {"name", "freq", "legs": [{"name", "family", "params"} | {"name": <TEMPLATES key>}]}."""
    entries = load_promoted_combos()
    if any(e["name"] == spec["name"] for e in entries):
        return
    entries.append({"name": spec["name"], "freq": spec["freq"], "legs": spec["legs"]})
    # mkdir the parent of the ACTUAL path, not STATE_DIR: the two diverge whenever a
    # caller patches one and not the other, and then this writes into real paper state.
    PROMOTED_COMBOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROMOTED_COMBOS_PATH, "w") as fh:
        json.dump(entries, fh, indent=1)


def _leg_signal(leg):
    """A leg is either a TEMPLATES entry (name alone is enough) or a generated candidate
    (needs family+params to rebuild)."""
    if leg.get("params"):
        return rebuild_signal(leg["family"], leg["params"])
    if leg["name"] in TEMPLATES:
        return TEMPLATES[leg["name"]][0]
    raise KeyError(f"combo leg {leg['name']!r} is neither a template nor a generated spec")


def combo_target_weights(prices, spec):
    """70% of the 60/40 core + 30% equal-weight blend of each leg's own vol-targeted
    weights -- the identical construction piggyback.target_weights() uses, so a promoted
    combo is allocated exactly like a hand-picked piggyback book rather than by a second,
    subtly different rule."""
    from .engine import BENCH_W, sized_weights
    leg_w = [sized_weights(prices, _leg_signal(l)(prices)).iloc[-1].fillna(0.0)
             for l in spec["legs"]]
    sleeve_w = sum(leg_w) / len(leg_w)
    bench_w = pd.Series(BENCH_W).reindex(prices.columns).fillna(0.0)
    return (1 - COMBO_SLEEVE) * bench_w + COMBO_SLEEVE * sleeve_w
