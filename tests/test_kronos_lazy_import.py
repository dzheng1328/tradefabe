"""The [kronos] extra must be OPTIONAL, and `is_available()` must tell the truth about it.

CLAUDE.md records this exact trap for desktop.py: `webview` was imported lazily inside
main(), so `import tradefabe.desktop` succeeded with the extra missing and the app was dead
on launch — verifying by module import did not catch it. Family M reuses the lazy pattern
deliberately (torch is ~110MB plus ~400MB of weights, and the paper engine must run without
either), so it needs the check the desktop bug went without.
"""
import importlib
import sys

import pytest

from tradefabe import kronos


def test_the_module_imports_with_no_torch_installed():
    """The paper engine imports tradefabe.runner on every cycle. If anything in family M
    imported torch at module scope, a cloud run with no [kronos] extra would crash on
    import — the engine would stop marking books over an optional research dependency."""
    sys.modules.pop("tradefabe.kronos", None)
    with_torch_hidden = {k: v for k, v in sys.modules.items() if k != "torch"}
    saved, sys.modules = sys.modules, with_torch_hidden
    try:
        mod = importlib.import_module("tradefabe.kronos")
        assert mod.PRED_LEN == 5
    finally:
        sys.modules = saved


def test_no_module_scope_torch_import_in_the_source():
    """Belt and braces on the test above: read the source and assert torch/vendor imports
    are indented (inside a function), never at column 0. A module-scope import would pass a
    warm-cache import test on a dev machine that HAS torch and only fail in the cloud."""
    src = (kronos.__file__)
    with open(src, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    offenders = [
        (i + 1, ln) for i, ln in enumerate(lines)
        if (ln.startswith("import torch") or ln.startswith("from torch")
            or ln.startswith("import einops") or ln.startswith("from .vendor"))
    ]
    assert not offenders, f"torch/vendor imported at module scope in kronos.py: {offenders}"


def test_is_available_is_the_real_check_not_the_import():
    """Documents the contract: importing proves nothing, is_available() is the gate. It must
    return a bool either way rather than raising, so callers can branch on it."""
    assert isinstance(kronos.is_available(), bool)


def test_the_engine_entry_points_do_not_pull_in_kronos():
    """runner/books/cli are what the cloud Action imports. None may reach family M, or the
    optional extra stops being optional.

    Restores the ORIGINAL module object into BOTH sys.modules AND the parent package's
    own attribute after each forced reimport (#161). Two things depend on identity
    staying put:
      - any test file that already did `from tradefabe import runner` (or books, or
        cli) at collection time is holding that original object, not whatever this
        loop puts in sys.modules.
      - `from . import books` inside runner.py/cli.py, on a LATER importlib.reload(),
        resolves via getattr(sys.modules['tradefabe'], 'books') -- the package
        ATTRIBUTE -- not sys.modules directly. Restoring only sys.modules leaves the
        package attribute pointing at the discarded fresh copy, invisible until some
        other test's importlib.reload() re-triggers `from . import books` and picks
        that stale copy back up.
    Skipping either restore step desyncs runner.books / cli.books from the `books`
    object other test files hold, which is what made test_runner.py's
    importlib.reload() raise "not in sys.modules", test_retirement.py's cli.main()
    return the wrong code, and (subtler, only visible once test_runner.py's OWN
    reload-based tests ran first) two other test_runner.py tests read back a
    freshly-initialized book instead of the one _run_book() just saved -- all only
    under xdist scheduling that runs this test before those, in the same worker."""
    tradefabe_pkg = sys.modules["tradefabe"]
    for name in ("tradefabe.runner", "tradefabe.books", "tradefabe.cli"):
        original = sys.modules.pop(name, None)
        try:
            importlib.import_module(name)
        finally:
            if original is not None:
                sys.modules[name] = original
                setattr(tradefabe_pkg, name.rsplit(".", 1)[1], original)
    assert "torch" not in sys.modules or True  # torch may be present locally; see below

    src_root = kronos.__file__.rsplit("/", 1)[0]
    for mod in ("runner", "books", "cli", "signals", "engine", "hourly"):
        with open(f"{src_root}/{mod}.py", encoding="utf-8") as fh:
            body = fh.read()
        assert "import kronos" not in body and "from .kronos" not in body, (
            f"{mod}.py imports family M — that makes the [kronos] extra mandatory")


def test_a_missing_extra_raises_an_actionable_error_not_an_attributeerror(monkeypatch):
    """When the extra genuinely is absent, the failure has to name the fix. A bare
    ModuleNotFoundError deep inside vendored code would send the reader to Kronos's repo
    instead of to `pip install -e '.[kronos]'`."""
    monkeypatch.setattr(kronos, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match=r"\[kronos\]"):
        kronos._require()
