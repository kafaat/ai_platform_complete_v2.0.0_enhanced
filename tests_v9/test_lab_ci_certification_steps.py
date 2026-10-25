"""The local lab runs the CI Integration Tests certification steps, and stays in sync.

scripts/lab/run_certification.py reads the restricted-role certification steps from
.github/workflows/ci.yml at run time. These tests fail CI when that reading breaks
(the shared integration step is renamed, a step becomes unrunnable outside Actions),
when a step's pytest call names a file that does not exist or runs without a
*_CERTIFICATION_REQUIRED switch, or when scripts/lab/README.md and run.sh no longer
describe what CI runs.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "scripts" / "lab" / "README.md"
RUN_SH = ROOT / "scripts" / "lab" / "run.sh"

# The steps #1272 left uncovered; a floor, not the whole list (new CI steps run too).
COVERED_FLOOR = (
    "Create restricted application role for RLS certification",
    "IRR-F01 fresh-schema certification",
    "IRR-F01 upgrade certification (Gate U1",
    "H5.1 field↔source binding certification",
    "RLS tenant isolation certification",
    "Imagery automation RLS certification",
    "D1 raster invalidation queue RLS certification",
)


def _runner():
    spec = importlib.util.spec_from_file_location(
        "lab_run_certification", ROOT / "scripts" / "lab" / "run_certification.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_reads_every_certification_step_from_ci() -> None:
    names = [s["name"] for s in _runner().certification_steps(WORKFLOW)]
    for prefix in COVERED_FLOOR:
        assert any(n.startswith(prefix) for n in names), prefix
    assert names[0] == COVERED_FLOOR[0]


def test_every_pytest_call_names_existing_files_and_a_required_switch() -> None:
    runner = _runner()
    for step in runner.certification_steps(WORKFLOW):
        calls = runner.pytest_calls(step["run"])
        if not calls:
            continue
        switches = {
            k: str(v) for k, v in step["env"].items() if k.endswith("_CERTIFICATION_REQUIRED")
        }
        assert switches and set(switches.values()) == {"1"}, step["name"]
        for call in calls:
            files = re.findall(r"tests_v9/\S+\.py", call)
            assert files, call
            assert all((ROOT / f).is_file() for f in files), call


def test_restricted_role_is_the_ci_app_role() -> None:
    runner = _runner()
    assert runner.restricted_roles(runner.certification_steps(WORKFLOW)) == ["sahool_app_test"]


def test_readme_lists_every_ci_certification_step() -> None:
    readme = README.read_text(encoding="utf-8")
    missing = [
        s["name"] for s in _runner().certification_steps(WORKFLOW) if s["name"] not in readme
    ]
    assert not missing, f"scripts/lab/README.md does not list: {missing}"


def test_run_sh_exports_the_shared_step_switches() -> None:
    import yaml

    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["integration-tests"][
        "steps"
    ]
    shared = next(s for s in steps if (s.get("run") or "").strip() == _runner().SHARED_RUN)
    ci = {k for k in shared["env"] if k.endswith("_CERTIFICATION_REQUIRED")}
    lab = set(re.findall(r"\b(\w+_CERTIFICATION_REQUIRED)=1\b", RUN_SH.read_text(encoding="utf-8")))
    assert ci == lab


@pytest.mark.parametrize(
    "extra",
    [
        {"uses": "actions/checkout@v5"},
        {"env": {"X": "${{ secrets.Y }}"}},
        {"if": "always()"},
    ],
)
def test_runner_refuses_steps_it_cannot_run_as_written(tmp_path: Path, extra: dict) -> None:
    import yaml

    step = {"name": "s", "run": "true", **extra}
    workflow = {
        "jobs": {
            "integration-tests": {
                "steps": [{"name": "shared", "run": "pytest -v -m integration --tb=short"}, step]
            }
        }
    }
    path = tmp_path / "ci.yml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(SystemExit, match="LAB_CI_STEP_UNSUPPORTED"):
        _runner().certification_steps(path)


def test_pytest_calls_join_line_continuations() -> None:
    run = 'pytest -v a.py\nX="$Y" \\\n  pytest -v -rs tests_v9/b.py\n# pytest in a comment\n'
    calls = _runner().pytest_calls(run)
    assert calls[:2] == ["pytest -v a.py", "pytest -v -rs tests_v9/b.py"]
