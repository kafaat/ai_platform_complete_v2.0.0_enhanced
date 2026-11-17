"""Unit tests for scripts/ci/helm_render_guard.py (HELM-RENDER-UNPINNED-RUNNER-BINARY-01)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "helm_render_guard", ROOT / "scripts" / "ci" / "helm_render_guard.py"
)
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)


def _junit(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "helm-render.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_complete_render_run_passes(tmp_path: Path) -> None:
    report = _junit(
        tmp_path,
        '<testsuites><testsuite name="pytest" tests="14" skipped="0" failures="0" errors="0"/>'
        "</testsuites>",
    )
    assert guard.junit_problems(report) == []


def test_a_skipped_render_test_fails_the_guard(tmp_path: Path) -> None:
    report = _junit(tmp_path, '<testsuite name="pytest" tests="14" skipped="1"/>')
    assert guard.junit_problems(report) == ["1 helm_render tests skipped"]


def test_missing_render_tests_fail_the_guard(tmp_path: Path) -> None:
    report = _junit(tmp_path, '<testsuites><testsuite tests="13" skipped="0"/></testsuites>')
    assert guard.junit_problems(report) == ["13 helm_render tests ran, at least 14 expected"]


def test_failures_and_errors_fail_the_guard(tmp_path: Path) -> None:
    report = _junit(tmp_path, '<testsuite tests="14" failures="2" errors="1"/>')
    assert guard.junit_problems(report) == [
        "2 helm_render tests failures",
        "1 helm_render tests errors",
    ]


def test_an_unreadable_report_fails_the_guard(tmp_path: Path) -> None:
    assert guard.junit_problems(tmp_path / "absent.xml")[0].startswith("junit report unreadable")
    report = _junit(tmp_path, "<testsuites/>")
    assert guard.junit_problems(report) == ["junit report has no testsuite"]


def test_the_runner_image_helm_is_refused() -> None:
    assert guard.version_problems("v3.16.4", "v3.16.4+g7877b45\n") == []
    assert guard.version_problems("v3.16.4", "v3.17.0+gabcdef0") == [
        "helm on PATH reports 'v3.17.0+gabcdef0', expected v3.16.4"
    ]
    assert guard.path_problems("/tmp/pinned/helm", None) == ["no helm on PATH"]
    assert guard.path_problems("/tmp/pinned/helm", "/usr/local/bin/helm") == [
        "helm on PATH is /usr/local/bin/helm, not the pinned /tmp/pinned/helm"
    ]


def test_main_reports_every_problem_and_exits_one(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(guard.shutil, "which", lambda _name: None)
    report = _junit(tmp_path, '<testsuite tests="14" skipped="14"/>')
    code = guard.main(["--junit", str(report), "--expected-version", "v3.16.4"])
    out = capsys.readouterr().out
    assert code == 1
    assert "HELM_RENDER_INCOMPLETE: no helm on PATH" in out
    assert "HELM_RENDER_INCOMPLETE: 14 helm_render tests skipped" in out
