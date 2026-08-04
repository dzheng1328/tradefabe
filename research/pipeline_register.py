"""
pipeline_register.py — the research pipeline's pre-registration checkpoint (#179).

DOCTRINE v1.11's fully-automatic checkpoint (Dave's explicit call, 2026-08-01): once a
candidate clears #175's prelim screen, its spec is frozen and committed to
STRATEGIES.md immediately, automatically, same day -- no human review, no PR that waits
on approval. This is deliberately less cautious than #179's own issue text initially
leaned ("pre-registration is supposed to be a real commitment made with judgment, not a
rubber stamp a script clears"), traded for a genuinely hands-off daily pipeline; the
tradeoff is recorded, not glossed over, in DOCTRINE.md's own amendment.

Pre-registration here means two things, both written before #180 (not yet built) can
run a real OOS test on this candidate:
  1. Human-readable prose appended to STRATEGIES.md's own "Research pipeline —
     pre-registered candidates" section -- generated programmatically from the
     validated proposal (#177), since no human is writing it by hand on this path.
  2. A durable, append-only stamp in PREREGISTERED_LEDGER, so #180 has a
     machine-readable way to find "pre-registered but not yet OOS-tested" candidates
     without parsing markdown.

Idempotent by name: a candidate already pre-registered is never re-appended, the same
promotion-registry idempotency factory.promote() already uses.
"""
from __future__ import annotations
import datetime
import os

import pandas as pd

import harness

STRATEGIES_PATH = os.path.join(harness.BASE, "STRATEGIES.md")
PREREGISTERED_LEDGER = os.path.join(harness.BASE, "pipeline_preregistered.csv")

PREREG_SECTION_HEADER = "## Research pipeline — pre-registered candidates (#179)"
PREREG_INTRO = (
    "Every candidate the research pipeline (#174) proposes and clears #175's prelim "
    "screen is pre-registered here AUTOMATICALLY -- DOCTRINE v1.11's fully-automatic "
    "checkpoint (Dave's explicit call, 2026-08-01), no human review before the full "
    "OOS test (#180) runs. Generated programmatically from the validated proposal "
    "(`research/pipeline_register.py`), not hand-written prose like the families "
    "above.\n")
PREREG_INSERT_BEFORE = "## Rules of the roster"


def _preregistered_names() -> set[str]:
    if not os.path.exists(PREREGISTERED_LEDGER):
        return set()
    return set(pd.read_csv(PREREGISTERED_LEDGER)["name"].unique())


def _log_preregistration(name: str) -> None:
    row = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "name": name}
    pd.DataFrame([row]).to_csv(PREREGISTERED_LEDGER, mode="a",
                               header=not os.path.exists(PREREGISTERED_LEDGER), index=False)


def format_preregistration(proposal: dict) -> str:
    """Renders a validated pipeline proposal (#177's full return -- name, primitive,
    params, freq, rationale, citation) as a STRATEGIES.md section, matching the prose
    every hand-tested strategy gets, minus the hand-writing."""
    name = proposal["name"]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    params_str = ", ".join(f"{k}={v}" for k, v in proposal["params"].items())
    return (
        f"\n### `{name}` (primitive `{proposal['primitive']}`)\n\n"
        f"**PRE-REGISTRATION — frozen {now}, committed automatically before any OOS "
        f"test ran (#179).** Parameters: {params_str}. Rebalance freq: "
        f"{proposal['freq']}.\n\n"
        f"Rationale: {proposal['rationale']}\n\n"
        f"Citation: {proposal['citation']}\n")


def preregister_candidate(proposal: dict) -> bool:
    """Appends `proposal`'s pre-registration to STRATEGIES.md and stamps
    PREREGISTERED_LEDGER. Returns True if newly registered, False if this name was
    already pre-registered (idempotent no-op, not an error). The actual git commit is
    NOT done here -- it's picked up by pipeline-daily.yml's existing "commit ledgers"
    step, the same way every other automated ledger write in this repo is committed,
    rather than this module shelling out to git itself."""
    name = proposal["name"]
    if name in _preregistered_names():
        print(f"[pipeline_register] {name} already pre-registered -- skipping")
        return False

    with open(STRATEGIES_PATH) as fh:
        text = fh.read()
    if PREREG_INSERT_BEFORE not in text:
        raise RuntimeError(
            f"STRATEGIES.md is missing the {PREREG_INSERT_BEFORE!r} marker -- cannot "
            "safely locate the pre-registration insertion point")

    insertion = "" if PREREG_SECTION_HEADER in text else f"{PREREG_SECTION_HEADER}\n\n{PREREG_INTRO}"
    insertion += format_preregistration(proposal)
    text = text.replace(PREREG_INSERT_BEFORE, insertion + "\n" + PREREG_INSERT_BEFORE, 1)

    with open(STRATEGIES_PATH, "w") as fh:
        fh.write(text)
    _log_preregistration(name)
    print(f"[pipeline_register] pre-registered {name} to STRATEGIES.md")
    return True
