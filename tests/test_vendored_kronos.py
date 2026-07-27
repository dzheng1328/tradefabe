"""Integrity of the vendored Kronos model code.

The verdicts in family M are produced by a specific sampler at a specific commit. If that
code drifts — an edit made to work around a bug in OUR code, a re-pull that quietly changes
sampling — every frozen inference parameter in STRATEGIES.md was registered against
something that no longer exists. These tests make drift loud.

None of them need torch: they read the vendored source as text.
"""
import os
import re

import pytest

VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "src", "tradefabe", "vendor")
KRONOS_DIR = os.path.join(VENDOR, "kronos_model")
PINNED_SHA = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"


def read(name):
    with open(os.path.join(KRONOS_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def code(name):
    """Source with whole-line comments stripped.

    Needed because the vendoring patch's own comment QUOTES the upstream lines it replaced
    (`sys.path.append("../")`), so a naive substring search over the raw file matches the
    documentation of the fix and reports the bug it fixed.
    """
    return "\n".join(ln for ln in read(name).splitlines()
                     if not ln.lstrip().startswith("#"))


def test_the_mit_licence_ships_with_the_code():
    """MIT requires the copyright notice travel with the source. Deleting it would make the
    repo's use of Kronos non-compliant, silently."""
    licence = read("LICENSE")
    assert "MIT License" in licence
    assert "ShiYu" in licence


def test_the_pinned_commit_is_recorded_and_matches_the_readme():
    """The SHA is the whole reproducibility claim. If the vendor README and this test ever
    disagree, one of them was updated without the other."""
    with open(os.path.join(VENDOR, "README.md"), encoding="utf-8") as fh:
        readme = fh.read()
    assert PINNED_SHA in readme
    assert "shiyu-coder/Kronos" in readme


def test_the_sys_path_hack_has_not_crept_back():
    """Upstream does `sys.path.append("../")` + `from model.module import *`, which only
    resolves when cwd is the Kronos repo root. Re-pulling upstream without re-applying the
    documented patch would reintroduce it and break the import from anywhere else."""
    src = code("kronos.py")
    assert "sys.path.append" not in src
    assert "from model.module import" not in src
    assert "from .module import *" in src


def test_the_documented_patch_is_the_only_import_change():
    """The vendor README claims exactly one patch. Anything else importing from outside the
    vendored package means the copy is no longer a faithful pin."""
    src = code("kronos.py")
    bad = re.findall(r"^\s*(?:from|import)\s+(model|finetune|examples|webui)\b",
                     src, flags=re.MULTILINE)
    assert not bad, f"vendored kronos.py reaches outside the vendored package: {bad}"


def test_the_sampler_still_averages_paths_internally():
    """The single most load-bearing fact about this library for family M: it collapses the
    sampled paths with `np.mean(preds, axis=1)` before returning. `forecast_paths()` exists
    solely to work around that. If a re-pull ever changes it, forecast_paths' replicate-
    across-the-batch trick becomes redundant at best and wrong at worst — so notice."""
    src = read("kronos.py")
    assert "np.mean(preds, axis=1)" in src, (
        "upstream no longer averages sample_count internally — revisit "
        "tradefabe.kronos.forecast_paths(), which is built entirely around that behaviour")


def test_the_inference_defaults_we_pre_registered_against_are_unchanged():
    """We froze T/top_p/top_k against the authors' own values. Those live in our module, but
    the SIGNATURE they're passed into lives here — a reordered or renamed kwarg would bind
    our frozen 0.6 to the wrong parameter without any error."""
    src = read("kronos.py")
    assert re.search(r"def predict_batch\(\s*self,.*?pred_len,\s*T=1\.0,\s*top_k=0,"
                     r"\s*top_p=0\.9,\s*sample_count=1", src, flags=re.DOTALL), (
        "KronosPredictor.predict_batch's signature changed — re-verify that "
        "tradefabe.kronos passes T/top_k/top_p/sample_count to the parameters it means to")


def test_vendored_package_is_importable_without_torch_present():
    """`import tradefabe.vendor` must stay free of torch: the vendor __init__ is deliberately
    empty of imports so the paper engine can import the package tree without the extra."""
    with open(os.path.join(VENDOR, "__init__.py"), encoding="utf-8") as fh:
        body = fh.read()
    assert "import torch" not in body
    assert "kronos_model" not in body.replace("`kronos_model`", "")
