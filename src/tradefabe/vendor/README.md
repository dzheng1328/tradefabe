# Vendored third-party code

Nothing in this directory is ours. It is copied verbatim (modulo the documented patches
below) from an upstream project, pinned to a commit, so that a verdict produced against it
stays reproducible even if upstream moves, rewrites history, or disappears.

## `kronos_model/` — Kronos

| | |
|---|---|
| upstream | https://github.com/shiyu-coder/Kronos |
| pinned commit | `67b630e67f6a18c9e9be918d9b4337c960db1e9a` (2026-04-13) |
| licence | MIT — see `kronos_model/LICENSE`, © 2025 ShiYu |
| paper | [arXiv:2508.02739](https://arxiv.org/abs/2508.02739), AAAI 2026 |
| files | `__init__.py`, `kronos.py`, `module.py` (~1,270 lines total) |

### Why vendored rather than pip-installed

Upstream ships no `setup.py` and no `pyproject.toml` — it is not an installable package,
only a repo you are expected to `cd` into. The alternatives were a git submodule or a
clone-at-setup-time step; both make a doctrine verdict depend on a network fetch of a
moving target. Three files totalling 54KB is a cheap price for reproducibility.

**Model *weights* are not vendored.** They are ~400MB and are pulled from the Hugging Face
Hub at first use (`NeoQuasar/Kronos-base`, `NeoQuasar/Kronos-Tokenizer-base`), then cached.

### Patches applied

Exactly one, in `kronos.py`:

```diff
-import sys
-sys.path.append("../")
-from model.module import *
+from .module import *
```

Upstream resolves `model.module` as a top-level package, which only works when the current
working directory is the Kronos repo root. Vendored, there is no top-level `model` package,
so the import raised `ModuleNotFoundError`. The replacement is an explicit relative import
with identical star semantics. No change to the model, the tokenizer, or the sampler.

`tests/test_vendored_kronos.py` asserts this patch is the only difference in the import
block and that no `sys.path` manipulation has crept back in.

### Updating

Do not edit these files to fix a bug in our own code — fix it in `src/tradefabe/kronos.py`
instead. If upstream genuinely needs to be re-pulled, re-pin the SHA above, re-apply the
patch, and treat it as a spec change: every frozen inference parameter in `STRATEGIES.md`
family M was registered against *this* commit, so a different sampler is a new row and a
new graveyard entry under roster rule 2.
