"""tradefabe.dashboard -- Streamlit-free data-shaping and chart-building layer for
the lab dashboard. app.py's render_* functions and the FastAPI layer (src/tradefabe/api/)
both import from here; this module has no Streamlit calls, mirroring how harness.py
imports engine.py rather than keeping a private copy of doctrine math.
"""
import json
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from tradefabe import factory
from tradefabe.kronos import KRONOS_OOS_START
from tradefabe.pricing import NON_PRICED as ACCRUAL_ONLY_BOOKS
from tradefabe.paths import REPO_ROOT, ARTIFACTS

BASE = str(REPO_ROOT)
ART = str(ARTIFACTS)

ANN  = 252


SURF, PAGE  = "#fcfcfb", "#f9f9f7"


INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


SLOTS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]


GOOD, CRIT  = "#0ca30c", "#d03b3b"


BENCH_C, SPY_C = "#52514e", "#898781"


DIV = ["#2a78d6", "#f0efec", "#e34948"]          # diverging blue <-> red, gray midpoint


def load_carry_backtest():
    """The carry book's backtest lives outside harness.py's artifacts (separate study,
    research/carry_hl.py) — different universe, different date range (since 2023-05, not
    2018 OOS), different stat shape (yield-based, not Sharpe-framed)."""
    curve = pd.read_csv(os.path.join(ART, "carry_hl_curve.csv"), index_col=0, parse_dates=True)
    with open(os.path.join(ART, "carry_hl_meta.json")) as fh:
        meta = json.load(fh)
    return curve.iloc[:, 0].rename("carry_net"), meta


def load_paper_state():
    """Deliberately uncached (small files, changes daily) so a page refresh always shows
    the latest `tradefabe run` cycle."""
    p = os.path.join(BASE, "state", "paper")
    summ = os.path.join(p, "summary.csv")
    hist = os.path.join(p, "history.csv")
    if not (os.path.exists(summ) and os.path.exists(hist)):
        return None, None
    psum = pd.read_csv(summ)
    phist = pd.read_csv(hist)
    # history.csv mixes bare-date rows (tradefabe run) with full-timestamp rows
    # (tradefabe mark, every 30min) -- read_csv's own parse_dates can't infer a single
    # format across that mix, so parse explicitly with format="mixed" instead.
    raw = phist["date"].astype(str)
    bare = ~raw.str.contains("T| ", regex=True)
    phist["date"] = pd.to_datetime(raw, format="mixed")
    # LEGACY REPAIR (#109). run_daily() used to key history on a bare date; that parses to
    # MIDNIGHT, so once sorted, the daily cycle's post-rebalance equity -- written around
    # 22:00-23:10 UTC -- was drawn at the START of the day it belonged at the END of,
    # producing a one-minute-wide V-notch on every chart at every daily boundary.
    # run_daily() now stamps minutes like run_mark(), but ~47 rows already exist and the
    # Action owns state/, so they are corrected on READ rather than by rewriting a ledger
    # this process does not own. End-of-day is the honest placement: a bare date can only
    # have come from the daily cycle, which never runs before 22:00 UTC.
    phist.loc[bare, "date"] += pd.Timedelta(hours=23, minutes=59)
    return psum, phist


def load_book_json(name):
    path = os.path.join(BASE, "state", "paper", f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def ann_stats(r):
    r = pd.Series(r).dropna()
    if len(r) < 30:
        return dict(Sharpe=np.nan, Sortino=np.nan, CAGR=np.nan, Vol=np.nan, MaxDD=np.nan, Calmar=np.nan)
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (ANN / len(r)) - 1
    vol = r.std() * np.sqrt(ANN)
    sharpe = r.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan
    dn = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(ANN) if dn > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return dict(Sharpe=sharpe, Sortino=sortino, CAGR=cagr, Vol=vol, MaxDD=dd,
                Calmar=(cagr / abs(dd) if dd else np.nan))


def fmt(v, kind="ratio"):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.2f}" if kind == "ratio" else f"{v:.1%}"


def signals_cost_bps():
    """The engine's per-side cost, read rather than hardcoded so the caption cannot drift
    from the number actually charged."""
    try:
        from tradefabe.engine import COST_BPS
        return float(COST_BPS)
    except Exception:                                    # noqa: BLE001
        return float("nan")


def money(v):
    """Whole dollars, or an em dash when the value genuinely isn't known (#109).

    `f"${nan:,.0f}"` renders as "$nan" and `f"${-0.08:,.0f}"` renders as "$-0" — both read
    as "this book is empty" when the truth is "we could not price it". A figure we cannot
    compute must never be typeset as a number."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"${v:,.0f}"


def _rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def themed_layout(**overrides):
    base = dict(
        paper_bgcolor=SURF, plot_bgcolor=SURF,
        font=dict(family="IBM Plex Mono, monospace", size=11, color=INK2),
        margin=dict(l=44, r=20, t=28, b=40),
        xaxis=dict(gridcolor=GRID, zeroline=False, showline=True, linecolor=GRID),
        yaxis=dict(gridcolor=GRID, zeroline=False, showline=True, linecolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        height=340,
    )
    base.update(overrides)
    return base


def book_panel_data(name, phist, full, meta, gy_last, price_now, price_date, piggy=None,
                    factory_bt=None, hourly_bt=None, kronos_bt=None, pipeline_bt=None):
    """Normalize a live paper book into one shape the panel can render, regardless of
    whether it's an equity-signal book (backtest in full_returns.csv, real ticker
    positions), a piggyback construction (backtest in piggyback_returns.csv, same
    positions shape as an equity book), a promoted strategy-factory candidate (backtest
    in factory_returns.csv, #28b -- only promoted candidates get a persisted curve, not
    all 20/day tested), a family L hourly book (backtest in hourly_returns.csv, #86), a
    promoted research-pipeline candidate (backtest in pipeline_returns.csv, #180 -- same
    only-promoted-gets-a-curve reasoning as the factory), or the carry book (backtest in
    a separate study, funding-accrual, no ticker positions).

    EVERY source that can produce a live book must be listed here. The fallback is a bare
    `full[name]`, which raises KeyError and takes the whole dashboard down -- adding
    family L to the Research Lab's lookup but not to THIS one did exactly that on
    2026-07-26, which is the failure CLAUDE.md's Known-gaps entry describes word for
    word."""
    live_hist = (phist[phist["book"] == name]
                 .drop_duplicates("date", keep="last")
                 .set_index("date")["equity"].sort_index())
    live_start = live_hist.index.min()
    kind = "carry" if name == "carry_btc_eth" else "equity"

    if kind == "equity":
        oos_start = pd.Timestamp(meta["oos_start"])
        if piggy is not None and name in piggy.columns:
            bt_returns = piggy[name]
        elif factory_bt is not None and name in factory_bt.columns:
            bt_returns = factory_bt[name]
        elif hourly_bt is not None and name in hourly_bt.columns:
            bt_returns = hourly_bt[name]
        elif kronos_bt is not None and name in kronos_bt.columns:
            bt_returns = kronos_bt[name]
            # Family M's window is the model's pretraining cutoff, NOT meta["oos_start"].
            # Slicing at 2018 here would be a no-op on the data but would mislabel the
            # chart and compute stats over a window the verdict never used.
            oos_start = pd.Timestamp(KRONOS_OOS_START)
        elif pipeline_bt is not None and name in pipeline_bt.columns:
            bt_returns = pipeline_bt[name]
        else:
            bt_returns = full[name]
        bt_curve = (1 + bt_returns.fillna(0)).cumprod()
        bt_curve = bt_curve[bt_curve.index >= oos_start]
        stats = ann_stats(bt_returns[bt_returns.index >= oos_start])
        row = gy_last.loc[name]
        extra = {"verdict": row["verdict"], "corr_bench": float(row["corr_bench"]),
                 "null_p95": float(row["null_p95"]), "freq": row["freq"]}
    else:
        carry_curve, carry_meta = load_carry_backtest()
        bt_curve = carry_curve
        stats = ann_stats(carry_curve.pct_change())
        extra = {"carry_meta": carry_meta}

    # The backtest window's real start, for the caption. Hardcoding "2018" was fine while
    # every book shared harness's OOS_START; family M does not (#105).
    bt_start = bt_curve.index.min() if len(bt_curve) else None

    handoff = bt_curve.asof(live_start)
    if pd.isna(handoff):
        handoff = bt_curve.iloc[-1] if len(bt_curve) else 1.0

    positions_df = None
    deployment = None
    # ACCRUAL_ONLY_BOOKS (#143) never populate `positions`/`cash` via this path -- their
    # equity moves through kronos_live.run_carry_kronos()/hourly.run_funding_timing()'s
    # direct multiplicative accrual instead, so cash+positions math here would silently
    # compute the untouched STARTING cash forever, not the real accrued equity (#149).
    # They still keep `kind == "equity"` for everything else (verdict badge, backtest
    # curve sourcing) -- only this specific figure needs the carve-out.
    if kind == "equity" and name not in ACCRUAL_ONLY_BOOKS:
        book = load_book_json(name)
        cash = float((book or {}).get("cash", 0.0))
        # The LEDGER's own prices first (#109). data/prices.csv is gitignored, so it is
        # local-only and can be arbitrarily stale while the ledger arrives fresh from the
        # Action every cycle -- and it holds only the 15 daily ETFs, so crypto_reversal_1h's
        # BTC-USD/ETH-USD priced to NaN and the panel rendered $-0 for a fully-deployed
        # $100k book. books.record_prices() now stores whatever actually priced each mark.
        ledger_px = (book or {}).get("last_prices") or {}
        rows = []
        for t, sh in sorted((book or {}).get("positions", {}).items(), key=lambda kv: -abs(kv[1])):
            p = ledger_px.get(t)
            if p is None and price_now is not None and t in price_now.index:
                p = price_now.get(t)
            p = float(p) if p is not None and pd.notna(p) else np.nan
            rows.append({"ticker": t, "units": sh, "last_price": p,
                         "value": sh * p if pd.notna(p) else np.nan})
        positions_df = pd.DataFrame(rows)
        held = len(positions_df)
        n_unpriced = int(positions_df["value"].isna().sum()) if held else 0
        # Series.sum() skips NaN, so an ALL-unpriceable book summed to 0.0 and equity
        # collapsed to cash -- rendering "$0 gross, $-0 equity" for a book that is fully
        # deployed. A number we cannot compute must read as unknown, never as zero.
        all_unpriced = held > 0 and n_unpriced == held
        # equity = cash + net position value (books.equity()'s own formula) -- the
        # denominator for "weight" must be TOTAL equity, not sum of position values, or
        # the weight column always sums to 100% and silently hides how much is in cash.
        priced_val = float(positions_df["value"].sum()) if held else 0.0
        equity = np.nan if all_unpriced else cash + priced_val
        if held and positions_df["value"].notna().any() and equity and pd.notna(equity):
            positions_df["weight"] = positions_df["value"] / equity
        gross = np.nan if all_unpriced else (
            float(positions_df["value"].abs().sum()) if held else 0.0)
        net = np.nan if all_unpriced else priced_val
        pct = lambda v: (v / equity if pd.notna(equity) and equity else np.nan)  # noqa: E731
        deployment = dict(cash=cash, equity=equity, gross=gross, net=net,
                          cash_pct=pct(cash), gross_pct=pct(gross), net_pct=pct(net),
                          n_unpriced=n_unpriced, n_held=held,
                          priced_at=(book or {}).get("last_prices_at"),
                          # A long/short book holds cash ABOVE equity because the short
                          # proceeds are cash. Callers caption on this rather than
                          # asserting vol-targeting, which family L books do not use.
                          is_short_funded=bool(pd.notna(net) and net < 0))

    return dict(kind=kind, bt_curve=bt_curve, live_start=live_start, bt_start=bt_start,
                handoff=handoff, live_hist=live_hist, stats=stats, positions_df=positions_df,
                deployment=deployment, positions_asof=price_date,
                trades_df=trades_frame(load_book_json(name)),
                book_json=load_book_json(name), **extra)


def trades_frame(book):
    """The book's fill log as a display frame, newest first (#109).

    Modular in the same sense `pricing.BOOK_SOURCE` is: any book whose ledger carries a
    `trades` list renders here with no per-book branch, so a future source needs no change.
    Returns an EMPTY frame (not None) when a book predates the log, so callers distinguish
    "no trades recorded yet" from "this book cannot have trades" via `book_json`.
    """
    cols = ["ts", "ticker", "side", "shares", "price", "notional", "position_after"]
    rows = (book or {}).get("trades") or []
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    for c in cols:                       # tolerate a row written by an older schema
        if c not in df.columns:
            df[c] = np.nan
    df["ts"] = pd.to_datetime(df["ts"], format="mixed", errors="coerce")
    return df[cols].sort_values("ts", ascending=False, kind="stable").reset_index(drop=True)


RANGE_WINDOWS = {
    "5H": pd.Timedelta(hours=5),
    "1D": pd.Timedelta(days=1),
    "1W": pd.Timedelta(days=7),
    "1M": pd.Timedelta(days=30),
    "3M": pd.Timedelta(days=90),
    "1Y": pd.Timedelta(days=365),
}


MIN_CHART_POINTS = 2


Y_PAD = 0.30


def window_slice(live_hist, window_label):
    """Slice the live ledger to the selected range, returning (series, widened). Never
    yields fewer than MIN_CHART_POINTS while the full series has that many: a book that
    only records one mark per day has a single row inside a 5H window, which Plotly draws
    as a lone dot. Widening back to the last two marks keeps it a LINE — and the caller
    captions the fact rather than silently pretending the window was honored."""
    if window_label == "ALL" or window_label not in RANGE_WINDOWS:
        return live_hist, False
    cutoff = live_hist.index[-1] - RANGE_WINDOWS[window_label]
    win = live_hist[live_hist.index >= cutoff]
    if len(win) >= MIN_CHART_POINTS or len(live_hist) < MIN_CHART_POINTS:
        return win, False
    return live_hist.tail(MIN_CHART_POINTS), True


def padded_range(values, pad=Y_PAD):
    """Y-axis bounds `pad` of the high-low span beyond each end, instead of Plotly's
    default — which, with fill="tozeroy", anchors the axis at $0 and squashes a $100k
    book's real ±0.3% moves into a dead-flat line. A perfectly flat series has no span to
    scale, so fall back to a small proportional band around it. Returns None for an empty
    series (let Plotly autorange rather than emit a degenerate range)."""
    v = pd.Series(values).dropna()
    if v.empty:
        return None
    lo, hi = float(v.min()), float(v.max())
    span = hi - lo
    if span <= 0:
        span = abs(hi) * 0.001 or 1.0
    return [lo - span * pad, hi + span * pad]


def live_equity_chart(live_hist, color, window_label):
    """Primary panel chart: the real paper ledger's own dollar equity, on its own time
    axis, filtered to the selected range — decoupled from the backtest curve entirely so
    ~2 days of live history is no longer an invisible sliver next to years of backtest.
    The y-axis is scaled to the VISIBLE data (see padded_range), not to zero: at $100k
    start capital every book's real day-to-day move is a rounding error against a $0
    baseline. The tozeroy fill is kept for the area look — Plotly clips it to the axis."""
    win, _ = window_slice(live_hist, window_label)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=win.index, y=win.values, name="Live paper equity",
                             mode="lines+markers", line=dict(color=color, width=2.6),
                             marker=dict(size=6 if len(win) < 10 else 3),
                             fill="tozeroy", fillcolor=_rgba(color, 0.08)))
    fig.update_layout(**themed_layout(height=340, yaxis_title="equity ($)",
                                      yaxis_tickformat="$,.2f", showlegend=False,
                                      yaxis_range=padded_range(win.values)))
    return fig


def backtest_chart(bt_curve, color):
    """Secondary/context chart: the full-history backtest, on its OWN natural time axis
    (not rescaled or spliced to the live series) — lives in a collapsed expander since it
    tells one multi-year story, not something to re-read every day."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bt_curve.index, y=bt_curve.values, name="Backtest (formula)",
                             mode="lines", line=dict(color=color, width=1.6, dash="dash")))
    fig.update_layout(**themed_layout(height=280, yaxis_title="growth of $1", showlegend=False))
    return fig


def divergence_status(data):
    """DOCTRINE.md v1.2 kill-rule-1, made real: trailing (up to) 2-month cumulative
    live-minus-backtest-implied return against a 2*sigma_m*sqrt(2) band, sigma_m = that
    book's own frozen backtest monthly-return std. Returns (state, detail) with state in
    {"insufficient", "ok", "diverging"} — "insufficient" below 60 days live, matching the
    doctrine's own 0-3-month plumbing-only tier (no verdict is legitimate that early)."""
    live_hist = data["live_hist"]
    elapsed_days = (live_hist.index[-1] - live_hist.index[0]).days
    if elapsed_days < 60 or len(live_hist) < 2:
        return "insufficient", (f"Only {elapsed_days}d of live history — doctrine v1.2 needs "
                                 f"≥60d before a divergence read means anything.")

    bt_at_live_dates = data["bt_curve"].reindex(live_hist.index, method="ffill")
    live_cum = live_hist / live_hist.iloc[0] - 1
    bt_cum = bt_at_live_dates / data["handoff"] - 1
    diff = live_cum - bt_cum
    window_start = diff.index[-1] - pd.Timedelta(days=min(60, elapsed_days))
    base = diff.loc[:window_start]
    divergence = diff.iloc[-1] - (base.iloc[-1] if len(base) else 0.0)

    monthly = data["bt_curve"].resample("ME").last().pct_change().dropna()
    sigma_m = monthly.std()
    threshold = 2 * sigma_m * np.sqrt(2)

    if abs(divergence) > threshold:
        return "diverging", (f"Live diverged {divergence:+.1%} from backtest-implied over the "
                              f"trailing ~2mo — outside the ±{threshold:.1%} expected band "
                              f"(doctrine kill-rule 1).")
    return "ok", (f"Live is tracking backtest within the expected ±{threshold:.1%} noise "
                  f"band (trailing ~2mo divergence {divergence:+.1%}).")


def luck_floor_chart(arr, freq_label, marks, color_of):
    bar = float(np.percentile(arr, 95))
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=arr, nbinsx=40, marker_color="#86b6ef",
                               marker_line_color=SURF, marker_line_width=0.5,
                               name="random strategies"))
    fig.add_vline(x=bar, line_dash="dash", line_color=INK,
                 annotation_text=f"p95 luck = {bar:.2f}", annotation_position="top",
                 annotation_font=dict(size=9, color=INK))
    for s_name, v in marks:
        c = color_of.get(s_name, INK2)
        fig.add_vline(x=v, line_color=c, line_width=2,
                     annotation_text=f"{s_name} {v:.2f}", annotation_position="top",
                     annotation_font=dict(size=8, color=c), annotation_textangle=-90)
    fig.update_layout(**themed_layout(
        xaxis_title=f"OOS Sharpe of {len(arr)} random strategies ({freq_label.lower()})",
        showlegend=False))
    return fig


def drawdown_chart(dd, color):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dd.index, y=dd.values, mode="lines", line=dict(color=color, width=1.4),
                             fill="tozeroy", fillcolor=_rgba(color, 0.30), name="drawdown"))
    fig.update_layout(**themed_layout(yaxis_title="drawdown", yaxis_tickformat=".0%", showlegend=False))
    return fig


def correlation_heatmap(cm):
    colorscale = [[0.0, DIV[0]], [0.5, DIV[1]], [1.0, DIV[2]]]
    fig = go.Figure(go.Heatmap(
        z=cm.values, x=list(cm.columns), y=list(cm.columns), zmin=-1, zmax=1,
        colorscale=colorscale, colorbar=dict(title=""),
        text=cm.round(2).values, texttemplate="%{text}",
        textfont=dict(size=10, color=INK),
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>"))
    fig.update_layout(**themed_layout(height=440, xaxis=dict(gridcolor=GRID, tickangle=-40),
                                      yaxis=dict(gridcolor=GRID, autorange="reversed")))
    return fig


def growth_chart(show, colors):
    fig = go.Figure()
    for col, c in zip(show.columns, colors):
        fig.add_trace(go.Scatter(x=show.index, y=show[col], mode="lines", name=col,
                                 line=dict(color=c, width=1.6)))
    fig.update_layout(**themed_layout(height=340, yaxis_title="growth of $1"))
    return fig


def fmt_full_dollars(v):
    """Full dollar-and-cent precision (e.g. $99,663.87) -- book status used to abbreviate
    to $99.7K, but at 8 live books the exact figure is worth the extra width."""
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


BOOK_FAMILIES = {
    "A": "Trend / momentum",
    "B": "Mean reversion",
    "C": "Calendar / seasonality",
    "D": "Defensive anomaly",
    "E": "Carry / structural",
    "F": "Volatility risk premium",
    "G": "Information / signal-following",
    "H": "Piggyback / combined",
    "I": "Breakout / channel",
    "L": "Intraday / hourly",
    "M": "Learned forecaster",   # #150 -- missing here silently dropped carry_kronos_vol/
                                 # kronos_wick_agg from every Family-grouped render, since
                                 # group_books_by_family() only emits keys of this dict.
    "O": "Research pipeline",   # #174 -- automated daily proposals (any PRIMITIVES shape),
                                # grouped by ORIGIN like L/M/N already are, not by mechanism
                                # -- pair_zscore and asset_class_trend_hedge share nothing
                                # mechanically, but both come from the same routine.
}


BOOK_FAMILY = {
    "tsmom_12m": "A", "tsmom_ensemble": "A", "green_line_200d": "A", "xsec_momentum": "A",
    "str_reversal_5d": "B",
    "turn_of_month": "C",
    "low_vol_xsec": "D",
    "carry_btc_eth": "E",
    "insider_buying_21d": "G",
    "piggyback_2a": "H", "piggyback_2b": "H", "piggyback_3": "H", "piggyback_4": "H",
    # strategy factory (#28) template variants -- STRATEGIES.md has the pre-registered specs
    "tsmom_3m": "A", "tsmom_6m": "A", "tsmom_9m": "A", "tsmom_18m": "A", "tsmom_24m": "A",
    "str_reversal_3d": "B", "str_reversal_10d": "B", "str_reversal_15d": "B", "str_reversal_20d": "B",
    "turn_of_month_narrow": "C", "turn_of_month_wide": "C",
    "low_vol_xsec_30d": "D", "low_vol_xsec_120d": "D",
    "donchian_20d": "I", "donchian_55d": "I",
    # family L, hourly (#86) -- all DEAD, all regime-limited to 2023+ by data availability
    "funding_timing_1h": "L", "crypto_reversal_1h": "L", "equity_tsmom_1h": "L",
    # family M, Kronos learned forecaster (#105) -- all DEAD, window is 2025-06-05+ only
    # (the model's pretraining cutoff), so these are NOT comparable to a 2018+ row
    "kronos_dir_daily": "M", "kronos_wick_agg": "M", "carry_kronos_vol": "M",
    # family N, pairs/cointegration (#172) -- DEAD, only LQD/HYG cleared the
    # cointegration filter of the 6 economically-motivated pairs tested
    "pairs_cointegration": "N",
}


def _load_generated_ledger():
    """Cached lookup of every LIVE-GENERATED candidate ever tested (#28b) -- name ->
    {"family", "rationale"} -- so book_family()/strategy_description() can resolve a
    generated candidate's name (e.g. "tsmom_gen_147d") without a static per-name dict
    entry, which is impossible here: the parameter is drawn fresh each cycle, not fixed
    at review time like TEMPLATES. generated_templates.csv is factory.py's own
    git-tracked audit ledger (every draw logged at generation time, before its verdict
    is known), so this is reading the SAME record the doctrine itself relies on."""
    path = os.path.join(BASE, "generated_templates.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return {row["name"]: {"family": row["family"], "rationale": row["rationale"]}
            for _, row in df.iterrows()}


def _load_pipeline_ledger():
    """Same role as _load_generated_ledger(), for the research pipeline's rp_-prefixed
    names (#174) instead of the factory's _gen_/combo ones. pipeline_ideas.csv has no
    per-row family column (unlike generated_templates.csv) because every pipeline
    proposal -- whichever PRIMITIVES shape it used -- shares the same origin, family "O",
    not a mechanism-specific one; see BOOK_FAMILIES's comment for why."""
    path = os.path.join(BASE, "pipeline_ideas.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return {row["name"]: {"family": "O", "rationale": row["rationale"]}
            for _, row in df.iterrows()}


def book_family(name):
    """BOOK_FAMILY lookup with two pattern-based fallbacks: factory_run.py names every
    combo it builds `factory_combo_<leg_a>_<leg_b>` (the legs vary run to run, since
    complementary_pairs() picks whichever pair is least-correlated THIS cycle) and every
    live-generated candidate `<family-prefix>_gen_<params>` (the params are drawn fresh
    each cycle) -- neither can have a static per-name dict entry. Anything else unmapped
    falls back to "?" (rendered as "Other")."""
    if name in BOOK_FAMILY:
        return BOOK_FAMILY[name]
    if name.startswith("factory_combo_"):
        return "H"
    gen = _load_generated_ledger().get(name)
    if gen:
        return gen["family"]
    pipe = _load_pipeline_ledger().get(name)
    if pipe:
        return pipe["family"]
    return "?"


REVIEW_AGE_DAYS = 60   # #147 -- how long a factory-promoted book monitors before it


def factory_owned_names() -> set:
    """Every book the factory itself has ever promoted (template + generated + combo
    origin) -- the pool research/factory_run.py's MAX_FACTORY_PROMOTED (#147) bounds.
    Hand-picked, hourly (family L), and Kronos (family M) books are never in this set:
    the factory doesn't touch them, so they have no accumulation problem to review."""
    return (set(factory.load_promoted())
            | {g["name"] for g in factory.load_promoted_generated()}
            | {c["name"] for c in factory.load_promoted_combos()})


def books_up_for_review(psum, phist, review_days=REVIEW_AGE_DAYS) -> list:
    """Factory-owned books that have been live `review_days`+ and aren't already
    retired -- a READ-ONLY nudge, not a retirement mechanism (#147). DOCTRINE v1.6
    (#113) is explicit: retiring a paper book is Dave's decision alone, no performance
    trigger, no drawdown threshold, no age rule -- so this list has no button and takes
    no action of its own. It exists purely so a factory-promoted book doesn't sit
    unreviewed forever just because nobody remembered it was there; the only way to
    actually retire one is still `tradefabe retire <book> --reason "..."`, run by hand.

    Returns rows sorted oldest-first (most overdue for a look), each carrying enough to
    decide without leaving the dashboard: book, days_live, equity, return, verdict."""
    if psum is None or psum.empty:
        return []
    introduced = book_introduced_dates(phist)
    owned = factory_owned_names()
    cutoff_days = pd.Timestamp.now().normalize()
    out = []
    for _, r in psum.iterrows():
        name = r["book"]
        if name not in owned:
            continue
        if pd.notna(r.get("retired_at")) and r.get("retired_at"):
            continue
        intro = introduced.get(name, pd.NaT)
        if pd.isna(intro):
            continue
        days_live = (cutoff_days - intro.normalize()).days
        if days_live < review_days:
            continue
        out.append({"book": name, "days_live": days_live, "equity": r["equity"],
                    "return": r["return"], "introduced": intro})
    out.sort(key=lambda r: r["days_live"], reverse=True)
    return out


def _is_monitor_only(name, gy_last):
    """A book is 'monitor-only' when it's live but backtest-DEAD (DOCTRINE v1.2's
    paper-testing scope: paper-tracked for research/dashboard value, never eligible for
    a paper-confirmed verdict). carry_btc_eth and any future factory-promoted book with
    no graveyard row at all -- i.e. genuinely ALIVE, not just untested -- are NOT
    monitor-only; only a logged DEAD verdict counts."""
    return gy_last is not None and name in gy_last.index and gy_last.loc[name, "verdict"] == "DEAD"


def group_books_by_family(psum, gy_last=None, show_monitor_only=True):
    """Pure grouping logic behind render_book_status(), split out so it's testable
    without a Streamlit runtime: which family each book in `psum` belongs to (unmapped
    names fall back to family key "?", displayed as "Other"), filtered by the
    monitor-only toggle. Returns an ordered list of (family_key, family_label, rows)
    tuples, family order matching BOOK_FAMILIES (A-H) then "Other" last, and empty
    families omitted entirely."""
    monitor_only = {r["book"]: _is_monitor_only(r["book"], gy_last) for _, r in psum.iterrows()}
    by_family = {}
    for _, r in psum.iterrows():
        if not show_monitor_only and monitor_only[r["book"]]:
            continue
        by_family.setdefault(book_family(r["book"]), []).append(r)
    out = []
    for family in list(BOOK_FAMILIES) + ["?"]:
        rows = by_family.get(family)
        if rows:
            out.append((family, BOOK_FAMILIES.get(family, "Other"), rows))
    return out


def book_introduced_dates(phist) -> dict:
    """Earliest recorded mark per book, from state/paper/history.csv (one row per mark) --
    a book's first appearance IS when it was introduced, no new data source needed. A book
    with zero phist rows is simply absent from the dict; callers must use
    `.get(name, pd.NaT)`, never `None` (mixing None/Timestamp breaks sort_values)."""
    if phist is None or phist.empty:
        return {}
    return phist.groupby("book")["date"].min().to_dict()


def book_return_today(phist) -> dict:
    """Change since the previous calendar day's close, per book -- NOT the total-return-
    since-inception column already on psum. `nan` (never raises) for a book with fewer
    than 2 distinct calendar days of history yet (e.g. just opened today), same NaN-safe
    convention as book_introduced_dates's NaT."""
    if phist is None or phist.empty:
        return {}
    out = {}
    for book, g in phist.groupby("book"):
        g = g.sort_values("date")
        today = g["date"].iloc[-1].normalize()
        prior = g[g["date"].dt.normalize() < today]
        out[book] = (g["equity"].iloc[-1] / prior["equity"].iloc[-1] - 1) if len(prior) else float("nan")
    return out


def sort_books_flat(psum, phist, gy_last=None, show_monitor_only=True, sort_key="recent"):
    """Flat (ungrouped) alternative to group_books_by_family(), for the non-"Family" sort
    modes -- same monitor-only filter, same row shape (dicts, drop-in for the Series
    group_books_by_family's rows already are: both support `r["book"]` / `r.get(...)`),
    just one list sorted descending instead of family-bucketed tuples.

    sort_key: "recent" (book_introduced_dates), "return_today" (book_return_today), or
    "total_return" (psum's own `return` column). Sorted via pandas sort_values, NOT a
    hand-rolled sorted() -- comparing None to a Timestamp, or NaN to a float, raises under
    plain Python sort but sort_values(na_position="last") handles both cleanly."""
    monitor_only = {r["book"]: _is_monitor_only(r["book"], gy_last) for _, r in psum.iterrows()}
    rows = [r for _, r in psum.iterrows() if show_monitor_only or not monitor_only[r["book"]]]
    if not rows:
        return []
    introduced = book_introduced_dates(phist)
    return_today = book_return_today(phist)
    df = pd.DataFrame(rows)
    df["_introduced"] = df["book"].map(lambda n: introduced.get(n, pd.NaT))
    df["_return_today"] = df["book"].map(lambda n: return_today.get(n, float("nan")))
    sort_col = {"recent": "_introduced", "return_today": "_return_today",
                "total_return": "return"}[sort_key]
    df = df.sort_values(sort_col, ascending=False, na_position="last")
    return list(df.to_dict("records"))


STRATEGY_DESCRIPTIONS = {
    "tsmom_12m": "Goes long or short on the sign of the trailing 12-month return — "
                 "a trend-follower betting that news gets underreacted to, not overreacted to.",
    "tsmom_ensemble": "Blends 3-, 6-, and 12-month trend signals into one vote, so no single "
                       "lookback window can whipsaw the book on its own.",
    "green_line_200d": "Long above its 200-day moving average, short below it — "
                        "the oldest trend rule there is, applied literally.",
    "turn_of_month": "Long the whole universe only around month-end (last 4 + first 3 "
                      "trading days) — a calendar flow, not a price prediction.",
    "piggyback_2a": "A 30% sleeve of tsmom_12m + low_vol_xsec on top of a 70% 60/40 core — "
                     "testing whether two standalone-dead bets earn their keep as diversifiers.",
    "piggyback_3": "A 30% sleeve of tsmom_12m + green_line_200d + low_vol_xsec on a 70% 60/40 "
                    "core — three standalone-dead legs, tested together as a diversifying sleeve.",
    "piggyback_4": "A 30% sleeve of tsmom_12m + xsec_momentum + green_line_200d + low_vol_xsec "
                    "on a 70% 60/40 core — the widest of the four piggyback blends.",
    "carry_btc_eth": "Delta-neutral: long spot, short perp on BTC and ETH, collecting the funding "
                      "rate with price risk hedged out by construction.",
    "xsec_momentum": "Ranks the universe by trailing 12-month return each month, long the top "
                      "half and short the bottom half — the cross-sectional cousin of trend.",
    "str_reversal_5d": "Fades the trailing 5-day move, rebalanced weekly — the opposite bet to "
                        "momentum: short-horizon overreaction instead of underreaction.",
    "low_vol_xsec": "Long the calmer half of the universe, short the wilder half (BAB-style: "
                     "leverage-constrained investors overpay for volatile assets).",
    "piggyback_2b": "A 30% sleeve of low_vol_xsec + turn_of_month on a 70% 60/40 core — the one "
                     "piggyback blend never wired live (DEAD before and after the v1.3 correction).",
    "insider_buying_21d": "Buys on Form-4 open-market insider purchases of $100k+, holding 21 "
                           "trading days — tests whether copying legally-disclosed insider trades "
                           "beats picking randomly.",
    # strategy factory (#28) template variants -- src/tradefabe/factory.py has each
    # template's full rationale; these mirror it in one line.
    "tsmom_3m": "Trend: sign of the trailing 3-month return — a faster lookback than "
                "tsmom_12m, testing whether the underreaction edge shows up sooner.",
    "tsmom_6m": "Trend: sign of the trailing 6-month return, between tsmom_3m and "
                "tsmom_12m's lookbacks.",
    "tsmom_9m": "Trend: sign of the trailing 9-month return.",
    "tsmom_18m": "Trend: sign of the trailing 18-month return — slower than tsmom_12m, "
                 "testing whether it filters more noise than signal.",
    "tsmom_24m": "Trend: sign of the trailing 24-month return, the slowest trend variant tested.",
    "str_reversal_3d": "Mean reversion: fade the trailing 3-day move — faster than the "
                        "already-tested 5-day fade.",
    "str_reversal_10d": "Mean reversion: fade the trailing 10-day move.",
    "str_reversal_15d": "Mean reversion: fade the trailing 15-day move.",
    "str_reversal_20d": "Mean reversion: fade the trailing 20-day move — slower than the "
                         "already-tested 5-day fade, closer to a monthly reversal.",
    "turn_of_month_narrow": "Calendar: narrower turn-of-month window (first 2 + last 2 "
                             "trading days) than the already-tested 3+4.",
    "turn_of_month_wide": "Calendar: wider turn-of-month window (first 5 + last 5 trading "
                           "days) than the already-tested 3+4.",
    "low_vol_xsec_30d": "Defensive anomaly: BAB-lite split using a faster 30-day vol window "
                         "than the already-tested 60-day one.",
    "low_vol_xsec_120d": "Defensive anomaly: BAB-lite split using a slower 120-day vol window "
                          "than the already-tested 60-day one.",
    "donchian_20d": "Breakout: long a new 20-day high, short a new 20-day low — reacts to a "
                    "price EXTREME rather than an average; the faster classic Turtle Trader length.",
    "donchian_55d": "Breakout: long a new 55-day high, short a new 55-day low — the slower "
                     "classic Turtle Trader channel length.",
    "funding_timing_1h": "Hourly: delta-neutral BTC+ETH carry whose notional is on when the "
                         "trailing 24h mean funding is positive and flat when it is negative. "
                         "DEAD — always-on carry returned +10.4%/yr at Sharpe 12.4 over the "
                         "identical window, so the timing overlay destroyed 40% of the return. "
                         "Regime-limited: hourly funding only exists from 2023-05.",
    "crypto_reversal_1h": "Hourly: fade the trailing 6h move on BTC+ETH, equal weight, "
                          "long/short. DEAD — turnover drag alone is 173%/yr (0.40 per bar × "
                          "8,679 bars/yr × 5bps). Regime-limited to 2024-07+.",
    "equity_tsmom_1h": "Hourly: sign of the trailing 24-bar (~5 session) return on the 15-ETF "
                       "universe, long/short. DEAD — lost 14.4%/yr against 14%/yr of turnover "
                       "drag. Regime-limited to 2023-08+.",
    "kronos_dir_daily": "Learned forecaster: sign of Kronos-base's 5-day forecast return on the "
                        "15-ETF universe, long/short, vol-targeted. DEAD — the forecast has NO "
                        "directional skill post-cutoff: 47.6% 5-day sign agreement (below a coin "
                        "flip) and corr −0.031 with realized over 4,245 pairs. Window is "
                        "2025-06-05+ only, the model's pretraining cutoff.",
    "kronos_wick_agg": "Learned forecaster, OHLC-only: long a name whose FORECAST bars form a "
                       "hammer (lower wick > 2× body, close in the top third) after a 5-day "
                       "pullback, held 5 bars, equal-weight, no vol targeting. DEAD — in-market "
                       "21% of bars for a sub-benchmark 0.69 Sharpe while SPY did 1.73. Window is "
                       "2025-06-05+ only.",
    "carry_kronos_vol": "Learned forecaster on the one ALIVE edge: delta-neutral BTC+ETH funding "
                        "carry with notional scaled by Kronos's forecast vol, capped at 1.0. "
                        "DEAD — strictly WORSE than always-on carry (Calmar 1.01 vs 32.71, and a "
                        "deeper drawdown), because every scale move pays cost on both legs. "
                        "Benchmark is always-on carry, not 60/40. Window is 2025-06-05+ only.",
    "pairs_cointegration": "Engle-Granger cointegration on 6 economically-motivated pairs "
                           "(GLD/SLV, TLT/IEF, EFA/EEM, SPY/QQQ, USO/DBC, LQD/HYG) — long/short "
                           "the SPREAD (hedge ratio frozen from 2007-2017), z-score entry/exit. "
                           "DEAD — only LQD/HYG cleared the cointegration filter (ADF p<0.05), and "
                           "that one pair's spread showed essentially no edge, Sharpe ≈0.00.",
}


def strategy_description(name):
    """STRATEGY_DESCRIPTIONS lookup with two pattern-based fallbacks, mirroring
    book_family(): factory_run.py's combo names vary run to run (whichever pair was
    least-correlated that cycle), so a static per-name entry can't cover them, and the
    leg names can't be unambiguously recovered by splitting the combo name on "_" (leg
    names themselves contain underscores) -- a generic description beats a fragile
    parse. Live-generated candidates (#28b) get their real per-candidate rationale from
    generated_templates.csv (logged at generation time), not a generic line."""
    if name in STRATEGY_DESCRIPTIONS:
        return STRATEGY_DESCRIPTIONS[name]
    if name.startswith("factory_combo_"):
        return ("A 30% sleeve on a 70% 60/40 core, built from the least-correlated pair "
                "of factory-tested candidates that cycle — see graveyard.csv for which two.")
    gen = _load_generated_ledger().get(name)
    if gen:
        return gen["rationale"]
    pipe = _load_pipeline_ledger().get(name)
    if pipe:
        return pipe["rationale"]
    return "(no description yet — add one to STRATEGY_DESCRIPTIONS in app.py)"


def retirement_note(book_json):
    """The ledger's own retirement block, or None (#113). Reads the book JSON rather than
    summary.csv so the panel keeps working on a ledger written before the column existed."""
    r = (book_json or {}).get("retired")
    if not r:
        return None
    return {"at": r.get("at"), "reason": r.get("reason") or "(no reason recorded)"}


def _dead_strategy_returns(name, oos, piggy, factory_bt=None, hourly_bt=None,
                           kronos_bt=None, pairs_bt=None, pipeline_bt=None):
    """Best-effort OOS return series for ANY graveyard entry (ALIVE or DEAD), for the
    strategy detail view below. Bare strategies live in `oos` (full_returns.csv, sliced
    to OOS_START by the caller); piggyback constructions in `piggy`
    (piggyback_returns.csv, already OOS-only at source -- see piggyback_backtest.py);
    promoted strategy-factory candidates in `factory_bt` (factory_returns.csv, #28b --
    only promoted candidates get a curve, not all 20/day tested); promoted research-
    pipeline candidates in `pipeline_bt` (pipeline_returns.csv, #180 -- same only-
    promoted-gets-a-curve reasoning). Returns None if none of the sources has this name
    (e.g. insider_buying_21d, whose backtest lives in a differently-shaped artifact,
    artifacts/insider_curves.csv, or a DEAD factory/pipeline candidate that was never
    promoted) -- the caller falls back to graveyard.csv's own logged summary stats
    rather than crashing."""
    if name in oos.columns:
        return oos[name].fillna(0)
    if piggy is not None and name in piggy.columns:
        return piggy[name].dropna()
    if factory_bt is not None and name in factory_bt.columns:
        return factory_bt[name].dropna()
    if hourly_bt is not None and name in hourly_bt.columns:
        return hourly_bt[name].dropna()
    if kronos_bt is not None and name in kronos_bt.columns:
        return kronos_bt[name].dropna()
    if pairs_bt is not None and name in pairs_bt.columns:
        return pairs_bt[name].dropna()
    if pipeline_bt is not None and name in pipeline_bt.columns:
        return pipeline_bt[name].dropna()
    return None
