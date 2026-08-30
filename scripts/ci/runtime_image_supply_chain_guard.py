#!/usr/bin/env python3
"""Fail closed when runtime-image build, scan, SBOM, or attestation controls drift."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_WORKFLOW = ROOT / ".github/workflows/runtime-image-provenance.yml"
MATRIX_WORKFLOW = ROOT / ".github/workflows/docker-build-matrix-verifier.yml"
TRIVY_INSTALLER = ROOT / "scripts/ci/install_pinned_trivy.sh"

ATTEST_PIN = "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
BUILD_PIN = "docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a"
TRIVY_VERSION = "0.74.0"
TRIVY_ARCHIVE_SHA256 = "2ae6fe3ee734b7fdf11335663e18c75ea12dccc76062f09f164a3b0f8be4371a"


def _workflow(text: str, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{label}: invalid YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label}: workflow must be a mapping")
    return value


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    value = job.get("steps")
    return [step for step in value if isinstance(step, dict)] if isinstance(value, list) else []


def _run_blocks(workflow: dict[str, Any]) -> list[str]:
    blocks: list[str] = []
    jobs = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return blocks
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in _steps(job):
            if isinstance(step.get("run"), str):
                blocks.append(step["run"])
    return blocks


def evaluate(runtime_text: str, matrix_text: str, installer_text: str) -> list[str]:
    errors: list[str] = []
    try:
        runtime = _workflow(runtime_text, "runtime image workflow")
        matrix = _workflow(matrix_text, "docker matrix workflow")
    except ValueError as exc:
        return [str(exc)]

    if runtime.get("permissions") != {"contents": "read"}:
        errors.append("runtime workflow top-level permissions must be contents:read only")

    jobs = runtime.get("jobs") or {}
    build = jobs.get("build-and-attest") if isinstance(jobs, dict) else None
    publish = jobs.get("publish-manifest") if isinstance(jobs, dict) else None
    if not isinstance(build, dict) or not isinstance(publish, dict):
        return errors + ["runtime workflow jobs are missing"]

    if build.get("permissions") != {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }:
        errors.append("build job permissions are not least-privilege and explicit")
    if publish.get("permissions") != {"contents": "read", "actions": "read"}:
        errors.append("publish job permissions must remain read-only")

    steps = _steps(build)
    checkouts = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    if (
        len(checkouts) != 1
        or (checkouts[0].get("with") or {}).get("persist-credentials") is not False
    ):
        errors.append("build checkout must disable persisted credentials")

    build_steps = [step for step in steps if step.get("uses") == BUILD_PIN]
    if len(build_steps) != 1:
        errors.append("exactly one pinned Docker build step is required")
    else:
        config = build_steps[0].get("with") or {}
        if config.get("push") is not True:
            errors.append("runtime image must be pushed before digest verification")
        if config.get("provenance") != "mode=max":
            errors.append("BuildKit provenance must be explicit mode=max")
        if config.get("sbom") is not True:
            errors.append("BuildKit SBOM attestation must be enabled")
        if "@${{ steps.build.outputs.digest }}" in str(config.get("tags", "")):
            errors.append("build tags must not pretend to be digest references")

    attest_steps = [step for step in steps if step.get("uses") == ATTEST_PIN]
    if len(attest_steps) != 2:
        errors.append("exactly two pinned attest steps are required: provenance and SBOM")
    else:
        for step in attest_steps:
            config = step.get("with") or {}
            if config.get("subject-digest") != "${{ steps.build.outputs.digest }}":
                errors.append("every attestation must bind the exact build digest")
            if config.get("push-to-registry") is not True:
                errors.append("every OCI attestation must be pushed to the registry")
        if sum("sbom-path" in (step.get("with") or {}) for step in attest_steps) != 1:
            errors.append("exactly one image attestation must bind the CycloneDX SBOM")

    runtime_runs = "\n".join(_run_blocks(runtime))
    for token, message in (
        ("--severity HIGH,CRITICAL --exit-code 1", "Trivy must fail on HIGH/CRITICAL findings"),
        (
            "os.environ['IMAGE_NAME']+'@'+digest",
            "manifest image reference must be assembled from a digest",
        ),
        (
            'gh attestation verify "oci://${IMAGE_REF}"',
            "OCI attestations must be verified by digest",
        ),
        (
            "--predicate-type https://slsa.dev/provenance/v1",
            "SLSA provenance predicate must be verified",
        ),
        ("--predicate-type https://cyclonedx.org/bom", "CycloneDX predicate must be verified"),
        ("scripts/ci/install_pinned_trivy.sh", "the pinned Trivy installer must be used"),
        (
            "scripts/ci/install_pinned_gh_attestation_cli.sh",
            "the pinned GitHub attestation verifier must be used",
        ),
    ):
        if token not in runtime_text and token not in runtime_runs:
            errors.append(message)
    for field in (
        "vulnerability_scan_sha256",
        "sbom_cdx_sha256",
        "provenance_verification_sha256",
        "sbom_verification_sha256",
    ):
        if field not in runtime_text:
            errors.append(f"runtime manifest evidence binding missing: {field}")
    if "provenance: false" in runtime_text:
        errors.append("provenance must never be disabled")
    if "${{ inputs." in runtime_runs or "${{ github.event.inputs." in runtime_runs:
        errors.append("untrusted workflow inputs must enter shell only through env")

    matrix_runs = "\n".join(_run_blocks(matrix))
    if "${{ inputs." in matrix_runs or "${{ github.event.inputs." in matrix_runs:
        errors.append("docker matrix shell has direct template input expansion")
    for token in ('case "$INPUT_MODE"', 'case "$SKIP_SECURITY"', '"${security_args[@]}"'):
        if token not in matrix_runs:
            errors.append(f"docker matrix input allow-list/array guard missing: {token}")

    for token in (
        f'VERSION="{TRIVY_VERSION}"',
        f'EXPECTED="{TRIVY_ARCHIVE_SHA256}"',
        "sha256sum --check --strict -",
        "curl --fail --silent --show-error --location --retry 3 --retry-all-errors",
    ):
        if token not in installer_text:
            errors.append(f"pinned Trivy installer control missing: {token}")

    return errors


def main() -> int:
    errors = evaluate(
        RUNTIME_WORKFLOW.read_text(encoding="utf-8"),
        MATRIX_WORKFLOW.read_text(encoding="utf-8"),
        TRIVY_INSTALLER.read_text(encoding="utf-8"),
    )
    if errors:
        print("runtime_image_supply_chain_guard_failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("runtime_image_supply_chain_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
