"""Risk register for the carry book (#10).

The carry book is the only strategy in this lab that cleared doctrine, and its ~12%/yr is
payment for bearing real tail risk. This module holds that risk in one place so the
dashboard can show it next to the yield rather than letting the yield stand alone.

Two kinds of entry:
  - CITED   — external base rates, each with a real source and URL. No invented numbers.
  - MEASURED — computed from this lab's own data (the persisted carry curve, the live
    carry_risk.json), so they describe THIS book rather than the asset class.

Nothing here is advice; it is a disclosure of what can go wrong.
"""
from __future__ import annotations
import pandas as pd

SEVERITY = ("total loss", "severe", "moderate", "operational")


def _r(key, title, category, likelihood, impact, detail, source=None, url=None,
       measured=False):
    return {"key": key, "title": title, "category": category, "likelihood": likelihood,
            "impact": impact, "detail": detail, "source": source, "url": url,
            "measured": measured}


# ---------------------------------------------------------------- cited base rates
CITED = [
    _r("venue_failure", "Venue failure", "total loss",
       "45% of 40 exchanges failed; median life 381 days (2013 sample). ~59% of 845 "
       "exchanges failed over 2010–2023.",
       "Total loss of posted margin.",
       "Two independent samples a decade apart agree that exchange failure is a base-rate "
       "event, not a tail one. Hyperliquid is a DEX-style perp venue, the lower-risk half "
       "of the split — decentralised venues showed a 31.2% lower failure probability than "
       "centralised ones — but 'lower' is not 'low'.",
       "Moore & Christin (FC 2013); Sapkota, J. Int. Financial Markets (2024)",
       "https://tylermoore.utulsa.edu/toit17.pdf"),

    _r("forced_settlement", "Venue governance / forced settlement", "severe",
       "One realised instance on this venue (2025-03-26).",
       "A delta-neutral position can be closed at a price you did not choose, breaking "
       "the hedge by fiat rather than by market move.",
       "In the JELLY incident Hyperliquid validators voted to delist the perp and settled "
       "open positions at $0.0095 against a $0.50 listed price, absorbing ~$12M of vault "
       "loss. Consensus took about two minutes, which is the point: the venue can "
       "unilaterally redefine your exit. Delta-neutrality assumes both legs settle at "
       "market — this is the assumption breaking.",
       "Hyperliquid community incident record; CoinDesk (2025-03-26)",
       "https://www.coindesk.com/markets/2025/03/26/hyperliquid-delists-jellyjelly-after-vault-squeezed-in-usd13m-tussle"),

    _r("stablecoin_depeg", "Stablecoin depeg", "severe",
       "USDC fell to ~$0.87 in March 2023 and recovered within ~3 days. >1,900 depeg "
       "events across stablecoins 2020–mid-2023 (609 large-cap).",
       "Margin and P&L are denominated in a stablecoin; a depeg marks the whole book down "
       "even when the hedge is working perfectly.",
       "Typical deviation is small — mean absolute deviation ~0.19% for USDC and ~0.28% "
       "for USDT — but the distribution has a fat left tail driven by the reserve bank, "
       "not by crypto. The 2023 episode traced to Circle's $3.3B held at Silicon Valley "
       "Bank and resolved only when depositors were backstopped.",
       "S&P Global (2023); Moody's depeg count; Circle/SVB disclosures",
       "https://www.spglobal.com/en/research-insights/featured/special-editorial/stablecoins-a-deep-dive-into-valuation-and-depegging"),
]


# ---------------------------------------------------------------- measured in-lab
def measured_funding_risk(curve: pd.Series) -> dict:
    """Negative-funding statistics from the book's own persisted net curve.

    Net, i.e. after the 1.5%/yr fee drag — which is the number that matters and is
    strictly worse than the headline 'funding positive' figure the carry study reports on
    GROSS funding. Days where funding is positive but smaller than the drag still lose
    money."""
    r = curve.pct_change().dropna()
    neg = r < 0
    runs = (neg != neg.shift()).cumsum()
    lengths = neg.groupby(runs).sum()[neg.groupby(runs).first()]
    m30 = curve.pct_change(30).dropna()
    return {
        "days": int(len(r)),
        "start": r.index.min().date(), "end": r.index.max().date(),
        "pct_days_negative": float(neg.mean()),
        "longest_negative_run": int(lengths.max()) if len(lengths) else 0,
        "worst_day": float(r.min()),
        "worst_30d": float(m30.min()) if len(m30) else float("nan"),
        "pct_30d_windows_negative": float((m30 < 0).mean()) if len(m30) else float("nan"),
        "max_drawdown": float((curve / curve.cummax() - 1).min()),
    }


def measured_liquidation_risk(risk_json: dict | None, posture: str = "25%") -> dict | None:
    """Short-leg liquidation distance at a given fraction of the venue's live max
    leverage, from the monitor's own report. The book itself models pure funding yield
    with no leverage — this is a what-if overlay for an operator who ran it levered."""
    if not risk_json or "coins" not in risk_json:
        return None
    out = {}
    for coin, c in risk_json["coins"].items():
        p = (c.get("postures") or {}).get(posture)
        if p:
            out[coin] = {"leverage": p["leverage"], "liq_distance": p["liq_distance"]}
    return out or None


OPERATIONAL = _r(
    "operational", "Operational / data bugs", "operational",
    "Several realised, all caught; see CLAUDE.md's Known gaps.",
    "Wrong or stale numbers on the dashboard. No capital at risk while the book is paper.",
    "Realised examples: a promoted book with no persisted backtest curve crashed the "
    "dashboard outright; Python 3.14 silently skips hidden .pth files, breaking imports "
    "after a clean install; the 30-min mark cron does not fire while the machine sleeps, "
    "leaving real holes in the equity history. These are the failure mode most likely to "
    "mislead, precisely because they are silent.",
    measured=True)


def build(curve: pd.Series | None = None, risk_json: dict | None = None) -> list[dict]:
    """Full register: cited entries, plus measured ones when their data is available."""
    rows = list(CITED)
    if curve is not None and len(curve) > 31:
        m = measured_funding_risk(curve)
        rows.append(_r(
            "negative_funding", "Negative funding regime", "moderate",
            f"{m['pct_days_negative']:.1%} of days negative; longest run "
            f"{m['longest_negative_run']} days; {m['pct_30d_windows_negative']:.0%} of "
            f"30-day windows negative.",
            f"Worst 30-day stretch {m['worst_30d']:+.2%}; max drawdown "
            f"{m['max_drawdown']:+.2%}.",
            "The strategy's own core risk, and the one it is paid for: funding goes "
            "negative in bear regimes and the book bleeds. Measured net of the fee drag "
            f"over {m['days']} days ({m['start']} → {m['end']}). Realised drawdown has "
            "been shallow, but this sample contains no sustained bear funding regime — "
            "absence of a bad case is not evidence it cannot happen.",
            source="measured: artifacts/carry_hl_curve.csv", measured=True))
    rows.append(OPERATIONAL)
    return rows
