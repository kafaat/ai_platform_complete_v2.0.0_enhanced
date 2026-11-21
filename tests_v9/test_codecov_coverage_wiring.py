"""Test five independent coverage uploads and Git-root path preservation."""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path

import coverage
import pytest
import yaml

from scripts.ci.codecov_coverage_guard import CoveragePathError, validate_report

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
ACTION = "codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5"
RASTER_EVIDENCE_UPLOAD = {
    "name": "Preserve raster PostgreSQL certification evidence",
    "if": "always()",
    "uses": "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9",
    "with": {
        "name": "raster-live-pg-${{ github.run_id }}-${{ github.run_attempt }}",
        "path": "${{ runner.temp }}/raster-live-pg/",
        "if-no-files-found": "error",
        "retention-days": 14,
    },
}


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
        (
            "decision-033-pg16-proof",
            "decision-033-pg16",
            "coverage-decision-033-pg16.xml",
        ),
    ],
)
def test_five_separate_uploads_without_report_autodiscovery(job, flag, report):
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


def test_live_pg16_decision_writers_upload_their_coverage():
    """persistence.py's live writers run only in decision-033-pg16-proof (real PG16).

    Without this upload Codecov sees those lines as unhit, whatever the live job proves.
    """
    steps = JOBS["decision-033-pg16-proof"]["steps"]
    runs = [s.get("run") or "" for s in steps]
    proof = next(i for i, r in enumerate(runs) if "tests/test_migration_033_pg16.py" in r)
    export = next(i for i, r in enumerate(runs) if "-o coverage-decision-033-pg16.xml" in r)
    guard = next(i for i, r in enumerate(runs) if "--report coverage-decision-033-pg16.xml" in r)
    upload = next(i for i, s in enumerate(steps) if s.get("uses") == ACTION)
    assert proof < export < guard < upload
    assert ".coverage.decision-033-pg16" in steps[proof]["env"]["COVERAGE_FILE"]
    words = runs[proof].split()
    assert "--cov-report=" in words
    assert "--cov=${{ github.workspace }}/services/decision-service" in runs[proof]
    assert "services/decision-service/.coveragerc" in runs[proof]
    assert not any(w.startswith("--cov-fail-under") for w in words), "no floor on live lanes"
    assert "--data-file=.coverage.decision-033-pg16" in runs[export]
    assert "--rcfile=services/decision-service/.coveragerc" in runs[export]
    assert "--forbid-prefix services/decision-service/tests" in runs[guard]
    assert "--require-file services/decision-service/persistence.py" in runs[guard]
    assert any('"pytest-cov>=5.0.0"' in r for r in runs)


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


def _live_auth_reporting_positions(steps):
    """Preserve coverage ordering and allow only the exact raster evidence tail."""
    runs = [s.get("run") or "" for s in steps]
    export = next(i for i, r in enumerate(runs) if "-o coverage-integration-auth.xml" in r)
    guard = next(i for i, r in enumerate(runs) if "--report coverage-integration-auth.xml" in r)
    upload = next(i for i, s in enumerate(steps) if s.get("uses") == ACTION)
    live = [i for i, r in enumerate(runs) if _pytest_calls(r)]
    assert max(live) < export < guard < upload, "live < export < guard < Codecov is required"
    assert steps[upload + 1 :] == [RASTER_EVIDENCE_UPLOAD], (
        "only the exact raster evidence upload may follow Codecov"
    )
    return runs, export, guard


def test_live_auth_export_is_guarded_after_every_live_step():
    runs, export, guard = _live_auth_reporting_positions(JOBS["integration-tests"]["steps"])
    assert "--data-file=.coverage.integration-auth" in runs[export], runs[export]
    assert "--include=services/*" in runs[export], "the export must keep every live service"
    assert "--omit=services/auth/tests/*,*/tests/*,*/test_*.py" in runs[export], runs[export]
    words = runs[guard].split()
    prefixes = [words[i + 1] for i, w in enumerate(words) if w == "--prefix"]
    assert prefixes == ["services"], f"live report prefixes: {prefixes}"
    assert "--forbid-prefix services/auth/tests" in runs[guard], runs[guard]
    for required in (
        "services/auth/routers/users.py",
        "services/auth/routers/invitations.py",
        "services/auth/session_tokens.py",
        "services/sahool-platform/api/routers/security_audit.py",
        # Reached only by live certification steps (#1508 read anomaly_store_pg.py at 35%).
        "services/vegetation-analysis-service/anomaly_store_pg.py",
        "services/soil-service/plan_copy_store.py",
    ):
        assert f"--require-file {required}" in runs[guard], required


@pytest.mark.parametrize(
    "change",
    ["missing", "duplicate", "extra-command", "extra-action", "late-pytest", "early-codecov"],
)
def test_live_auth_reporting_rejects_extra_steps_and_reordering(change):
    steps = deepcopy(JOBS["integration-tests"]["steps"])
    expected_error = "only the exact raster evidence upload"
    if change == "missing":
        steps.pop()
    elif change == "duplicate":
        steps.append(deepcopy(steps[-1]))
    elif change == "extra-command":
        steps.append({"name": "Unexpected command", "run": "echo unreviewed"})
    elif change == "extra-action":
        steps.append({"uses": RASTER_EVIDENCE_UPLOAD["uses"]})
    elif change == "late-pytest":
        steps.insert(
            -1, {"name": "Late test", "run": "pytest tests_v9/test_codecov_coverage_wiring.py"}
        )
        expected_error = "live < export < guard < Codecov"
    else:
        upload = next(i for i, step in enumerate(steps) if step.get("uses") == ACTION)
        steps.insert(upload - 1, steps.pop(upload))
        expected_error = "live < export < guard < Codecov"
    with pytest.raises(AssertionError, match=expected_error):
        _live_auth_reporting_positions(steps)


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"name": "Other upload"}, id="different-name"),
        pytest.param({"if": "success()"}, id="conditional-upload"),
        pytest.param({"uses": "actions/upload-artifact@v7"}, id="unpinned-action"),
        pytest.param({"uses": "actions/upload-artifact@" + "0" * 40}, id="different-action-pin"),
        pytest.param({"run": "echo hidden-command"}, id="injected-command"),
        pytest.param({"env": {"UPLOAD_MODE": "changed"}}, id="extra-env"),
        pytest.param({"shell": "bash"}, id="extra-shell"),
        pytest.param({"working-directory": "."}, id="different-working-directory"),
        pytest.param({"continue-on-error": True}, id="ignore-upload-failure"),
    ],
)
def test_live_auth_reporting_rejects_changed_raster_upload_headers(overrides):
    steps = deepcopy(JOBS["integration-tests"]["steps"])
    steps[-1].update(overrides)
    with pytest.raises(AssertionError, match="only the exact raster evidence upload"):
        _live_auth_reporting_positions(steps)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("name", "other-evidence"),
        ("path", "${{ runner.temp }}/"),
        ("if-no-files-found", "warn"),
        ("retention-days", 90),
        ("overwrite", True),
    ],
)
def test_live_auth_reporting_rejects_changed_raster_upload_inputs(key, value):
    steps = deepcopy(JOBS["integration-tests"]["steps"])
    steps[-1]["with"][key] = value
    with pytest.raises(AssertionError, match="only the exact raster evidence upload"):
        _live_auth_reporting_positions(steps)


# CI-LIVE-PG-COVERAGE-UNREPORTED-01: every certification step after the shared integration
# run appends its coverage to the job's one data file. The shared run stays as it is: the lab
# runner (scripts/lab/run_certification.py) matches it verbatim.
SHARED_RUN = "pytest -v -m integration --tb=short"
LIVE_DATA_FILE = ".coverage.integration-auth"
LIVE_RC = "config/coverage-live-integration.rc"


def _pytest_calls(run: str) -> list[str]:
    joined = re.sub(r"\\\n\s*", " ", run)
    return [m.group(0).strip() for m in re.finditer(r"(?<![\w-])pytest\b[^\n]*", joined)]


def live_steps_without_coverage(steps: list[dict]) -> list[str]:
    """Names of certification steps whose pytest calls do not append to the live data file."""
    runs = [(s.get("run") or "").strip() for s in steps]
    shared = runs.index(SHARED_RUN)
    missing = []
    for step in steps[shared + 1 :]:
        calls = _pytest_calls(step.get("run") or "")
        if not calls:
            continue
        env = step.get("env") or {}
        ok = env.get("COVERAGE_FILE") == LIVE_DATA_FILE
        for call in calls:
            words = call.split()
            ok = ok and "--cov-append" in words and "--cov-report=" in words
            ok = ok and any(w.startswith("--cov=") for w in words)
            ok = ok and not any(w.startswith("--cov-fail-under") for w in words)
        if not ok:
            missing.append(step.get("name", "<unnamed>"))
    return missing


def test_every_live_certification_step_appends_to_the_job_coverage():
    steps = JOBS["integration-tests"]["steps"]
    missing = live_steps_without_coverage(steps)
    assert not missing, (
        f"certification steps whose live-only lines Codecov would read as uncovered: {missing}"
    )
    calls = [c for s in steps for c in _pytest_calls(s.get("run") or "")]
    certified = [c for c in calls if c.strip() != SHARED_RUN and "--cov=services " in c + " "]
    assert len(certified) >= 25, f"the service-wide live lane looks empty: {len(certified)}"
    for call in certified:
        assert f"--cov-config={LIVE_RC}" in call, (
            f"{call}: the root .coveragerc omits the soil stores and decision-service, which "
            "only these live steps reach"
        )


def test_live_coverage_config_omits_only_test_code():
    import configparser

    parser = configparser.ConfigParser()
    parser.read(ROOT / LIVE_RC, encoding="utf-8")
    omit = {line.strip() for line in parser["run"]["omit"].splitlines() if line.strip()}
    assert omit == {"*/tests/*", "*/test_*.py"}, f"live lane must omit test code only: {omit}"


def test_live_coverage_check_flags_a_step_without_coverage():
    """Negative control: the checker refuses a certification step with no --cov."""
    steps = [
        {"run": SHARED_RUN},
        {
            "name": "covered",
            "env": {"COVERAGE_FILE": LIVE_DATA_FILE},
            "run": "pytest -v -m integration -rs tests_v9/a.py --cov=services --cov-append "
            "--cov-report=",
        },
        {"name": "bare", "env": {}, "run": "pytest -v -m integration -rs tests_v9/b.py"},
        {
            "name": "wrong-file",
            "env": {"COVERAGE_FILE": ".coverage"},
            "run": "pytest -v -m integration -rs tests_v9/c.py --cov=services --cov-append "
            "--cov-report=",
        },
        {
            "name": "two-calls",
            "env": {"COVERAGE_FILE": LIVE_DATA_FILE},
            "run": "pytest tests_v9/d.py --cov=services --cov-append --cov-report=\n"
            "pytest tests_v9/e.py",
        },
    ]
    assert live_steps_without_coverage(steps) == ["bare", "wrong-file", "two-calls"], (
        "the live-coverage checker missed a step that drops its coverage"
    )


def test_codecov_waits_for_every_report_before_notifying():
    options = yaml.safe_load((ROOT / "codecov.yml").read_text(encoding="utf-8"))
    uploads = sum(
        1
        for job in JOBS.values()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith("codecov/codecov-action@")
    )
    assert uploads == 5
    assert options["codecov"]["notify"]["after_n_builds"] == uploads
    assert options["comment"]["after_n_builds"] == uploads
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
