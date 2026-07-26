---
name: ship
description: Branch, PR, wait for CI, verify the merge landed, then clean up. Use when shipping a change in tradefabe. Encodes the verify-before-delete sequence that three closed PRs were caused by skipping.
disable-model-invocation: true
---

# ship

The repo's git workflow, as a procedure rather than something retyped each time. The
ordering matters more than it looks: PRs #65, #80 and #92 were each closed unmerged by
getting step 5 wrong, and GitHub **will not reopen a PR whose branch has been deleted** —
recovery meant digging the commit out of reflog and opening a fresh PR.

## 1. Branch

```sh
git checkout main && git pull -q
git checkout -b <topic>
```

Never commit to `main`. If work is already on `main` uncommitted, branch first — the commit
follows the branch.

## 2. Run the suite locally

```sh
.venv/bin/pytest tests/ -q          # parallel, ~13s
```

Green locally before pushing. CI takes ~4 minutes; local takes 13 seconds.

## 3. Commit, excluding Action-owned state

`state/paper/` belongs to the paper-engine Action. Stage code explicitly rather than
`git add -A`:

```sh
git add src/ tests/ app.py CLAUDE.md      # whatever the change actually touched
git status --porcelain                    # confirm no state/ crept in
```

Only stage `state/` when deliberately opening or repairing a book, and say so in the commit
message. A hook will ask you to confirm.

## 4. PR, then wait for CI

```sh
git push -u origin <topic> -q
gh pr create --base main --title "..." --body "..."
gh pr checks <N> --watch --interval 20
```

The body should carry the reasoning: what broke, why, what proves it fixed. Note that CI
only fires for PRs targeting `main` — a PR onto another branch reports "no checks reported",
which reads like failure but means the workflow never ran.

## 5. Merge, then VERIFY, then clean up — three separate commands

```sh
gh pr merge <N> --squash
gh pr view <N> --json state,mergedAt        # must print MERGED
git checkout main && git pull -q
git branch -D <topic>
git push origin --delete <topic>
```

**Never chain the delete onto the merge**, and never use `--delete-branch`. `gh pr merge`
fails on a bad flag or a `state/` conflict, and a chained delete still runs — closing the
unmerged PR permanently. A hook blocks the chained form; this step is why.

If the merge fails on a `state/` conflict, resolve by taking the Action's version
(`git checkout origin/main -- state/paper`) and make the PR code-only. The marks regenerate
next cycle.

## 6. Confirm it landed

```sh
git log --oneline -1
gh pr list --state open --json number -q '.[].number' | wc -l
```
