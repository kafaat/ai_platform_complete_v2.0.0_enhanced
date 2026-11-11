"""Every ``isolated_runtime`` test file runs, by path, in a workflow that a change to it triggers.

S1 F3 (`OFFICE-20261110:F3` on #1369). ``isolated_runtime`` exists for files that need a
dependency the shared unit layer cannot hold (``test_realtime_webhooks.py`` needs the LiveKit
SDK, which pins PyJWT 2.15.1 against the unit layer's 2.15.0). ``-m unit`` deselects such a
file, so the marker alone would make it run nowhere: the dormancy the marker guard and the
dependency-dormancy guard exist to prevent, reached by a third road. This check makes the
marker a promise that names its gate:

* a pytest step in some workflow names the file (literally or by a glob that matches it);
* that workflow runs on ``pull_request`` with no ``paths`` filter, or with one that matches
  the file, so editing the file triggers the run.

The check reads the workflows with ``yaml`` and the markers with ``ast``; it runs nothing.
"""

from __future__ import annotations

import ast
import shlex
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
MARKER = "isolated_runtime"


def _module_marks(source: str) -> set[str]:
    marks: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            for sub in ast.walk(node.value):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Attribute)
                    and sub.value.attr == "mark"
                ):
                    marks.add(sub.attr)
    return marks


def isolated_files() -> list[str]:
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "tests_v9"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.split()
    return sorted(
        rel
        for rel in tracked
        if Path(rel).name.startswith("test_")
        and rel.endswith(".py")
        and MARKER in _module_marks((ROOT / rel).read_text(encoding="utf-8"))
    )


def _pull_request_paths(document: dict) -> list[str] | None:
    """``None`` when the workflow does not run on pull_request; ``[]`` when it runs on all."""
    triggers = document.get("on", document.get(True))  # PyYAML reads a bare `on:` as True
    if isinstance(triggers, str):
        triggers = {triggers: None}
    if isinstance(triggers, list):
        triggers = {name: None for name in triggers}
    if not isinstance(triggers, dict) or "pull_request" not in triggers:
        return None
    config = triggers.get("pull_request") or {}
    return list(config.get("paths") or [])


def gates_for(rel: str, workflows: dict[str, dict]) -> list[str]:
    """Workflow:job pairs that run ``rel`` by path on a pull request changing it."""
    found: list[str] = []
    for name, document in sorted(workflows.items()):
        paths = _pull_request_paths(document)
        if paths is None or (paths and not any(fnmatchcase(rel, p) for p in paths)):
            continue
        for job_name, job in (document.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                run = step.get("run")
                if not isinstance(run, str) or "pytest" not in run:
                    continue
                try:
                    tokens = shlex.split(run.replace("\\\n", " "))
                except ValueError:
                    tokens = run.split()
                if any(token == rel or fnmatchcase(rel, token) for token in tokens):
                    found.append(f"{name}:{job_name}")
    return found


def _workflows() -> dict[str, dict]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for path in sorted(WORKFLOWS.glob("*.y*ml"))
    }


def test_every_isolated_runtime_file_runs_in_a_gate_that_its_change_triggers():
    workflows = _workflows()
    orphans = [rel for rel in isolated_files() if not gates_for(rel, workflows)]
    assert not orphans, (
        f"`{MARKER}` files that no pull-request workflow runs by path: {orphans}. "
        "`-m unit` deselects them, so without a named gate they run nowhere"
    )


def test_the_realtime_webhook_file_is_isolated_and_gated_by_its_own_workflow():
    """The case that created the marker: still marked, still run where the SDK is mandatory."""
    rel = "tests_v9/test_realtime_webhooks.py"
    assert rel in isolated_files()
    assert "realtime-session.yml:isolated-service" in gates_for(rel, _workflows())


def test_the_check_catches_a_marked_file_no_workflow_names():
    """Without this, the first assertion also passes for a check that finds nothing."""
    workflows = {
        "other.yml": {
            "on": {"pull_request": {"paths": ["tests_v9/test_realtime_*.py"]}},
            "jobs": {"test": {"steps": [{"run": "python -m pytest -q tests_v9/test_other.py"}]}},
        },
        "unfiltered.yml": {
            "on": {"push": {"branches": ["main"]}},
            "jobs": {"t": {"steps": [{"run": "pytest tests_v9/test_realtime_webhooks.py"}]}},
        },
    }
    # Named nowhere on a pull request: the second workflow runs it only on push.
    assert gates_for("tests_v9/test_realtime_webhooks.py", workflows) == []
    # Named by glob in a workflow whose paths filter matches: found.
    workflows["other.yml"]["jobs"]["test"]["steps"][0]["run"] = (
        "python -m pytest -q tests_v9/test_realtime_*.py"
    )
    assert gates_for("tests_v9/test_realtime_webhooks.py", workflows) == ["other.yml:test"]
