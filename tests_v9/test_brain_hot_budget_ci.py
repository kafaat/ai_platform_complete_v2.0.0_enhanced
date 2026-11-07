"""Keep the historical brain budget guard blocking in the required CI job."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = "scripts/ci/brain_append_only_guard.py"
STEP = "brain-append-only-budget-guard"
BASE_EXPRESSION = (
    "${{ github.event_name == 'pull_request' && "
    "github.event.pull_request.base.sha || github.event.before }}"
)
INVOCATION = f'exec python {GUARD} --base "$BRAIN_BASE_SHA" --head HEAD'


def _workflow() -> dict:
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))


def _guard_step(workflow: dict) -> dict:
    return next(
        step for step in workflow["jobs"]["structural-lint"]["steps"] if step.get("name") == STEP
    )


def _assert_wiring(workflow: dict) -> None:
    # PyYAML's YAML 1.1 reader treats the Actions `on` key as boolean True.
    events = workflow.get("on", workflow.get(True, {}))
    assert "pull_request" in events
    assert "main" in events.get("push", {}).get("branches", [])
    required = json.loads(
        (ROOT / "docs/architecture/required_status_checks_contract.json").read_text(
            encoding="utf-8"
        )
    )["required_contexts"]
    job = workflow["jobs"]["structural-lint"]
    assert job["name"] in required
    assert "if" not in job and not job.get("continue-on-error")
    steps = job["steps"]
    guards = [step for step in steps if step.get("name") == STEP]
    assert len(guards) == 1
    guard = guards[0]
    assert "if" not in guard and not guard.get("continue-on-error")
    assert guard["shell"] == "bash"
    assert " ".join(guard["env"]["BRAIN_BASE_SHA"].split()) == BASE_EXPRESSION
    assert INVOCATION in guard["run"].splitlines()
    assert "${{" not in guard["run"]
    checkouts = [
        step
        for step in steps[: steps.index(guard)]
        if step.get("uses", "").startswith("actions/checkout@")
    ]
    assert checkouts
    checkout = checkouts[-1]
    assert checkout.get("with", {}).get("fetch-depth") == 0
    assert "ref" not in checkout.get("with", {})


def test_historical_brain_budget_guard_is_required_and_uses_event_commits() -> None:
    _assert_wiring(_workflow())


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_guard",
        "shallow_history",
        "nonblocking_step",
        "conditional_step",
        "nonblocking_job",
        "conditional_job",
        "mutable_base",
        "unrequired_name",
        "unmerged_checkout",
        "missing_pr_trigger",
    ],
)
def test_wiring_contract_rejects_a_bypassed_guard(tamper: str) -> None:
    workflow = copy.deepcopy(_workflow())
    job = workflow["jobs"]["structural-lint"]
    guard = _guard_step(workflow)
    checkout = next(step for step in job["steps"] if "uses" in step)
    if tamper == "missing_guard":
        job["steps"].remove(guard)
    elif tamper == "shallow_history":
        checkout["with"]["fetch-depth"] = 1
    elif tamper == "nonblocking_step":
        guard["continue-on-error"] = True
    elif tamper == "conditional_step":
        guard["if"] = "false"
    elif tamper == "nonblocking_job":
        job["continue-on-error"] = True
    elif tamper == "conditional_job":
        job["if"] = "false"
    elif tamper == "mutable_base":
        guard["env"]["BRAIN_BASE_SHA"] = "origin/main"
    elif tamper == "unrequired_name":
        job["name"] = "Advisory brain budget check"
    elif tamper == "unmerged_checkout":
        checkout["with"]["ref"] = "${{ github.event.pull_request.head.sha }}"
    elif tamper == "missing_pr_trigger":
        workflow.get("on", workflow.get(True)).pop("pull_request")
    with pytest.raises(AssertionError):
        _assert_wiring(workflow)


def _run_guard_step(tmp_path: Path, base: str, guard_exit: int = 0):
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    capture = tmp_path / "guard-arguments"
    python = binary_dir / "python"
    python.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$GUARD_CAPTURE"\nexit "$GUARD_EXIT_CODE"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
        "BRAIN_BASE_SHA": base,
        "GUARD_CAPTURE": str(capture),
        "GUARD_EXIT_CODE": str(guard_exit),
    }
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", _guard_step(_workflow())["run"]],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result, capture


@pytest.mark.parametrize("guard_exit", [0, 1, 2])
def test_workflow_passes_commits_and_propagates_guard_failures(
    tmp_path: Path, guard_exit: int
) -> None:
    base = "a" * 40
    result, capture = _run_guard_step(tmp_path, base, guard_exit)
    assert result.returncode == guard_exit, result.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        GUARD,
        "--base",
        base,
        "--head",
        "HEAD",
    ]


@pytest.mark.parametrize("base", ["", "0" * 40, "main", "x" * 40, "a" * 39, "$(printf unsafe)"])
def test_workflow_rejects_missing_zero_and_invalid_base_without_running_guard(
    tmp_path: Path, base: str
) -> None:
    result, capture = _run_guard_step(tmp_path, base)
    assert result.returncode != 0
    assert "nonzero immutable base commit" in result.stdout
    assert not capture.exists()
