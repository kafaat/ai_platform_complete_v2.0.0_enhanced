"""Test four independent coverage uploads and Git-root path preservation."""

from __future__ import annotations

import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import coverage
import pytest
import yaml

from scripts.ci.codecov_coverage_guard import CoveragePathError, validate_report

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
ACTION = "codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5"


def _upload(job):
    steps = [step for step in JOBS[job]["steps"] if step.get("uses") == ACTION]
    assert len(steps) == 1
    return steps[0]["with"]


@pytest.mark.parametrize(
    ("job", "flag", "report"),
    [
        ("unit-tests", "unit-tests", "coverage-unit.xml"),
        ("platform-unit-tests", "platform-unit-tests", "coverage-platform.xml"),
        (
            "decision-service-tests",
            "decision-service-tests",
            "coverage-decision-service.xml",
        ),
        ("integration-tests", "integration-auth", "coverage-integration-auth.xml"),
    ],
)
def test_four_separate_uploads_without_report_autodiscovery(job, flag, report):
    options = _upload(job)
    assert options["files"] == report
    assert options["flags"] == flag
    assert options["disable_search"] is True
    assert options["fail_ci_if_error"] is False


def test_platform_keeps_its_api_and_core_sources():
    commands = [step.get("run", "") for step in JOBS["platform-unit-tests"]["steps"]]
    assert any("--cov=api --cov=core" in text for text in commands)
    assert any(
        "--data-file=services/sahool-platform/.coverage" in text
        and "--include=services/sahool-platform/api/*,services/sahool-platform/core/*" in text
        for text in commands
    )
    assert any("codecov_coverage_guard.py" in text for text in commands)
    assert any("--rcfile=services/sahool-platform/.coveragerc" in text for text in commands)


def test_decision_job_aggregates_existing_real_pg_tests():
    job = JOBS["decision-service-tests"]
    assert "--cov-append" in job["env"]["PYTEST_ADDOPTS"]
    assert "--cov-report=" in job["env"]["PYTEST_ADDOPTS"]
    assert ".coverage.decision-service" in job["env"]["COVERAGE_FILE"]
    assert "--cov-config=" in job["env"]["PYTEST_ADDOPTS"]
    assert "services/decision-service/.coveragerc" in job["env"]["PYTEST_ADDOPTS"]
    commands = [step.get("run", "") for step in job["steps"]]
    assert any('"pytest-cov>=5.0.0"' in text for text in commands)
    assert any("tests/test_ac1_agronomic_context.py" in text for text in commands)
    assert any("tests/test_agronomic_lineage_integrity.py" in text for text in commands)
    assert any("--data-file=.coverage.decision-service" in text for text in commands)
    assert any("--rcfile=services/decision-service/.coveragerc" in text for text in commands)
    assert any("--forbid-prefix services/decision-service/tests" in text for text in commands)


def test_unit_reexport_is_validated_from_repo_root():
    commands = [step.get("run", "") for step in JOBS["unit-tests"]["steps"]]
    assert any("--data-file=.coverage" in command for command in commands)
    assert any("--include=services/*" in command for command in commands)
    assert any("--report coverage-unit.xml" in command for command in commands)


# The live certification steps that drive the real auth app and the real platform app,
# and the coverage source each must collect into the shared live data file.
LIVE_AUTH_COVERAGE = {
    "tests_v9/test_mfa_hardening_integration_v29_5.py": ("--cov=services/auth",),
    "tests_v9/test_auth_admin_tenant_scope_live_pg.py": ("--cov=services/auth",),
    "tests_v9/test_auth_admin_authz_live_pg_redis.py": ("--cov=services/auth",),
    "tests_v9/test_platform_denial_log_scope_live.py": (
        "--cov=services/sahool-platform/api",
        "--cov=services/sahool-platform/core",
    ),
}


@pytest.mark.parametrize("test_file,sources", sorted(LIVE_AUTH_COVERAGE.items()))
def test_live_auth_steps_append_to_one_coverage_file(test_file, sources):
    steps = JOBS["integration-tests"]["steps"]
    selected = [s for s in steps if test_file in (s.get("run") or "")]
    assert len(selected) == 1, test_file
    step = selected[0]
    assert step["env"]["COVERAGE_FILE"] == ".coverage.integration-auth"
    words = step["run"].split()
    assert words[:5] == ["pytest", "-v", "-m", "integration", "-rs"], step["run"]
    assert "--cov-append" in words and "--cov-report=" in words
    assert not any(w.startswith("--cov-fail-under") for w in words), "no floor on live lanes"
    assert set(sources) <= set(words), step["run"]


def test_live_auth_export_is_guarded_after_every_live_step():
    steps = JOBS["integration-tests"]["steps"]
    runs = [s.get("run") or "" for s in steps]
    export = next(i for i, r in enumerate(runs) if "-o coverage-integration-auth.xml" in r)
    guard = next(i for i, r in enumerate(runs) if "--report coverage-integration-auth.xml" in r)
    upload = next(i for i, s in enumerate(steps) if s.get("uses") == ACTION)
    live = [i for i, r in enumerate(runs) if any(f in r for f in LIVE_AUTH_COVERAGE)]
    assert max(live) < export < guard < upload == len(steps) - 1
    assert "--data-file=.coverage.integration-auth" in runs[export]
    assert "--omit=services/auth/tests/*" in runs[export]
    assert "--forbid-prefix services/auth/tests" in runs[guard]
    for required in (
        "services/auth/routers/users.py",
        "services/auth/routers/invitations.py",
        "services/auth/session_tokens.py",
        "services/sahool-platform/api/routers/security_audit.py",
    ):
        assert f"--require-file {required}" in runs[guard]


def test_codecov_waits_for_four_reports_before_notifying():
    options = yaml.safe_load((ROOT / "codecov.yml").read_text(encoding="utf-8"))
    assert options["codecov"]["notify"]["after_n_builds"] == 4
    assert options["comment"]["after_n_builds"] == 4
    assert "coverage" not in options
    assert "ignore" not in options
    assert "fixes" not in options


def test_decision_service_coverage_omits_test_source_only():
    cfg = (ROOT / "services/decision-service/.coveragerc").read_text(encoding="utf-8")
    assert "*/tests/*" in cfg
    assert "*/main.py" not in cfg, "production source must stay measured; only tests are omitted"
    assert "*/persistence.py" not in cfg, (
        "production source must stay measured; only tests are omitted"
    )


def _fake_report(tmp_path, filenames):
    for filename in filenames:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    root = ET.Element("coverage")
    ET.SubElement(ET.SubElement(root, "sources"), "source").text = str(tmp_path)
    classes = ET.SubElement(ET.SubElement(root, "packages"), "classes")
    for filename in filenames:
        node = ET.SubElement(classes, "class", {"filename": filename})
        ET.SubElement(
            ET.SubElement(node, "lines"),
            "line",
            {"number": "1", "hits": "1"},
        )
    report = tmp_path / "report.xml"
    ET.ElementTree(root).write(report)
    return report


def test_unmatched_and_duplicate_paths_fail_closed(tmp_path):
    filename = "services/sahool-platform/api/foo.py"
    report = _fake_report(tmp_path, [filename])
    prefixes = ("services/sahool-platform/api",)
    assert validate_report(report, tmp_path, prefixes, (filename,)) == (1, 1, 1)
    xml = ET.parse(report)
    xml.find(".//class").set("filename", "foo.py")
    xml.write(report)
    with pytest.raises(CoveragePathError, match="out-of-scope"):
        validate_report(report, tmp_path, prefixes, (filename,))
    xml.find(".//class").set("filename", filename)
    ET.SubElement(xml.find(".//classes"), "class", {"filename": filename})
    xml.write(report)
    with pytest.raises(CoveragePathError, match="duplicate"):
        validate_report(report, tmp_path, prefixes, (filename,))


def test_root_export_preserves_same_basenames_in_two_packages(tmp_path):
    paths = (
        "services/sahool-platform/api/same.py",
        "services/sahool-platform/core/same.py",
    )
    for filename in paths:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 7\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    database = tmp_path / "services/sahool-platform/.coverage"
    cov = coverage.Coverage(data_file=str(database))
    cov.start()
    for filename in paths:
        runpy.run_path(str(tmp_path / filename))
    cov.stop()
    cov.save()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "xml",
            "--data-file=services/sahool-platform/.coverage",
            "--include=services/sahool-platform/api/*,services/sahool-platform/core/*",
            "-o",
            "coverage-platform.xml",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert validate_report(
        tmp_path / "coverage-platform.xml",
        tmp_path,
        ("services/sahool-platform/api", "services/sahool-platform/core"),
        paths,
    ) == (2, 2, 2)


def test_forbidden_decision_test_source_is_refused(tmp_path):
    name = "services/decision-service/tests/test_bad.py"
    report = _fake_report(tmp_path, [name])
    with pytest.raises(CoveragePathError, match="forbidden test/source path"):
        validate_report(
            report,
            tmp_path,
            ("services/decision-service",),
            (),
            ("services/decision-service/tests",),
        )


def test_untracked_coverage_path_is_refused(tmp_path):
    name = "services/decision-service/main.py"
    report = _fake_report(tmp_path, [name])
    (tmp_path / name).unlink()
    with pytest.raises(CoveragePathError, match="not tracked source"):
        validate_report(report, tmp_path, ("services/decision-service",), ())
