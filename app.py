"""app.py — tradefabe lab dashboard.   Run:  .venv/bin/streamlit run app.py
Renders artifacts produced by harness.py (run that first). Paper/backtest only — no live trading.
"""
import json
import os
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

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


@st.cache_data
def load():
    full = pd.read_csv(os.path.join(ART, "full_returns.csv"), index_col=0, parse_dates=True)
    with open(os.path.join(ART, "meta.json")) as fh:
        meta = json.load(fh)
    nulls = {k: v for k, v in np.load(os.path.join(ART, "nulls.npz")).items()}
    gy = pd.read_csv(os.path.join(BASE, "graveyard.csv"))
    return full, meta, nulls, gy


def ann_stats(r):
    r = r.dropna()
    if len(r) < 30:
        return dict(Sharpe=np.nan, CAGR=np.nan, MaxDD=np.nan, Calmar=np.nan)
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (ANN / len(r)) - 1
    sd = r.std()
    sharpe = r.mean() / sd * np.sqrt(ANN) if sd > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return dict(Sharpe=sharpe, CAGR=cagr, MaxDD=dd, Calmar=(cagr / abs(dd) if dd else np.nan))


def styled_fig(w=9.5, h=3.4):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(alpha=.6, color=GRID, linewidth=.6)
    return fig, ax


try:
    full, meta, nulls, gy = load()
except FileNotFoundError:
    st.error("No artifacts found — run `.venv/bin/python harness.py` first.")
    st.stop()

OOS    = pd.Timestamp(meta["oos_start"])
strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
color_of = {s: SLOTS[i % len(SLOTS)] for i, s in enumerate(strats)}
oos    = full[full.index >= OOS]
gy_last = gy.drop_duplicates("strategy", keep="last").set_index("strategy")

# ---------------- sidebar ----------------
with st.sidebar:
    st.title("📉 tradefabe lab")
    st.caption("An honest lab for killing bad trading strategies. **Paper/backtest only.**")
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

# ---------------- header tiles ----------------
n_tested = gy_last.shape[0]
n_alive  = int((gy_last["verdict"] == "ALIVE").sum())
best     = gy_last["oos_sharpe"].astype(float).idxmax()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Strategies tested", n_tested)
c2.metric("Alive", n_alive)
c3.metric("Dead", n_tested - n_alive)
c4.metric("Luck floor (M) p95 Sharpe", f"{meta['null_bars'].get('M', float('nan')):.2f}")
c5.metric(f"Best OOS Sharpe — {best}", f"{float(gy_last.loc[best, 'oos_sharpe']):.2f}")
st.caption(f"60/40 benchmark OOS Sharpe: **{float(gy_last['bench_sharpe'].iloc[0]):.2f}** — the honest bar for gate 2.")

# ---------------- equity curves ----------------
st.subheader("Growth of $1 — out-of-sample")
sel = st.multiselect("Strategies", strats, default=strats, label_visibility="collapsed")
cols, colors = [], []
show = pd.DataFrame(index=oos.index)
for s in sel:
    show[s] = (1 + oos[s].fillna(0)).cumprod()
    colors.append(color_of[s])
show["60/40"] = (1 + oos["bench_6040"].fillna(0)).cumprod()
colors.append(BENCH_C)
show["SPY"] = (1 + oos["spy"].fillna(0)).cumprod()
colors.append(SPY_C)
st.line_chart(show, color=colors, height=340)
st.caption("Strategies run at a ~10% vol target; 60/40 and SPY are the passive context lines. "
           "Sharpe/Calmar (below) are the fair comparison — raw growth favors whoever took more risk.")

# ---------------- verdict table ----------------
st.subheader("Verdicts — the graveyard ledger")
tbl = gy_last.reset_index()[["strategy", "freq", "oos_sharpe", "oos_sortino", "oos_calmar",
                             "oos_maxdd", "corr_bench", "null_p95", "verdict"]].copy()
tbl["verdict"] = tbl["verdict"].map(lambda v: ("✅ " if v == "ALIVE" else "💀 ") + v)
st.dataframe(
    tbl.style.map(lambda v: f"color: {GOOD}; font-weight: 600" if "ALIVE" in str(v)
                  else (f"color: {CRIT}; font-weight: 600" if "DEAD" in str(v) else ""),
                  subset=["verdict"]),
    use_container_width=True, hide_index=True)

# ---------------- luck floor ----------------
st.subheader("The luck floor — is anything distinguishable from random?")
freq_names = {"M": "Monthly-rebalanced", "W": "Weekly-rebalanced", "D": "Daily-rebalanced"}
present = [f for f in ("M", "W", "D") if f in nulls]
tabs = st.tabs([freq_names[f] for f in present])
for tab, f in zip(tabs, present):
    with tab:
        arr = nulls[f]
        bar = float(np.percentile(arr, 95))
        fig, ax = styled_fig()
        ax.hist(arr, bins=40, color="#86b6ef", edgecolor=SURF, linewidth=.5)
        ax.axvline(bar, color=INK, ls="--", lw=1.2)
        ax.text(bar, ax.get_ylim()[1] * .95, f"  p95 luck = {bar:.2f}", color=INK, fontsize=9, va="top")
        for s_name, s_freq in meta["strategy_freq"].items():
            if s_freq == f and s_name in gy_last.index:
                v = float(gy_last.loc[s_name, "oos_sharpe"])
                ax.axvline(v, color=color_of.get(s_name, INK2), lw=2)
                ax.text(v, ax.get_ylim()[1] * .82, f" {s_name} {v:.2f}",
                        color=color_of.get(s_name, INK2), fontsize=8, rotation=90, va="top")
        ax.set_xlabel(f"OOS Sharpe of {len(arr)} random strategies ({freq_names[f].lower()})",
                      color=INK2, fontsize=9)
        st.pyplot(fig, use_container_width=True)

# ---------------- drawdown ----------------
st.subheader("Underwater — drawdown from peak")
pick = st.selectbox("Strategy", strats + ["60/40", "SPY"])
col = {"60/40": "bench_6040", "SPY": "spy"}.get(pick, pick)
r = oos[col].fillna(0)
eq = (1 + r).cumprod()
dd = eq / eq.cummax() - 1
c = color_of.get(pick, BENCH_C if pick == "60/40" else SPY_C)
fig, ax = styled_fig()
ax.fill_between(dd.index, dd, 0, color=c, alpha=.30)
ax.plot(dd.index, dd, color=c, lw=1.2)
ax.set_ylabel("drawdown", color=INK2, fontsize=9)
st.pyplot(fig, use_container_width=True)
st.caption(f"Max drawdown: **{dd.min():.1%}**")

# ---------------- correlation ----------------
st.subheader("Correlation — different bets, or the same bet in disguise?")
cm = oos[strats + ["bench_6040"]].rename(columns={"bench_6040": "60/40"}).corr()
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("div", DIV)
fig, ax = styled_fig(8, 5.4)
im = ax.imshow(cm.values, cmap=cmap, vmin=-1, vmax=1)
ax.set_xticks(range(len(cm))); ax.set_yticks(range(len(cm)))
ax.set_xticklabels(cm.columns, rotation=40, ha="right", fontsize=8)
ax.set_yticklabels(cm.columns, fontsize=8)
ax.grid(False)
for i in range(len(cm)):
    for j in range(len(cm)):
        v = cm.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5,
                color="#ffffff" if abs(v) > .6 else INK)
st.pyplot(fig, use_container_width=False)
with st.expander("Table view"):
    st.dataframe(cm.round(2), use_container_width=True)

# ---------------- piggyback lab ----------------
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
        cmp_df = pd.DataFrame({"60/40 + sleeve": (1 + combo).cumprod(),
                               "60/40 alone": (1 + oos["bench_6040"].fillna(0)).cumprod()})
        st.line_chart(cmp_df, color=["#2a78d6", BENCH_C], height=240)
        st.caption("Reminder: a sleeve usually LOWERS raw dollars while smoothing the ride — "
                   "Sharpe up ≠ more profit.")

st.divider()
st.caption("tradefabe · doctrine-governed strategy lab · backtests & paper only — nothing here is "
           "investment advice, and no real money is connected.")
