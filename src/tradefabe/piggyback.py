"""Piggyback books: 70% 60/40 core + 30% fixed equal-weight sleeve of named legs.

Single source of truth for the 4 constructions pre-registered in STRATEGIES.md family H
and backtest-verdicted by research/piggyback_backtest.py (which imports LEGS/SPECS from
here rather than redefining them). SPECS holds all 4 as backtested; REGISTRY is the
subset actually wired into the live paper engine.

Status as of DOCTRINE v1.3 (2026-07-24, Bonferroni correction): piggyback_2a/3/4
originally verdicted ALIVE under a flat p95 bar, then flipped to DEAD once judged against
the honest multiple-testing-corrected bar at their real n_tested (9-12) -- see
graveyard.csv (both the original and corrected rows are kept, append-only) and
DOCTRINE.md's v1.3 amendment for why. Dave's call (2026-07-24): keep all 3 running live,
same status DOCTRINE v1.2 already gives the backtest-DEAD trend books (tsmom_12m etc) --
paper-tracked for monitoring/dashboard value, explicitly NOT eligible for a
paper-confirmed verdict. REGISTRY is therefore "live for monitoring," not "live because
ALIVE" -- don't read membership here as a doctrine verdict. piggyback_2b was DEAD before
AND after the correction and was never wired live.
"""
from __future__ import annotations
import pandas as pd

from .engine import BENCH_W, sized_weights
from .signals import (sig_tsmom_12m, sig_tsmom_ensemble, sig_xsec_momentum,
                      sig_green_line_200d, sig_low_vol, sig_turn_of_month_research)

SLEEVE = 0.30   # fixed piggyback weight on the 0.70 60/40 core (pre-committed, not optimized)

# leg name -> signal fn. Covers every leg referenced by SPECS below (incl. DEAD ones,
# so research/piggyback_backtest.py can still backtest them), not just the live subset.
LEGS = {
    "tsmom_12m":       sig_tsmom_12m,
    "tsmom_ensemble":  sig_tsmom_ensemble,
    "xsec_momentum":   sig_xsec_momentum,
    "green_line_200d": sig_green_line_200d,
    "low_vol_xsec":    sig_low_vol,
    "turn_of_month":   sig_turn_of_month_research,
}

# construction name -> (legs, rebalance freq). All 4 pre-registered specs, backtested.
SPECS = {
    "piggyback_2a": (("tsmom_12m", "low_vol_xsec"), "M"),
    "piggyback_2b": (("low_vol_xsec", "turn_of_month"), "M"),
    "piggyback_3":  (("tsmom_12m", "green_line_200d", "low_vol_xsec"), "M"),
    "piggyback_4":  (("tsmom_12m", "xsec_momentum", "green_line_200d", "low_vol_xsec"), "M"),
}

# Live-for-monitoring subset (see module docstring -- corrected-DEAD as of v1.3, kept
# running by Dave's explicit decision, not a doctrine ALIVE verdict). piggyback_2b was
# excluded from the start (DEAD both before and after the Bonferroni correction).
_LIVE_MONITORED = {"piggyback_2a", "piggyback_3", "piggyback_4"}
REGISTRY = {name: spec for name, spec in SPECS.items() if name in _LIVE_MONITORED}


def target_weights(prices: pd.DataFrame, name: str) -> pd.Series:
    """Today's target weights: 70% of BENCH_W + 30% of the equal-weight blend of each
    leg's OWN vol-targeted, capped weights (the same sizing each leg gets standalone) --
    a real capital allocation across positions, not a return-stream blend."""
    legs, _ = REGISTRY[name]
    leg_weights = [sized_weights(prices, LEGS[leg](prices)).iloc[-1].fillna(0.0) for leg in legs]
    sleeve_w = sum(leg_weights) / len(leg_weights)
    bench_w = pd.Series(BENCH_W).reindex(prices.columns).fillna(0.0)
    return (1 - SLEEVE) * bench_w + SLEEVE * sleeve_w
