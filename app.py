"""app.py — tradefabe lab dashboard.   Run:  .venv/bin/streamlit run app.py

Two views, picked from the sidebar:
  Paper Books   — the live forward-paper books (state/paper/), home view. Per-strategy
                  drill-down: stats, positions/funding context, and a backtest -> live
                  spliced equity chart. Landing view.
  Research Lab  — the backtest summary produced by harness.py (run that first if
                  artifacts/ is empty): verdicts, luck floor, correlation, piggyback lab.

Paper/backtest only — no live trading.
"""
import json
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

BASE = os.path.dirname(os.path.abspath(__file__))
ART  = os.path.join(BASE, "artifacts")
ANN  = 252

# ---- design tokens (validated reference palette, light mode) ----
SURF, PAGE  = "#fcfcfb", "#f9f9f7"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SLOTS = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
GOOD, CRIT  = "#0ca30c", "#d03b3b"
BENCH_C, SPY_C = "#52514e", "#898781"
DIV = ["#2a78d6", "#f0efec", "#e34948"]          # diverging blue <-> red, gray midpoint

st.set_page_config(page_title="tradefabe lab", page_icon="📉", layout="wide")

# ---- lab-protocol visual identity (works with Streamlit, not against it) ----
LAB_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{
  --paper:#f7f8f7; --card:#fdfdfc; --ink:#14171a; --ink2:#4d5560; --mut:#8a929c;
  --rule:#e3e6e2; --accent:#2a5db0; --dead:#b3402e; --alive:#1e7d43;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,monospace;
  --disp:'Space Grotesk',system-ui,sans-serif;
}
[data-testid="stAppViewContainer"]{background:var(--paper);}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"],#MainMenu,footer{visibility:hidden;}
h1,h2,h3{font-family:var(--disp)!important;color:var(--ink)!important;}
h3{font-size:0.95rem!important;font-weight:600!important;text-transform:uppercase;
   letter-spacing:.07em;border-bottom:1px solid var(--rule);padding-bottom:.45rem!important;
   margin-top:1.4rem!important;}
.lab-eyebrow{font-family:var(--mono);font-size:.70rem;letter-spacing:.22em;color:var(--mut);
   text-transform:uppercase;margin-bottom:.35rem;}
.lab-spec{font-family:var(--mono);font-size:.72rem;color:var(--ink2);
   border-bottom:1px solid var(--rule);padding-bottom:.9rem;margin-bottom:.4rem;}
.lab-spec b{color:var(--ink);font-weight:600;}
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--rule);border-radius:6px;
   padding:.7rem .9rem .6rem;}
[data-testid="stMetricLabel"] p{font-family:var(--mono)!important;font-size:.66rem!important;
   letter-spacing:.12em;text-transform:uppercase;color:var(--mut)!important;}
[data-testid="stMetricValue"]{font-family:var(--mono)!important;font-weight:600;
   font-size:1.55rem!important;color:var(--ink)!important;}
[data-testid="stMetricDelta"]{font-family:var(--mono)!important;font-size:.78rem!important;}
[data-testid="stCaptionContainer"] p{font-family:var(--mono)!important;font-size:.70rem!important;
   color:var(--mut)!important;}
[data-testid="stDataFrame"]{font-variant-numeric:tabular-nums;}
[data-testid="stSidebar"]{background:#f1f3f1;border-right:1px solid var(--rule);}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] li{font-size:.80rem;color:var(--ink2);}
hr{border-color:var(--rule)!important;}
a{color:var(--accent);}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
</style>
"""
st.markdown(LAB_CSS, unsafe_allow_html=True)


# ==================================================================== data loading
@st.cache_data
def load_backtest():
    full = pd.read_csv(os.path.join(ART, "full_returns.csv"), index_col=0, parse_dates=True)
    with open(os.path.join(ART, "meta.json")) as fh:
        meta = json.load(fh)
    nulls = {k: v for k, v in np.load(os.path.join(ART, "nulls.npz")).items()}
    gy = pd.read_csv(os.path.join(BASE, "graveyard.csv"))
    return full, meta, nulls, gy


@st.cache_data
def load_piggyback_backtest():
    """Backtest OOS returns for the 4 piggyback constructions (research/piggyback_backtest.py),
    same shape as full_returns.csv's columns but kept separate since it's a different study
    (constructions, not bare strategies) that can be rerun independently. None if not yet run."""
    path = os.path.join(ART, "piggyback_returns.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


@st.cache_data
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
    phist = pd.read_csv(hist, parse_dates=["date"])
    return psum, phist


def load_carry_risk():
    """Deliberately uncached, same reasoning as load_paper_state — this is the report
    check_carry_risk() writes once per `tradefabe run` cycle, never fetched live from the
    dashboard itself."""
    path = os.path.join(BASE, "state", "paper", "carry_risk.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


@st.cache_data
def load_price_snapshot():
    """Last cached close per ticker, for pricing open paper positions in the UI. Not a
    live quote — the caption on the positions table says so."""
    path = os.path.join(BASE, "data", "prices.csv")
    if not os.path.exists(path):
        return None, None
    px = pd.read_csv(path, index_col=0, parse_dates=True)
    return px.iloc[-1], px.index[-1]


def load_book_json(name):
    path = os.path.join(BASE, "state", "paper", f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


# ==================================================================== stats
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


# ==================================================================== plotly theming
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


# ==================================================================== per-book normalization
def book_panel_data(name, phist, full, meta, gy_last, price_now, price_date, piggy=None):
    """Normalize a live paper book into one shape the panel can render, regardless of
    whether it's an equity-signal book (backtest in full_returns.csv, real ticker
    positions), a piggyback construction (backtest in piggyback_returns.csv, same
    positions shape as an equity book), or the carry book (backtest in a separate study,
    funding-accrual, no ticker positions)."""
    live_hist = (phist[phist["book"] == name]
                 .drop_duplicates("date", keep="last")
                 .set_index("date")["equity"].sort_index())
    live_start = live_hist.index.min()
    kind = "carry" if name == "carry_btc_eth" else "equity"

    if kind == "equity":
        oos_start = pd.Timestamp(meta["oos_start"])
        bt_returns = piggy[name] if piggy is not None and name in piggy.columns else full[name]
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

    handoff = bt_curve.asof(live_start)
    if pd.isna(handoff):
        handoff = bt_curve.iloc[-1] if len(bt_curve) else 1.0

    positions_df = None
    deployment = None
    if kind == "equity":
        book = load_book_json(name)
        cash = float((book or {}).get("cash", 0.0))
        rows = []
        for t, sh in sorted((book or {}).get("positions", {}).items(), key=lambda kv: -abs(kv[1])):
            p = float(price_now.get(t)) if price_now is not None and t in price_now.index else np.nan
            rows.append({"ticker": t, "units": sh, "last_price": p, "value": sh * p if pd.notna(p) else np.nan})
        positions_df = pd.DataFrame(rows)
        # equity = cash + net position value (books.equity()'s own formula) -- the
        # denominator for "weight" must be TOTAL equity, not sum of position values, or
        # the weight column always sums to 100% and silently hides how much is in cash.
        priced_val = positions_df["value"].sum() if len(positions_df) else 0.0
        equity = cash + (priced_val if pd.notna(priced_val) else 0.0)
        if len(positions_df) and positions_df["value"].notna().any() and equity:
            positions_df["weight"] = positions_df["value"] / equity
        gross = float(positions_df["value"].abs().sum()) if len(positions_df) else 0.0
        net = float(priced_val) if pd.notna(priced_val) else 0.0
        deployment = dict(cash=cash, equity=equity, gross=gross, net=net,
                          cash_pct=(cash / equity if equity else np.nan),
                          gross_pct=(gross / equity if equity else np.nan),
                          net_pct=(net / equity if equity else np.nan))

    return dict(kind=kind, bt_curve=bt_curve, live_start=live_start,
                handoff=handoff, live_hist=live_hist, stats=stats, positions_df=positions_df,
                deployment=deployment, positions_asof=price_date,
                book_json=load_book_json(name), **extra)


# ==================================================================== chart builders
RANGE_WINDOWS = {"1D": 1, "1W": 7, "1M": 30, "3M": 90, "1Y": 365}


def live_equity_chart(live_hist, color, window_label):
    """Primary panel chart: the real paper ledger's own dollar equity, on its own time
    axis, filtered to the selected range — decoupled from the backtest curve entirely so
    ~2 days of live history is no longer an invisible sliver next to years of backtest."""
    if window_label != "ALL" and window_label in RANGE_WINDOWS:
        cutoff = live_hist.index[-1] - pd.Timedelta(days=RANGE_WINDOWS[window_label])
        live_hist = live_hist[live_hist.index >= cutoff]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=live_hist.index, y=live_hist.values, name="Live paper equity",
                             mode="lines+markers", line=dict(color=color, width=2.6),
                             marker=dict(size=6 if len(live_hist) < 10 else 3),
                             fill="tozeroy", fillcolor=_rgba(color, 0.08)))
    fig.update_layout(**themed_layout(height=340, yaxis_title="equity ($)",
                                      yaxis_tickformat="$,.0f", showlegend=False))
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


# ==================================================================== Paper Books view
def render_paper_books(psum, phist, full, meta, gy_last):
    st.markdown(
        '<div class="lab-eyebrow">tradefabe · live paper books · paper only</div>',
        unsafe_allow_html=True)

    if psum is None or psum.empty:
        st.info("No paper books yet — run `.venv/bin/tradefabe run` to open the first cycle.")
        return

    st.subheader("Book status")
    cols = st.columns(len(psum))
    for col, (_, r) in zip(cols, psum.iterrows()):
        col.metric(r["book"], f"${r['equity']:,.0f}", f"{r['return']:+.2%}")
    st.caption(f"Books start at $100k paper capital. Last run: **{psum['last_run'].max()}** · "
               "run `.venv/bin/tradefabe run` daily (or via cron) to advance.")

    st.divider()
    names = psum["book"].tolist()
    color_of = {n: SLOTS[i % len(SLOTS)] for i, n in enumerate(names)}
    pick = st.selectbox("Strategy", names)

    price_now, price_date = load_price_snapshot()
    piggy = load_piggyback_backtest()
    data = book_panel_data(pick, phist, full, meta, gy_last, price_now, price_date, piggy)
    render_strategy_panel(pick, data, color_of[pick])


def render_strategy_panel(name, data, color):
    st.markdown(f"### {name}")
    s = data["stats"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Sharpe", fmt(s["Sharpe"]))
    c2.metric("Sortino", fmt(s["Sortino"]))
    c3.metric("Calmar", fmt(s["Calmar"]))
    c4.metric("Max Drawdown", fmt(s["MaxDD"], "pct"))
    c5.metric("CAGR", fmt(s["CAGR"], "pct"))
    c6.metric("Vol (ann.)", fmt(s["Vol"], "pct"))
    st.caption("Stats computed on the out-of-sample backtest — the paper track alone is "
               "too young (< 30 days) for its own Sharpe/Sortino/etc. to mean anything yet.")

    if data["kind"] == "equity":
        verdict = "✅ ALIVE" if data["verdict"] == "ALIVE" else "💀 DEAD"
        st.caption(f"Backtest verdict: **{verdict}** · corr to 60/40: **{data['corr_bench']:.2f}** · "
                   f"noise floor p95: **{data['null_p95']:.2f}** · rebalance **{data['freq']}**")
    else:
        cm = data["carry_meta"]
        st.caption("Delta-neutral funding carry (BTC + ETH perps, Hyperliquid) — price risk hedged "
                   "out by construction; the book earns funding minus a 1.5%/yr fee drag.")
        m1, m2, m3 = st.columns(3)
        m1.metric("Net yield (since 2023-05)", f"{cm['net_yield']:.1%}")
        m2.metric("% days positive", f"{cm['pct_days_positive']:.0%}")
        m3.metric("Carried through BTC crash", f"{cm['carry_through_crash']:+.1%}",
                  f"BTC drawdown {cm['btc_worst_dd']:.0%}")

    st.divider()
    st.markdown("**Live paper equity**")
    live_hist = data["live_hist"]
    span_days = (live_hist.index[-1] - live_hist.index[0]).days
    options = [w for w in ("1D", "1W", "1M", "3M", "1Y", "ALL")
               if w == "ALL" or span_days >= RANGE_WINDOWS[w]]
    choice = st.segmented_control("Range", options, default="ALL", required=True,
                                  key=f"range_{name}", label_visibility="collapsed")
    st.plotly_chart(live_equity_chart(live_hist, color, choice), width="stretch")
    st.caption(f"Real paper fills since **{data['live_start'].date()}** (start "
               f"${live_hist.iloc[0]:,.0f}). The ledger (`state/paper/{name}.json`) is "
               f"never modified by this display.")

    with st.expander("Backtest history (2018 → present) & live tracking check"):
        st.plotly_chart(backtest_chart(data["bt_curve"], INK2), width="stretch")
        state, detail = divergence_status(data)
        icon = {"insufficient": "⏳", "ok": "✅", "diverging": "⚠️"}[state]
        (st.warning if state == "diverging" else st.caption)(f"{icon} {detail}")

    st.divider()
    if data["kind"] == "equity":
        st.markdown("**Capital deployed**")
        dep = data["deployment"]
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Cash (undeployed)", f"${dep['cash']:,.0f}", fmt(dep["cash_pct"], "pct") + " of equity")
        d2.metric("Gross exposure", f"${dep['gross']:,.0f}", fmt(dep["gross_pct"], "pct") + " of equity")
        d3.metric("Net exposure", f"${dep['net']:,.0f}", fmt(dep["net_pct"], "pct") + " of equity")
        d4.metric("Total equity", f"${dep['equity']:,.0f}")
        st.caption("Gross = sum of |position value| (both legs of a long/short book); net = "
                   "long minus short (directional tilt). Vol-targeted sizing deliberately "
                   "leaves room in cash rather than forcing 100% deployment — that's a "
                   "feature of the sizing (see `engine.py`'s `sized_weights`), not a bug.")

        st.markdown("**Current positions**")
        pdf = data["positions_df"]
        if pdf is None or pdf.empty:
            st.caption("No open positions (book hasn't rebalanced yet).")
        else:
            st.dataframe(pdf, width="stretch", hide_index=True, column_config={
                "ticker": st.column_config.TextColumn("Ticker"),
                "units": st.column_config.NumberColumn("Units", format="%.2f"),
                "last_price": st.column_config.NumberColumn("Last price", format="$%.2f"),
                "value": st.column_config.NumberColumn("Value", format="$%.0f"),
                "weight": st.column_config.NumberColumn("Weight (% of equity)", format="percent"),
            })
            asof = data["positions_asof"]
            st.caption(f"Priced as of the cached data date ({asof.date() if asof is not None else 'unknown'}), "
                       "not a live quote. Weight is % of TOTAL equity (cash + positions), "
                       "not % of invested value — it no longer always sums to 100%.")
    else:
        bj = data["book_json"] or {}
        st.markdown("**Book state**")
        st.write(f"Equity **${bj.get('equity', float('nan')):,.2f}** · "
                 f"last run **{bj.get('last_run', '—')}**")

        st.divider()
        st.markdown("**Risk monitor** — funding-flip alert + short-leg liquidation distance")
        render_carry_risk_panel()


def render_carry_risk_panel():
    risk = load_carry_risk()
    if risk is None:
        st.caption("No risk report yet — generated automatically by `.venv/bin/tradefabe run`.")
        return

    st.caption(f"As of **{risk['generated_at']}** · trailing **{risk['funding_window_days']}d** funding")
    rc1, rc2 = st.columns(2)
    for col, coin in zip((rc1, rc2), ("BTC", "ETH")):
        c = risk["coins"][coin]
        f7 = c["funding_7d"]
        flip = c["funding_flip_alert"]
        val = f"{'⚠️ ' if flip else ''}{f7:+.2%}" if f7 is not None else "—"
        col.metric(f"{coin} 7d funding", val)
    if risk["blended_funding_flip_alert"]:
        st.warning("Blended 7d funding has turned negative — bear-regime bleed. The book "
                   "loses money net of the fee drag until this flips back.")

    rows = []
    for coin in ("BTC", "ETH"):
        c = risk["coins"][coin]
        for frac_label, p in c["postures"].items():
            rows.append({"posture": frac_label, "coin": coin, "leverage": p["leverage"],
                        "liq_distance": p["liq_distance"]})
    if rows:
        pdf = pd.DataFrame(rows).pivot(index="posture", columns="coin", values=["leverage", "liq_distance"])
        pdf = pdf.reindex([f"{f:.0%}" for f in [0.10, 0.25, 0.50, 1.00]])
        pdf.columns = [f"{coin} {metric.replace('_', ' ')}" for metric, coin in pdf.columns]
        st.dataframe(pdf.style.format({c: ("{:.1f}x" if "leverage" in c else "{:+.1%}") for c in pdf.columns}),
                    width="stretch")
        hl = risk["headline_leverage_fraction"]
        flagged = [c for c, v in risk["high_risk_alert"].items() if v]
        if flagged:
            st.error(f"High risk: at {hl:.0%} of Hyperliquid's live max leverage, "
                     f"**{', '.join(flagged)}** liquidation distance is under the "
                     f"{risk['liq_distance_warn']:.0%} pump-cushion threshold.")
    else:
        st.caption("Leverage tiers unavailable this run (Hyperliquid unreachable) — funding "
                   "alert above still reflects the last successful fetch.")
    st.caption("Postures are % of Hyperliquid's **live** max leverage per coin (fetched fresh "
               "each `tradefabe run`), not what this paper book actually holds — the book models "
               "pure funding yield with no leverage. This is a what-if overlay: if an operator ran "
               "the short leg at that leverage, how far could price pump before liquidation.")


# ==================================================================== Research Lab view
def render_research_lab(full, meta, nulls, gy):
    OOS = pd.Timestamp(meta["oos_start"])
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    color_of = {s: SLOTS[i % len(SLOTS)] for i, s in enumerate(strats)}
    oos = full[full.index >= OOS]
    gy_last = gy.drop_duplicates("strategy", keep="last").set_index("strategy")

    st.markdown(
        f"""<div class="lab-eyebrow">tradefabe · strategy evaluation lab · paper only</div>
<div class="lab-spec">DATA <b>{meta['source']}</b> {meta['start']} → {meta['end']} ·
OOS FROM <b>{meta['oos_start']}</b> · {meta['n_assets']} ASSETS ·
DOCTRINE <b>v1.0.1</b> — pre-registered gates, no tuning after verdicts</div>""",
        unsafe_allow_html=True)

    n_tested = gy_last.shape[0]
    n_alive = int((gy_last["verdict"] == "ALIVE").sum())
    best = gy_last["oos_sharpe"].astype(float).idxmax()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tested", n_tested)
    c2.metric("Alive", n_alive)
    c3.metric("Dead", n_tested - n_alive)
    c4.metric("Luck floor p95", f"{meta['null_bars'].get('M', float('nan')):.2f}")
    c5.metric(f"Best · {best}", f"{float(gy_last.loc[best, 'oos_sharpe']):.2f}")
    st.caption(f"60/40 benchmark OOS Sharpe: **{float(gy_last['bench_sharpe'].iloc[0]):.2f}** — the honest bar for gate 2.")

    st.subheader("Growth of $1 — out-of-sample")
    sel = st.multiselect("Strategies", strats, default=strats, label_visibility="collapsed")
    show = pd.DataFrame(index=oos.index)
    colors = []
    for s in sel:
        show[s] = (1 + oos[s].fillna(0)).cumprod()
        colors.append(color_of[s])
    show["60/40"] = (1 + oos["bench_6040"].fillna(0)).cumprod()
    colors.append(BENCH_C)
    show["SPY"] = (1 + oos["spy"].fillna(0)).cumprod()
    colors.append(SPY_C)
    st.plotly_chart(growth_chart(show, colors), width="stretch")
    st.caption("Strategies run at a ~10% vol target; 60/40 and SPY are the passive context lines. "
               "Sharpe/Calmar (below) are the fair comparison — raw growth favors whoever took more risk.")

    st.subheader("Verdicts — the graveyard ledger")
    tbl = gy_last.reset_index()[["strategy", "freq", "oos_sharpe", "oos_sortino", "oos_calmar",
                                 "oos_maxdd", "corr_bench", "null_p95", "verdict"]].copy()
    tbl["verdict"] = tbl["verdict"].map(lambda v: ("✅ " if v == "ALIVE" else "💀 ") + v)
    st.dataframe(
        tbl.style.map(lambda v: f"color: {GOOD}; font-weight: 600" if "ALIVE" in str(v)
                      else (f"color: {CRIT}; font-weight: 600" if "DEAD" in str(v) else ""),
                      subset=["verdict"]),
        width="stretch", hide_index=True)

    st.subheader("The luck floor — is anything distinguishable from random?")
    freq_names = {"M": "Monthly-rebalanced", "W": "Weekly-rebalanced", "D": "Daily-rebalanced"}
    present = [f for f in ("M", "W", "D") if f in nulls]
    tabs = st.tabs([freq_names[f] for f in present])
    for tab, f in zip(tabs, present):
        with tab:
            arr = nulls[f]
            marks = [(s_name, float(gy_last.loc[s_name, "oos_sharpe"]))
                     for s_name, s_freq in meta["strategy_freq"].items()
                     if s_freq == f and s_name in gy_last.index]
            st.plotly_chart(luck_floor_chart(arr, freq_names[f], marks, color_of), width="stretch")

    st.subheader("Underwater — drawdown from peak")
    pick = st.selectbox("Strategy", strats + ["60/40", "SPY"])
    col = {"60/40": "bench_6040", "SPY": "spy"}.get(pick, pick)
    r = oos[col].fillna(0)
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    c = color_of.get(pick, BENCH_C if pick == "60/40" else SPY_C)
    st.plotly_chart(drawdown_chart(dd, c), width="stretch")
    st.caption(f"Max drawdown: **{dd.min():.1%}**")

    st.subheader("Correlation — different bets, or the same bet in disguise?")
    cm = oos[strats + ["bench_6040"]].rename(columns={"bench_6040": "60/40"}).corr()
    st.plotly_chart(correlation_heatmap(cm), width="content")
    with st.expander("Table view"):
        st.dataframe(cm.round(2), width="stretch")

    st.subheader("Piggyback lab — sleeve on the 60/40 core")
    st.caption("A DEAD-standalone strategy can still earn a seat as a diversifier. "
               "Blend a sleeve into the passive core and see what happens to the combined book.")
    lc, rc = st.columns([1, 2])
    with lc:
        sleeve_pct = st.slider("Sleeve weight (%)", 0, 50, 30, 5)
        sleeve_sel = st.multiselect("Sleeve strategies (equal-weighted)", strats,
                                    default=["xsec_momentum", "tsmom_12m"])
    if sleeve_sel:
        sleeve = oos[sleeve_sel].mean(axis=1)
        w = sleeve_pct / 100
        combo = (1 - w) * oos["bench_6040"].fillna(0) + w * sleeve.fillna(0)
        sb, sc_ = ann_stats(oos["bench_6040"]), ann_stats(combo)
        with rc:
            m1, m2, m3 = st.columns(3)
            m1.metric("Sharpe", f"{sc_['Sharpe']:.2f}", f"{sc_['Sharpe'] - sb['Sharpe']:+.2f} vs 60/40")
            m2.metric("Calmar", f"{sc_['Calmar']:.2f}", f"{sc_['Calmar'] - sb['Calmar']:+.2f} vs 60/40")
            m3.metric("Max drawdown", f"{sc_['MaxDD']:.1%}", f"{(sc_['MaxDD'] - sb['MaxDD']) * 100:+.1f} pts vs 60/40")
            cmp_show = pd.DataFrame({"60/40 + sleeve": (1 + combo).cumprod(),
                                     "60/40 alone": (1 + oos["bench_6040"].fillna(0)).cumprod()})
            st.plotly_chart(growth_chart(cmp_show, ["#2a78d6", BENCH_C]), width="stretch")
            st.caption("Reminder: a sleeve usually LOWERS raw dollars while smoothing the ride — "
                       "Sharpe up ≠ more profit.")


# ==================================================================== entry point
psum, phist = load_paper_state()
try:
    full, meta, nulls, gy = load_backtest()
    gy_last = gy.drop_duplicates("strategy", keep="last").set_index("strategy")
    backtest_ok = True
except FileNotFoundError:
    full = meta = nulls = gy = gy_last = None
    backtest_ok = False

with st.sidebar:
    st.markdown('<div class="lab-eyebrow">tradefabe</div>'
                '<h1 style="font-size:1.3rem;margin:0 0 .4rem">evaluation lab</h1>',
                unsafe_allow_html=True)
    st.caption("An honest lab for killing bad trading strategies. **Paper/backtest only.**")
    view = st.radio("View", ["Paper Books", "Research Lab"], label_visibility="collapsed")
    st.divider()
    if view == "Paper Books":
        if psum is not None:
            st.markdown(f"**{len(psum)} books live** · last run {psum['last_run'].max()[:10]}\n\n"
                        "Each book trades a doctrine-tested signal forward with simulated fills "
                        "(equity books) or real accrued funding (carry). Run "
                        "`.venv/bin/tradefabe run` daily to advance.")
        else:
            st.markdown("No paper books yet — run `.venv/bin/tradefabe run` to open the first cycle.")
    elif backtest_ok:
        st.markdown(
            f"**Data** {meta['source']} · {meta['start']} → {meta['end']} · {meta['n_assets']} assets\n\n"
            f"**Out-of-sample** from {meta['oos_start']}\n\n"
            f"**Universe** {', '.join(meta['universe'])}\n\n"
            f"*Artifacts generated {meta['generated_at']}*")
        st.divider()
        st.markdown(
            "**Doctrine gates (all must pass)**\n"
            "1. Beat the p95 of random strategies (same rebalance freq, same costs)\n"
            "2. Beat 60/40 on Calmar, or genuinely diversify\n"
            "3. MaxDD ≤ 1.5× the benchmark's\n\n"
            "No tuning to rescue a DEAD strategy.")

if view == "Paper Books":
    if not backtest_ok:
        st.warning("Backtest artifacts not found — per-strategy stats need `.venv/bin/python harness.py` "
                   "run at least once. Book status still shows below.")
        psum2, phist2 = psum, phist
        if psum2 is not None:
            st.subheader("Book status")
            cols = st.columns(len(psum2))
            for col, (_, r) in zip(cols, psum2.iterrows()):
                col.metric(r["book"], f"${r['equity']:,.0f}", f"{r['return']:+.2%}")
        else:
            st.info("No paper books yet — run `.venv/bin/tradefabe run` to open the first cycle.")
    else:
        render_paper_books(psum, phist, full, meta, gy_last)
else:
    if not backtest_ok:
        st.error("No artifacts found — run `.venv/bin/python harness.py` first.")
        st.stop()
    render_research_lab(full, meta, nulls, gy)

st.divider()
st.caption("tradefabe · doctrine-governed strategy lab · backtests & paper only — nothing here is "
           "investment advice, and no real money is connected.")
