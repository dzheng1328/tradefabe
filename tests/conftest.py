"""Test-suite runtime budget, enforced.

Same reasoning as tests/test_claude_md_budget.py's CLAUDE.md budget: "add a test for
every real bug or gate" is right, but nothing stops that from quietly compounding into
a suite nobody wants to run. Rather than capping the NUMBER of tests -- which can't
distinguish a real regression guard from padding, and would fight a legitimate new
subsystem (family M alone added ~80) -- this caps what actually costs something: how
long the suite takes, and how long any one test takes.

Measured 2026-07-31: 491 tests, 3.5s locally (parallel, `-n auto --dist worksteal`),
~13s in CI (the CI job's real cost is `pip install -e .` at ~27s, not tests). Slowest
single test was 1.08s. Budgets below give real headroom over both, sized for a
solo research-lab project run constantly during dev, not enterprise CI.

WHAT TO DO WHEN THIS FAILS
--------------------------
Per-test failure: that one test is slow. Before raising SLOW_TEST_BUDGET_SECONDS, check
whether it's doing something it shouldn't -- real network I/O instead of a mock, a
full-history backtest where a synthetic frame would prove the same thing, a fixture
rebuilding a large object per-test instead of module/session-scoped. If it genuinely
needs the time (e.g. a real doctrine evaluation over years of data), that's legitimate;
raise the budget for that reason, not to make a red X go away.

Whole-suite failure: no single test is over budget, but the sum grew. Same question at
the suite level -- is the new coverage doing more work than it needs to, or did the
suite just grow because the project did? If it's the latter, this is a real signal to
sanity-check test count against tests/test_claude_md_budget.py's own philosophy: does
each new test trace to a bug that actually happened or a gate that actually matters,
not "test everything reachable" defensive padding.
"""
import time

import pytest

from tradefabe import remote

SUITE_DURATION_BUDGET_SECONDS = 45.0
SLOW_TEST_BUDGET_SECONDS = 5.0

_session_start = None


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """remote.py tries GitHub before local disk (see its docstring) -- without this, every
    test touching a dashboard loader makes a real HTTPS call, which is exactly the "real
    network I/O instead of a mock" this file's own docstring tells you to fix, and it's
    slow enough to trip SLOW_TEST_BUDGET_SECONDS on its own. Forces every read down the
    local-disk fallback path so existing BASE/ART tmp_path isolation keeps working.
    test_remote.py overrides this per-test to exercise the real network branch."""
    def _blocked(url):
        raise OSError(f"real network access blocked in tests: {url}")

    monkeypatch.setattr(remote, "_get", _blocked)


def pytest_sessionstart(session):
    global _session_start
    _session_start = time.monotonic()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    if _session_start is None:
        return
    elapsed = time.monotonic() - _session_start
    if elapsed > SUITE_DURATION_BUDGET_SECONDS:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"\n[test-budget] full suite took {elapsed:.1f}s, over the "
                f"{SUITE_DURATION_BUDGET_SECONDS:.0f}s budget. Read tests/conftest.py's "
                f"docstring before raising it.",
                red=True,
            )
        session.exitstatus = 1


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.passed and call.duration > SLOW_TEST_BUDGET_SECONDS:
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} took {call.duration:.2f}s, over the "
            f"{SLOW_TEST_BUDGET_SECONDS:.0f}s per-test budget (tests/conftest.py). "
            f"Read that file's docstring before raising it."
        )
