"""Offline contract for the S3 Compose-slice acceptance (no Docker calls here).

The incident freeze forbids running the migrator or any migration, even against a
disposable database; this test keeps the runner unable to start one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/ci/run_s3_compose_slice_acceptance.sh"
SLICE = {
    "sahool-minio",
    "sahool-minio-init",
    "sahool-raster-service",
    "sahool-scout-ingest",
    "sahool-titiler",
}


def _text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_runner_never_names_a_database_or_migration_service():
    text = _text()
    for forbidden in (
        "sahool-migrate",
        "sahool-postgres",
        "SAHOOL_MIGRATE_APPLY",
        "apply_in_compose",
    ):
        assert forbidden not in text, forbidden


def test_every_started_service_is_in_the_slice_and_dependencies_are_not_pulled_in():
    starts = re.findall(r"\bdc\b[^\n]*?\b(up|run)\b([^\n]*)", _text())
    assert starts
    for verb, rest in starts:
        services = [tok for tok in rest.split() if tok.startswith("sahool-")]
        assert services, (verb, rest)
        for service in services:
            assert service in SLICE, service
            if service != "sahool-minio":
                # minio has no dependencies; every other start must not pull the stack in.
                assert "--no-deps" in rest, (verb, rest)


def test_runner_is_fail_closed_and_keeps_secrets_out():
    text = _text()
    for needle in (
        "NOT_RUN_DOCKER_UNAVAILABLE",
        "NOT_RUN_DOCKER_DAEMON_UNAVAILABLE",
        "trap cleanup EXIT INT TERM",
        "down --volumes --remove-orphans",
        "secrets.token_hex",
        "S3_SLICE_BREAK_NOT_OBSERVED",
        "S3_SLICE_SCOPE_NOT_ENFORCED",
        "S3_SLICE_TITILER_REFUSAL_FAILED",
        "S3_SLICE_SCOUT_EXTERNAL_NOT_REFUSED",
        "S3_SLICE_RASTER_EXTERNAL_NOT_REFUSED",
        "S3_SLICE_REFUSAL_ECHOED_INPUT",
        "S3_SLICE_SECRET_IN_EVIDENCE",
        '"tested_sha": sha',
    ):
        assert needle in text, needle


def test_slice_services_exist_with_the_internal_opt_in_defaulting_off():
    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    assert SLICE <= set(services)
    for name in ("sahool-raster-service", "sahool-scout-ingest", "sahool-titiler"):
        env = services[name]["environment"]
        assert env["S3_ALLOW_PLAINTEXT_INTERNAL"] == "${S3_ALLOW_PLAINTEXT_INTERNAL:-false}", name
    assert services["sahool-minio-init"]["depends_on"] == {
        "sahool-minio": {"condition": "service_healthy"}
    }


def test_ci_runs_the_slice_acceptance():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
    steps = [
        (job, step)
        for job in jobs.values()
        for step in job.get("steps", [])
        if "scripts/ci/run_s3_compose_slice_acceptance.sh" in str(step.get("run", ""))
    ]
    assert len(steps) == 1
    job, step = steps[0]
    assert str(job["runs-on"]).startswith("ubuntu-")
    assert "continue-on-error" not in job and "continue-on-error" not in step
