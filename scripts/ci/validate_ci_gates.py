#!/usr/bin/env python3
"""Validate CI/CD quality-gate coverage for the Sahool release.

The checker is dependency-free so it can run in GitHub Actions, local shells,
and minimal release environments. It validates presence and wiring of the
release/security/observability/deployment gates that must block merges and
production deployments.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

REQUIRED_WORKFLOWS = [
    ".github/workflows/sahool-production-gates.yml",
    ".github/workflows/raster-service-gates.yml",
]

REQUIRED_LOCAL_GATES = [
    "scripts/ci/local_quality_gate.sh",
    "scripts/ci/raster_quality_gate.sh",
    "scripts/production_validation_gate.sh",
    "scripts/security_audit.sh",
    "scripts/security/rls_runtime_gate.py",
    "scripts/observability/validate_observability_assets.py",
    "scripts/deploy/validate_helm_readiness.py",
    "scripts/release/validate_release_package.py",
    "scripts/migrations/validate_migration_manifest.py",
    "scripts/security/validate_rls_write_policies.py",
    "scripts/ci/github_actions_policy_guard.py",
]

REQUIRED_WORKFLOW_TOKENS = [
    "production-validation-gate",
    "security-audit",
    "observability-assets",
    "helm-readiness",
    "release-package",
    "python-compile-sweep",
    "pytest-contracts",
    "supply-chain-static-scan",
    "runtime-stack-e2e-chaos",
]

FORBIDDEN_WORKFLOW_PATTERNS = [
    (
        re.compile(r"image:\s*latest\b", re.I),
        "workflow must not pin runner container images to latest",
    ),
    (re.compile(r"continue-on-error:\s*true", re.I), "quality gates must not continue on error"),
    (
        re.compile(r"pull_request_target\s*:", re.I),
        "pull_request_target is not allowed for untrusted CI",
    ),
]

REQUIRED_RELEASE_TOKENS = [
    "scripts/ci/validate_ci_gates.py",
    "scripts/ci/local_quality_gate.sh",
    "scripts/ci/raster_quality_gate.sh",
    "scripts/migrations/validate_migration_manifest.py",
    "scripts/security/validate_rls_write_policies.py",
    ".github/workflows/sahool-production-gates.yml",
    ".github/workflows/raster-service-gates.yml",
]


def _workflow_run_blocks(workflow_text: str) -> list[str]:
    """Extract simple literal ``run: |`` shell blocks from GitHub Actions YAML.

    This intentionally avoids a YAML dependency and catches syntax regressions
    like a broken ``if`` statement that token-based validators miss.
    """
    lines = workflow_text.splitlines()
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*run:\s*\|\s*$", line):
            base_indent = len(line) - len(line.lstrip(" "))
            block_lines: list[str] = []
            i += 1
            while i < len(lines):
                current = lines[i]
                if current.strip() and (len(current) - len(current.lstrip(" "))) <= base_indent:
                    break
                block_lines.append(current)
                i += 1
            blocks.append(textwrap.dedent("\n".join(block_lines)).strip() + "\n")
            continue
        i += 1
    return blocks


def validate_workflow_shell_blocks(workflow_text: str) -> list[str]:
    errors: list[str] = []
    for index, block in enumerate(_workflow_run_blocks(workflow_text), start=1):
        if not block.strip():
            continue
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sh", delete=False) as tmp:
            tmp.write(block)
            tmp_path = Path(tmp.name)
        try:
            result = subprocess.run(
                ["bash", "-n", str(tmp_path)], text=True, capture_output=True, check=False
            )
            if result.returncode != 0:
                errors.append(
                    f"workflow run block #{index} has invalid bash syntax: {result.stderr.strip()}"
                )
        finally:
            tmp_path.unlink(missing_ok=True)
    return errors


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for rel in REQUIRED_LOCAL_GATES + REQUIRED_WORKFLOWS:
        require((root / rel).exists(), f"missing required CI gate asset: {rel}", errors)

    workflow_path = root / ".github/workflows/sahool-production-gates.yml"
    workflow = read(workflow_path) if workflow_path.exists() else ""
    for token in REQUIRED_WORKFLOW_TOKENS:
        require(token in workflow, f"workflow does not wire required job/token: {token}", errors)
    for pattern, message in FORBIDDEN_WORKFLOW_PATTERNS:
        require(not pattern.search(workflow), message, errors)
    errors.extend(validate_workflow_shell_blocks(workflow))
    require(
        "permissions:" in workflow and "contents: read" in workflow,
        "workflow must set read-only contents permissions",
        errors,
    )
    require(
        "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09" in workflow,
        "workflow must use immutable checkout v5 commit",
        errors,
    )
    require(
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow,
        "workflow must use immutable setup-python v6 commit",
        errors,
    )
    for script_call in [
        "bash scripts/production_validation_gate.sh",
        "bash scripts/security_audit.sh",
        "bash scripts/runtime_smoke.sh",
        "bash scripts/e2e/e2e_field_imagery_ai.sh",
        "bash scripts/chaos/run_chaos_tests.sh",
    ]:
        require(
            script_call in workflow,
            f"workflow must invoke {script_call} via bash, not executable bit",
            errors,
        )

    local_gate = root / "scripts/ci/local_quality_gate.sh"
    local_gate_text = read(local_gate) if local_gate.exists() else ""
    for rel in REQUIRED_LOCAL_GATES[1:]:
        require(rel in local_gate_text, f"local gate does not invoke {rel}", errors)
    require("py_compile" in local_gate_text, "local gate must include python compile sweep", errors)
    require(
        "pytest" in local_gate_text, "local gate must include targeted pytest contracts", errors
    )

    release_builder = root / "scripts/release/build_release_bundle.py"
    release_builder_text = read(release_builder) if release_builder.exists() else ""
    for token in REQUIRED_RELEASE_TOKENS:
        require(
            token in release_builder_text,
            f"release builder does not track CI asset: {token}",
            errors,
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = validate(root)
    if errors:
        print("CI/CD gate validation failed:")
        for error in errors:
            print(f" - {error}")
        return 1
    print("CI/CD gate validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
