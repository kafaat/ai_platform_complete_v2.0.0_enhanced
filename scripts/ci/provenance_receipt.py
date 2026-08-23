#!/usr/bin/env python3
"""Create/validate the external provenance receipt required by the read-only bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
HEX = re.compile(r"^[0-9a-f]{64}$")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


def validate(
    obj: object, *, expected_bundle_sha: str | None = None, expected_source_sha: str | None = None
) -> list[str]:
    e = []
    if not isinstance(obj, dict):
        return ["receipt_not_object"]
    if obj.get("schema_version") != "1.0":
        e.append("unsupported_receipt_schema")
    if obj.get("verification_result") != "verified":
        e.append("provenance_not_verified")
    if obj.get("verifier") != "github-cli-attestation":
        e.append("untrusted_provenance_verifier")
    if not HEX.fullmatch(str(obj.get("bundle_sha256") or "")):
        e.append("invalid_bundle_sha256")
    if not SHA.fullmatch(str(obj.get("source_sha") or "")):
        e.append("invalid_source_sha")
    for k in (
        "repository",
        "source_ref",
        "signer_workflow",
        "attestation_subject_digest",
        "verification_run_id",
    ):
        if not isinstance(obj.get(k), str) or not obj[k].strip():
            e.append(f"invalid_{k}")
    if expected_bundle_sha and obj.get("bundle_sha256") != expected_bundle_sha:
        e.append("bundle_digest_mismatch")
    if expected_source_sha and obj.get("source_sha") != expected_source_sha:
        e.append("receipt_source_sha_mismatch")
    return e


def main(argv=None):
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", action="store_true")
    g.add_argument("--check", action="store_true")
    p.add_argument("--bundle")
    p.add_argument("--attestation-json")
    p.add_argument("--output")
    p.add_argument("--receipt")
    p.add_argument("--repository")
    p.add_argument("--source-sha")
    p.add_argument("--source-ref")
    p.add_argument("--signer-workflow")
    p.add_argument("--verification-run-id")
    a = p.parse_args(argv)
    if a.create:
        required = [
            a.bundle,
            a.attestation_json,
            a.output,
            a.repository,
            a.source_sha,
            a.source_ref,
            a.signer_workflow,
            a.verification_run_id,
        ]
        if not all(required):
            p.error("--create requires bundle, attestation-json, output and GitHub claims")
        b = Path(a.bundle)
        att = Path(a.attestation_json)
        try:
            data = json.loads(att.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"attestation verification JSON invalid: {ex}", file=sys.stderr)
            return 1
        # gh output must be non-empty JSON. The command exit code is enforced by the workflow.
        if data in ({}, [], None):
            print("attestation verification JSON empty", file=sys.stderr)
            return 1
        subject = sha256(b)
        obj = {
            "schema_version": "1.0",
            "verification_result": "verified",
            "verifier": "github-cli-attestation",
            "bundle_sha256": subject,
            "attestation_subject_digest": "sha256:" + subject,
            "repository": a.repository,
            "source_sha": a.source_sha,
            "source_ref": a.source_ref,
            "signer_workflow": a.signer_workflow,
            "verification_run_id": a.verification_run_id,
            "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "gh_verification_output_sha256": sha256(att),
        }
        errs = validate(obj, expected_bundle_sha=subject, expected_source_sha=a.source_sha)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        out = Path(a.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")
        print(f"provenance_receipt_ok bundle_sha256={subject}")
        return 0
    try:
        obj = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    except Exception as ex:
        print(f"receipt invalid: {ex}", file=sys.stderr)
        return 1
    errs = validate(obj, expected_source_sha=a.source_sha)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    print("provenance_receipt_valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
