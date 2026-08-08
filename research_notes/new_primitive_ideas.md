# New-primitive ideas — for Dave to review manually

Written by the daily pipeline research routine when its research surfaces a mechanism that
does **not** fit any primitive currently in `src/tradefabe/pipeline.py`'s `PRIMITIVES`.
Nothing here is pre-registered, proposed, or tested — expanding the vocabulary is a
deliberate human decision, so these are notes only. Append, don't rewrite.

---

## 2026-08-08 — long-horizon valuation-anchored spread (no primitive fits)

**What the research surfaced.** The gold/oil ratio is at a multi-decade extreme: roughly
55–58 barrels per ounce as of mid-2026 against a 50-year average near 15–20, having peaked
at 82.1 in February 2026. The 30-day GLD/USO correlation is negative (~−0.18) — the two are
being driven by genuinely different demand stories (safe-haven vs geopolitical supply risk),
not by one common commodity factor.

**Why it doesn't fit the current vocabulary.**
- `pair_zscore` is the closest shape, but its `z_window` is capped at 120 days. A 120-day
  z-score cannot see a multi-decade level extreme — it renormalizes to whatever the last six
  months looked like, so a ratio that has been 3x its historical average for two years scores
  near zero. The signal the research points at is a *level* anchored on a multi-year mean;
  the primitive only expresses a *rolling* one.
- `static_spread_carry` is always-on and directionless-by-construction — it can hold the
  spread but has no notion of the spread being far from an anchor, and its stated purpose is
  a structural risk-premium bet, not a valuation bet.
- `asset_class_trend_hedge` is unavailable: `ASSET_CLASS` puts both GLD and USO in
  `commodity`, so the two-different-asset-classes guard rejects the pair (correctly).

**The gap, stated generally.** There is no primitive for "spread between two UNIVERSE
tickers is far from a multi-year anchor, fade it," with the anchor window measured in years
rather than months.

**Caveats worth weighing before adding anything.** A long-anchor primitive has very few
independent observations per unit of backtest — a 5-year anchor over a 2018+ OOS window
gives on the order of a handful of genuinely independent signals, which is exactly the
setup where DSR/CPCV are least able to distinguish edge from luck. It would also need a
pre-registered rule for the anchor window that isn't chosen after seeing which window makes
the current gold/oil reading look extreme. Both are reasons this may be a gap worth leaving
open rather than filling.
