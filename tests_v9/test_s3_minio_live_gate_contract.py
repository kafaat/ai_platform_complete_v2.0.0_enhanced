"""Offline safety contract for the disposable Docker/MinIO/GDAL acceptance gate.

No Docker calls and no service traffic in this test file.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/s3_minio_gdal_live_acceptance.py"
COMPOSE = ROOT / "tests/integration/s3_minio_gdal.compose.yml"
RUNNER = ROOT / "scripts/ci/run_s3_minio_gdal_live.sh"


def _runner_module():
    spec = importlib.util.spec_from_file_location("sahool_s3_live_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("uri", "disposable", "reason"),
    [
        ("http://127.0.0.1:19057", False, "disposable_lab_opt_in_missing"),
        ("https://127.0.0.1:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://localhost:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://sahool-minio.railway.internal:9000", True, "test_endpoint_must_be_exact_loopback"),
        ("http://127.0.0.2:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://127.0.0.1:19057/a/b", True, "test_endpoint_must_be_exact_loopback"),
        ("http://user:pass@127.0.0.1:19057", True, "test_endpoint_must_be_exact_loopback"),
        ("http://127.0.0.1:80", True, "test_endpoint_must_be_exact_loopback"),
    ],
)
def test_acceptance_refuses_unsafe_endpoint_or_missing_optin(uri, disposable, reason):
    with pytest.raises(ValueError, match=reason):
        _runner_module().validate_test_target(uri, disposable)


def test_acceptance_allows_only_explicit_disposable_loopback_endpoint():
    assert _runner_module().validate_test_target("http://127.0.0.1:19057", True) == (
        "127.0.0.1",
        19057,
    )


def test_docker_compose_lab_has_no_data_volumes_or_public_ports():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert len(services) == 1
    service = services["s3-acceptance-minio"]
    assert service["ports"] == ["127.0.0.1:${S3_TEST_HOST_PORT:?set test port}:9000"]
    assert service["tmpfs"] == ["/data:size=128m"]
    assert "volumes" not in service
    assert service["restart"] == "no"
    assert "@sha256:" in service["image"]
    assert "--certs-dir" not in service["command"]
    # No unfounded assumptions about a mandatory MINIO_DISABLE_HTTPS or
    # MINIO_SERVER_URL flag. HTTPS redirects are tested at the API endpoint.
    assert "MINIO_DISABLE_HTTPS" not in service["environment"]
    assert "MINIO_SERVER_URL" not in service["environment"]


def test_orchestrator_records_docker_unavailable_as_not_run():
    text = RUNNER.read_text(encoding="utf-8")
    assert "NOT_RUN_DOCKER_UNAVAILABLE" in text
    assert "NOT_RUN_DOCKER_DAEMON_UNAVAILABLE" in text
    assert "exit 3" in text
    assert "SAHOOL_S3_ACCEPTANCE_DISPOSABLE=1" in text
    assert "docker compose" in text
    assert "trap cleanup EXIT INT TERM" in text
    assert "STATUS" in text and '"200"' in text
    assert "NOT_RUN_UNPINNED_MINIO_IMAGE" in text
    assert "@sha256:[0-9a-f]{64}$" in text
    assert "docker inspect --format" in text
    assert "S3_TEST_IMAGE_ID" in text


def test_ci_runs_the_live_gate_on_a_docker_runner():
    """Un-wiring the gate from CI would turn it back into an unrun promise."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))["jobs"]
    hosts = [
        job
        for job in jobs.values()
        if any(
            "scripts/ci/run_s3_minio_gdal_live.sh" in str(step.get("run", ""))
            for step in job.get("steps", [])
        )
    ]
    assert len(hosts) == 1
    assert str(hosts[0]["runs-on"]).startswith("ubuntu-")
    assert "continue-on-error" not in hosts[0]
    step = next(
        s for s in hosts[0]["steps"] if "run_s3_minio_gdal_live.sh" in str(s.get("run", ""))
    )
    assert "continue-on-error" not in step
