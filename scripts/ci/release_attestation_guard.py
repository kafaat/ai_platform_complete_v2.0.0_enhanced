#!/usr/bin/env python3
"""Fail closed when the release artifact attestation workflow is weakened."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release-artifact-attestation.yml"
VERIFY = ROOT / "scripts/release/verify_attested_artifact.sh"


def main() -> int:
    errors: list[str] = []
    if not WORKFLOW.is_file():
        errors.append(f"missing workflow: {WORKFLOW.relative_to(ROOT)}")
        workflow = ""
    else:
        workflow = WORKFLOW.read_text(encoding="utf-8")

    required_tokens = {
        "contents: read": "read-only repository permission",
        "id-token: write": "OIDC permission",
        "attestations: write": "attestation permission",
        "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d": "immutable attestation action",
        "subject-path:": "artifact subject binding",
        "sbom-path: release/SBOM_DEPENDENCIES.cdx.json": "CycloneDX SBOM binding",
        "sha256sum": "artifact checksum",
        "git archive": "commit-bound source archive",
        "scripts/release/scan_release_archive.py": "release archive secret scan",
    }
    for token, purpose in required_tokens.items():
        if token not in workflow:
            errors.append(f"workflow missing {purpose}: {token}")
    if workflow.count("uses: actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d") < 2:
        errors.append("workflow must create both provenance and SBOM attestations")
    forbidden = ("permissions: write-all", "pull_request_target:", "continue-on-error: true")
    for token in forbidden:
        if token in workflow:
            errors.append(f"unsafe workflow token: {token}")

    if not VERIFY.is_file():
        errors.append(f"missing verifier: {VERIFY.relative_to(ROOT)}")
    else:
        verifier = VERIFY.read_text(encoding="utf-8")
        for token in ("sha256sum -c", "gh attestation verify", "--repo"):
            if token not in verifier:
                errors.append(f"verifier missing fail-closed check: {token}")

    if errors:
        print("release attestation guard: FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("release attestation guard: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
