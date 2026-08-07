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
from tradefabe import risk_register, factory
from tradefabe.pricing import NON_PRICED as ACCRUAL_ONLY_BOOKS
from tradefabe.dashboard import (
    ART, BASE, BENCH_C, CRIT, GOOD, INK2, MIN_CHART_POINTS, RANGE_WINDOWS,
    REVIEW_AGE_DAYS, SLOTS, SPY_C, Y_PAD,
    load_carry_backtest, load_paper_state, load_book_json, ann_stats, fmt,
    signals_cost_bps, money, _rgba, themed_layout, book_panel_data, trades_frame,
    window_slice, padded_range, live_equity_chart, backtest_chart, divergence_status,
    luck_floor_chart, drawdown_chart, correlation_heatmap, growth_chart,
    fmt_full_dollars, book_family, factory_owned_names, books_up_for_review,
    _is_monitor_only, group_books_by_family, book_introduced_dates, book_return_today,
    sort_books_flat, strategy_description, retirement_note, _dead_strategy_returns,
    load_backtest, load_piggyback_backtest, load_factory_backtest,
    load_pipeline_backtest, load_hourly_backtest, load_kronos_backtest,
    load_price_snapshot, book_colors, latest_verdicts, available_windows,
)

BASE = os.path.dirname(os.path.abspath(__file__))
ART  = os.path.join(BASE, "artifacts")

st.set_page_config(page_title="tradefabe lab", page_icon=":material/monitoring:", layout="wide")

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
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--rule);border-radius:8px;
   padding:.7rem .9rem .6rem;transition:border-color .12s ease,box-shadow .12s ease;}
[data-testid="stMetricLabel"] p{font-family:var(--mono)!important;font-size:.66rem!important;
   letter-spacing:.12em;text-transform:uppercase;color:var(--mut)!important;
   white-space:normal!important;overflow-wrap:break-word;line-height:1.3;}
[data-testid="stMetricValue"]{font-family:var(--mono)!important;font-weight:600;
   font-size:1.55rem!important;color:var(--ink)!important;
   white-space:normal!important;overflow-wrap:break-word;}
[data-testid="stMetricDelta"]{font-family:var(--mono)!important;font-size:.78rem!important;}
[data-testid="stCaptionContainer"] p{font-family:var(--mono)!important;font-size:.70rem!important;
   color:var(--mut)!important;}
[data-testid="stDataFrame"]{font-variant-numeric:tabular-nums;}
[data-testid="stSidebar"]{background:#f1f3f1;border-right:1px solid var(--rule);}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] li{font-size:.80rem;color:var(--ink2);}
hr{border-color:var(--rule)!important;}
a{color:var(--accent);}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}

/* -- status badges: a ledger-stamp, not a SaaS pill -- squared corners, bordered,
   uppercase mono, reused everywhere a verdict/state needs to read at a glance -- */
.tf-badge{display:inline-block;padding:.1rem .45rem;border-radius:3px;
   font-family:var(--mono);font-size:.68rem;font-weight:600;letter-spacing:.05em;
   text-transform:uppercase;white-space:nowrap;border:1px solid currentColor;
   vertical-align:1px;}
.tf-badge--alive{color:var(--alive);background:rgba(30,125,67,.08);}
.tf-badge--dead{color:var(--dead);background:rgba(179,64,46,.08);}
.tf-badge--warn{color:#8a5a00;background:rgba(138,90,0,.08);}
.tf-badge--muted{color:var(--mut);background:rgba(138,146,156,.10);}

/* -- strategy blurb: one plain-English line, always in the same spot (right under
   the strategy header, above the stat row) so the eye learns where to find it -- */
.tf-blurb{font-family:var(--mono);font-size:.82rem;color:var(--ink2);line-height:1.55;
   border-left:2px solid var(--accent);padding:.1rem 0 .1rem .75rem;margin:.3rem 0 1rem;}

/* -- book status cards: click target is an invisible button absolutely stacked over
   the whole card, so clicking anywhere selects it. The bordered box lives on the CARD
   CONTAINER itself (not on the inner st.metric, as it used to) so the name + "introduced"
   date can render as their own lines ABOVE the metric and still land inside the same box
   -- st.metric's own box is stripped back to transparent here, scoped to book cards only,
   so every OTHER st.metric in the app (strategy stat rows, etc.) is untouched. */
/* min-height reserves room for name + date + metric + an optional "retired" badge, so a
   row mixing retired/non-retired cards (common in the flat sort modes, which interleave
   far more than family grouping did) doesn't look jagged -- shorter cards just keep
   whitespace at the bottom instead of the row shrinking unevenly. */
div[class*="st-key-book_card_"]{position:relative;min-height:148px;background:var(--card);
   border:1px solid var(--rule);border-radius:8px;padding:.7rem .9rem .6rem;
   transition:border-color .12s ease,box-shadow .12s ease;}
div[class*="st-key-book_card_"] [data-testid="stMetric"]{
   cursor:pointer;background:transparent;border:none;padding:0;}
div[class*="st-key-book_card_idle_"]:hover{
   border-color:var(--accent);box-shadow:0 1px 6px rgba(20,23,26,.06);}
div[class*="st-key-book_card_active_"]{
   border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);}
.tf-book-name{font-family:var(--mono);font-size:.66rem;letter-spacing:.12em;
   text-transform:uppercase;color:var(--mut);overflow-wrap:break-word;line-height:1.3;}
.tf-book-date{font-family:var(--mono);font-size:.68rem;color:var(--mut);
   margin:.1rem 0 .15rem;}
div[class*="st-key-book_click_"]{position:absolute;inset:0;z-index:3;}
div[class*="st-key-book_click_"] [data-testid="stElementContainer"]{
   position:absolute!important;inset:0!important;width:100%!important;height:100%!important;}
div[class*="st-key-book_click_"] button{
   position:absolute!important;inset:0!important;width:100%!important;height:100%!important;
   min-height:0!important;min-width:0!important;
   margin:0!important;padding:0!important;border:none!important;opacity:0!important;cursor:pointer;}
/* the Cmd+R keybinding shim is a functional iframe, not UI -- st.iframe rejects a
   0 size (components.html allowed it), so it renders 1px and is hidden here. */
iframe[title="st.iframe"]{display:none!important;}
</style>
"""
st.markdown(LAB_CSS, unsafe_allow_html=True)


def _bind_refresh_shortcut():
    """Cmd+R (Mac) / Ctrl+R triggers the same cache-clear + rerun as the sidebar Refresh
    button, without the browser/desktop-window doing its own native reload.

    st.iframe (not st.html) is required here: the script must run in a real iframe with
    same-origin access so it can reach window.parent.document and see keystrokes on the
    actual app. st.html renders inline and would break that. A flag on the parent document
    guards against re-binding on every rerun."""
    st.iframe("""
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.__tfRefreshBound) return;
            doc.__tfRefreshBound = true;
            doc.addEventListener('keydown', function(e) {
                const mod = e.metaKey || e.ctrlKey;
                if (mod && e.key.toLowerCase() === 'r') {
                    e.preventDefault();
                    e.stopPropagation();
                    const btn = doc.querySelector('.st-key-refresh_data_btn button');
                    if (btn) btn.click();
                }
            }, true);
        })();
        </script>
    """, height=1, width=1)


# ==================================================================== data loading


@st.cache_data
def load_pairs_backtest():
    """Backtest OOS returns for family N, pairs/cointegration (research/pairs_backtest.py,
    #172). A SIXTH curve source beside full/piggyback/factory/hourly/kronos -- same reason
    as hourly: the study builds its own signal over a ticker subset (only pairs that
    cleared the cointegration filter), not harness.py's full-universe daily cache. None if
    the study hasn't been run."""
    path = os.path.join(ART, "pairs_returns.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path, index_col=0, parse_dates=True)


def load_carry_risk():
    """Deliberately uncached, same reasoning as load_paper_state — this is the report
    check_carry_risk() writes once per `tradefabe run` cycle, never fetched live from the
    dashboard itself."""
    path = os.path.join(BASE, "state", "paper", "carry_risk.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


# Delta-neutral carry/gated-carry books (#143). These update equity via a direct
# multiplicative funding accrual (kronos_live.run_carry_kronos(), hourly.run_funding_timing(),
# carry_live.run_carry()) and NEVER call books.rebalance_to()/log_trades() -- there is no
# discrete "trade" in their economics, just a continuous funding payment. Unlike a book
# that simply hasn't had a qualifying signal fire yet (e.g. kronos_wick_agg, which DOES
# call rebalance_to() and will eventually log a fill), these will NEVER populate `trades`,
# so the generic "no fills yet, starts at next rebalance" caption is actively false for
# them.
#
# ACCRUAL_ONLY_BOOKS is `pricing.NON_PRICED` (imported above, aliased for readability at
# each call site below) -- NOT a second independent set (#157). Before this alias, the
# exact same book names were hand-maintained separately in both files; a book added to
# one and not the other would silently pass in whichever module got updated and render
# wrong numbers (or fetch a price for an unpriced book) in whichever didn't. There is now
# exactly one place a new accrual-only book must be registered: pricing.NON_PRICED.
# tests/test_book_accounting_consistency.py enforces that membership against the source
# of every book-owning module, so a book that directly sets book["equity"] without being
# added there fails a test instead of rendering the frozen starting cash forever.


def render_trade_log(data):
    """The fill log: what was traded, when, at what price (#109).

    Before this, `rebalance_to()` computed target shares, turnover and cost and then kept
    only the resulting position — so a book could be watched but never seen ACTING. Every
    row here is one real simulated fill from the ledger.

    Deliberately no per-book branching for books THAT CAN have trades: any ledger carrying
    a `trades` list renders, so a new book source needs no change here (same contract as
    `pricing.BOOK_SOURCE`). ACCRUAL_ONLY_BOOKS is the one necessary exception -- those
    books structurally never populate `trades`, so they need a caption that says so."""
    tdf = data.get("trades_df")
    if tdf is None:
        return
    st.markdown("**Trade log**")
    name = (data.get("book_json") or {}).get("name")
    if tdf.empty and name in ACCRUAL_ONLY_BOOKS:
        st.caption("This book is delta-neutral carry: its value moves from funding "
                   "accrual, not discrete trades, so no fill log ever applies here — "
                   "not an empty log waiting to fill, a different economics entirely.")
        return
    if tdf.empty:
        st.caption("No fills recorded yet. The log starts at this book's next rebalance — "
                   "earlier trades happened before the ledger recorded them (#109) and "
                   "cannot be reconstructed, since only the resulting position was kept.")
        return

    st.dataframe(tdf, width="stretch", hide_index=True, column_config={
        "ts": st.column_config.DatetimeColumn("When (UTC)", format="YYYY-MM-DD HH:mm"),
        "ticker": st.column_config.TextColumn("Ticker"),
        "side": st.column_config.TextColumn("Side"),
        "shares": st.column_config.NumberColumn("Δ units", format="%+.2f"),
        "price": st.column_config.NumberColumn("Fill price", format="$%.2f"),
        "notional": st.column_config.NumberColumn("Notional", format="$%.0f"),
        "position_after": st.column_config.NumberColumn("Position after", format="%.2f"),
    })
    last_ts = tdf["ts"].max()
    st.caption(
        f"{len(tdf)} fill(s), newest first; last {last_ts:%Y-%m-%d %H:%M} UTC. "
        "Sides are named from the POSITION's view, not the order's: BUY/SELL open or "
        "grow a long, SHORT/COVER open or reduce a short. Simulated fills at the mark "
        f"close with a {signals_cost_bps():.0f}bp per-side cost, capped at the most "
        "recent 500 — these ledgers are committed to git every cycle, so the log is "
        "bounded on purpose.")


def badge(text, kind="muted"):
    """Ledger-stamp status tag (see .tf-badge in LAB_CSS) -- render with
    unsafe_allow_html=True, inline inside an st.markdown/st.caption string."""
    return f'<span class="tf-badge tf-badge--{kind}">{text}</span>'


def _select_book(name):
    st.session_state.selected_book = name


# Per-family extra metrics beyond the generic 6-stat row, for strategies whose economics
# the generic row doesn't fully cover (e.g. carry's yield-based economics -- see
# render_strategy_panel's carry branch). Empty for families with no DEAD strategy needing
# it yet -- add an entry here only once a specific family's generic-6 stats turn out to
# miss something, not preemptively (#31).
FAMILY_EXTRA_METRICS = {}


def render_book_status(psum, phist, gy_last=None):
    """Book-status cards. Default sort groups by family (STRATEGIES.md's own A-H
    taxonomy) so the grid stays scannable as the roster grows past a handful of books;
    three more sort modes (recency, today's return, total return) flatten into one
    ordered list instead, via sort_books_flat() (#141). Each card is a real st.metric
    (same type scale as everywhere else in the app) with an invisible full-card button
    stacked on top, so clicking anywhere on a card selects that book (replaces the old
    'Strategy' dropdown). Wrapped at 4 per row so cards stay wide enough for full $
    precision without truncating or overlapping (fix for the 8-book truncation bug)."""
    st.subheader("Book status")
    names = psum["book"].tolist()
    if st.session_state.get("selected_book") not in names:
        st.session_state.selected_book = names[0]

    sort_mode = st.selectbox(
        "Sort by", ["Family", "Recently added", "Return today", "Total return"],
        key="book_sort_mode",
        help="Family (default) groups cards by STRATEGIES.md's A-H taxonomy. The other "
             "three flatten into one list, ordered newest/highest-return first.")

    monitor_only = {n: _is_monitor_only(n, gy_last) for n in names}
    show_monitor_only = True
    if gy_last is not None and any(monitor_only.values()) and not all(monitor_only.values()):
        show_monitor_only = st.checkbox(
            "Show monitor-only (backtest-DEAD) books", value=True, key="show_monitor_only",
            help="Books that are live for research/dashboard value but backtest-DEAD -- "
                 "DOCTRINE v1.2 bars them from a paper-confirmed verdict under any "
                 "circumstance. Hiding these keeps the default view on confirmed/live "
                 "candidates as the roster grows.")
        # if the filter just hid the currently-selected book, fall back to the first
        # still-visible one rather than leaving the panel below pointing at a book with
        # no highlighted card in the grid. Sort-mode switches never need this: they only
        # reorder/flatten the SAME visible set, and highlighting matches by name, not
        # position, so a book keeps its highlight wherever it lands.
        if not show_monitor_only and monitor_only.get(st.session_state.selected_book):
            visible = [n for n in names if not monitor_only[n]]
            if visible:
                st.session_state.selected_book = visible[0]

    introduced = book_introduced_dates(phist)
    return_today = book_return_today(phist)

    def render_card(col, r, show_today_return):
        name = r["book"]
        selected = st.session_state.selected_book == name
        with col:
            with st.container(key=f"book_card_{'active' if selected else 'idle'}_{name}"):
                with st.container(key=f"book_click_{name}"):
                    st.button(name, key=f"book_btn_{name}", on_click=_select_book, args=(name,))
                if show_today_return:
                    rt = return_today.get(name, float("nan"))
                    delta = f"{rt:+.2%}" if np.isfinite(rt) else "—"
                else:
                    delta = f"{r['return']:+.2%}"
                # Name + "introduced" date rendered manually (not st.metric's label) so the
                # date can sit on its OWN line between the name and the $ value -- a single
                # label string has no way to carry two lines. st.metric still owns the $
                # value + delta pair, same typography/arrow logic as everywhere else in
                # the app; only its label is collapsed to avoid a duplicate name.
                st.markdown(f'<div class="tf-book-name">{name}</div>', unsafe_allow_html=True)
                intro = introduced.get(name, pd.NaT)
                if pd.notna(intro):
                    st.markdown(f'<div class="tf-book-date">{intro.strftime("%-m.%-d.%y")}</div>',
                               unsafe_allow_html=True)
                st.metric("", fmt_full_dollars(r["equity"]), delta, label_visibility="collapsed")
                # summary.csv gained retired_at in #113; .get() keeps a card
                # rendering against a summary written before the column existed.
                if pd.notna(r.get("retired_at")) and r.get("retired_at"):
                    st.markdown(badge("retired", "muted"), unsafe_allow_html=True)

    PER_ROW = 4
    if sort_mode == "Family":
        for family, label, rows in group_books_by_family(psum, gy_last, show_monitor_only):
            st.markdown(f'<div class="lab-eyebrow">{label}</div>', unsafe_allow_html=True)
            for i in range(0, len(rows), PER_ROW):
                cols = st.columns(PER_ROW)
                for col, r in zip(cols, rows[i:i + PER_ROW]):
                    render_card(col, r, show_today_return=False)
    else:
        sort_key = {"Recently added": "recent", "Return today": "return_today",
                    "Total return": "total_return"}[sort_mode]
        rows = sort_books_flat(psum, phist, gy_last, show_monitor_only, sort_key)
        for i in range(0, len(rows), PER_ROW):
            cols = st.columns(PER_ROW)
            for col, r in zip(cols, rows[i:i + PER_ROW]):
                render_card(col, r, show_today_return=(sort_key == "return_today"))


def render_up_for_review(psum, phist, gy_last):
    """Read-only nudge (#147) -- lists factory-owned books past REVIEW_AGE_DAYS so they
    don't sit unreviewed just because nobody remembered them, WITHOUT taking any action
    itself. No button here retires anything; the only real path is `tradefabe retire`,
    run by hand, same as always -- see books_up_for_review()'s docstring for why."""
    rows = books_up_for_review(psum, phist)
    if not rows:
        return
    with st.expander(f"Up for review ({len(rows)})", icon=":material/history:"):
        st.caption(
            f"Factory-promoted, live {REVIEW_AGE_DAYS}+ days. A nudge to look, not an "
            "automatic action -- DOCTRINE v1.6 makes retiring a book your decision "
            "alone. Free a slot with `.venv/bin/tradefabe retire <book> --reason \"...\"`.")
        df = pd.DataFrame(rows)
        df["verdict"] = df["book"].map(
            lambda n: gy_last.loc[n, "verdict"] if gy_last is not None and n in gy_last.index else "—")
        df["introduced"] = df["introduced"].dt.strftime("%-m.%-d.%y")
        df["equity"] = df["equity"].map(fmt_full_dollars)
        df["return"] = df["return"].map(lambda v: f"{v:+.2%}")
        df = df.rename(columns={"book": "Book", "days_live": "Days live", "introduced": "Introduced",
                                "equity": "Equity", "return": "Return", "verdict": "Backtest verdict"})
        st.dataframe(df[["Book", "Days live", "Introduced", "Equity", "Return", "Backtest verdict"]],
                    hide_index=True, width="stretch")


# ==================================================================== Paper Books view
def render_paper_books(psum, phist, full, meta, gy_last):
    st.markdown(
        '<div class="lab-eyebrow">tradefabe · live paper books · paper only</div>',
        unsafe_allow_html=True)

    if psum is None or psum.empty:
        st.info("No paper books yet — run `.venv/bin/tradefabe run` to open the first cycle.",
                icon=":material/info:")
        return

    render_book_status(psum, phist, gy_last)
    st.caption(f"Books start at $100k paper capital. Last run: **{psum['last_run'].max()}** · "
               "run `.venv/bin/tradefabe run` daily (or via cron) to advance.")
    render_up_for_review(psum, phist, gy_last)

    st.divider()
    names = psum["book"].tolist()
    color_of = book_colors(names)
    pick = st.session_state.selected_book

    price_now, price_date = load_price_snapshot()
    piggy = load_piggyback_backtest()
    factory_bt = load_factory_backtest()
    data = book_panel_data(pick, phist, full, meta, gy_last, price_now, price_date, piggy,
                           factory_bt, load_hourly_backtest(), load_kronos_backtest(),
                           load_pipeline_backtest())
    render_strategy_panel(pick, data, color_of[pick])


def render_strategy_panel(name, data, color):
    st.markdown(f"### {name}")
    blurb = strategy_description(name)
    st.markdown(f'<div class="tf-blurb">{blurb}</div>', unsafe_allow_html=True)
    retired = retirement_note(data.get("book_json"))
    if retired:
        st.info(f"**Retired {retired['at']}** — {retired['reason']}\n\n"
                f"The ledger is frozen: no further rebalances or marks. Everything below "
                f"is the record as of that moment, kept deliberately — a monitor-only "
                f"book's forward history is the evidence it was opened to collect. "
                f"Retirement here is always a human decision; nothing in the engine "
                f"retires a book on its own.", icon=":material/pause_circle:")
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
        verdict_badge = badge(data["verdict"], "alive" if data["verdict"] == "ALIVE" else "dead")
        st.caption(f"Backtest verdict: {verdict_badge} · corr to 60/40: **{data['corr_bench']:.2f}** · "
                   f"noise floor bar: **{data['null_p95']:.2f}** (Bonferroni-adjusted, DOCTRINE v1.3) · "
                   f"rebalance **{data['freq']}**", unsafe_allow_html=True)
    else:
        cm = data["carry_meta"]
        st.caption(f"Backtest verdict: {badge('ALIVE', 'alive')} — the only strategy that has "
                   "cleared doctrine for real-capital consideration (still paper here) · "
                   "funding shown net of a 1.5%/yr fee drag", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Net yield (since 2023-05)", f"{cm['net_yield']:.1%}")
        m2.metric("% days positive", f"{cm['pct_days_positive']:.0%}")
        m3.metric("Carried through BTC crash", f"{cm['carry_through_crash']:+.1%}",
                  f"BTC drawdown {cm['btc_worst_dd']:.0%}")

    st.divider()
    st.markdown("**Live paper equity**")
    live_hist = data["live_hist"]
    options = available_windows(live_hist)
    choice = st.segmented_control("Range", options, default="ALL", required=True,
                                  key=f"range_{name}", label_visibility="collapsed")
    st.plotly_chart(live_equity_chart(live_hist, color, choice), width="stretch")
    win, widened = window_slice(live_hist, choice)
    if widened:
        st.caption(f"Only one mark falls inside the {choice} window — showing the last "
                   f"{len(win)} marks ({win.index[0]:%Y-%m-%d %H:%M} → "
                   f"{win.index[-1]:%Y-%m-%d %H:%M}) so this reads as a line rather than "
                   "a single dot. This book marks less often than the 30min cron.")
    st.caption(f"Real paper fills since **{data['live_start'].date()}** (start "
               f"${live_hist.iloc[0]:,.0f}). Y-axis is scaled to the visible range "
               f"(±{Y_PAD:.0%} padding), not to $0. The ledger "
               f"(`state/paper/{name}.json`) is never modified by this display.")

    bt_from = data.get("bt_start")
    bt_label = f"{bt_from:%Y-%m-%d}" if bt_from is not None else "2018"
    with st.expander(f"Backtest history ({bt_label} → present) & live tracking check"):
        st.plotly_chart(backtest_chart(data["bt_curve"], INK2), width="stretch")
        state, detail = divergence_status(data)
        state_badge = badge({"insufficient": "pending", "ok": "tracking",
                             "diverging": "diverging"}[state],
                            {"insufficient": "muted", "ok": "alive", "diverging": "warn"}[state])
        if state == "diverging":
            st.warning(detail, icon=":material/warning:")
        else:
            st.caption(f"{state_badge} {detail}", unsafe_allow_html=True)

    st.divider()
    if data["kind"] == "equity":
        st.markdown("**Capital deployed**")
        if name in ACCRUAL_ONLY_BOOKS:
            # #149 -- same set #143 already carved out of the trade log, for the same
            # reason: positions/cash are permanently untouched by the accrual path, so
            # the cash+positions math below would silently show the frozen starting
            # cash forever instead of the real accrued equity.
            st.caption("This book is delta-neutral carry: its value moves from funding "
                       "accrual, not discrete positions, so there's no cash/gross/net "
                       "breakdown to show here — the live equity chart above is the "
                       "real number.")
        else:
            dep = data["deployment"]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Cash (undeployed)", money(dep["cash"]), fmt(dep["cash_pct"], "pct") + " of equity")
            d2.metric("Gross exposure", money(dep["gross"]), fmt(dep["gross_pct"], "pct") + " of equity")
            d3.metric("Net exposure", money(dep["net"]), fmt(dep["net_pct"], "pct") + " of equity")
            d4.metric("Total equity", money(dep["equity"]))
            if dep.get("n_unpriced"):
                st.warning(
                    f"{dep['n_unpriced']} of {dep['n_held']} held position(s) could not be "
                    "priced, so the figures above are incomplete. This is shown rather than "
                    "silently summed to $0 — an unpriceable book is not an empty one.",
                    icon=":material/warning:")
            cap = ("Gross = sum of |position value| (both legs of a long/short book); net = "
                   "long minus short (directional tilt).")
            if dep.get("is_short_funded"):
                cap += (" **Cash exceeds equity because this book is net short** — the short "
                        "proceeds are cash, so cash = equity − net exposure. Nothing is "
                        "borrowed and nothing is wrong.")
            else:
                cap += (" Vol-targeted sizing deliberately leaves room in cash rather than "
                        "forcing 100% deployment — that's a feature of the sizing (see "
                        "`engine.py`'s `sized_weights`), not a bug.")
            if dep.get("priced_at"):
                cap += f" Priced from the ledger's own marks as of {dep['priced_at']} UTC."
            st.caption(cap)

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

        render_trade_log(data)
    else:
        bj = data["book_json"] or {}
        st.markdown("**Book state**")
        st.write(f"Equity **${bj.get('equity', float('nan')):,.2f}** · "
                 f"last run **{bj.get('last_run', '—')}**")

        st.divider()
        st.markdown("**Risk monitor** — funding-flip alert + short-leg liquidation distance")
        render_carry_risk_panel()

        st.divider()
        render_risk_register()


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
        val = f"{f7:+.2%}" if f7 is not None else "—"
        col.metric(f"{coin} 7d funding", val)
        if flip:
            col.markdown(badge("funding flip", "warn"), unsafe_allow_html=True)
    if risk["blended_funding_flip_alert"]:
        st.warning("Blended 7d funding has turned negative — bear-regime bleed. The book "
                   "loses money net of the fee drag until this flips back.",
                   icon=":material/warning:")

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
                     f"{risk['liq_distance_warn']:.0%} pump-cushion threshold.",
                     icon=":material/error:")
    else:
        st.caption("Leverage tiers unavailable this run (Hyperliquid unreachable) — funding "
                   "alert above still reflects the last successful fetch.")
    st.caption("Postures are % of Hyperliquid's **live** max leverage per coin (fetched fresh "
               "each `tradefabe run`), not what this paper book actually holds — the book models "
               "pure funding yield with no leverage. This is a what-if overlay: if an operator ran "
               "the short leg at that leverage, how far could price pump before liquidation.")


SEVERITY_BADGE = {"total loss": "dead", "severe": "warn", "moderate": "warn",
                  "operational": "muted"}


def render_risk_register():
    """The tail risk the carry yield is payment for, shown next to the yield (#10).

    Entries are either CITED (external base rate, real source + URL) or MEASURED (computed
    from this lab's own curve). No invented probabilities."""
    st.markdown("**Risk register** — what the ~12%/yr is actually paying for")
    curve, _ = load_carry_backtest()
    rows = risk_register.build(curve, load_carry_risk())

    for r in rows:
        sev = badge(r["category"], SEVERITY_BADGE.get(r["category"], "muted"))
        tag = badge("measured" if r["measured"] else "cited",
                    "alive" if r["measured"] else "muted")
        with st.expander(r["title"]):
            st.markdown(f"{sev} {tag}", unsafe_allow_html=True)
            st.markdown(f"**How often:** {r['likelihood']}")
            st.markdown(f"**If it happens:** {r['impact']}")
            st.caption(r["detail"])
            if r["source"]:
                src = f"[{r['source']}]({r['url']})" if r["url"] else r["source"]
                st.caption(f"Source: {src}")

    st.caption("Cited entries carry a real source; measured entries are computed from this "
               "lab's own data. Neither is a forecast — a base rate is what happened to a "
               "population, not a probability for this book. Absence of a bad case in a "
               "3-year sample is not evidence one cannot occur.")


def render_strategy_detail(gy_last, oos, piggy, factory_bt=None, hourly_bt=None,
                           kronos_bt=None, pairs_bt=None, pipeline_bt=None):
    """Per-strategy detail for ANY graveyard entry, not just the strategies that made it
    to a live paper book -- the "Verdicts" table above is the full ledger, but until this
    every DEAD strategy was just one flat row in it, with no blurb/chart/stat-card
    treatment at all (#31). Same visual language as render_strategy_panel's live-book
    view (blurb, verdict badge, 6-stat row, backtest chart) minus anything that only
    makes sense for a LIVE book (live-equity chart, positions, capital deployed)."""
    st.subheader("Strategy detail — every tested candidate, alive or dead")
    st.caption("The Verdicts table above is the full ledger; pick one strategy at a time "
               "for the same depth of detail a live paper book gets.")
    names = list(gy_last.index)
    pick = st.selectbox("Strategy", names, key="dead_detail_pick", label_visibility="collapsed")
    row = gy_last.loc[pick]

    st.markdown(f"### {pick}")
    blurb = strategy_description(pick)
    st.markdown(f'<div class="tf-blurb">{blurb}</div>', unsafe_allow_html=True)

    r = _dead_strategy_returns(pick, oos, piggy, factory_bt, hourly_bt, kronos_bt, pairs_bt,
                               pipeline_bt)
    if r is not None:
        s = ann_stats(r)
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Sharpe", fmt(s["Sharpe"]))
        c2.metric("Sortino", fmt(s["Sortino"]))
        c3.metric("Calmar", fmt(s["Calmar"]))
        c4.metric("Max Drawdown", fmt(s["MaxDD"], "pct"))
        c5.metric("CAGR", fmt(s["CAGR"], "pct"))
        c6.metric("Vol (ann.)", fmt(s["Vol"], "pct"))
    else:
        st.caption("Backtest return series isn't stored in the standard format for this "
                   "strategy (see `research/insider_backtest.py`'s own artifact) — showing "
                   "the summary stats logged at evaluation time instead.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sharpe", fmt(float(row["oos_sharpe"])))
        c2.metric("Sortino", fmt(float(row["oos_sortino"])))
        c3.metric("Calmar", fmt(float(row["oos_calmar"])))
        c4.metric("Max Drawdown", fmt(float(row["oos_maxdd"]), "pct"))

    verdict_badge = badge(row["verdict"], "alive" if row["verdict"] == "ALIVE" else "dead")
    st.caption(f"Backtest verdict: {verdict_badge} · corr to 60/40: **{fmt(float(row['corr_bench']))}** · "
               f"noise floor bar: **{fmt(float(row['null_p95']))}** · rebalance **{row['freq']}**",
               unsafe_allow_html=True)

    extra = FAMILY_EXTRA_METRICS.get(book_family(pick))
    if extra is not None:
        extra(row)

    if r is not None:
        eq = (1 + r).cumprod()
        st.plotly_chart(backtest_chart(eq, INK2), width="stretch")
    else:
        st.caption("See `artifacts/insider_curves.csv` for this strategy's own backtest study output.")


# ==================================================================== Research Lab view
def render_research_lab(full, meta, nulls, gy):
    OOS = pd.Timestamp(meta["oos_start"])
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    color_of = {s: SLOTS[i % len(SLOTS)] for i, s in enumerate(strats)}
    oos = full[full.index >= OOS]
    gy_last = latest_verdicts(gy)

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
    st.dataframe(
        tbl.style.map(lambda v: f"color: {GOOD}; font-weight: 600" if "ALIVE" in str(v)
                      else (f"color: {CRIT}; font-weight: 600" if "DEAD" in str(v) else ""),
                      subset=["verdict"]),
        width="stretch", hide_index=True)

    piggy = load_piggyback_backtest()
    factory_bt = load_factory_backtest()
    render_strategy_detail(gy_last, oos, piggy, factory_bt, load_hourly_backtest(),
                           load_kronos_backtest(), load_pairs_backtest(),
                           load_pipeline_backtest())

    st.subheader("The luck floor — is anything distinguishable from random?")
    freq_names = {"M": "Monthly-rebalanced", "W": "Weekly-rebalanced", "D": "Daily-rebalanced"}
    # DOCTRINE v1.5 (#112) made the null DUTY-CYCLE matched, so it is per-STRATEGY: each
    # candidate is scored against random rotations of its OWN signal, which preserves its
    # turnover exactly. A per-frequency chart would therefore be showing a distribution
    # that did not decide any of the verdicts marked on it. Older artifacts are keyed by
    # frequency, so detect which style is on disk rather than crashing on one of them.
    per_strategy = not set(nulls).issubset({"M", "W", "D"})
    if per_strategy:
        st.caption("Each strategy is scored against random **rotations of its own signal** "
                   "(DOCTRINE v1.5) — same turnover, no predictive content — so the floor "
                   "below is that strategy's own, not a shared per-frequency one.")
        pick_null = st.selectbox("Strategy", sorted(nulls), key="luckfloor")
        arr = nulls[pick_null]
        freq = meta.get("strategy_freq", {}).get(pick_null, "")
        marks = ([(pick_null, float(gy_last.loc[pick_null, "oos_sharpe"]))]
                 if pick_null in gy_last.index else [])
        label = f"{freq_names.get(freq, freq)} — {pick_null}" if freq else pick_null
        st.plotly_chart(luck_floor_chart(arr, label, marks, color_of), width="stretch")
    else:
        present = [f for f in ("M", "W", "D") if f in nulls]
        tabs = st.tabs([freq_names[f] for f in present])
        for tab, f in zip(tabs, present):
            with tab:
                arr = nulls[f]
                marks = [(s_name, float(gy_last.loc[s_name, "oos_sharpe"]))
                         for s_name, s_freq in meta["strategy_freq"].items()
                         if s_freq == f and s_name in gy_last.index]
                st.plotly_chart(luck_floor_chart(arr, freq_names[f], marks, color_of),
                                width="stretch")

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
    gy_last = latest_verdicts(gy)
    backtest_ok = True
except FileNotFoundError:
    full = meta = nulls = gy = gy_last = None
    backtest_ok = False

with st.sidebar:
    st.markdown('<div class="lab-eyebrow">tradefabe</div>'
                '<h1 style="font-size:1.3rem;margin:0 0 .4rem">evaluation lab</h1>',
                unsafe_allow_html=True)
    st.caption("An honest lab for killing bad trading strategies. **Paper/backtest only.**")
    with st.container(key="refresh_control"):
        if st.button("Refresh data", key="refresh_data_btn", use_container_width=True,
                    icon=":material/refresh:",
                    help="Reloads the latest paper-book state and re-reads backtest artifacts "
                         "(harness.py output) without restarting the app. Cmd+R (Mac) / "
                         "Ctrl+R does the same."):
            st.cache_data.clear()
            st.rerun()
    _bind_refresh_shortcut()
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
                   "run at least once. Book status still shows below.", icon=":material/warning:")
        psum2, phist2 = psum, phist
        if psum2 is not None:
            render_book_status(psum2, phist2)
        else:
            st.info("No paper books yet — run `.venv/bin/tradefabe run` to open the first cycle.",
                icon=":material/info:")
    else:
        render_paper_books(psum, phist, full, meta, gy_last)
else:
    if not backtest_ok:
        st.error("No artifacts found — run `.venv/bin/python harness.py` first.",
                 icon=":material/error:")
        st.stop()
    render_research_lab(full, meta, nulls, gy)

st.divider()
st.caption("tradefabe · doctrine-governed strategy lab · backtests & paper only — nothing here is "
           "investment advice, and no real money is connected.")
