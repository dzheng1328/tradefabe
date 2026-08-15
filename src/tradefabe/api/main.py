import json
import math

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradefabe import dashboard, risk_register

app = FastAPI(title="tradefabe dashboard API")

# Vite's dev server -- the only origin that ever calls this locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _finite_or_none(v):
    """FastAPI/Starlette's default JSONResponse uses json.dumps(allow_nan=True), which
    emits the bare (invalid-JSON) token NaN for a non-finite float -- browser fetch().json()
    throws on that. Every numeric field that can be NaN (ann_stats, book_return_today,
    etc.) must be routed through this before it reaches a response body."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _deep_finite(obj):
    """Recursively applies _finite_or_none-style NaN-safety through a nested structure
    -- carry_risk.json nests two levels (coins -> BTC/ETH -> postures -> tier). Only a
    genuine float/int leaf that is NaN/inf gets nulled; bool/str/None pass through
    unchanged (bool is checked before the int/float branch since bool is an int
    subclass in Python)."""
    if isinstance(obj, dict):
        return {k: _deep_finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_finite(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float)):
        return _finite_or_none(obj)
    return obj


def _load_gy_last():
    """None if artifacts/full_returns.csv or graveyard.csv doesn't exist yet -- same
    FileNotFoundError handling app.py's own entry point already does."""
    try:
        _full, _meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        return None
    return dashboard.latest_verdicts(gy)


def _sparkline(phist, name, n=20):
    h = (phist[phist["book"] == name].drop_duplicates("date", keep="last")
         .sort_values("date")["equity"])
    return [_finite_or_none(v) for v in h.tail(n).tolist()]


def _row_json(r, *, colors, introduced, return_today, monitor_only, phist,
              generated_ledger, pipeline_ledger):
    name = r["book"]
    intro = introduced.get(name, pd.NaT)
    return {
        "book": name,
        "equity": _finite_or_none(r["equity"]),
        "return": _finite_or_none(r["return"]),
        "last_run": r["last_run"],
        "retired_at": r.get("retired_at") if pd.notna(r.get("retired_at")) else None,
        "family": dashboard.book_family(name, generated_ledger=generated_ledger,
                                        pipeline_ledger=pipeline_ledger),
        "color": colors.get(name),
        "introduced": intro.isoformat() if pd.notna(intro) else None,
        "return_today": _finite_or_none(return_today.get(name, float("nan"))),
        "monitor_only": monitor_only.get(name, False),
        "sparkline": _sparkline(phist, name),
    }


@app.get("/api/books/summary")
def books_summary(sort: str = "total_return", show_monitor_only: bool = True):
    if sort not in ("recent", "return_today", "total_return", "sharpe"):
        raise HTTPException(status_code=400, detail=f"unknown sort: {sort}")

    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"books": []}

    gy_last = _load_gy_last()
    names = psum["book"].tolist()
    colors = dashboard.book_colors(names)
    introduced = dashboard.book_introduced_dates(phist)
    return_today = dashboard.book_return_today(phist)
    monitor_only = {n: dashboard._is_monitor_only(n, gy_last) for n in names}
    generated_ledger = dashboard._load_generated_ledger()
    pipeline_ledger = dashboard._load_pipeline_ledger()

    def row_kwargs():
        return dict(colors=colors, introduced=introduced, return_today=return_today,
                   monitor_only=monitor_only, phist=phist,
                   generated_ledger=generated_ledger, pipeline_ledger=pipeline_ledger)

    rows = dashboard.sort_books_flat(psum, phist, gy_last, show_monitor_only, sort)
    return {"books": [_row_json(r, **row_kwargs()) for r in rows]}


@app.get("/api/books/up_for_review")
def books_up_for_review():
    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"books": []}
    gy_last = _load_gy_last()
    rows = dashboard.books_up_for_review(psum, phist)
    out = []
    for r in rows:
        name = r["book"]
        verdict = "—"
        if gy_last is not None and name in gy_last.index:
            verdict = gy_last.loc[name, "verdict"]
        out.append({
            "book": name,
            "days_live": r["days_live"],
            "equity": _finite_or_none(r["equity"]),
            "return": _finite_or_none(r["return"]),
            "introduced": r["introduced"].isoformat(),
            "verdict": verdict,
        })
    return {"books": out}


def _stats_json(stats):
    return {k: _finite_or_none(v) for k, v in stats.items()}


def _carry_meta_json(carry_meta):
    """carry_hl_meta.json mixes numeric fields (net_yield, net_maxdd, ...) with
    non-numeric ones (window: a [start, end] date-string pair; generated_at: an ISO
    string) -- _finite_or_none's float(v) raises on both, and the broad except in that
    helper was silently coercing them to None, dropping the backtest window range and
    generation timestamp from every carry_btc_eth response. Route only genuine
    int/float values through NaN-safety; pass everything else through unchanged."""
    return {k: (_finite_or_none(v) if isinstance(v, (int, float)) else v)
            for k, v in carry_meta.items()}


def _deployment_json(dep):
    if dep is None:
        return None
    return {
        "cash": _finite_or_none(dep["cash"]), "gross": _finite_or_none(dep["gross"]),
        "net": _finite_or_none(dep["net"]), "equity": _finite_or_none(dep["equity"]),
        "cash_pct": _finite_or_none(dep["cash_pct"]),
        "gross_pct": _finite_or_none(dep["gross_pct"]),
        "net_pct": _finite_or_none(dep["net_pct"]),
        "n_unpriced": int(dep["n_unpriced"]), "n_held": int(dep["n_held"]),
        "priced_at": dep.get("priced_at"),
        "is_short_funded": bool(dep["is_short_funded"]),
    }


def _positions_json(positions_df):
    if positions_df is None:
        return None
    has_weight = "weight" in positions_df.columns
    out = []
    for _, row in positions_df.iterrows():
        out.append({
            "ticker": row["ticker"],
            "units": _finite_or_none(row["units"]),
            "last_price": _finite_or_none(row.get("last_price")),
            "value": _finite_or_none(row.get("value")),
            "weight": _finite_or_none(row.get("weight")) if has_weight else None,
        })
    return out


def _trades_json(trades_df):
    out = []
    for _, row in trades_df.iterrows():
        ts = row["ts"]
        out.append({
            "ts": ts.isoformat() if pd.notna(ts) else None,
            "ticker": row["ticker"] if isinstance(row["ticker"], str) else None,
            "side": row["side"] if isinstance(row["side"], str) else None,
            "shares": _finite_or_none(row["shares"]),
            "price": _finite_or_none(row["price"]),
            "notional": _finite_or_none(row["notional"]),
            "position_after": _finite_or_none(row["position_after"]),
        })
    return out


@app.get("/api/books/{name}/detail")
def book_detail(name: str, window: str = "ALL"):
    psum, phist = dashboard.load_paper_state()
    if psum is None or name not in psum["book"].values:
        raise HTTPException(status_code=404, detail=f"unknown book: {name}")

    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    gy_last = dashboard.latest_verdicts(gy)

    price_now, price_date = dashboard.load_price_snapshot()
    piggy = dashboard.load_piggyback_backtest()
    factory_bt = dashboard.load_factory_backtest()
    hourly_bt = dashboard.load_hourly_backtest()
    kronos_bt = dashboard.load_kronos_backtest()
    pipeline_bt = dashboard.load_pipeline_backtest()

    data = dashboard.book_panel_data(
        name, phist, full, meta, gy_last, price_now, price_date, piggy,
        factory_bt, hourly_bt, kronos_bt, pipeline_bt, compute_positions=True,
    )

    live_hist = data["live_hist"]
    color = dashboard.book_colors(psum["book"].tolist())[name]
    windows = dashboard.available_windows(live_hist)
    win_choice = window if window in windows else "ALL"
    live_chart = dashboard.live_equity_chart(live_hist, color, win_choice)
    bt_chart = dashboard.backtest_chart(data["bt_curve"], dashboard.INK2)
    div_state, div_detail = dashboard.divergence_status(data)

    body = {
        "name": name,
        "kind": data["kind"],
        "blurb": dashboard.strategy_description(name),
        "retirement_note": dashboard.retirement_note(data.get("book_json")),
        "stats": _stats_json(data["stats"]),
        "live_start": data["live_start"].isoformat(),
        "bt_start": data["bt_start"].isoformat() if data.get("bt_start") is not None else None,
        "available_windows": windows,
        "live_equity_chart": json.loads(live_chart.to_json()),
        "backtest_chart": json.loads(bt_chart.to_json()),
        "divergence_state": div_state,
        "divergence_detail": div_detail,
    }
    if data["kind"] == "equity":
        body["verdict"] = data["verdict"]
        body["corr_bench"] = _finite_or_none(data["corr_bench"])
        body["null_p95"] = _finite_or_none(data["null_p95"])
        body["freq"] = data["freq"]
        body["accrual_only"] = name in dashboard.ACCRUAL_ONLY_BOOKS
        body["cost_bps"] = _finite_or_none(dashboard.signals_cost_bps())
        body["deployment"] = _deployment_json(data["deployment"])
        body["positions"] = _positions_json(data["positions_df"])
        body["positions_asof"] = (
            data["positions_asof"].date().isoformat()
            if data.get("positions_asof") is not None else None
        )
        body["trades"] = _trades_json(data["trades_df"])
    else:
        body["carry_meta"] = _carry_meta_json(data["carry_meta"])
        book_json = data.get("book_json") or {}
        body["book_state"] = {
            "equity": _finite_or_none(book_json.get("equity")),
            "last_run": book_json.get("last_run"),
        }
        curve, _carry_meta_unused = dashboard.load_carry_backtest()
        risk_json = dashboard.load_carry_risk()
        body["carry_risk"] = _deep_finite(risk_json) if risk_json is not None else None
        body["risk_register"] = risk_register.build(curve, risk_json)
    return body


@app.get("/api/research/overview")
def research_overview():
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    OOS = pd.Timestamp(meta["oos_start"])
    gy_last = dashboard.latest_verdicts(gy)
    # The deduplicated universe (#28/#174/#86/#105/#172 curves unioned, near-duplicate
    # clusters collapsed to one representative each) -- not just full_returns.csv's own
    # 9-strategy hand-picked roster, which is all this endpoint plotted before. See
    # dashboard.unique_strategy_universe()'s own docstring for what "unique" means here
    # and why it isn't literally every strategy ever tested.
    strats, oos = dashboard.unique_strategy_universe(gy_last)

    best = gy_last["oos_sharpe"].astype(float).idxmax()
    n_alive = int((gy_last["verdict"] == "ALIVE").sum())

    show = pd.DataFrame(index=oos.index)
    colors = []
    for i, s in enumerate(strats):
        show[s] = dashboard.growth_series(oos[s])
        colors.append(dashboard.SLOTS[i % len(dashboard.SLOTS)])
    show["60/40"] = dashboard.growth_series(oos["bench_6040"])
    colors.append(dashboard.BENCH_C)
    spy_oos = full[full.index >= OOS]["spy"].reindex(oos.index)
    show["SPY"] = dashboard.growth_series(spy_oos)
    colors.append(dashboard.SPY_C)
    growth = dashboard.growth_chart(show, colors, show_legend=False)

    cm = oos[strats + ["bench_6040"]].rename(columns={"bench_6040": "60/40"}).corr()
    heatmap = dashboard.correlation_heatmap(cm)

    return {
        "meta": {
            "source": meta["source"], "start": meta["start"], "end": meta["end"],
            "oos_start": meta["oos_start"], "n_assets": meta["n_assets"],
        },
        "stats": {
            "n_tested": int(gy_last.shape[0]), "n_alive": n_alive,
            "n_dead": int(gy_last.shape[0]) - n_alive,
            "luck_floor_p95": _finite_or_none(meta["null_bars"].get("M", float("nan"))),
            "best_strategy": best,
            "best_sharpe": _finite_or_none(gy_last.loc[best, "oos_sharpe"]),
            "bench_sharpe": _finite_or_none(gy_last["bench_sharpe"].iloc[0]),
        },
        "strategies": strats,
        # hide_hover_legend: a SIBLING of data/layout, not read by react-plotly.js's
        # <Plot> at all (it only destructures data/layout/config/frames), so Plotly.js
        # can never see or mutate it -- unlike the earlier approach of sniffing
        # layout.hoverlabel.bgcolor for a sentinel color, which broke the moment
        # Plotly's own color-normalization pass rewrote "rgba(0,0,0,0)" to
        # "rgba(0, 0, 0, 0)" (spaces added) in place on the shared layout object,
        # flipping the frontend's strict-equality check to false after the first
        # redraw (confirmed live, 2026-08-14).
        "growth_chart": {**json.loads(growth.to_json()), "hide_hover_legend": True},
        "correlation_heatmap": json.loads(heatmap.to_json()),
    }


@app.get("/api/research/verdicts")
def research_verdicts():
    try:
        _full, _meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    cols = ["freq", "timestamp", "oos_sharpe", "oos_sortino", "oos_calmar", "oos_maxdd",
            "corr_bench", "null_p95", "verdict"]
    generated_ledger = dashboard._load_generated_ledger()
    pipeline_ledger = dashboard._load_pipeline_ledger()
    rows = []
    for strategy, row in gy_last[cols].iterrows():
        rows.append({
            "strategy": strategy,
            "freq": row["freq"],
            "tested": row["timestamp"],
            "kind": dashboard.research_kind(strategy, generated_ledger=generated_ledger,
                                            pipeline_ledger=pipeline_ledger),
            "oos_sharpe": _finite_or_none(row["oos_sharpe"]),
            "oos_sortino": _finite_or_none(row["oos_sortino"]),
            "oos_calmar": _finite_or_none(row["oos_calmar"]),
            "oos_maxdd": _finite_or_none(row["oos_maxdd"]),
            "corr_bench": _finite_or_none(row["corr_bench"]),
            "null_p95": _finite_or_none(row["null_p95"]),
            "verdict": row["verdict"],
        })
    return {"rows": rows}


@app.get("/api/research/strategy/{name}")
def research_strategy_detail(name: str):
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    if name not in gy_last.index:
        raise HTTPException(status_code=404, detail=f"unknown strategy: {name}")
    row = gy_last.loc[name]

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    piggy = dashboard.load_piggyback_backtest()
    factory_bt = dashboard.load_factory_backtest()
    hourly_bt = dashboard.load_hourly_backtest()
    kronos_bt = dashboard.load_kronos_backtest()
    pairs_bt = dashboard.load_pairs_backtest()
    pipeline_bt = dashboard.load_pipeline_backtest()

    r = dashboard._dead_strategy_returns(name, oos, piggy, factory_bt, hourly_bt,
                                          kronos_bt, pairs_bt, pipeline_bt)

    body = {
        "name": name,
        "blurb": dashboard.strategy_description(name),
        "verdict": row["verdict"],
        "freq": row["freq"],
        "corr_bench": _finite_or_none(row["corr_bench"]),
        "null_p95": _finite_or_none(row["null_p95"]),
        "has_returns": r is not None,
    }
    if r is not None:
        s = dashboard.ann_stats(r)
        body["stats"] = _stats_json(s)
        eq = (1 + r).cumprod()
        chart = dashboard.backtest_chart(eq, dashboard.INK2)
        body["chart"] = json.loads(chart.to_json())
    else:
        body["stats"] = {
            "Sharpe": _finite_or_none(row["oos_sharpe"]),
            "Sortino": _finite_or_none(row["oos_sortino"]),
            "Calmar": _finite_or_none(row["oos_calmar"]),
            "MaxDD": _finite_or_none(row["oos_maxdd"]),
        }
        body["chart"] = None
    return body


@app.get("/api/research/luck_floor")
def research_luck_floor(strategy: str):
    try:
        full, meta, nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    if strategy not in gy_last.index:
        raise HTTPException(status_code=400, detail=f"unknown strategy: {strategy}")

    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    color_of = {s: dashboard.SLOTS[i % len(dashboard.SLOTS)] for i, s in enumerate(strats)}
    freq_names = {"M": "Monthly-rebalanced", "W": "Weekly-rebalanced", "D": "Daily-rebalanced"}
    freq = gy_last.loc[strategy, "freq"]
    marks = [(strategy, float(gy_last.loc[strategy, "oos_sharpe"]))]

    # nulls.npz is either keyed per-strategy (current shape, DOCTRINE v1.5) or per-frequency
    # (legacy shape, {D,M,W} -- the real artifact on disk as of 2026-08). Mirror app.py's
    # render_research_lab detection so both shapes work behind the same URL contract. The two
    # shapes carry a real semantic difference (this strategy's own null distribution vs. a
    # distribution SHARED across every same-frequency strategy) -- callers need to know which
    # one they got, hence `shape` in the response.
    if strategy in nulls:
        arr = nulls[strategy]
        shape = "per_strategy"
        label = f"{freq_names.get(freq, freq)} — {strategy}" if freq else strategy
    elif freq in nulls:
        arr = nulls[freq]
        shape = "per_frequency"
        label = freq_names.get(freq, freq)
    else:
        raise HTTPException(status_code=400, detail=f"no null distribution for: {strategy}")

    chart = dashboard.luck_floor_chart(arr, label, marks, color_of)
    return {"chart": json.loads(chart.to_json()), "label": label, "shape": shape}


@app.get("/api/research/drawdown")
def research_drawdown(pick: str):
    try:
        full, meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    OOS = pd.Timestamp(meta["oos_start"])
    oos = full[full.index >= OOS]
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]
    color_of = {s: dashboard.SLOTS[i % len(dashboard.SLOTS)] for i, s in enumerate(strats)}

    if pick in ("60/40", "SPY"):
        col = {"60/40": "bench_6040", "SPY": "spy"}[pick]
        if col not in oos.columns:
            raise HTTPException(status_code=400, detail=f"unknown pick: {pick}")
        r = oos[col].fillna(0)
        c = dashboard.BENCH_C if pick == "60/40" else dashboard.SPY_C
    else:
        piggy = dashboard.load_piggyback_backtest()
        factory_bt = dashboard.load_factory_backtest()
        hourly_bt = dashboard.load_hourly_backtest()
        kronos_bt = dashboard.load_kronos_backtest()
        pairs_bt = dashboard.load_pairs_backtest()
        pipeline_bt = dashboard.load_pipeline_backtest()
        r = dashboard._dead_strategy_returns(pick, oos, piggy, factory_bt, hourly_bt,
                                              kronos_bt, pairs_bt, pipeline_bt)
        if r is None:
            raise HTTPException(status_code=400, detail=f"unknown pick: {pick}")
        r = r.fillna(0)
        c = color_of.get(pick, dashboard.INK2)

    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    chart = dashboard.drawdown_chart(dd, c)
    return {"chart": json.loads(chart.to_json()), "max_drawdown": _finite_or_none(dd.min())}


def _piggyback_universe():
    """gy_last + the deduplicated (kept_names, oos) pair, shared by /piggyback and
    /piggyback/recommend so both endpoints rank/blend against the exact same universe
    the search bar and recommended list are drawn from."""
    _full, _meta, _nulls, gy = dashboard.load_backtest()
    gy_last = dashboard.latest_verdicts(gy)
    kept, oos = dashboard.unique_strategy_universe(gy_last)
    return gy_last, kept, oos


@app.get("/api/research/piggyback")
def research_piggyback(sleeve: str, weight: int):
    try:
        _gy_last, _kept, oos = _piggyback_universe()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    if not (0 <= weight <= 100):
        raise HTTPException(status_code=400, detail="weight must be 0-100")

    sleeve_names = [s for s in sleeve.split(",") if s]
    if not sleeve_names:
        raise HTTPException(status_code=400, detail="sleeve must name at least one strategy")

    unknown = [s for s in sleeve_names if s not in oos.columns]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies in sleeve: {unknown}")

    result = dashboard.piggyback_blend(oos, sleeve_names, weight)
    bench = result["bench_stats"]
    combo = result["combo_stats"]
    bench_growth = (1 + oos["bench_6040"].fillna(0)).cumprod()
    show = pd.DataFrame({"60/40 + sleeve": result["combo"], "60/40 alone": bench_growth})
    chart = dashboard.growth_chart(show, ["#2a78d6", dashboard.BENCH_C])

    return {
        "stats": {
            "sharpe": _finite_or_none(combo["Sharpe"]),
            "sharpe_delta": _finite_or_none(combo["Sharpe"] - bench["Sharpe"]),
            "calmar": _finite_or_none(combo["Calmar"]),
            "calmar_delta": _finite_or_none(combo["Calmar"] - bench["Calmar"]),
            "maxdd": _finite_or_none(combo["MaxDD"]),
            "maxdd_delta": _finite_or_none(combo["MaxDD"] - bench["MaxDD"]),
        },
        "chart": json.loads(chart.to_json()),
    }


@app.get("/api/research/piggyback/recommend")
def research_piggyback_recommend(sleeve: str = "", weight: int = 30, limit: int = 8):
    """Ranks candidates to ADD to the current sleeve, not standalone strategies -- each
    candidate's rank comes from re-blending the FULL sleeve (existing picks + this one
    candidate) against the 60/40 core, so the list reflects the piggybacked TOTAL, not
    the candidate in isolation. With an empty sleeve this degenerates to ranking each
    candidate alone against the core, which is exactly the right first list to show
    before anything's been picked yet.

    Recommends from the same deduplicated universe unique_strategy_universe() builds
    for the overview chart (near-duplicate clusters already collapsed to one
    representative), so this list doesn't surface two near-identical strategies as if
    they were two different opportunities."""
    try:
        _gy_last, kept, oos = _piggyback_universe()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")
    if not (0 <= weight <= 100):
        raise HTTPException(status_code=400, detail="weight must be 0-100")

    sleeve_names = [s for s in sleeve.split(",") if s]
    unknown = [s for s in sleeve_names if s not in oos.columns]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies in sleeve: {unknown}")

    baseline_sharpe = (
        dashboard.piggyback_blend(oos, sleeve_names, weight)["combo_stats"]["Sharpe"]
        if sleeve_names else
        dashboard.ann_stats(oos["bench_6040"].fillna(0))["Sharpe"]
    )

    candidates = [s for s in kept if s not in sleeve_names]
    scored = []
    for name in candidates:
        combo = dashboard.piggyback_blend(oos, sleeve_names + [name], weight)["combo_stats"]
        sharpe = combo["Sharpe"]
        if pd.isna(sharpe):
            continue
        scored.append({
            "strategy": name,
            "resulting_sharpe": _finite_or_none(sharpe),
            "resulting_calmar": _finite_or_none(combo["Calmar"]),
            "delta_sharpe": _finite_or_none(sharpe - baseline_sharpe)
                            if pd.notna(baseline_sharpe) else None,
        })
    scored.sort(key=lambda r: r["resulting_sharpe"] if r["resulting_sharpe"] is not None else -1e9,
               reverse=True)

    return {"recommendations": scored[:limit]}


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
