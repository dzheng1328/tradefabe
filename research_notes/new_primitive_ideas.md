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

---

## 2026-08-14 — term-structure-gated commodity carry (no primitive fits)

**What the research surfaced.** WTI and Brent are in *opposite* term-structure states right
now. WTI's front three contracts are in contango at roughly $0.45/bbl per month (about
0.65%/month against a ~$68.7 front price), while Brent is in backwardation near $0.20/bbl.
The split is location-specific rather than a global oil story: US crude inventories have
posted three consecutive weekly builds on refinery maintenance plus record domestic output
above 13.5 mb/d, pushing a Cushing surplus into contango, while Brent-linked stocks in the
North Sea, ARA and key Asian import hubs have drawn steadily. The IEA's August report has
the *global* balance in a 1.8 mb/d deficit for 3Q26 with observed inventories down 69 mb in
July — so the contango is a US storage-economics fact, not a global-glut fact.

This matters for the UNIVERSE because roll yield is not a footnote for these wrappers: USO
holds front-month WTI and pays or earns the roll directly every month, whereas DBC rolls an
optimized schedule across a diversified basket. A term-structure divergence of this size is
a mechanical, sign-known difference in the two ETFs' carry.

**Why it doesn't fit the current vocabulary.**
- `static_spread_carry` is the closest economically, but it is always-on with a *fixed*
  direction — it cannot condition on whether the curve is currently in contango or
  backwardation, which is the entire content of the finding. It is also unusable here for a
  second reason: `rp_static_spread_carry_USO_DBC_a` is already verdicted, so proposing
  `long_leg="b"` would be an exact sign flip of a tested strategy — testing a spread, seeing
  it fail, and re-proposing its mirror is precisely the multiple-testing move DOCTRINE
  exists to stop. Noting that explicitly so a later run doesn't reach for it.
- `pair_zscore` conditions on the price spread's own rolling z-score, which is the wrong
  object. Roll yield accrues as a *steady drift*, not as a dislocation — and a rolling
  z-score treats a steady drift as the new mean, so the primitive actively cancels the very
  effect the research points at.
- `curve_carry` is the right *shape* — external data gating a spread between two fixed
  tickers, with a mechanical hedge-effectiveness guard — but it is hard-fixed to TLT/IEF and
  the FRED Treasury curve, with no ticker choice by construction.
- `single_asset_trend`, `cross_sectional_rank` and `asset_class_trend_hedge` are all
  price-momentum only and see no term structure at all. (`asset_class_trend_hedge` is
  doubly unavailable: `ASSET_CLASS` puts USO and DBC both in `commodity`.)

**The gap, stated generally.** There is no primitive in which an external *term-structure or
carry* series gates a commodity spread — i.e. `curve_carry`'s design pattern (real
off-price data decides the sign of a two-leg position) generalized past the single
pre-registered TLT/IEF rates case.

**Caveats worth weighing before adding anything.**
- It needs a pre-registered external data source. `rates.py` covers the FRED Treasury curve;
  a front-vs-deferred futures curve for WTI is not currently loaded anywhere in the repo,
  and picking a source after seeing which one makes the current setup look clean would be
  the same p-hacking the ranges are designed to prevent.
- Partial double-counting risk: USO's realized roll drag is *already inside* its own price
  history, so a backtest that also gates on the curve may be paid twice for one effect. Any
  such primitive would need a stated reason why the gate adds information the price series
  doesn't already contain.
- Generalizing `curve_carry` to caller-chosen tickers re-opens the ticker-selection
  multiple-testing problem that fixing it to TLT/IEF deliberately closed. That constraint
  was a feature; relaxing it should be priced as such, and would want its own
  calibration-window guard analogous to `curve_carry_hedge_is_effective()`.

Sources: IEA Oil Market Report, August 2026 — https://www.iea.org/reports/oil-market-report-august-2026 ;
CMB News, crude oil market analysis (WTI front-curve contango $0.45/bbl per month vs Brent
backwardation $0.20/bbl) — https://commodity-board.com/wti-curve-softens-as-opec-eases-cuts-and-demand-signals-cool ;
FXTorch, "WTI-Brent Spread: The Inventory Divergence OPEC+ Can't Ignore" (Cushing builds,
US output above 13.5 mb/d, North Sea/ARA/Asia draws) —
https://www.fxtorch.com/posts/2026/07/13/0500-wti-brent-spread-the-inventory-divergence-opec-cant-ignore/
