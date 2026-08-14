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


def _row_json(r, *, colors, introduced, return_today, monitor_only, phist):
    name = r["book"]
    intro = introduced.get(name, pd.NaT)
    return {
        "book": name,
        "equity": _finite_or_none(r["equity"]),
        "return": _finite_or_none(r["return"]),
        "last_run": r["last_run"],
        "retired_at": r.get("retired_at") if pd.notna(r.get("retired_at")) else None,
        "family": dashboard.book_family(name),
        "color": colors.get(name),
        "introduced": intro.isoformat() if pd.notna(intro) else None,
        "return_today": _finite_or_none(return_today.get(name, float("nan"))),
        "monitor_only": monitor_only.get(name, False),
        "sparkline": _sparkline(phist, name),
    }


@app.get("/api/books/summary")
def books_summary(sort: str = "family", show_monitor_only: bool = True):
    if sort not in ("family", "recent", "return_today", "total_return"):
        raise HTTPException(status_code=400, detail=f"unknown sort: {sort}")

    psum, phist = dashboard.load_paper_state()
    if psum is None:
        return {"families": []} if sort == "family" else {"books": []}

    gy_last = _load_gy_last()
    names = psum["book"].tolist()
    colors = dashboard.book_colors(names)
    introduced = dashboard.book_introduced_dates(phist)
    return_today = dashboard.book_return_today(phist)
    monitor_only = {n: dashboard._is_monitor_only(n, gy_last) for n in names}

    def row_kwargs():
        return dict(colors=colors, introduced=introduced, return_today=return_today,
                   monitor_only=monitor_only, phist=phist)

    if sort == "family":
        groups = dashboard.group_books_by_family(psum, gy_last, show_monitor_only)
        return {"families": [
            {"family": family, "label": label,
             "books": [_row_json(r, **row_kwargs()) for r in rows]}
            for family, label, rows in groups
        ]}

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
    oos = full[full.index >= OOS]
    gy_last = dashboard.latest_verdicts(gy)
    strats = [c for c in full.columns if c not in ("bench_6040", "spy")]

    best = gy_last["oos_sharpe"].astype(float).idxmax()
    n_alive = int((gy_last["verdict"] == "ALIVE").sum())

    show = pd.DataFrame(index=oos.index)
    colors = []
    for s in strats:
        show[s] = (1 + oos[s].fillna(0)).cumprod()
        colors.append(dashboard.SLOTS[strats.index(s) % len(dashboard.SLOTS)])
    show["60/40"] = (1 + oos["bench_6040"].fillna(0)).cumprod()
    colors.append(dashboard.BENCH_C)
    show["SPY"] = (1 + oos["spy"].fillna(0)).cumprod()
    colors.append(dashboard.SPY_C)
    growth = dashboard.growth_chart(show, colors)

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
        "growth_chart": json.loads(growth.to_json()),
        "correlation_heatmap": json.loads(heatmap.to_json()),
    }


@app.get("/api/research/verdicts")
def research_verdicts():
    try:
        _full, _meta, _nulls, gy = dashboard.load_backtest()
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="backtest artifacts not found")

    gy_last = dashboard.latest_verdicts(gy)
    cols = ["freq", "oos_sharpe", "oos_sortino", "oos_calmar", "oos_maxdd",
            "corr_bench", "null_p95", "verdict"]
    rows = []
    for strategy, row in gy_last[cols].iterrows():
        rows.append({
            "strategy": strategy,
            "freq": row["freq"],
            "oos_sharpe": _finite_or_none(row["oos_sharpe"]),
            "oos_sortino": _finite_or_none(row["oos_sortino"]),
            "oos_calmar": _finite_or_none(row["oos_calmar"]),
            "oos_maxdd": _finite_or_none(row["oos_maxdd"]),
            "corr_bench": _finite_or_none(row["corr_bench"]),
            "null_p95": _finite_or_none(row["null_p95"]),
            "verdict": row["verdict"],
        })
    return {"rows": rows}


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
