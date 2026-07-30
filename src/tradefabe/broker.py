"""Alpaca paper-trading broker wrapper (#5, order placement added #134).

Scope of this module, deliberately narrow: a thin wrapper for CONNECTIVITY and one-off
DIAGNOSTIC order placement (#134's empirical cost check). runner.py/books.py still do
every book's simulated-fill accounting -- nothing here routes a BOOK's rebalance through
Alpaca yet. Proving the credentials authenticate, and that a real paper order round-trips
to a real fill, are both steps before wiring this into the live engine; that wiring is a
follow-up, not this file.

**Paper only, always, no exceptions.** `client()` hardcodes `paper=True` -- it is not read
from `ALPACA_PAPER_TRADE`, so that env var being anything other than unset can't flip it.
`credentials()` separately REFUSES to return anything unless `ALPACA_PAPER_TRADE` is
exactly `"true"`, so getting the key/secret out of the environment at all requires the
flag be set correctly. Two independent checks, not one; see CLAUDE.md's hard rule (never
connect real money/credentials).

alpaca-py is imported lazily -- same reasoning as `kronos.py`'s torch and `desktop.py`'s
webview (CLAUDE.md's live gotchas): `import tradefabe.broker` must keep succeeding with no
`[alpaca]` extra installed, so `is_available()` is the real check, not the bare import.

Credentials: `ALPACA_API_KEY_ID`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER_TRADE` in a repo-root
`.env` (gitignored -- see `.gitignore` -- and MUST NEVER be committed), loaded via
python-dotenv if present. If dotenv isn't installed or `.env` doesn't exist, the vars must
already be in the process environment (e.g. exported by the caller or CI)."""
from __future__ import annotations

import os

from .paths import REPO_ROOT

_ENV_LOADED = False


def _load_env() -> None:
    """Load repo-root .env once, if python-dotenv is installed and the file exists. Never
    raises: a missing .env or missing dotenv just means the vars must already be set."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


def is_available() -> bool:
    """True when the [alpaca] extra is actually usable.

    Import of THIS module succeeds without alpaca-py by design, so `import
    tradefabe.broker` proves nothing -- exactly the failure mode CLAUDE.md records for
    desktop.py, where omitting [desktop] left the import fine and the app dead. Call this
    instead, same as tradefabe.kronos.is_available()."""
    try:
        import alpaca.trading.client  # noqa: F401
    except ImportError:
        return False
    return True


def _require() -> None:
    if not is_available():
        raise RuntimeError(
            "Alpaca needs the optional extra: pip install -e '.[alpaca]'. "
            "tradefabe.broker imports fine without it (alpaca-py is lazy), so an import "
            "check will not catch this -- use tradefabe.broker.is_available()."
        )


class PaperOnlyError(RuntimeError):
    """Raised whenever ALPACA_PAPER_TRADE isn't affirmatively "true". Refusing to guess is
    the point -- there is no default here that could silently mean live."""


def credentials() -> tuple[str, str]:
    """(key_id, secret_key) from the environment, loading .env first if present.

    Raises PaperOnlyError unless ALPACA_PAPER_TRADE is exactly "true", and RuntimeError if
    the key/secret are missing. Both checks happen before either value is returned -- a
    caller can't accidentally get real credentials out of this without both gates passing.
    """
    _load_env()
    if os.environ.get("ALPACA_PAPER_TRADE", "").strip().lower() != "true":
        raise PaperOnlyError(
            'ALPACA_PAPER_TRADE must be set to "true" in .env. This wrapper refuses to '
            "run against anything else -- see CLAUDE.md's hard rule (paper only, no "
            "exceptions without Dave explicitly saying so in chat)."
        )
    key_id = os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not key_id or not secret_key:
        raise RuntimeError(
            "ALPACA_API_KEY_ID / ALPACA_SECRET_KEY missing. Create a paper account at "
            "alpaca.markets, generate PAPER keys, and put them in a repo-root .env "
            "(gitignored, never committed) -- see issue #5."
        )
    return key_id, secret_key


def client():
    """A TradingClient wired to Alpaca's PAPER endpoint.

    `paper=True` is HARDCODED here, not derived from ALPACA_PAPER_TRADE -- that env var is
    a refuse-to-run gate in credentials() above, not a switch that could flip this to live
    by being set to some other value."""
    _require()
    from alpaca.trading.client import TradingClient
    key_id, secret_key = credentials()
    return TradingClient(key_id, secret_key, paper=True)


def check_connection() -> dict:
    """Verifies the credentials actually authenticate against Alpaca's paper endpoint by
    fetching account info. Returns only non-secret fields for a human to eyeball -- never
    the keys. This is a connectivity check, not a trading operation: no order is placed."""
    acct = client().get_account()
    return {
        "account_number": acct.account_number,
        "status": str(acct.status),
        "currency": acct.currency,
        "cash": str(acct.cash),
        "portfolio_value": str(acct.portfolio_value),
        "pattern_day_trader": acct.pattern_day_trader,
    }


def market_is_open() -> bool:
    """True if Alpaca's clock says the market is open right now. A market order submitted
    while closed queues rather than filling immediately -- callers that need a same-call
    fill (e.g. cost_check.py, #134) must check this first and refuse to run otherwise."""
    return bool(client().get_clock().is_open)


def submit_market_order(symbol: str, notional: float, side: str):
    """Submit a real Alpaca PAPER market order for `notional` dollars of `symbol`.

    `side` is "buy" or "sell". Uses `notional` (a dollar amount), not `qty` (a share
    count), so a caller doesn't need to know the current price to size a small order.
    `client()` already hardcodes paper=True -- this places a real order against that paper
    account, not a simulation on top of it. Returns the alpaca-py Order object (has `.id`,
    `.status`, not yet a fill -- pass `.id` to await_fill())."""
    _require()
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    req = MarketOrderRequest(
        symbol=symbol, notional=notional,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    )
    return client().submit_order(req)


def await_fill(order_id, timeout: float = 30.0, poll_interval: float = 1.0) -> float:
    """Poll `order_id` until it fills, then return the realized fill price.

    Raises RuntimeError if the order is rejected/canceled/expired, or TimeoutError if it's
    still not in a terminal state after `timeout` seconds -- a market order during market
    hours should fill in well under that, so a timeout here is itself a signal something's
    wrong, not routine."""
    _require()
    from alpaca.trading.enums import OrderStatus
    import time
    c = client()
    deadline = time.monotonic() + timeout
    while True:
        order = c.get_order_by_id(order_id)
        if order.status == OrderStatus.FILLED:
            return float(order.filled_avg_price)
        if order.status in (OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.EXPIRED):
            raise RuntimeError(f"order {order_id} ended as {order.status}, not filled")
        if time.monotonic() >= deadline:
            raise TimeoutError(f"order {order_id} still {order.status} after {timeout}s")
        time.sleep(poll_interval)
