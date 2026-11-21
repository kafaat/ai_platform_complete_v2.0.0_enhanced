"""The local lab runs the CI Integration Tests certification steps, and stays in sync.

scripts/lab/run_certification.py reads the restricted-role certification steps from
.github/workflows/ci.yml at run time. These tests fail CI when that reading breaks
(the shared integration step is renamed, a step becomes unrunnable outside Actions),
when a step's pytest call names a file that does not exist or runs without its
*_CERTIFICATION_REQUIRED switch (or the raster step's mandatory JUnit adapter),
or when scripts/lab/README.md and run.sh no longer describe what CI runs.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "scripts" / "lab" / "README.md"
RUN_SH = ROOT / "scripts" / "lab" / "run.sh"
RASTER_STEP = "Exercise raster leases and scene enqueue as the restricted application role"
RASTER_ADAPTER = "scripts.raster_pg.required_cases"

# The steps #1272 left uncovered; a floor, not the whole list (new CI steps run too).
COVERED_FLOOR = (
    "Create restricted application role for RLS certification",
    "IRR-F01 fresh-schema certification",
    "IRR-F01 upgrade certification (Gate U1",
    RASTER_STEP,
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


def _has_required_gate(step: dict, call: str) -> bool:
    if step["name"] == RASTER_STEP:
        tokens = shlex.split(call)
        plugins = {
            plugin for option, plugin in zip(tokens, tokens[1:], strict=False) if option == "-p"
        }
        return RASTER_ADAPTER in plugins and f"no:{RASTER_ADAPTER}" not in plugins
    switches = {
        k: str(v)
        for k, v in (step.get("env") or {}).items()
        if k.endswith("_CERTIFICATION_REQUIRED")
    }
    return bool(switches) and set(switches.values()) == {"1"}


def _test_files(call: str) -> set[str]:
    return {
        token.split("::", 1)[0]
        for token in shlex.split(call)
        if token.startswith(("tests_v9/", "services/")) and token.split("::", 1)[0].endswith(".py")
    }


def test_every_pytest_call_names_existing_files_and_an_enforced_gate() -> None:
    runner = _runner()
    for step in runner.certification_steps(WORKFLOW):
        calls = runner.pytest_calls(step["run"])
        if not calls:
            continue
        for call in calls:
            assert _has_required_gate(step, call), step["name"]
            files = _test_files(call)
            assert files, call
            assert all((ROOT / f).is_file() for f in files), call


@pytest.mark.parametrize(
    ("name", "env", "call"),
    [
        ("legacy step", {}, f"pytest -p {RASTER_ADAPTER} tests_v9/a.py"),
        (RASTER_STEP, {"RASTER_CERTIFICATION_REQUIRED": "1"}, "pytest services/a.py"),
        (RASTER_STEP, {}, f"pytest -p {RASTER_ADAPTER}_optional services/a.py"),
        (RASTER_STEP, {}, f"pytest -p {RASTER_ADAPTER} -p no:{RASTER_ADAPTER} services/a.py"),
        ("legacy step", {"OLD_CERTIFICATION_REQUIRED": "0"}, "pytest tests_v9/a.py"),
    ],
)
def test_raster_adapter_exception_cannot_weaken_other_certification_gates(
    name: str, env: dict, call: str
) -> None:
    assert not _has_required_gate({"name": name, "env": env}, call)


def test_raster_certification_uses_live_files_restricted_role_and_pg15() -> None:
    import yaml

    runner = _runner()
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["integration-tests"][
        "steps"
    ]
    raster = next(
        step for step in runner.certification_steps(WORKFLOW) if step["name"] == RASTER_STEP
    )
    calls = runner.pytest_calls(raster["run"])
    assert len(calls) == 1
    assert _has_required_gate(raster, calls[0])
    assert _test_files(calls[0]) == {
        "services/raster-service/test_raster_batch_postgres_integration.py",
        "services/raster-service/test_single_scene_concurrent_pg.py",
    }
    env = raster["env"]
    dsn = urlsplit(env["RASTER_TEST_DATABASE_URL"])
    assert dsn.username == env["APP_ROLE"] == env["SAHOOL_TEST_PGROLE"] == "sahool_app_test"
    assert dsn.username != env["SAHOOL_TEST_PGOWNER"]
    assert dsn.hostname == env["PGHOST"]
    assert dsn.port == int(env["PGPORT"]) == 5433
    assert dsn.path.removeprefix("/") == env["SAHOOL_TEST_PGDATABASE"] == "sahool_test"
    assert {".", "services/raster-service"} <= set(env["PYTHONPATH"].split(":"))

    # The source of this same job's database must stay PostgreSQL 15; a PG16
    # proof in a different job cannot certify these raster cases for PG15.
    builds = []
    for index, step in enumerate(steps):
        for line in re.sub(r"\\\n\s*", " ", step.get("run", "")).splitlines():
            tokens = shlex.split(line, comments=True)
            if tokens and tokens[0] == "scripts/ci/build_postgis_test_image.sh":
                builds.append((index, tokens))
    assert len(builds) == 1
    build_index, command = builds[0]
    assert command[2] == "15"
    assert build_index < steps.index(raster)


def test_pg16_raster_certification_enforces_cases_role_and_evidence() -> None:
    import argparse

    import yaml

    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"][
        "live-pg-fake-connection-proofs"
    ]["steps"]
    raster_steps = [step for step in steps if step.get("id") == "raster_live_pg16"]
    assert len(raster_steps) == 1, "PG16 must run the mandatory raster certification"
    raster = raster_steps[0]
    assert not raster.get("continue-on-error", False)
    calls = _runner().pytest_calls(raster["run"])
    assert len(calls) == 1
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-p", action="append", default=[])
    parser.add_argument("--raster-pg-major", type=int)
    parser.add_argument("--junitxml")
    options, _ = parser.parse_known_args(shlex.split(calls[0])[1:])
    assert RASTER_ADAPTER in options.p and f"no:{RASTER_ADAPTER}" not in options.p
    assert options.raster_pg_major == 16
    assert options.junitxml
    assert _test_files(calls[0]) == {
        "services/raster-service/test_raster_batch_postgres_integration.py",
        "services/raster-service/test_single_scene_concurrent_pg.py",
    }
    env = raster["env"]
    dsn = urlsplit(env["RASTER_TEST_DATABASE_URL"])
    assert dsn.username == env["SAHOOL_TEST_PGROLE"] == "sahool_app"
    assert dsn.username != env["SAHOOL_TEST_PGOWNER"]
    assert dsn.hostname == env["PGHOST"]
    assert dsn.port == int(env["PGPORT"]) == 5435
    assert dsn.path.removeprefix("/") == env["SAHOOL_TEST_PGDATABASE"] == "sahool"
    uploads = [
        step
        for step in steps
        if step.get("with", {}).get("path") == "${{ runner.temp }}/raster-live-pg16/"
    ]
    assert len(uploads) == 1, "PG16 raster JUnit and evidence must be retained"
    upload = uploads[0]
    assert steps.index(upload) > steps.index(raster)
    assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload["uses"])
    condition = re.sub(r"\s+", "", upload["if"]).replace('"', "'")
    assert condition == "always()&&steps.raster_live_pg16.outcome!='skipped'"
    assert not upload.get("continue-on-error", False)
    assert upload["with"]["if-no-files-found"] == "error"


def test_restricted_role_is_the_ci_app_role() -> None:
    runner = _runner()
    assert runner.restricted_roles(runner.certification_steps(WORKFLOW)) == [
        "irr_f01_writer",
        "sahool_app_test",
    ]


# Tests that once hid behind ``xfail(strict=False)`` naming the closed gap
# AUTH-E2E-UNDER-RESTRICTED-ROLE (audit 2026-11-01 Q5 and its 2026-11-02 follow-up).
# Under the restricted role each failed on a harness bug the marker swallowed; now each
# must run in a certification step as ``sahool_app_test`` with its switch, and carry no xfail.
FORMER_STRICT_FALSE_XFAILS = {
    "tests_v9/test_mfa_hardening_integration_v29_5.py": "MFA_E2E_CERTIFICATION_REQUIRED",
    "tests_v9/test_services_functional.py": "SOIL_FUNCTIONAL_CERTIFICATION_REQUIRED",
}


@pytest.mark.parametrize("test_file,switch", sorted(FORMER_STRICT_FALSE_XFAILS.items()))
def test_former_xfail_runs_for_real_under_the_restricted_role(test_file: str, switch: str) -> None:
    runner = _runner()
    steps = [
        s
        for s in runner.certification_steps(WORKFLOW)
        if any(test_file in call for call in runner.pytest_calls(s["run"]))
    ]
    assert steps, f"no certification step runs {test_file}"
    for step in steps:
        env = {str(k): str(v) for k, v in step["env"].items()}
        assert env.get(switch) == "1", (step["name"], switch)
        assert runner.restricted_roles([step]) == ["sahool_app_test"], step["name"]
    source = (ROOT / test_file).read_text(encoding="utf-8")
    assert "mark.xfail" not in source, f"{test_file} carries an xfail marker again"


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


def test_runner_stops_at_the_coverage_report_steps() -> None:
    import yaml

    runner = _runner()
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["integration-tests"][
        "steps"
    ]
    names = [s.get("name") for s in steps]
    assert runner.COVERAGE_EXPORT_STEP in names
    selected = runner.certification_steps(WORKFLOW)
    tail = steps[names.index(runner.COVERAGE_EXPORT_STEP) :]
    assert all(step not in selected for step in tail)
    assert names.index(selected[-1]["name"]) == names.index(runner.COVERAGE_EXPORT_STEP) - 1


def _raster_upload_step() -> dict:
    import yaml

    runner = _runner()
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["integration-tests"][
        "steps"
    ]
    uploads = [step for step in steps if step.get("name") == runner.RASTER_EVIDENCE_UPLOAD_STEP]
    assert len(uploads) == 1
    return uploads[0]


def test_raster_evidence_is_retained_after_certification_on_success_or_failure() -> None:
    import yaml

    runner = _runner()
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["integration-tests"][
        "steps"
    ]
    upload = _raster_upload_step()
    assert runner._is_raster_evidence_upload(upload)
    boundary = next(
        i for i, step in enumerate(steps) if step.get("name") == runner.COVERAGE_EXPORT_STEP
    )
    raster_index = next(i for i, step in enumerate(steps) if step.get("name") == RASTER_STEP)
    assert raster_index < boundary < steps.index(upload)
    assert upload not in runner.certification_steps(WORKFLOW)
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "${{ runner.temp }}/raster-live-pg/"
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize(
    "change",
    [
        {"run": "pytest services/raster-service/test_single_scene_concurrent_pg.py"},
        {"uses": "actions/checkout@" + "a" * 40},
        {"uses": "actions/upload-artifact@v7"},
        {"if": "success()"},
        {"continue-on-error": True},
        {"env": {"ANY": "value"}},
        {"with": {"path": "${{ github.workspace }}/"}},
    ],
)
def test_raster_upload_exception_cannot_hide_execution_or_unrelated_uploads(
    tmp_path: Path, change: dict
) -> None:
    import yaml

    runner = _runner()
    upload = {**_raster_upload_step(), **change}
    assert not runner._is_raster_evidence_upload(upload)
    workflow = {
        "jobs": {
            "integration-tests": {
                "steps": [
                    {"name": "shared", "run": runner.SHARED_RUN},
                    {"name": "cert", "run": "true"},
                    {"name": runner.COVERAGE_EXPORT_STEP, "run": "python -m coverage xml -o x.xml"},
                    upload,
                ]
            }
        }
    }
    path = tmp_path / "ci.yml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(SystemExit, match="LAB_CI_STEP_UNSUPPORTED"):
        runner.certification_steps(path)


@pytest.mark.parametrize(
    "after",
    [
        {"name": "late certification", "run": "pytest -v -m integration -rs tests_v9/x.py"},
        {"name": "late shell", "run": "echo not a report"},
        {"uses": "actions/upload-artifact@v4", "with": {"path": "x"}},
        {"name": "guarded", "if": "always()", "run": "python -m coverage xml -o x.xml"},
        {"name": "hidden shell", "run": "python -m coverage xml -o x.xml; echo hidden"},
        {"name": "hidden shell", "run": "python -m coverage xml -o x.xml && echo hidden"},
        {"name": "hidden shell", "run": "python -m coverage xml -o x.xml\npython hidden.py"},
        {"name": "hidden shell", "run": "python -m coverage xml -o $(python hidden.py)"},
        {"name": "wrong command", "run": "python -m coverage xml-hidden -o x.xml"},
        {
            "name": "Preserve raster PostgreSQL certification evidence",
            "run": "python -m coverage xml -o x.xml",
        },
    ],
)
def test_runner_refuses_anything_but_reports_after_the_boundary(
    tmp_path: Path, after: dict
) -> None:
    import yaml

    runner = _runner()
    workflow = {
        "jobs": {
            "integration-tests": {
                "steps": [
                    {"name": "shared", "run": "pytest -v -m integration --tb=short"},
                    {"name": "cert", "run": "true"},
                    {"name": runner.COVERAGE_EXPORT_STEP, "run": "python -m coverage xml -o x.xml"},
                    after,
                    {"uses": "codecov/codecov-action@abc", "with": {"files": "x.xml"}},
                ]
            }
        }
    }
    path = tmp_path / "ci.yml"
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    with pytest.raises(SystemExit, match="LAB_CI_STEP_UNSUPPORTED"):
        runner.certification_steps(path)
    workflow["jobs"]["integration-tests"]["steps"].remove(after)
    path.write_text(yaml.safe_dump(workflow), encoding="utf-8")
    assert [s["name"] for s in runner.certification_steps(path)] == ["cert"]
