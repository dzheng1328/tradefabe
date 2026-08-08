#!/usr/bin/env python3
"""AXI-standard CLI over ops/ui_plan_data.json -- the UI visual-language
implementation plan for the tradefabe dashboard rebuild. See CLAUDE.md /
ops/ui_plan_progress.md for how this fits into the wider project.
"""
import json
import sys
from pathlib import Path

VERSION = "0.1.0"

# --version / -v / -V must resolve before anything else runs.
if len(sys.argv) == 2 and sys.argv[1] in ("--version", "-v", "-V"):
    print(VERSION)
    sys.exit(0)

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / "ui_plan_data.json"
PROGRESS_PATH = HERE / "ui_plan_progress.md"

BIN_PATH = str(Path(__file__).resolve()).replace(str(Path.home()), "~")
DESCRIPTION = (
    "UI visual-language implementation plan for the tradefabe dashboard rebuild "
    "(6 phases, gameplan-derived, axi-readable)."
)

TOP_COMMANDS = ("list", "show", "next", "step")


# ---------------------------------------------------------------- data i/o

def load_data():
    if not DATA_PATH.exists():
        fail(f"plan data file not found at {DATA_PATH}", ["nothing to read -- was ops/ui_plan_data.json moved or deleted?"], code=1)
    with DATA_PATH.open() as f:
        return json.load(f)


def save_data(data):
    with DATA_PATH.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def append_progress_line(text):
    with PROGRESS_PATH.open("a") as f:
        f.write(text.rstrip() + "\n")


# ---------------------------------------------------------------- errors

def fail(msg, help_lines, code=2):
    print(f"error: {msg}")
    for h in help_lines:
        print(f"help: {h}")
    sys.exit(code)


def validate_flags(cmd, argv, allowed):
    allowed = set(allowed) | {"--json", "--help", "-h"}
    for a in argv:
        if a.startswith("-") and a not in allowed:
            fail(
                f'unknown flag "{a}" for `{cmd}`',
                [f"valid flags for `{cmd}`: {', '.join(sorted(allowed))}"],
            )


# ---------------------------------------------------------------- toon

def toon_scalar(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    needs_quote = any(c in s for c in (",", ":", '"')) or s == "" or _looks_numeric(s)
    if needs_quote:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _looks_numeric(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def emit_table(lines, name, rows, fields):
    lines.append(f"{name}[{len(rows)}]{{{','.join(fields)}}}:")
    for r in rows:
        lines.append("  " + ",".join(toon_scalar(r.get(f)) for f in fields))


def emit_kv(lines, key, value, indent=0):
    pad = "  " * indent
    if isinstance(value, dict):
        lines.append(f"{pad}{key}:")
        for k, v in value.items():
            emit_kv(lines, k, v, indent + 1)
    elif isinstance(value, list) and all(isinstance(v, str) for v in value):
        lines.append(f"{pad}{key}[{len(value)}]:")
        for v in value:
            lines.append(f"{pad}  - {v}")
    else:
        lines.append(f"{pad}{key}: {toon_scalar(value)}")


def emit_help(lines, items):
    lines.append(f"help[{len(items)}]:")
    for item in items:
        lines.append(f"  {item}")


def truncate(text, limit=500):
    if len(text) <= limit:
        return text, False
    return text[:limit], True


# ---------------------------------------------------------------- domain

def phase_progress(phase):
    steps = phase["steps"]
    total = len(steps)
    done = sum(1 for s in steps if s["status"] == "done")
    if total and done == total:
        status = "done"
    elif done > 0 or any(s["status"] == "in_progress" for s in steps):
        status = "in_progress"
    else:
        status = "pending"
    return status, done, total


def find_phase(data, phase_id):
    for p in data["phases"]:
        if p["id"] == phase_id:
            return p
    return None


def find_step(data, step_id):
    for phase in data["phases"]:
        for s in phase["steps"]:
            if s["id"] == step_id:
                return phase, s
    return None, None


def find_next(data):
    by_id = {p["id"]: p for p in data["phases"]}
    blocked = []
    for phase in data["phases"]:
        status, _, _ = phase_progress(phase)
        if status == "done":
            continue
        deps_ok = all(phase_progress(by_id[d])[0] == "done" for d in phase.get("depends_on", []))
        if not deps_ok:
            blocked.append(phase["id"])
            continue
        for s in phase["steps"]:
            if s["status"] == "in_progress":
                return phase, s, blocked
        for s in phase["steps"]:
            if s["status"] == "pending":
                return phase, s, blocked
    return None, None, blocked


# ---------------------------------------------------------------- rendering

def phases_table_rows(data):
    rows = []
    for p in data["phases"]:
        status, done, total = phase_progress(p)
        rows.append({"id": p["id"], "title": p["title"], "status": status, "progress": f"{done}/{total}"})
    return rows


def render_home(data, as_json):
    if as_json:
        phase, step, blocked = find_next(data)
        print(json.dumps({
            "bin": BIN_PATH,
            "description": DESCRIPTION,
            "next": {"phase": phase["id"], "step": step["id"], "title": step["title"]} if step else None,
            "blocked_phases": blocked,
            "phases": data["phases"],
        }, indent=2))
        return

    lines = [f"bin: {BIN_PATH}", f"description: {DESCRIPTION}"]
    phase, step, blocked = find_next(data)
    if step is not None:
        lines.append(f'next: step "{step["id"]}" {step["title"]!r} in phase {phase["id"]} ({phase["title"]})')
    elif blocked:
        lines.append(f"next: nothing actionable -- remaining phases blocked on {', '.join(blocked)}")
    else:
        lines.append("next: nothing -- all phases complete")
    lines.append("")
    emit_table(lines, "phases", phases_table_rows(data), ["id", "title", "status", "progress"])
    lines.append("")
    emit_help(lines, [
        "Run `ui_plan.py next` for the next actionable step's full detail",
        "Run `ui_plan.py show <phase-id>` for a phase's full detail (files, summary, steps)",
        "Run `ui_plan.py step show <step-id>` for a step's full detail",
    ])
    print("\n".join(lines))


def render_list(data, as_json):
    if as_json:
        print(json.dumps(data["phases"], indent=2))
        return
    lines = []
    emit_table(lines, "phases", phases_table_rows(data), ["id", "title", "status", "progress"])
    lines.append("")
    emit_help(lines, [
        "Run `ui_plan.py show <phase-id>` for a phase's full detail",
        "Run `ui_plan.py next` for the next actionable step",
    ])
    print("\n".join(lines))


def render_show(data, phase_id, full, as_json):
    phase = find_phase(data, phase_id)
    if phase is None:
        valid = ", ".join(p["id"] for p in data["phases"])
        fail(f'no phase "{phase_id}"', [f"valid phase ids: {valid}"], code=1)

    if as_json:
        print(json.dumps(phase, indent=2))
        return

    status, done, total = phase_progress(phase)
    summary, truncated = (phase["summary"], False) if full else truncate(phase["summary"])

    lines = ["phase:"]
    emit_kv(lines, "id", phase["id"], 1)
    emit_kv(lines, "title", phase["title"], 1)
    emit_kv(lines, "kind", phase["kind"], 1)
    emit_kv(lines, "status", f"{status} ({done}/{total} steps)", 1)
    emit_kv(lines, "depends_on", ", ".join(phase["depends_on"]) or "none", 1)
    emit_kv(lines, "files", ", ".join(phase["files"]), 1)
    if truncated:
        lines.append(f"  summary: {summary}...")
        lines.append(f"  summary_truncated: {len(phase['summary'])} chars total, run with --full to see all")
    else:
        lines.append(f"  summary: {summary}")
    lines.append("")

    emit_table(lines, "steps", phase["steps"], ["id", "title", "status"])

    if "validated_params" in phase:
        lines.append("")
        emit_kv(lines, "validated_params", phase["validated_params"])

    lines.append("")
    emit_help(lines, [
        "Run `ui_plan.py step show <step-id>` for a step's full detail",
        "Run `ui_plan.py step start <step-id>` to mark work started",
    ])
    print("\n".join(lines))


def render_next(data, full, as_json):
    phase, step, blocked = find_next(data)
    if step is None:
        if as_json:
            print(json.dumps({"next": None, "blocked_phases": blocked}, indent=2))
            return
        if blocked:
            print(f"next: nothing actionable -- remaining phases blocked on {', '.join(blocked)}")
        else:
            print("next: nothing -- all 6 phases complete")
        return
    render_step_detail(phase, step, full, as_json)


def render_step_detail(phase, step, full, as_json):
    if as_json:
        print(json.dumps({"phase": phase["id"], "phase_title": phase["title"], **step}, indent=2))
        return

    detail, truncated = (step["detail"], False) if full else truncate(step["detail"])
    lines = ["step:"]
    emit_kv(lines, "id", step["id"], 1)
    emit_kv(lines, "phase", f'{phase["id"]} ({phase["title"]})', 1)
    emit_kv(lines, "title", step["title"], 1)
    emit_kv(lines, "status", step["status"], 1)
    if truncated:
        lines.append(f"  detail: {detail}...")
        lines.append(f"  detail_truncated: {len(step['detail'])} chars total, run with --full to see all")
    else:
        lines.append(f"  detail: {detail}")
    lines.append("")
    emit_help(lines, [
        f'Run `ui_plan.py step start {step["id"]}` to mark it in progress',
        f'Run `ui_plan.py step done {step["id"]}` to mark it complete',
    ])
    print("\n".join(lines))


def render_step_show(data, step_id, full, as_json):
    phase, step = find_step(data, step_id)
    if step is None:
        fail(f'no step "{step_id}"', ["run `ui_plan.py list` then `ui_plan.py show <phase-id>` to find a valid step id"], code=1)
    render_step_detail(phase, step, full, as_json)


def cmd_step_start(data, step_id, as_json):
    phase, step = find_step(data, step_id)
    if step is None:
        fail(f'no step "{step_id}"', ["run `ui_plan.py show <phase-id>` to list a phase's step ids"], code=1)

    if step["status"] == "in_progress":
        msg = f"step: {step_id} already in_progress (no-op)"
        print(json.dumps({"step": step_id, "status": "in_progress", "changed": False}, indent=2) if as_json else msg)
        return

    was = step["status"]
    step["status"] = "in_progress"
    save_data(data)
    note = (
        f'Phase {step_id}: reopened (was done) -- {step["title"]}' if was == "done"
        else f'Phase {step_id}: started -- {step["title"]}'
    )
    append_progress_line(note)

    if as_json:
        print(json.dumps({"step": step_id, "status": "in_progress", "changed": True, "was": was}, indent=2))
        return
    print(f'step: {step_id} -> in_progress' + (" (reopened, was done)" if was == "done" else ""))
    print(f'help: Run `ui_plan.py step done {step_id}` when finished')


def cmd_step_done(data, step_id, as_json):
    phase, step = find_step(data, step_id)
    if step is None:
        fail(f'no step "{step_id}"', ["run `ui_plan.py show <phase-id>` to list a phase's step ids"], code=1)

    if step["status"] == "done":
        msg = f"step: {step_id} already done (no-op)"
        print(json.dumps({"step": step_id, "status": "done", "changed": False}, indent=2) if as_json else msg)
        return

    step["status"] = "done"
    save_data(data)
    append_progress_line(f'Phase {step_id}: complete -- {step["title"]}')

    if as_json:
        print(json.dumps({"step": step_id, "status": "done", "changed": True}, indent=2))
        return
    print(f"step: {step_id} -> done")
    print("help: Run `ui_plan.py next` to see what's next")


# ---------------------------------------------------------------- help text

TOP_HELP = f"""ui_plan.py -- {DESCRIPTION}

Usage:
  ui_plan.py                        show current status (default view)
  ui_plan.py list                   list all phases with progress
  ui_plan.py show <phase-id>        full detail for one phase
  ui_plan.py next                   the next actionable step, in dependency order
  ui_plan.py step show <step-id>    full detail for one step
  ui_plan.py step start <step-id>   mark a step in_progress (idempotent)
  ui_plan.py step done <step-id>    mark a step done (idempotent)

Global flags:
  --json       raw JSON instead of TOON-formatted text
  --full       don't truncate long text fields (show, next, step show)
  --help, -h   this message, or a command's own help
  --version, -v, -V   print version and exit

Examples:
  ui_plan.py show 1
  ui_plan.py step start 1.1
  ui_plan.py next --json
"""

COMMAND_HELP = {
    "list": "ui_plan.py list [--json]\n\nList all phases with id/title/status/progress.\n",
    "show": "ui_plan.py show <phase-id> [--full] [--json]\n\nFull detail for one phase: files, summary, steps, and (phase 0 only) validated_params.\n",
    "next": "ui_plan.py next [--full] [--json]\n\nThe first pending/in_progress step whose phase's dependencies are all done.\n",
    "step": (
        "ui_plan.py step show <step-id> [--full] [--json]\n"
        "ui_plan.py step start <step-id> [--json]\n"
        "ui_plan.py step done <step-id> [--json]\n\n"
        "Inspect or mutate one step. start/done are idempotent -- re-running a no-op exits 0.\n"
    ),
}


# ---------------------------------------------------------------- main

def main(argv):
    if "--json" in argv:
        as_json = True
        argv = [a for a in argv if a != "--json"]
    else:
        as_json = False
    full = "--full" in argv
    argv = [a for a in argv if a != "--full"]

    if not argv:
        if as_json or full:
            pass  # harmless on the home view
        render_home(load_data(), as_json)
        return 0

    if argv[0] in ("--help", "-h"):
        print(TOP_HELP)
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd not in TOP_COMMANDS:
        fail(f'unknown command "{cmd}"', [f"valid commands: {', '.join(TOP_COMMANDS)}", "run `ui_plan.py --help` for details"])

    if "--help" in rest or "-h" in rest:
        print(COMMAND_HELP[cmd])
        return 0

    data = load_data()

    if cmd == "list":
        validate_flags("list", rest, [])
        render_list(data, as_json)
        return 0

    if cmd == "show":
        validate_flags("show", rest, ["--full"])
        positional = [a for a in rest if not a.startswith("-")]
        if not positional:
            fail("show requires a <phase-id>", ["ui_plan.py show <phase-id>", "ui_plan.py list -- to see valid ids"])
        render_show(data, positional[0], full, as_json)
        return 0

    if cmd == "next":
        validate_flags("next", rest, ["--full"])
        render_next(data, full, as_json)
        return 0

    if cmd == "step":
        if not rest:
            fail("step requires a subcommand", ["valid subcommands: show, start, done"])
        sub, sub_rest = rest[0], rest[1:]
        if sub not in ("show", "start", "done"):
            fail(f'unknown step subcommand "{sub}"', ["valid subcommands: show, start, done"])
        allowed = ["--full"] if sub == "show" else []
        validate_flags(f"step {sub}", sub_rest, allowed)
        positional = [a for a in sub_rest if not a.startswith("-")]
        if not positional:
            fail(f"step {sub} requires a <step-id>", [f"ui_plan.py step {sub} <step-id>"])
        step_id = positional[0]
        if sub == "show":
            render_step_show(data, step_id, full, as_json)
        elif sub == "start":
            cmd_step_start(data, step_id, as_json)
        elif sub == "done":
            cmd_step_done(data, step_id, as_json)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
