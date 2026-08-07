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

    if sort not in ("recent", "return_today", "total_return"):
        raise HTTPException(status_code=400, detail=f"unknown sort: {sort}")

    rows = dashboard.sort_books_flat(psum, phist, gy_last, show_monitor_only, sort)
    return {"books": [_row_json(r, **row_kwargs()) for r in rows]}


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
