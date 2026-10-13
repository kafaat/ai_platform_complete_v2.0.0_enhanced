"""Recovery smoke fails on every requested failed probe, using offline clients."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def environment(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    curl = binary / "curl"
    curl.write_text(
        "#!/bin/bash\nset -eu\n"
        'out=""\nurl=""\nheader=""\nwhile (($#)); do\n'
        ' case "$1" in -o) out="$2"; shift 2;; -H) header="$2"; shift 2;; -w) shift 2;; '
        '-*) shift;; *) url="$1"; shift;; esac\ndone\n'
        'echo "$url" >> "$TEST_REQUESTS"\n'
        'printf "%s\\n" "$header" >> "$TEST_HEADERS"\n'
        'if [[ -n "$out" && "$out" != /dev/null ]]; then printf body > "$out"; fi\n'
        'code=200\nif [[ -n "${FAIL_MATCH:-}" && "$url" == *"$FAIL_MATCH"* ]]; then '
        'code="${FAIL_STATUS:-503}"; fi\nprintf "%s" "$code"\n'
        'if [[ -n "${TRANSPORT_MATCH:-}" && "$url" == *"$TRANSPORT_MATCH"* ]]; then '
        "exit 18; fi\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    psql = binary / "psql"
    psql.write_text('#!/bin/bash\nexit "${PSQL_STATUS:-0}"\n', encoding="utf-8")
    psql.chmod(0o755)
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    env = {
        **os.environ,
        "PATH": f"{binary}:{os.environ['PATH']}",
        "BASE_URL": "https://offline.invalid",
        "TMPDIR": str(temporary),
        "TEST_REQUESTS": str(tmp_path / "requests"),
        "TEST_HEADERS": str(tmp_path / "headers"),
    }
    for variable in (
        "FIELD_ID",
        "SAHOOL_JWT",
        "DATABASE_URL",
        "FAIL_MATCH",
        "FAIL_STATUS",
        "TRANSPORT_MATCH",
    ):
        env.pop(variable, None)
    return env


def run(env):
    result = subprocess.run(
        ["bash", "scripts/recovery/recovery_smoke.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert list(Path(env["TMPDIR"]).iterdir()) == [], "response file must be cleaned"
    return result


def test_baseline_health_checks_succeed_without_claiming_restore(environment):
    result = run(environment)
    assert result.returncode == 0, result.stderr
    assert "not a T7 restore" in result.stdout
    assert len(Path(environment["TEST_REQUESTS"]).read_text(encoding="utf-8").splitlines()) == 4


@pytest.mark.parametrize("status", ["302", "503"])
def test_health_redirect_or_failure_cannot_report_success(environment, status):
    environment.update(FAIL_MATCH="/api/raster/healthz", FAIL_STATUS=status)
    result = run(environment)
    assert result.returncode != 0
    assert "Recovery smoke completed" not in result.stdout


@pytest.mark.parametrize("probe", ["available-dates", "tilejson"])
def test_requested_field_failure_is_fatal(environment, probe):
    environment.update(FIELD_ID="field-1", FAIL_MATCH=probe)
    result = run(environment)
    assert result.returncode != 0
    assert "Recovery smoke completed" not in result.stdout


@pytest.mark.parametrize("status", ["401", "302"])
def test_requested_authenticated_outbox_failure_is_fatal(environment, status):
    environment.update(SAHOOL_JWT="offline-test", FAIL_MATCH="dead-letter", FAIL_STATUS=status)
    result = run(environment)
    assert result.returncode != 0
    assert "Recovery smoke completed" not in result.stdout


def test_outbox_database_failure_is_propagated(environment):
    environment.update(SAHOOL_JWT="offline-test", DATABASE_URL="offline", PSQL_STATUS="7")
    result = run(environment)
    assert result.returncode == 7
    assert "Recovery smoke completed" not in result.stdout


@pytest.mark.parametrize("probe", ["healthz", "dead-letter"])
def test_transport_failure_after_success_headers_is_not_accepted(environment, probe):
    environment.update(SAHOOL_JWT="offline-test", TRANSPORT_MATCH=probe)
    result = run(environment)
    assert result.returncode != 0
    assert "transport error" in result.stderr
    assert "Recovery smoke completed" not in result.stdout


def test_all_requested_checks_pass_but_missing_database_is_explicit(environment):
    environment.update(SAHOOL_JWT="offline-test", FIELD_ID="field-1")
    result = run(environment)
    assert result.returncode == 0, result.stderr
    assert "DB outbox query skipped" in result.stdout
    assert len(Path(environment["TEST_REQUESTS"]).read_text(encoding="utf-8").splitlines()) == 7
    headers = Path(environment["TEST_HEADERS"]).read_text(encoding="utf-8").splitlines()
    assert headers == ["Authorization: Bearer offline-test"] * 7
