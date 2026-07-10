from __future__ import annotations

import py_compile
from pathlib import Path

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
