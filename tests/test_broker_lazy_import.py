"""The [alpaca] extra must be OPTIONAL, and is_available() must tell the truth about it.

Same trap CLAUDE.md records for desktop.py and tradefabe.kronos guards against (see
tests/test_kronos_lazy_import.py): a lazy import means `import tradefabe.broker` can
succeed with alpaca-py missing while the module is actually unusable. CI installs only
`[dev]` (.github/workflows/tests.yml), so alpaca-py is never present there -- these tests
must pass with or without it.
"""
import importlib
import sys

import pytest

from tradefabe import broker


def test_the_module_imports_with_no_alpaca_installed():
    """runner.py/books.py/cli.py must keep importing on a cloud run with no [alpaca]
    extra. Nothing in tradefabe.broker itself may import alpaca-py at module scope."""
    sys.modules.pop("tradefabe.broker", None)
    with_alpaca_hidden = {k: v for k, v in sys.modules.items() if not k.startswith("alpaca")}
    saved, sys.modules = sys.modules, with_alpaca_hidden
    try:
        mod = importlib.import_module("tradefabe.broker")
        assert callable(mod.is_available)
    finally:
        sys.modules = saved


def test_no_module_scope_alpaca_import_in_the_source():
    """Belt and braces: read the source and assert every alpaca import is indented (inside
    a function), never at column 0."""
    with open(broker.__file__, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    offenders = [
        (i + 1, ln) for i, ln in enumerate(lines)
        if ln.startswith("import alpaca") or ln.startswith("from alpaca")
    ]
    assert not offenders, f"alpaca imported at module scope in broker.py: {offenders}"


def test_is_available_is_the_real_check_not_the_import():
    assert isinstance(broker.is_available(), bool)


def test_the_engine_entry_points_do_not_pull_in_broker():
    """This PR is connectivity-only (#5) -- runner/books/cli must not reach broker.py yet.
    Wiring real orders into the engine is a follow-up, not this change."""
    src_root = broker.__file__.rsplit("/", 1)[0]
    for mod in ("runner", "books", "cli"):
        with open(f"{src_root}/{mod}.py", encoding="utf-8") as fh:
            body = fh.read()
        assert "import broker" not in body and "from .broker" not in body, (
            f"{mod}.py imports broker.py -- that's out of scope for #5's connectivity-only pass")


def test_a_missing_extra_raises_an_actionable_error_not_an_importerror(monkeypatch):
    """A bare ModuleNotFoundError deep inside client() would send the reader chasing
    alpaca-py's own docs instead of to the one-line fix."""
    monkeypatch.setattr(broker, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match=r"\[alpaca\]"):
        broker._require()


# ---------------------------------------------------------------- credentials() / gates
def test_credentials_refuses_unless_paper_trade_flag_is_exactly_true(monkeypatch):
    monkeypatch.setattr(broker, "_load_env", lambda: None)
    monkeypatch.delenv("ALPACA_PAPER_TRADE", raising=False)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    with pytest.raises(broker.PaperOnlyError):
        broker.credentials()

    for bad in ("false", "", "TRUE_ISH", "1"):
        monkeypatch.setenv("ALPACA_PAPER_TRADE", bad)
        with pytest.raises(broker.PaperOnlyError):
            broker.credentials()


def test_credentials_accepts_true_case_insensitively(monkeypatch):
    monkeypatch.setattr(broker, "_load_env", lambda: None)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    for good in ("true", "True", "TRUE", " true "):
        monkeypatch.setenv("ALPACA_PAPER_TRADE", good)
        assert broker.credentials() == ("test-key", "test-secret")


def test_credentials_raises_when_keys_missing_even_with_flag_true(monkeypatch):
    monkeypatch.setattr(broker, "_load_env", lambda: None)
    monkeypatch.setenv("ALPACA_PAPER_TRADE", "true")
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ALPACA_API_KEY_ID"):
        broker.credentials()


def test_client_hardcodes_paper_true_regardless_of_the_env_flag(monkeypatch):
    """The flag only gates whether credentials() will hand back a key/secret at all
    (tested above) -- it must never be read as the paper/live switch itself."""
    pytest.importorskip("alpaca")
    monkeypatch.setattr(broker, "_load_env", lambda: None)
    monkeypatch.setenv("ALPACA_PAPER_TRADE", "true")
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

    captured = {}

    class _FakeTradingClient:
        def __init__(self, key_id, secret_key, paper):
            captured["key_id"] = key_id
            captured["secret_key"] = secret_key
            captured["paper"] = paper

    monkeypatch.setattr("alpaca.trading.client.TradingClient", _FakeTradingClient)
    client = broker.client()
    assert captured["paper"] is True
    assert captured["key_id"] == "test-key"
    assert isinstance(client, _FakeTradingClient)


# ---------------------------------------------------------------- order placement (#134)
def _fake_client(monkeypatch, **methods):
    """Patch broker.client() to return an object with the given method -> return_value (or
    callable) pairs, so order-placement tests never construct a real TradingClient/hit the
    network."""
    class _Fake:
        pass
    fake = _Fake()
    for name, behavior in methods.items():
        setattr(fake, name, behavior)
    monkeypatch.setattr(broker, "client", lambda: fake)
    return fake


def test_submit_market_order_uses_notional_and_the_right_side(monkeypatch):
    pytest.importorskip("alpaca")
    monkeypatch.setattr(broker, "is_available", lambda: True)
    captured = {}

    def _capture(req):
        captured["req"] = req
        return req

    _fake_client(monkeypatch, submit_order=_capture)

    broker.submit_market_order("SPY", 50.0, "buy")
    from alpaca.trading.enums import OrderSide, TimeInForce
    req = captured["req"]
    assert req.symbol == "SPY"
    assert req.notional == pytest.approx(50.0)
    assert req.side == OrderSide.BUY
    assert req.time_in_force == TimeInForce.DAY

    broker.submit_market_order("SPY", 50.0, "sell")
    assert captured["req"].side == OrderSide.SELL


def test_await_fill_polls_until_filled_and_returns_the_fill_price(monkeypatch):
    pytest.importorskip("alpaca")
    monkeypatch.setattr(broker, "is_available", lambda: True)
    from alpaca.trading.enums import OrderStatus

    class _Order:
        def __init__(self, status, filled_avg_price=None):
            self.status = status
            self.filled_avg_price = filled_avg_price

    calls = iter([_Order(OrderStatus.NEW), _Order(OrderStatus.FILLED, 123.45)])
    _fake_client(monkeypatch, get_order_by_id=lambda oid: next(calls))

    price = broker.await_fill("fake-order-id", timeout=5, poll_interval=0)
    assert price == pytest.approx(123.45)


def test_await_fill_raises_when_the_order_is_rejected(monkeypatch):
    pytest.importorskip("alpaca")
    monkeypatch.setattr(broker, "is_available", lambda: True)
    from alpaca.trading.enums import OrderStatus

    class _Order:
        status = OrderStatus.REJECTED
        filled_avg_price = None

    _fake_client(monkeypatch, get_order_by_id=lambda oid: _Order())
    with pytest.raises(RuntimeError, match="REJECTED"):
        broker.await_fill("fake-order-id", timeout=5, poll_interval=0)


def test_await_fill_times_out_if_never_filled(monkeypatch):
    pytest.importorskip("alpaca")
    monkeypatch.setattr(broker, "is_available", lambda: True)
    from alpaca.trading.enums import OrderStatus

    class _Order:
        status = OrderStatus.NEW
        filled_avg_price = None

    _fake_client(monkeypatch, get_order_by_id=lambda oid: _Order())
    with pytest.raises(TimeoutError):
        broker.await_fill("fake-order-id", timeout=0.05, poll_interval=0.01)


def test_market_is_open_reads_the_alpaca_clock(monkeypatch):
    class _Clock:
        def __init__(self, is_open):
            self.is_open = is_open

    _fake_client(monkeypatch, get_clock=lambda: _Clock(True))
    assert broker.market_is_open() is True

    _fake_client(monkeypatch, get_clock=lambda: _Clock(False))
    assert broker.market_is_open() is False
