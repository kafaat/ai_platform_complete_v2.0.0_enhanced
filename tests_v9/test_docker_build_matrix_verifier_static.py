from __future__ import annotations

import py_compile
import sys
from pathlib import Path

import pytest

from scripts.ci import docker_build_matrix_verifier as matrix

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "docker_build_matrix_verifier.py"
CHECKLIST = (
    ROOT / "docs" / "runbooks" / "DOCKER_BUILD_CHECKLIST_CRITICAL_AND_EXTENDED_SERVICES_20260710.md"
)


def test_docker_build_matrix_verifier_compiles() -> None:
    py_compile.compile(str(SCRIPT), doraise=True)


def test_verifier_uses_real_repository_dockerfile_paths() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert '"edge-inference": "services/edge-inference/Dockerfile.arm64"' in src
    assert '"sam2-inference/Dockerfile"' in src or "services/sam2-inference/Dockerfile" in src
    assert "discover_services" in src
    assert 'production_certified": False' in src


def test_verifier_does_not_mark_model_provisioning_verified_from_healthz_only() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    assert "artifact-present strict readiness must be run separately" in src
    assert "cannot be inferred from /healthz" in src


def test_checklist_mentions_extended_services_and_pcert_boundaries() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for service in [
        "raster-service",
        "weather-service",
        "edge-inference",
        "sam2-inference",
        "auth",
        "sahool-platform",
        "odoo-bridge",
    ]:
        assert service in text
    assert "P-CERT-3" in text
    assert "P-CERT-4" in text
    assert "Dockerfile.arm64" in text
    assert "production-certified" in text


@pytest.mark.parametrize(
    ("flags", "expected_exit"),
    [
        (["--skip-compose"], 1),  # Requested Trivy is missing.
        (["--skip-security"], 1),  # Requested Compose file is missing.
        (["--skip-security", "--skip-compose"], 0),
        (["--skip-security", "--skip-compose", "--skip-build"], 1),
    ],
)
def test_requested_matrix_phases_fail_closed(monkeypatch, tmp_path, flags, expected_exit):
    service = "edge-inference"
    monkeypatch.setattr(
        sys,
        "argv",
        ["verifier", "--services", service, "--compose-file", str(tmp_path / "absent.yml"), *flags],
    )
    monkeypatch.setattr(
        matrix,
        "build_service",
        lambda svc: matrix.BuildResult(svc, "Dockerfile", "pass", 1, None, None, None),
    )
    monkeypatch.setattr(
        matrix, "check_required_files", lambda svc: matrix.FileCheckResult(svc, "pass", [])
    )
    monkeypatch.setattr(
        matrix,
        "healthcheck_service",
        lambda svc, port: matrix.HealthResult(svc, "pass", 200, None, 1),
    )

    def missing_trivy(command, **kwargs):
        assert command == ["which", "trivy"]
        return 1, "", ""

    monkeypatch.setattr(matrix, "run_command", missing_trivy)
    assert matrix.main() == expected_exit
