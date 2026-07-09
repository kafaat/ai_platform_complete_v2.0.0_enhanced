import subprocess
import sys


def _run(*paths):
    return subprocess.run(
        [sys.executable, "scripts/ci/no_report_only_change_guard.py", *paths],
        text=True,
        capture_output=True,
    )


def test_report_only_change_is_blocked():
    result = _run("FOO_REPORT_20260709.md", "route_inventory.generated.json")
    assert result.returncode != 0
    assert "report-only" in result.stderr


def test_report_with_guard_change_is_allowed():
    result = _run("FOO_REPORT_20260709.md", "scripts/ci/example_guard.py")
    assert result.returncode == 0, result.stderr


def test_runbook_only_is_substantive_for_certification_path():
    result = _run("docs/runbooks/PRODUCTION_EVIDENCE_PACK.md")
    assert result.returncode == 0, result.stderr
