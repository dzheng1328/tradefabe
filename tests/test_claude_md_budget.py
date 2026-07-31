"""CLAUDE.md has a size budget, enforced.

CLAUDE.md is loaded into every agent session AND re-injected after every compaction, so its
cost is paid several times per session rather than once. Every other doc in this repo is read
on demand and costs nothing until someone opens it.

The file already tells its own reader to keep it short. That instruction has been in it since
the beginning and the file still grew to 265 lines, because "keep it short" is a wish and this
is a guard. Same reasoning as every other guard here: the test is the memory.

WHAT TO DO WHEN THIS FAILS
--------------------------
Do NOT just raise the cap. First check whether what you added belongs somewhere else:

  a rule an agent must follow before acting          -> CLAUDE.md (it earns its place)
  the post-mortem of a bug that now has a test       -> delete it; the test IS the memory
  a strategy spec, verdict, or evidence              -> STRATEGIES.md
  a doctrine version, threshold, or its reasoning    -> DOCTRINE.md
  a dated audit or decision record                   -> RUNDOWN.md
  human-facing orientation                           -> README.md
  anything derivable from `ls`, `gh issue list`, or   -> nowhere; let the agent run the command
    a file an agent can read on demand

Raising the cap is legitimate when the repo genuinely gained a new subsystem with new traps
(family M did). Raising it to accommodate narrative is not.
"""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bytes, not tokens: no tokenizer is a dependency of this repo, and bytes/4 is a good enough
# proxy for English prose. 18,000 bytes is ~4,500 tokens, ~8% above the 2026-07-29 measurement
# (16,657) -- enough headroom for a real addition, tight enough to notice drift.
CLAUDE_MD_MAX_BYTES = 18_000


def test_claude_md_stays_within_its_token_budget():
    path = os.path.join(BASE, "CLAUDE.md")
    size = os.path.getsize(path)
    assert size <= CLAUDE_MD_MAX_BYTES, (
        f"CLAUDE.md is {size:,} bytes (~{size // 4:,} tokens), over the "
        f"{CLAUDE_MD_MAX_BYTES:,}-byte budget. It is re-injected on every compaction, so this "
        f"is paid repeatedly. Read this test's docstring before raising the cap."
    )


def test_claude_md_still_carries_the_rules_that_cost_something_to_learn():
    """A size budget invites deleting the wrong things. These are the load-bearing ones --
    each traces to a specific incident that cost real work -- so trimming for size cannot
    quietly drop one. Substrings, not exact prose, so the file stays editable."""
    text = open(os.path.join(BASE, "CLAUDE.md")).read()
    required = {
        "paper only": "Paper only",                      # the standing hard rule
        "no chained branch delete": "NEVER chain a branch delete",   # cost PRs 65, 80, 92
        "verify MERGED": "must print MERGED",
        "quoted heredoc": "<<'EOF'",                     # cost a commit msg + an issue comment
        "state/ is Action-owned": "OWNED BY THE ACTION",  # cost a merge conflict + closed PR
        "CI only fires on main": "push/PR on `main`",
        "NaN is permanent": "NaN in the ledger is permanent",
        "books need a persisted curve": "persisted-curve story",     # cost a dashboard outage
        "minute stamps": 'timespec="minutes"',
        "manual-only retirement": "Dave's decision alone",
        "factory cron status is current": "Resumed 2026-07-31",
        "issues beat the board": "authoritative",
    }
    missing = [name for name, needle in required.items() if needle not in text]
    assert not missing, f"CLAUDE.md lost load-bearing rules: {missing}"


def test_the_other_docs_are_not_silently_growing_either():
    """Not a hard cap -- these are read on demand, and DOCTRINE.md / STRATEGIES.md are the
    pre-registration RECORD, which is supposed to accumulate. This only catches a doc that has
    grown enough to suggest it is being used as a dumping ground."""
    caps = {"README.md": 12_000, "RUNDOWN.md": 14_000}
    for name, cap in caps.items():
        size = os.path.getsize(os.path.join(BASE, name))
        assert size <= cap, (
            f"{name} is {size:,} bytes, over its {cap:,} soft cap. It is read on demand so "
            f"this is not urgent, but check whether content belongs in DOCTRINE.md or "
            f"STRATEGIES.md instead."
        )
