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

**RESOLVED (2026-08-05, Dave's call) — the exact mechanism:** a DV01-neutral TLT/IEF
position (see duration constants below) whose DIRECTION trend-follows the curve slope
itself — `sign(slope_today − slope_{today − lookback})` on `DGS10 − DGS2`, where
`lookback` is drawn from the exact same `(20, 252)` range `single_asset_trend` already
uses. Steepening trend → short TLT / long IEF (DV01-weighted); flattening trend → long
TLT / short IEF. This reuses the vocabulary's existing trend-primitive SHAPE (sign of a
trailing change over a routine-chosen, pre-registered window) applied to curve data
instead of price data — no new arbitrary "steep enough" cutoff invented; `lookback` is
the only free parameter, same as every comparable primitive already exposes. Fixed to
TLT/IEF specifically (no free ticker choice like `static_spread_carry`'s), since real
duration data is only pre-registered for this pair — a genuinely new mechanism class
(external-data-gated regime direction, DV01-neutral sizing), not derived from price
action alone the way every current primitive is, buildable with zero UNIVERSE expansion.

**RESOLVED (2026-08-05, Dave's call): the guard directly tests hedge effectiveness,
not divergence from `static_spread_carry`.** Once the legs are DV01-hedged, the
original "must differ from the unhedged static version" comparison stopped fitting —
a duration-hedged position is already structurally distinct from an unhedged one, so
that comparison wasn't testing the thing that actually matters. The real question is
whether the hedge worked: on calibration-window (2007–2017) data, the position's daily
P&L must have LOW correlation with a rate-level-move proxy (`DGS10`'s daily change) —
reusing `CALIB_CORR_CAP = 0.3`, the exact same threshold already pre-registered and
reviewed for `asset_class_trend_hedge` (v1.14), rather than inventing a new number.
Passes iff duration-neutrality actually held in calibration data, not just in the
static weights on paper — a mechanical, non-gameable check in the same spirit as
#194's two guards, applied to a different target.

**Decided by precedent, not re-litigated: pipeline-only, not a 6th factory family.**
`asset_class_trend_hedge` — the only other primitive added since launch — was
pipeline-only, not added to `GENERATION_RANGES`. `curve_carry` follows the same
precedent for the same reason: the factory's parameter-sweep model (many draws per
cycle, promote the single best regardless of verdict) doesn't fit a primitive whose
"parameters" are pre-registered duration constants, not a range to sweep. Revisit only
if a real reason to widen factory search surfaces later — not scoped here.

**RESOLVED (2026-08-05, Dave's call): the leg structure is duration-hedged (option a),
using static pre-registered duration constants.** `DOCTRINE.md` is explicit that
`carry_btc_eth`'s edge is delta-neutral funding-rate capture (long spot, short perp,
zero exposure to price direction). An unhedged long-TLT/short-IEF position is not
that — it's a directional bet on rate-level moves (duration exposure), structurally
closer to the trend family (0-for-many in this lab) than to the delta-neutral trade
that actually survived. `curve_carry`'s legs are sized so their DV01s roughly offset
(`w_TLT × TLT_DURATION ≈ w_IEF × IEF_DURATION`), isolating the position to curve-shape/
roll-down carry rather than a parallel-shift level bet — a duration-neutral curve
steepener/flattener, the standard institutional shape for this trade, buildable with
static ETF weights alone (no options/futures needed).

**Duration constants, pre-registered here (verified 2026-08-04, not assumed):**
`TLT_DURATION ≈ 15–16.5 years`, `IEF_DURATION ≈ 7–8 years` (iShares fact sheets,
mid-2026; sources: ishares.com TLT fact sheet, 247wallst.com TLT-vs-IEF analysis
2026-07-10). **Fixed and reviewed once, same discipline as `ASSET_CLASS`** — not
fetched live or re-derived per run, since duration drifts slowly and a
data-dependent hedge ratio would reopen the same meta-level p-hacking risk a fixed
`CALIB_CORR_CAP`-style constant avoids. Exact midpoint values (and any future
revision) are Dave's call at implementation time, not backward-fit from how a
particular ratio performs on calibration data.

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
