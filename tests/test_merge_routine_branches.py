"""research/merge_routine_branches.py: the safety net for the research routine landing
its proposals on a branch instead of main (observed 2026-08-03).

Three things matter more than any single test: a branch that touches anything besides
pipeline_ideas.csv is left alone (never force-merged), a branch that removes or modifies
an existing row is left alone (not a "pure append," so not something this module trusts
itself to resolve), and two branches based on the SAME original main tip both merge
cleanly in sequence -- this is the actual bug a naive `git cherry-pick` hits (both sides
add a line at the same position relative to their shared ancestor, and git's own 3-way
merge conflicts on it), which is why this module does a plain diff-extracted line append
instead of git's merge machinery.

Runs real git subprocesses against a throwaway tmp_path repo -- there is no way to test
"does git actually merge cleanly" without git actually doing it.
"""
import subprocess

import pytest

import merge_routine_branches as mrb


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    _git("init", "-q", "-b", "main", ".", cwd=tmp_path)
    _git("config", "user.name", "test", cwd=tmp_path)
    _git("config", "user.email", "test@example.com", cwd=tmp_path)
    (tmp_path / "README.md").write_text("placeholder\n")
    _git("add", "README.md", cwd=tmp_path)
    _git("commit", "-qm", "init", cwd=tmp_path)
    return tmp_path


def _make_branch(repo, name, files: dict, base="main"):
    """Creates `name` off `base`, writes/overwrites `files` (path -> content), commits.
    Leaves the repo checked out on `base` afterward, matching how independent routine
    runs each branch off main without ever depending on another run's branch."""
    _git("checkout", "-qb", name, base, cwd=repo)
    for path, content in files.items():
        (repo / path).write_text(content)
    _git("add", *files.keys(), cwd=repo)
    _git("commit", "-qm", f"pipeline research: {name} [skip ci]", cwd=repo)
    _git("checkout", "-q", base, cwd=repo)


def _log(repo):
    return subprocess.run(["git", "log", "--oneline", "main"], cwd=repo,
                          capture_output=True, text=True, check=True).stdout


HEADER = mrb.CANONICAL_HEADER


def test_no_matching_branches_is_a_clean_no_op(repo):
    assert mrb.merge_routine_branches(cwd=repo, verbose=False) == []


def test_a_single_clean_branch_merges_and_is_deleted(repo):
    _make_branch(repo, "claude/a", {
        mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:00:00+00:00,rp_a,,,,,\n"})

    results = mrb.merge_routine_branches(cwd=repo, verbose=False)
    assert results == [{"branch": "claude/a", "merged": True, "reason": None}]
    assert "rp_a" in (repo / mrb.LEDGER_PATH).read_text()
    assert "claude/a" not in subprocess.run(
        ["git", "branch", "--list", "claude/*"], cwd=repo, capture_output=True, text=True).stdout


@pytest.fixture
def repo_with_bad_branch(repo):
    _make_branch(repo, "claude/bad", {"STRATEGIES.md": "unexpected edit\n"})
    return repo


def test_branch_touching_another_file_is_skipped_not_merged(repo_with_bad_branch):
    results = mrb.merge_routine_branches(cwd=repo_with_bad_branch, verbose=False)
    assert results == [{"branch": "claude/bad", "merged": False,
                        "reason": "touches more than pipeline_ideas.csv"}]
    # branch survives untouched for manual review
    branches = subprocess.run(["git", "branch", "--list", "claude/*"],
                              cwd=repo_with_bad_branch, capture_output=True, text=True).stdout
    assert "claude/bad" in branches


def test_branch_that_removes_an_existing_row_is_skipped_not_merged(repo):
    (repo / mrb.LEDGER_PATH).write_text(f"{HEADER}\n2026-08-04T00:00:00+00:00,rp_old,,,,,\n")
    _git("add", mrb.LEDGER_PATH, cwd=repo)
    _git("commit", "-qm", "seed existing row", cwd=repo)

    _make_branch(repo, "claude/removes-a-row",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:00:00+00:00,rp_new,,,,,\n"})

    results = mrb.merge_routine_branches(cwd=repo, verbose=False)
    assert results == [{"branch": "claude/removes-a-row", "merged": False,
                        "reason": "removed or modified an existing row -- not a pure append"}]
    assert "rp_old" in (repo / mrb.LEDGER_PATH).read_text()   # untouched on main
    assert "rp_new" not in (repo / mrb.LEDGER_PATH).read_text()


def test_two_concurrent_branches_both_merge_cleanly(repo):
    """The actual bug this module exists to avoid: both branches are cut from the SAME
    main tip (pipeline_ideas.csv doesn't exist yet on either's base, exactly like the
    real 2026-08-03 incident), both create the file fresh with a header + one row. A
    naive `git cherry-pick` of the second branch conflicts here -- confirmed by hand
    before this module was written. Both must land, in order, header written once."""
    _make_branch(repo, "claude/a",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:00:00+00:00,rp_a,,,,,\n"})
    _make_branch(repo, "claude/b",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:05:00+00:00,rp_b,,,,,\n"})

    results = mrb.merge_routine_branches(cwd=repo, verbose=False)
    assert {r["branch"]: r["merged"] for r in results} == {"claude/a": True, "claude/b": True}

    text = (repo / mrb.LEDGER_PATH).read_text()
    assert text.count(HEADER) == 1          # no duplicate header
    assert "rp_a" in text and "rp_b" in text
    lines = [l for l in text.splitlines() if l]
    assert len(lines) == 3                  # header + 2 rows, nothing lost or duplicated


def test_merge_commits_are_attributed_to_dave_not_claude(repo):
    _make_branch(repo, "claude/a",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:00:00+00:00,rp_a,,,,,\n"})
    mrb.merge_routine_branches(cwd=repo, verbose=False)

    author = subprocess.run(["git", "log", "-1", "--format=%an <%ae>", "main"],
                            cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    assert author == f"{mrb.MERGE_COMMIT_NAME} <{mrb.MERGE_COMMIT_EMAIL}>"


def test_multiple_branches_process_in_a_stable_sorted_order(repo):
    _make_branch(repo, "claude/z-second",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:05:00+00:00,rp_second,,,,,\n"})
    _make_branch(repo, "claude/a-first",
                {mrb.LEDGER_PATH: f"{HEADER}\n2026-08-05T00:00:00+00:00,rp_first,,,,,\n"})

    results = mrb.merge_routine_branches(cwd=repo, verbose=False)
    assert [r["branch"] for r in results] == ["claude/a-first", "claude/z-second"]
