"""tradefabe CLI — the app entry point.

  tradefabe run      run one daily paper cycle: rebalance due books, mark the rest
  tradefabe mark      mark every book to the current price, no rebalancing (for a
                      tighter cron, so the live-equity chart isn't one dot/day)
  tradefabe status   print current book equities
  tradefabe reset    wipe paper state and start fresh ($100k/book)
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
    ap.add_argument("command", choices=["run", "mark", "status", "reset"])
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
