"""
merge_routine_branches.py — safety net for the research routine's proposals (#181).

The research routine (a Claude Code Routine on claude.ai, not a repo file) is
instructed to commit pipeline_ideas.csv appends directly to main -- but that's
Instructions text, not an enforced guarantee. On 2026-08-03 it landed on a fresh branch
instead: a cautious, CORRECT read of CLAUDE.md's general "never push to main" rule, just
missing the established ledger-write exception (tradefabe-bot's own commits). Rather
than assume an Instructions fix reliably changes that, this runs as the FIRST step of
every pipeline-daily.yml cycle regardless: find any `claude/*` branch, verify its diff
touches ONLY pipeline_ideas.csv as a pure line addition, and fold its new rows onto main
directly. Anything else -- another file touched, an existing row removed or modified --
is left alone for manual review, never force-merged.

WHY A PLAIN APPEND, NOT `git cherry-pick`/`git merge`: two routine runs based on the
same main tip (e.g. two candidates proposed the same day) both append at the same
position relative to their shared ancestor. git's own 3-way merge sees that as a content
conflict and refuses -- this module's own test_two_concurrent_branches_both_merge_
cleanly reproduces that exact failure against a naive cherry-pick and confirms a plain
line-level append (extracted from the diff, not merged by git) sidesteps it entirely,
since every branch is known in advance to be nothing but new CSV rows.

Idempotent and safe to run with zero matching branches (the common case, most days):
does nothing.

Usage: PYTHONPATH=research python research/merge_routine_branches.py [--repo PATH]
"""
from __future__ import annotations
import argparse
import os
import subprocess

BRANCH_PREFIX = "claude/"
LEDGER_PATH = "pipeline_ideas.csv"
CANONICAL_HEADER = "timestamp,name,primitive,freq,params,rationale,citation"
MERGE_COMMIT_NAME = "dzheng1328"
MERGE_COMMIT_EMAIL = "76966554+dzheng1328@users.noreply.github.com"


def _git(*args, cwd=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def list_research_branches(cwd=None) -> list[str]:
    """Every local branch (the caller is responsible for having fetched first) starting
    with BRANCH_PREFIX. Sorted, so a multi-branch day processes in a stable order."""
    out = _git("branch", "--list", f"{BRANCH_PREFIX}*", "--format=%(refname:short)", cwd=cwd)
    return sorted(b for b in out.splitlines() if b.strip())


def branch_is_ledger_only(base: str, branch: str, cwd=None) -> bool:
    files = _git("diff", "--name-only", base, branch, cwd=cwd).splitlines()
    return files == [LEDGER_PATH]


def extract_new_rows(base: str, branch: str, ledger_exists: bool, cwd=None) -> list[str] | None:
    """The new PIPELINE_LEDGER rows `branch` added since `base`, or None if the branch
    did anything other than a pure line addition to that file -- callers must treat
    None as "leave this branch alone, needs a human," never as "nothing changed."""
    lines = _git("diff", base, branch, "--", LEDGER_PATH, cwd=cwd).splitlines()
    added, removed = [], []
    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    if removed:
        return None
    if ledger_exists:
        # A branch that created the file fresh (main had none yet) legitimately
        # includes the header in its diff; a branch landing AFTER main already has the
        # file must not re-add a second header row.
        added = [row for row in added if row != CANONICAL_HEADER]
    return added


def merge_routine_branches(cwd=None, verbose=True) -> list[dict]:
    """Runs as the first step of every pipeline-daily.yml cycle. Returns one
    {"branch", "merged", "reason"} summary per claude/* branch found (empty list on a
    normal day with none)."""
    results = []
    ledger_path = os.path.join(cwd or ".", LEDGER_PATH)

    for branch in list_research_branches(cwd=cwd):
        base = _git("merge-base", "main", branch, cwd=cwd).strip()

        if not branch_is_ledger_only(base, branch, cwd=cwd):
            reason = "touches more than pipeline_ideas.csv"
            results.append({"branch": branch, "merged": False, "reason": reason})
            if verbose:
                print(f"[merge_routine_branches] {branch}: SKIPPED ({reason})")
            continue

        ledger_exists = os.path.exists(ledger_path)
        new_rows = extract_new_rows(base, branch, ledger_exists, cwd=cwd)
        if new_rows is None:
            reason = "removed or modified an existing row -- not a pure append"
            results.append({"branch": branch, "merged": False, "reason": reason})
            if verbose:
                print(f"[merge_routine_branches] {branch}: SKIPPED ({reason})")
            continue
        if not new_rows:
            reason = "nothing to append after filtering"
            results.append({"branch": branch, "merged": False, "reason": reason})
            if verbose:
                print(f"[merge_routine_branches] {branch}: SKIPPED ({reason})")
            continue

        with open(ledger_path, "a") as fh:
            for row in new_rows:
                fh.write(row + "\n")
        _git("add", LEDGER_PATH, cwd=cwd)
        _git("-c", f"user.name={MERGE_COMMIT_NAME}", "-c", f"user.email={MERGE_COMMIT_EMAIL}",
             "commit", "-m", f"pipeline research: merge {branch} [skip ci]", cwd=cwd)
        _git("branch", "-D", branch, cwd=cwd)
        results.append({"branch": branch, "merged": True, "reason": None})
        if verbose:
            print(f"[merge_routine_branches] {branch}: merged ({len(new_rows)} row(s))")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    args = parser.parse_args()
    merge_routine_branches(cwd=args.repo)


if __name__ == "__main__":
    main()
