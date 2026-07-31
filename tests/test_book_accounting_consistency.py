"""Static consistency guard for the #149 book-accounting-mismatch bug class (#157).

Two independently hand-maintained sets used to describe the exact same fact -- "this
book's equity moves by direct funding accrual (books.rebalance_to() is never called),
not by real ticker positions" -- in two different files: app.py's ACCRUAL_ONLY_BOOKS
and pricing.py's NON_PRICED. #157 consolidated app.py to import pricing.NON_PRICED
directly instead of keeping a second copy (see app.py's import + comment).

This test is the other half: it reads the SOURCE of every function that actually
updates a live book's equity, across every module currently capable of owning one, and
checks that its mechanism agrees with whether its book is in pricing.NON_PRICED. A
future accrual-only book added to a new or existing function without a matching
NON_PRICED entry fails HERE with a clear message, instead of silently rendering the
frozen $100k starting cash on the dashboard's Capital Deployed panel -- #149's exact
failure mode, and #143's before it for the trade log specifically.

Deliberately does NOT try to generically infer book names from arbitrary source code
(a `name: str = "..."` default parameter or a module constant isn't reliable enough to
regex for across arbitrary future functions). Instead it reads each module's own
registry where one already exists (hourly.PRICE_BOOK_NAMES, kronos_live.WICK_BOOK /
CARRY_BOOK) and asserts a closed-form equality against pricing.NON_PRICED, so a new
book that isn't wired into either direction is visibly incomplete rather than silently
passing.
"""
import inspect
import re

from tradefabe import carry_live, hourly, kronos_live, pricing

# A `book["equity"] = round(books.equity(...), 2)` line is a CACHE of the value
# books.equity() derived from positions/cash after a real rebalance_to() -- priced, not
# accrual, even though it's textually an assignment to book["equity"]. Only an
# assignment whose right-hand side does NOT call books.equity() is the real accrual
# pattern (carry_live.run_carry / hourly.run_funding_timing / kronos_live.run_carry_kronos
# all compute their own `eq`/`accrual` from funding math, never from books.equity()).
_EQUITY_ASSIGNMENT = re.compile(r'book\["equity"\]\s*=\s*(.*)')


def _writes_equity_directly(fn):
    for line in inspect.getsource(fn).splitlines():
        m = _EQUITY_ASSIGNMENT.search(line)
        if m and "books.equity(" not in m.group(1):
            return True
    return False


def _calls_rebalance_to(fn):
    return "rebalance_to(" in inspect.getsource(fn)


def test_carry_btc_eth_is_accrual_only():
    assert "carry_btc_eth" in pricing.NON_PRICED
    assert _writes_equity_directly(carry_live.run_carry)
    assert not _calls_rebalance_to(carry_live.run_carry)


def test_funding_timing_1h_is_accrual_only():
    assert "funding_timing_1h" in pricing.NON_PRICED
    assert _writes_equity_directly(hourly.run_funding_timing)
    assert not _calls_rebalance_to(hourly.run_funding_timing)


def test_carry_kronos_vol_is_accrual_only():
    assert kronos_live.CARRY_BOOK in pricing.NON_PRICED
    assert _writes_equity_directly(kronos_live.run_carry_kronos)
    assert not _calls_rebalance_to(kronos_live.run_carry_kronos)


def test_family_l_price_books_are_not_accrual_only():
    """crypto_reversal_1h and equity_tsmom_1h -- run_price_books() rebalances every
    name in hourly.BOOKS via books.rebalance_to(), never a direct equity write."""
    assert set(hourly.PRICE_BOOK_NAMES) == {"crypto_reversal_1h", "equity_tsmom_1h"}
    assert not pricing.NON_PRICED & set(hourly.PRICE_BOOK_NAMES)
    assert _calls_rebalance_to(hourly.run_price_books)
    assert not _writes_equity_directly(hourly.run_price_books)


def test_kronos_wick_agg_is_not_accrual_only():
    """run_kronos() dispatches every name in LIVE_BOOKS (its default `names` param)
    through run_price_book(), the same rebalance_to()-based mechanism
    kronos_wick_agg's flat-$100k bug (#158) was diagnosed against -- confirming it
    here is what makes #158's root cause (a cron timing issue, not an accounting
    one) trustworthy rather than assumed."""
    assert kronos_live.WICK_BOOK not in pricing.NON_PRICED
    assert kronos_live.WICK_BOOK in kronos_live.LIVE_BOOKS
    default_names = inspect.signature(kronos_live.run_kronos).parameters["names"].default
    assert default_names is kronos_live.LIVE_BOOKS
    assert "run_price_book(" in inspect.getsource(kronos_live.run_kronos)
    assert _calls_rebalance_to(kronos_live.run_price_book)
    assert not _writes_equity_directly(kronos_live.run_price_book)


def test_non_priced_has_no_book_this_test_does_not_account_for():
    """The completeness check: every name in pricing.NON_PRICED must be explained by
    one of the accrual tests above. A name added to NON_PRICED without a matching
    accrual function (or vice versa) fails here rather than silently drifting."""
    accounted_for = {"carry_btc_eth", "funding_timing_1h", kronos_live.CARRY_BOOK}
    assert pricing.NON_PRICED == accounted_for, (
        f"pricing.NON_PRICED {pricing.NON_PRICED} has diverged from the set of books "
        f"this test can trace to a real accrual function ({accounted_for}) -- add a "
        f"test above for the new book's owning function before trusting its accounting.")
