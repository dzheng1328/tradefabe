# Generalizing structural carry beyond crypto — design spec

Status: draft, awaiting Dave's review
Date: 2026-08-04
Related: DOCTRINE.md v1.14 (#194), issue #174 (daily research pipeline)

## Why this, why now

Of 139+ strategies ever tested in this lab, exactly two have survived: diversified
buy-and-hold and delta-neutral crypto funding carry. Every predictive mechanism class
tested — trend, mean-reversion, calendar effects, momentum, a pretrained OHLCV model —
is DEAD. Carry is the only mechanism class with a real track record, and DOCTRINE v1.14
already flagged, as an explicit non-goal of that amendment, that generalizing it further
is "blocked on data infrastructure (`tradefabe.engine.load_prices()` is spot ETF closes
only, no yield curve or futures term structure)."

Separately, Dave flagged (2026-08-04) that both automated generators — the strategy
factory (`GENERATION_RANGES`, 5 families) and the research pipeline (`PRIMITIVES`, 5
primitives) — only ever parameterize a small, fixed set of mechanical shapes, which is
why most of `state/paper/` reads as near-duplicate variants that perform similarly
(e.g. six `turn_of_month_gen_*` books at different window widths). Extending mechanism
classes that have gone 0-for-139 (more trend/mean-reversion variants) is lower leverage
than unblocking the one class that's actually worked. This spec scopes that unblock.

**Scope boundary:** this spec covers ONLY generalizing carry via real rate data. It does
NOT cover the rest of the "narrow vocabulary" backlog (new factory families beyond
carry, UNIVERSE expansion, research-source quality) — those become a separate tracking
issue + subissues, filed alongside this one, not designed here.

## Phase 1 — yield-curve data infrastructure

**New module:** `src/tradefabe/rates.py`, same-source-of-truth discipline as `engine.py`
(no private copies of this logic elsewhere).

**`load_yield_curve(series=("DGS2", "DGS10", "DGS30"), start=engine.START) -> pd.DataFrame`**
- Pulls free, key-less daily Treasury constant-maturity yields from FRED's CSV endpoint
  (`fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`), one request per series,
  concatenated into a single DataFrame indexed by date.
- `DGS2`/`DGS10`/`DGS30` are actual observed market quotes (Treasury's daily par yield
  curve), not modeled/revised economic estimates — no revision-leak risk the way GDP or
  employment series would carry.
- Same calibration-only firewall as prices: any function that computes a calibration-time
  decision (e.g. a guard evaluated against `CALIB_START`–`CALIB_END`) must not have
  access to rows past `CALIB_END`, mirroring how `harness.prelim_screen()` already works.
- Same cache discipline as `engine.load_prices()`: respects `TRADEFABE_CACHE_HOURS`,
  stale-cache-beats-none if FRED is unreachable.
- **Required implementation detail, not optional:** joining FRED's calendar (includes
  bank holidays, no trading-day concept) onto the engine's trading-day price index MUST
  use `pd.merge_asof(..., direction="backward")` or equivalent — never a naive
  `reindex().ffill()` from an unverified starting alignment. A forward-leaking join here
  would silently defeat `engine.py`'s existing `w_exec = w.shift(1)` no-lookahead
  guarantee at the join step, upstream of where that protection currently applies.
- **Missing-value handling:** FRED uses `"."` for no-quote days (market holidays) — must
  be coerced to NaN and explicitly forward-filled or dropped, never silently parsed as a
  string or a stray float, same `math.isfinite` discipline `books.mark()` already applies
  to price NaNs. A NaN that reaches a signal is a bug, not a degraded signal.
- **Never raises:** same in-process discipline as `run_hourly()`/`run_kronos()` — a FRED
  outage must skip-and-log the affected cycle, not take down the pipeline run that owns
  the real ledger.

**Testing:** unit tests inject synthetic yield-curve fixtures (same pattern as
`test_nan_marks.py`) — no live network calls in CI. Cover: the merge-asof alignment
(a trading day immediately after a FRED gap gets the correct prior value, not a future
one), the `"."` coercion, and cache staleness behavior.

## Phase 2 — `curve_carry` primitive (new mechanism, doctrine-reviewed)

**Mechanism:** a structural position in existing UNIVERSE duration ETFs (TLT vs IEF, or
TLT vs a cash-like leg) whose sizing or direction is gated by the REAL FRED curve slope
(e.g. `DGS10 - DGS2`) rather than being always-on-static (`static_spread_carry`) or
derived from price action the way every current primitive is. This is a genuinely new
mechanism class — external-data-gated regime, not a price-derived signal — buildable
with zero UNIVERSE expansion.

**Guard requirement (mirrors #194's asset-class + calibration-corr guards):** the
curve-gated version's calibration-window (2007–2017) behavior must measurably differ
from the existing always-on `static_spread_carry` TLT/IEF proposal — otherwise this is
the same static bet with extra steps, exactly the "two zero-edge signals dressed up as
new" risk DOCTRINE v1.14 designed around for compositional primitives.

**Open question, deliberately not resolved here:** the exact guard threshold (how much
divergence from the static version counts as "measurably different") needs to be picked
by Dave BEFORE looking at how any threshold choice performs on calibration data — picking
it by backward-fitting from calibration performance would be the same meta-level
p-hacking DOCTRINE.md exists to prevent, one level up. This spec flags the need for a
threshold; it does not set one.

**Open question, deliberately not resolved here:** whether `curve_carry` becomes a 6th
factory family (`GENERATION_RANGES`) in addition to a pipeline primitive, or
pipeline-only like `asset_class_trend_hedge` was. Factory promotion picks one
best-ranked candidate per cycle regardless of verdict — adding a family there widens
search breadth but wasn't scoped as part of this design's Phase 2 decision.

**Council finding (2026-08-04), incorporated here — the leg structure must be
duration-hedged, not a bare long/short pair.** `DOCTRINE.md` is explicit that
`carry_btc_eth`'s edge is delta-neutral funding-rate capture (long spot, short perp,
zero exposure to price direction). An unhedged long-TLT/short-IEF position is not
that — it's a directional bet on rate-level moves (duration exposure), structurally
closer to the trend family (0-for-many in this lab) than to the delta-neutral trade
that actually survived. Borrowing carry's track record by label without its risk
structure would not actually test the hypothesis this spec is funded on. Phase 2's
leg construction must either (a) duration-hedge the position (e.g. size the two legs
so their DV01s roughly offset, isolating curve-shape/roll-down carry rather than a
level bet) or (b) drop the "carry" framing honestly and evaluate it as a directional
rates mechanism on those terms. This is now a Phase 2 requirement, not a caveat.

**Wiring:** once built, `curve_carry` goes through the exact same downstream path every
other primitive already uses — `prelim_screen()` → pre-register → OOS test → promote
(capped at `MAX_PIPELINE_PROMOTED`) — no special-casing needed there. That path already
exists and works (verified during this design pass: `pipeline_daily.screen_pending_backlog()`
processes the full unscreened backlog every cycle, not just the newest row).

## Git process (for implementation, later)

- Two issues, two PRs — Phase 1 (infra) and Phase 2 (primitive) reviewed separately,
  matching this repo's existing "one PR per issue/topic" convention and the #194
  precedent of splitting infra risk from doctrine/multiple-testing risk.
- Phase 2's PR touches `STRATEGIES.md` (new primitive documented) and likely
  `pipeline.py`'s `PRIMITIVES` — the `doctrine-auditor` subagent must run before that PR
  merges, per today's new CLAUDE.md rule (added after #195 merged once without it).
- Branch/PR/merge mechanics go through `/ship` (or `/new-strategy` if Phase 2 counts as
  one) — both are `disable-model-invocation: true`, so Dave runs them, not an agent
  unprompted.
- `council` gets run on this spec before it's considered final (below), same review
  #182's own checklist calls for on the pipeline as a whole.

## Explicitly out of scope for this spec

- Commodity/futures term-structure carry (no equally clean free data source identified).
- UNIVERSE expansion, factory-family additions beyond `curve_carry`, and research-source
  quality — tracked separately as their own issue(s).
- Actual implementation — this spec is groundwork only, per Dave's explicit instruction
  (2026-08-04): plan now, implement later.
