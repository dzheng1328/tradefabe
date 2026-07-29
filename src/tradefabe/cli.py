"""tradefabe CLI — the app entry point.

  tradefabe run       run one daily paper cycle: rebalance due books, mark the rest
  tradefabe mark      mark every book to the current price, no rebalancing (for a
                      tighter cron, so the live-equity chart isn't one dot/day)
  tradefabe status    print current book equities
  tradefabe reset     wipe paper state and start fresh ($100k/book)
  tradefabe retire <book> --reason "..."    freeze a book: no more rebalances or marks,
                      history preserved. MANUAL ONLY — see DOCTRINE.md, nothing in the
                      engine ever retires a book on its own (#113)
  tradefabe unretire <book>                resume a retired book on the next cycle
"""
from __future__ import annotations
import argparse
import shutil
import sys
import pandas as pd
from .paths import STATE_DIR


def main() -> int:
    ap = argparse.ArgumentParser(prog="tradefabe", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "mark", "status", "reset",
                                        "retire", "unretire"])
    ap.add_argument("book", nargs="?", help="book name, for retire/unretire")
    ap.add_argument("--reason", help="why this book is being retired (required, recorded "
                                     "in the ledger — a retirement is a decision on the "
                                     "record, not a status flag)")
    args = ap.parse_args()

    if args.command == "run":
        from .runner import run_daily
        print("running daily paper cycle (paper only — nothing real is traded)...")
        summary = run_daily()
        print("\n" + summary.to_string(index=False))
    elif args.command == "mark":
        from .runner import run_mark
        print("marking paper books to market (paper only — nothing real is traded)...")
        summary = run_mark()
        print("\n" + summary.to_string(index=False))
    elif args.command == "status":
        f = STATE_DIR / "summary.csv"
        if not f.exists():
            print("no paper state yet — run `tradefabe run` first")
            return 1
        print(pd.read_csv(f).to_string(index=False))
    elif args.command == "reset":
        if STATE_DIR.exists():
            shutil.rmtree(STATE_DIR)
        print("paper state wiped — next `tradefabe run` starts fresh at $100k/book")
    elif args.command in ("retire", "unretire"):
        return _retirement(args)
    return 0


def _retirement(args) -> int:
    """retire/unretire share their argument checking, and both fail LOUDLY rather than
    guessing. `books.retire()` refuses a name with no ledger on disk -- load() would
    otherwise synthesize a fresh $100k book for a typo and immediately retire the phantom.
    """
    from . import books
    if not args.book:
        print(f"usage: tradefabe {args.command} <book>"
              f"{' --reason \"...\"' if args.command == 'retire' else ''}")
        return 2
    try:
        if args.command == "retire":
            if not args.reason:
                print("refusing to retire without --reason. A retirement is a human "
                      "decision recorded in the ledger, and the reason is the record.")
                return 2
            book = books.retire(args.book, args.reason)
            r = book["retired"]
            print(f"{args.book} retired at {r['at']} — {r['reason']}\n"
                  f"The ledger is frozen: no further rebalances or marks. Its history is "
                  f"untouched and it still appears in `status` and the dashboard.\n"
                  f"Reverse with: tradefabe unretire {args.book}")
        else:
            books.unretire(args.book)
            print(f"{args.book} un-retired — it resumes on the next `tradefabe run`. "
                  f"The gap stays visible on its equity chart rather than being filled in.")
    except (KeyError, ValueError) as e:
        print(f"error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
