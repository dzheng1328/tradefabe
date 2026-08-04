"""
pipeline_ideas.py — the research pipeline's idea-generation step (#177).

The one genuinely LLM-driven step in this repo, consistent with README.md's own
principle: strategies are deterministic, "no LLM in the trade loop" -- LLMs are for
research, not trading decisions. Nothing downstream of a proposal is nondeterministic:
the LLM picks a PRIMITIVE and PARAMETERS from a fixed, pre-registered vocabulary
(PRIMITIVES below), never code, and build_signal() turns that choice into an ordinary,
auditable, re-runnable signal function the same way factory.rebuild_signal() does for a
generated factory candidate.

Rate-limited to ONE proposal per day (already_proposed_today()) -- "generate many, keep
the best" would just hide multiple-testing in an untracked step, the opposite of what
#176's segregated bucket exists to prevent. Every proposal is logged to PIPELINE_LEDGER
at proposal time, before prelim_screen() (#175) even runs on it -- the same
before-the-result guarantee every other origin marker in this repo carries.

Budget: Dave's explicit hard cap is $0.05/day. estimate_cost() computes a PROVABLE UPPER
BOUND before any API call fires (conservative token estimate on the input side,
MAX_OUTPUT_TOKENS -- an actual API-enforced cap -- on the output side) and refuses to
call the model at all if that bound exceeds DAILY_BUDGET_USD. A day the cap would be
exceeded is a clean, logged skip, not a failure -- same as a day the model itself has
nothing to propose.

propose_idea()'s return value -- {"name", "sig_fn", "freq"} -- is directly consumable by
harness.prelim_screen() with no further translation, satisfying #177's own design
requirement ("specific enough that #175's prelim screen can run against it without more
design work"). #178 is expected to be a thin wrapper: call propose_idea(), then
prelim_screen() on the result if one came back.

Usage: PYTHONPATH=src:.:research python research/pipeline_ideas.py
"""
from __future__ import annotations
import datetime
import json
import os

import numpy as np
import pandas as pd

from tradefabe.engine import UNIVERSE
import harness

# ---------- the primitive vocabulary (pre-registered, STRATEGIES.md) ----------
# Fixed here, reviewed once, same discipline as factory.GENERATION_RANGES: the LLM picks
# a primitive and parameters WITHIN this pre-registered space, never a new mechanism or
# code. A numeric (lo, hi) 2-tuple is a RANGE; a list or a tuple whose elements aren't
# both int/float is a CATEGORICAL choice set (see validate_proposal()'s dispatch).
PRIMITIVES = {
    "pair_zscore": {
        "description": ("Mean-reversion of the z-scored log-spread between two UNIVERSE "
                        "tickers -- long-the-spread when it's unusually low, short when "
                        "unusually high, flat near the mean. A simple 1:1 log-spread, "
                        "not a regressed hedge ratio (unlike family N's pre-registered "
                        "pairs, this primitive has no dedicated calibration step of its "
                        "own -- appropriate for a cheap, general-purpose first look)."),
        "params": {"ticker_a": UNIVERSE, "ticker_b": UNIVERSE,
                   "z_window": (20, 120), "z_entry": (1.5, 3.0), "z_stop": (3.0, 6.0)},
    },
    "cross_sectional_rank": {
        "description": ("Long the top-K, short the bottom-K of the full UNIVERSE ranked "
                        "by a fixed metric over a lookback window."),
        "params": {"metric": ("momentum", "low_vol", "reversal"),
                   "lookback": (20, 252), "k": (1, 7)},
    },
    "single_asset_trend": {
        "description": ("Long/short a single ticker by the sign of its own trailing "
                        "return over a lookback window."),
        "params": {"ticker": UNIVERSE, "lookback": (20, 252)},
    },
    "static_spread_carry": {
        "description": ("A fixed, always-on long-short between two tickers -- a "
                        "structural risk-premium bet, not a mean-reversion signal."),
        "params": {"ticker_a": UNIVERSE, "ticker_b": UNIVERSE, "long_leg": ("a", "b")},
    },
}


def _sig_pair_zscore(params):
    a, b = params["ticker_a"], params["ticker_b"]
    window, entry, stop = params["z_window"], params["z_entry"], params["z_stop"]

    def sig(prices):
        spread = np.log(prices[a]) - np.log(prices[b])
        z = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()
        pos = np.zeros(len(z))
        state = 0.0
        for i, zi in enumerate(z.to_numpy()):
            if np.isnan(zi):
                state = 0.0
            elif state == 0.0:
                if -stop < zi < -entry:
                    state = 1.0
                elif entry < zi < stop:
                    state = -1.0
            elif state == 1.0:
                if zi >= 0 or zi < -stop:
                    state = 0.0
            elif state == -1.0:
                if zi <= 0 or zi > stop:
                    state = 0.0
            pos[i] = state
        pos_s = pd.Series(pos, index=z.index)
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[a] = pos_s
        out[b] = -pos_s
        return out
    return sig


def _sig_cross_sectional_rank(params):
    metric, lookback, k = params["metric"], params["lookback"], params["k"]

    def sig(prices):
        if metric == "momentum":
            score = prices / prices.shift(lookback) - 1
        elif metric == "reversal":
            score = -(prices / prices.shift(lookback) - 1)
        elif metric == "low_vol":
            score = -prices.pct_change().rolling(lookback).std()
        else:
            raise ValueError(f"unknown metric {metric!r}")
        rank = score.rank(axis=1, ascending=False)
        n = score.notna().sum(axis=1)   # per-row count -- must align on axis=0, not the
                                         # default axis=1 a bare `rank > (n - k)` would use
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[rank <= k] = 1.0
        out[rank.gt(n - k, axis=0)] = -1.0
        return out
    return sig


def _sig_single_asset_trend(params):
    ticker, lookback = params["ticker"], params["lookback"]

    def sig(prices):
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[ticker] = np.sign(prices[ticker] / prices[ticker].shift(lookback) - 1)
        return out
    return sig


def _sig_static_spread_carry(params):
    a, b = params["ticker_a"], params["ticker_b"]
    long_leg = params["long_leg"]

    def sig(prices):
        out = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        out[a] = 1.0 if long_leg == "a" else -1.0
        out[b] = -1.0 if long_leg == "a" else 1.0
        return out
    return sig


_BUILDERS = {
    "pair_zscore": _sig_pair_zscore,
    "cross_sectional_rank": _sig_cross_sectional_rank,
    "single_asset_trend": _sig_single_asset_trend,
    "static_spread_carry": _sig_static_spread_carry,
}


def build_signal(primitive: str, params: dict):
    """Reconstructs a signal function from a primitive name + params -- pure and
    deterministic, so it can be rebuilt identically in a later process the same way
    factory.rebuild_signal() reconstructs a generated candidate's signal."""
    if primitive not in _BUILDERS:
        raise ValueError(f"unknown primitive {primitive!r}")
    return _BUILDERS[primitive](params)


# ---------- validation ----------
def _is_numeric_range(bound) -> bool:
    return (isinstance(bound, tuple) and len(bound) == 2
            and all(isinstance(b, (int, float)) and not isinstance(b, bool) for b in bound))


def validate_proposal(raw: dict) -> dict | None:
    """Checks a raw LLM proposal against PRIMITIVES' pre-registered ranges/types.
    Permissive about WHAT the LLM proposes (any economic thesis, any citation), strict
    about the MECHANICAL shape (primitive membership, parameter bounds, non-empty
    rationale/citation) -- the same split factory.generate_candidate() draws between a
    fixed range (pre-registered) and the specific value drawn (not). Returns a
    normalized dict or None (reason printed) -- never raises on malformed input, since a
    malformed proposal from an LLM is an expected, not exceptional, outcome."""
    try:
        primitive = raw["primitive"]
        params = dict(raw["params"])
        freq = raw["freq"]
        rationale = raw["rationale"].strip()
        citation = raw["citation"].strip()
    except (KeyError, AttributeError, TypeError) as e:
        print(f"[pipeline_ideas] rejected: malformed proposal ({e})")
        return None

    if primitive not in PRIMITIVES:
        print(f"[pipeline_ideas] rejected: unknown primitive {primitive!r}")
        return None
    if freq not in ("D", "W", "M"):
        print(f"[pipeline_ideas] rejected: invalid freq {freq!r}")
        return None
    if not rationale or not citation:
        print("[pipeline_ideas] rejected: missing rationale or citation")
        return None

    spec = PRIMITIVES[primitive]["params"]
    normalized = {}
    for key, bound in spec.items():
        if key not in params:
            print(f"[pipeline_ideas] rejected: missing param {key!r} for {primitive!r}")
            return None
        val = params[key]
        if _is_numeric_range(bound):
            lo, hi = bound
            try:
                val = type(lo)(val)
            except (TypeError, ValueError):
                print(f"[pipeline_ideas] rejected: {key}={val!r} is not numeric")
                return None
            if not (lo <= val <= hi):
                print(f"[pipeline_ideas] rejected: {key}={val} outside [{lo}, {hi}]")
                return None
        else:
            if val not in bound:
                print(f"[pipeline_ideas] rejected: {key}={val!r} not one of {list(bound)}")
                return None
        normalized[key] = val

    if primitive in ("pair_zscore", "static_spread_carry") and \
            normalized["ticker_a"] == normalized["ticker_b"]:
        print("[pipeline_ideas] rejected: ticker_a and ticker_b must differ")
        return None
    if primitive == "pair_zscore" and not (normalized["z_entry"] < normalized["z_stop"]):
        print("[pipeline_ideas] rejected: z_entry must be < z_stop")
        return None

    return {"primitive": primitive, "params": normalized, "freq": freq,
            "rationale": rationale, "citation": citation}


# ---------- naming (#176's contract: every pipeline name is rp_-prefixed) ----------
def _fmt_param(v):
    return str(v).replace(".", "p") if isinstance(v, float) else str(v)


def make_name(primitive: str, params: dict) -> str:
    """Deterministic from (primitive, params) -- the SAME spec always gets the SAME
    name, so a re-proposed duplicate is recognizable as one rather than silently
    becoming a second row. Prefixed with harness.PIPELINE_NAME_PREFIX, satisfying #176's
    origin-classification contract by construction, not by convention the LLM could
    violate -- the LLM never invents the name."""
    bits = "_".join(_fmt_param(v) for v in params.values())
    return f"{harness.PIPELINE_NAME_PREFIX}{primitive}_{bits}"


# ---------- rate limiter ----------
def already_proposed_today(now: datetime.datetime | None = None) -> bool:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not os.path.exists(harness.PIPELINE_LEDGER):
        return False
    df = pd.read_csv(harness.PIPELINE_LEDGER)
    if "timestamp" not in df.columns or not len(df):
        return False
    stamps = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    return bool((stamps.dt.date == now.date()).any())


# ---------- ledger ----------
def record_proposal(name: str, proposal: dict) -> None:
    """Appends to PIPELINE_LEDGER at PROPOSAL time -- before prelim_screen() runs on
    this name, let alone an OOS verdict -- so #176's origin classification is never
    assigned after the fact."""
    row = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "name": name, "primitive": proposal["primitive"], "freq": proposal["freq"],
           "params": json.dumps(proposal["params"]), "rationale": proposal["rationale"],
           "citation": proposal["citation"]}
    pd.DataFrame([row]).to_csv(harness.PIPELINE_LEDGER, mode="a",
                               header=not os.path.exists(harness.PIPELINE_LEDGER), index=False)


# ---------- prompt ----------
MAX_ROSTER_NAMES = 400   # bounds prompt size regardless of how large the ledger grows

_STATE_SUMMARY = (
    "Every predictive strategy tested here so far is DEAD against pre-registered kill "
    "rules: trend, mean-reversion, calendar/seasonality, defensive-anomaly, "
    "cross-sectional momentum, breakout/channel, a pretrained OHLCV forecasting model, "
    "and pairs/cointegration across six economically-linked pairs. The two things that "
    "survived: diversified buy-and-hold, and delta-neutral crypto funding carry.")


def _format_primitives() -> str:
    lines = []
    for name, spec in PRIMITIVES.items():
        parts = []
        for k, v in spec["params"].items():
            parts.append(f"{k} in [{v[0]}, {v[1]}]" if _is_numeric_range(v) else f"{k} in {list(v)}")
        lines.append(f"- {name}: {spec['description']} Parameters: {', '.join(parts)}.")
    return "\n".join(lines)


def build_prompt() -> str:
    already = sorted(harness.pipeline_origin_names())[-MAX_ROSTER_NAMES:]
    already_str = ", ".join(already) if already else "(none proposed by this pipeline yet)"
    return f"""{_STATE_SUMMARY}

You may propose ONE new trading strategy idea today, built from exactly one of these
pre-registered primitives. You choose the primitive and its parameters; you may not
invent a new primitive, write code, or propose an instrument outside this universe.

{_format_primitives()}

Universe (ETF tickers only): {", ".join(UNIVERSE)}

Already proposed by this pipeline (do not repeat an identical spec): {already_str}

Respond with a SINGLE JSON object and nothing else, no other text:
{{"primitive": "<one of the primitive names above>", "params": {{...}}, "freq": "D"|"W"|"M", "rationale": "<one or two sentences, economic reasoning>", "citation": "<a real reference -- academic paper or well-known market convention -- or \\"n/a\\" if none exists>"}}

If you do not have a genuinely new, economically-motivated idea today, respond with
exactly: {{"skip": true, "reason": "<why>"}}. Proposing nothing is a legitimate outcome --
do not force an idea just to produce output."""


# ---------- budget-guarded model call ----------
MODEL = "claude-haiku-4-5-20251001"   # cheapest current model -- see DAILY_BUDGET_USD
PRICE_PER_INPUT_TOKEN_USD = 1.00 / 1_000_000    # Haiku 4.5, sourced 2026-08-01, claude.com/pricing
PRICE_PER_OUTPUT_TOKEN_USD = 5.00 / 1_000_000
DAILY_BUDGET_USD = 0.05    # Dave's explicit hard cap -- if a call would definitely
                           # exceed this, it must never fire, not just warn after the fact
MAX_OUTPUT_TOKENS = 600


def estimate_tokens(text: str) -> int:
    """A deliberately PESSIMISTIC approximation (~3 chars/token, denser than English
    text's typical ~4) -- this feeds a hard budget gate, so overestimating cost is the
    safe direction; underestimating is not."""
    return max(1, len(text) // 3)


def estimate_cost(prompt: str, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> float:
    """A PROVABLE UPPER BOUND on what a call can cost, not an average: max_output_tokens
    is the API's own hard cap on the response length, and estimate_tokens() overestimates
    the input side -- so a call that clears this check cannot exceed DAILY_BUDGET_USD in
    practice, regardless of what the model actually returns."""
    return (estimate_tokens(prompt) * PRICE_PER_INPUT_TOKEN_USD
            + max_output_tokens * PRICE_PER_OUTPUT_TOKEN_USD)


def _call_anthropic(prompt: str) -> str:
    from anthropic import Anthropic   # lazy import -- same shape as kronos.py/broker.py:
                                       # the paper engine must keep running with no
                                       # [pipeline] extra installed
    client = Anthropic()
    resp = client.messages.create(model=MODEL, max_tokens=MAX_OUTPUT_TOKENS,
                                  messages=[{"role": "user", "content": prompt}])
    return resp.content[0].text


def propose_idea(llm_fn=None) -> dict | None:
    """The idea-generation step. `llm_fn` is injectable for testing (defaults to a real,
    budget-guarded Anthropic API call) -- takes a prompt string, returns the raw text
    response. Returns a validated {"name", "sig_fn", "freq"} dict directly consumable by
    harness.prelim_screen(), or None if nothing was proposed. None is a LEGITIMATE
    outcome (rate-limited, budget would be exceeded, the model skipped, validation
    failed, or a duplicate of an already-tested spec) -- #178 must treat all of these as
    "nothing to screen today," not an error."""
    if already_proposed_today():
        print("[pipeline_ideas] already proposed today -- skipping")
        return None

    prompt = build_prompt()
    cost = estimate_cost(prompt)
    if cost > DAILY_BUDGET_USD:
        print(f"[pipeline_ideas] estimated cost ${cost:.4f} exceeds the "
              f"${DAILY_BUDGET_USD:.2f}/day cap -- refusing to call the model")
        return None

    call = llm_fn or _call_anthropic
    try:
        raw_text = call(prompt)
    except Exception as e:                                # noqa: BLE001
        print(f"[pipeline_ideas] model call failed: {e}")
        return None

    try:
        raw = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        print(f"[pipeline_ideas] model response was not valid JSON: {raw_text!r}")
        return None

    if not isinstance(raw, dict):
        print(f"[pipeline_ideas] model response was not a JSON object: {raw_text!r}")
        return None
    if raw.get("skip"):
        print(f"[pipeline_ideas] model proposed nothing today: {raw.get('reason', '')}")
        return None

    proposal = validate_proposal(raw)
    if proposal is None:
        return None

    name = make_name(proposal["primitive"], proposal["params"])
    already = harness.graveyard_strategy_names() | harness.pipeline_origin_names()
    if name in already:
        print(f"[pipeline_ideas] rejected: {name!r} already tested or proposed")
        return None

    record_proposal(name, proposal)
    sig_fn = build_signal(proposal["primitive"], proposal["params"])
    print(f"[pipeline_ideas] proposed {name} ({proposal['primitive']}, "
          f"freq={proposal['freq']}) -- {proposal['rationale']}")
    # {"name","sig_fn","freq"} is harness.prelim_screen()'s (#175) whole contract; the
    # rest (primitive/params/rationale/citation) rides along for #179's pre-registration
    # step, which needs the full spec to render STRATEGIES.md prose, not just what the
    # screen itself reads.
    return {"name": name, "sig_fn": sig_fn, "freq": proposal["freq"],
            "primitive": proposal["primitive"], "params": proposal["params"],
            "rationale": proposal["rationale"], "citation": proposal["citation"]}


def main():
    result = propose_idea()
    if result is None:
        print("[pipeline_ideas] nothing to record today")
        return
    print(f"[pipeline_ideas] recorded {result['name']} -- ready for #178's prelim screen")


if __name__ == "__main__":
    main()
