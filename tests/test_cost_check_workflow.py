"""Regression guard for #155: the cost-check workflow's `env:` block must set exactly
the environment variable names broker.credentials() actually reads. A mismatch here
(e.g. a rename on either side) is invisible in a code review of either file alone --
it only shows up as a real API run failing on a workday, which is exactly the kind of
silent failure #155 exists to eliminate."""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "cost-check.yml"
BROKER = Path(__file__).resolve().parents[1] / "src" / "tradefabe" / "broker.py"


def _run_step_env() -> dict:
    doc = yaml.safe_load(WORKFLOW.read_text())
    for job in doc["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == "run cost check":
                return step.get("env", {})
    raise AssertionError('no step named "run cost check" found -- has it been renamed?')


def test_workflow_sets_every_env_var_broker_credentials_reads():
    env = _run_step_env()
    broker_src = BROKER.read_text()
    for var in ("ALPACA_API_KEY_ID", "ALPACA_SECRET_KEY", "ALPACA_PAPER_TRADE"):
        assert f'os.environ.get("{var}"' in broker_src, (
            f"broker.py no longer reads {var} -- update this test's expectations"
        )
        assert var in env, f"cost-check.yml's run step never sets {var}"


def test_workflow_hardcodes_paper_trade_true_not_a_secret():
    # ALPACA_PAPER_TRADE must be the literal string "true", not sourced from a secret --
    # a secret could be misconfigured; the paper-only gate must not depend on that.
    env = _run_step_env()
    assert env["ALPACA_PAPER_TRADE"] == "true"


def test_workflow_pulls_credentials_from_secrets_not_hardcoded_values():
    env = _run_step_env()
    assert env["ALPACA_API_KEY_ID"] == "${{ secrets.ALPACA_API_KEY_ID }}"
    assert env["ALPACA_SECRET_KEY"] == "${{ secrets.ALPACA_SECRET_KEY }}"


def test_workflow_runs_weekly_not_daily():
    # Dave's explicit call (#155): weekly, not daily -- each run places 5 real paper
    # round-trip orders. A cron with 5 day-of-week fields all wildcarded (or a "1-5"
    # weekday range) would silently turn this into a daily job again.
    doc = yaml.safe_load(WORKFLOW.read_text())
    on = doc.get("on", doc.get(True))
    crons = [entry["cron"] for entry in on["schedule"]]
    assert len(crons) == 1
    dow_field = crons[0].split()[4]
    assert dow_field not in ("*", "1-5"), (
        f"cron {crons[0]!r} looks like it fires more than weekly -- confirm this is "
        "intentional before merging"
    )
