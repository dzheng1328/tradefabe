"""Paper ledgers: JSON state per book under state/paper/. Fills are simulated at the
latest close with a per-side cost — a local paper broker. (Alpaca swap-in is on the roadmap.)"""
from __future__ import annotations
import json
import datetime as dt
import pandas as pd
from .paths import STATE_DIR

START_CASH = 100_000.0


def _path(name):
    return STATE_DIR / f"{name}.json"


def load(name: str) -> dict:
    p = _path(name)
    if p.exists():
        return json.loads(p.read_text())
    return {"name": name, "cash": START_CASH, "positions": {}, "history": [],
            "last_run": None, "last_rebalance": None}


def save(book: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(book["name"]).write_text(json.dumps(book, indent=1))


def equity(book: dict, px: pd.Series) -> float:
    pos_val = sum(sh * float(px.get(t, 0) or 0) for t, sh in book["positions"].items())
    return book["cash"] + pos_val


def mark(book: dict, date: str, px: pd.Series) -> None:
    if not book["history"] or book["history"][-1][0] != date:
        book["history"].append([date, round(equity(book, px), 2)])
    book["last_run"] = dt.datetime.now().isoformat(timespec="seconds")


def rebalance_to(book: dict, weights: pd.Series, date: str, px: pd.Series, cost_bps: float) -> None:
    """Trade to target weights at today's close; charge cost on turnover."""
    eq = equity(book, px)
    turnover = 0.0
    new_pos = {}
    for t, w in weights.items():
        p = float(px.get(t, 0) or 0)
        if p <= 0:
            continue
        tgt_sh = (w * eq) / p
        cur_sh = book["positions"].get(t, 0.0)
        turnover += abs(tgt_sh - cur_sh) * p
        if abs(tgt_sh) > 1e-9:
            new_pos[t] = tgt_sh
    for t, cur_sh in book["positions"].items():          # closed names count in turnover
        if t not in weights.index:
            turnover += abs(cur_sh) * float(px.get(t, 0) or 0)
    cost = turnover * (cost_bps / 1e4)
    pos_val = sum(sh * float(px.get(t, 0) or 0) for t, sh in new_pos.items())
    book["cash"] = eq - pos_val - cost
    book["positions"] = new_pos
    book["last_rebalance"] = date
    mark(book, date, px)
