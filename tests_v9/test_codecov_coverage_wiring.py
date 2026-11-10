"""Test three independent coverage uploads and Git-root path preservation."""

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
JOBS = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
ACTION = "codecov/codecov-action@303a32d7a59b442fa8d48b6a1cc6825c09c847a5"


def _upload(job):
    steps = [step for step in JOBS[job]["steps"] if step.get("uses") == ACTION]
    assert len(steps) == 1
    return steps[0]["with"]


@pytest.mark.parametrize(
    ("job", "flag", "report"),
    [
        ("unit-tests", "unit-tests", "coverage.xml"),
        ("platform-unit-tests", "platform-unit-tests", "coverage-platform.xml"),
        ("decision-service-tests", "decision-service-tests", "coverage-decision-service.xml"),
    ],
)
def test_three_separate_uploads_without_report_autodiscovery(job, flag, report):
    options = _upload(job)
    assert options["files"] == report
    assert options["flags"] == flag
    assert options["disable_search"] is True
    assert options["fail_ci_if_error"] is True


def test_platform_keeps_its_api_and_core_sources():
    commands = [step.get("run", "") for step in JOBS["platform-unit-tests"]["steps"]]
    assert any("--cov=api --cov=core" in text for text in commands)
    assert any(
        "--data-file=services/sahool-platform/.coverage" in text
        and "--include=services/sahool-platform/api/*,services/sahool-platform/core/*" in text
        for text in commands
    )
    assert any("codecov_coverage_guard.py" in text for text in commands)


def test_decision_job_aggregates_existing_real_pg_tests():
    job = JOBS["decision-service-tests"]
    assert "--cov-append" in job["env"]["PYTEST_ADDOPTS"]
    assert "--cov-report=" in job["env"]["PYTEST_ADDOPTS"]
    assert ".coverage.decision-service" in job["env"]["COVERAGE_FILE"]
    commands = [step.get("run", "") for step in job["steps"]]
    assert any('"pytest-cov>=5.0.0"' in text for text in commands)
    assert any("tests/test_ac1_agronomic_context.py" in text for text in commands)
    assert any("tests/test_agronomic_lineage_integrity.py" in text for text in commands)
    assert any("--data-file=.coverage.decision-service" in text for text in commands)


def _fake_report(tmp_path, filenames):
    for filename in filenames:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    root = ET.Element("coverage")
    ET.SubElement(ET.SubElement(root, "sources"), "source").text = str(tmp_path)
    classes = ET.SubElement(ET.SubElement(root, "packages"), "classes")
    for filename in filenames:
        node = ET.SubElement(classes, "class", {"filename": filename})
        ET.SubElement(ET.SubElement(node, "lines"), "line", {"number": "1", "hits": "1"})
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
        path.write_text("value = 7\n")
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
            sys.executable, "-m", "coverage", "xml",
            "--data-file=services/sahool-platform/.coverage",
            "--include=services/sahool-platform/api/*,services/sahool-platform/core/*",
            "-o", "coverage-platform.xml",
        ],
        cwd=tmp_path, check=True, capture_output=True, text=True,
    )
    assert validate_report(
        tmp_path / "coverage-platform.xml",
        tmp_path,
        ("services/sahool-platform/api", "services/sahool-platform/core"),
        paths,
    ) == (2, 2, 2)
