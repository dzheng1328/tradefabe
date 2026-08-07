import json
import math

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tradefabe import dashboard

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
        factory_bt, hourly_bt, kronos_bt, pipeline_bt, compute_positions=False,
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
    else:
        body["carry_meta"] = {k: _finite_or_none(v) for k, v in data["carry_meta"].items()}
    return body


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
