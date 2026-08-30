from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/runtime_image_supply_chain_guard.py"
RUNTIME = ROOT / ".github/workflows/runtime-image-provenance.yml"
MATRIX = ROOT / ".github/workflows/docker-build-matrix-verifier.yml"
INSTALLER = ROOT / "scripts/ci/install_pinned_trivy.sh"
pytestmark = pytest.mark.unit


def _module():
    spec = importlib.util.spec_from_file_location("runtime_image_supply_chain_guard", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources() -> tuple[str, str, str]:
    return (
        RUNTIME.read_text(encoding="utf-8"),
        MATRIX.read_text(encoding="utf-8"),
        INSTALLER.read_text(encoding="utf-8"),
    )


def test_current_runtime_image_supply_chain_is_guarded() -> None:
    runtime, matrix, installer = _sources()
    assert _module().evaluate(runtime, matrix, installer) == []


@pytest.mark.parametrize(
    ("target", "find", "replace", "expected"),
    [
        ("runtime", "provenance: mode=max", "provenance: false", "provenance"),
        ("runtime", "sbom: true", "sbom: false", "SBOM"),
        (
            "runtime",
            "--severity HIGH,CRITICAL --exit-code 1",
            "--severity HIGH,CRITICAL --exit-code 0",
            "Trivy",
        ),
        (
            "runtime",
            "--predicate-type https://cyclonedx.org/bom",
            "--predicate-type https://example.invalid/bom",
            "CycloneDX predicate",
        ),
        (
            "runtime",
            "permissions:\n  contents: read",
            "permissions:\n  contents: read\n  id-token: write",
            "top-level permissions",
        ),
        (
            "matrix",
            'case "$INPUT_MODE"',
            'case "${{ github.event.inputs.mode }}"',
            "direct template input expansion",
        ),
        (
            "installer",
            "2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a",
            "0" * 64,
            "pinned Trivy installer",
        ),
    ],
)
def test_security_mutations_are_killed(target: str, find: str, replace: str, expected: str) -> None:
    runtime, matrix, installer = _sources()
    values = {"runtime": runtime, "matrix": matrix, "installer": installer}
    assert find in values[target], f"mutation anchor drifted: {find}"
    values[target] = values[target].replace(find, replace, 1)
    errors = _module().evaluate(values["runtime"], values["matrix"], values["installer"])
    assert any(expected in error for error in errors), errors
