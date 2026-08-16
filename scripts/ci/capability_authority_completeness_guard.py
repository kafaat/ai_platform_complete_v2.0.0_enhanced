#!/usr/bin/env python3
"""A′-4c — fail closed when a compatibility field has no explicit authority/disposition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
LEGACY = ROOT / "capabilities/registry/capabilities.json"
SCHEMA = "sahool.capability-field-authority/v1"
ALLOWED_AUTHORITIES = {
    "canonical_capability_definition",
    "legacy_registry_projection",
    "repository_traceability_projection",
    "repository_runtime_instrumentation",
    "runtime_verification",
    "certification",
    "composite_runtime_authorities",
    "composite_evidence_authorities",
}


class AuthorityCompletenessError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuthorityCompletenessError(f"not an object: {path}")
    return value


def inspect(root: Path = ROOT) -> tuple[list[str], set[str]]:
    policy = _load(root / POLICY.relative_to(ROOT))
    legacy = _load(root / LEGACY.relative_to(ROOT))
    if policy.get("schema") != SCHEMA:
        raise AuthorityCompletenessError("field authority policy schema mismatch")
    specs = policy.get("field_authority")
    rows = legacy.get("capabilities")
    if not isinstance(specs, dict):
        raise AuthorityCompletenessError("field_authority missing")
    if not isinstance(rows, list) or not rows:
        raise AuthorityCompletenessError("legacy registry has zero capabilities")
    fields = set().union(*(row.keys() for row in rows if isinstance(row, dict)))
    findings = []
    for field in sorted(fields):
        spec = specs.get(field)
        if not isinstance(spec, dict):
            findings.append(f"{field}:unclassified")
            continue
        authority = spec.get("authority")
        if authority not in ALLOWED_AUTHORITIES:
            findings.append(f"{field}:unknown_authority:{authority}")
    # stale historical writer declarations would re-authorize the conflict A′-4b removed.
    for field, spec in specs.items():
        if (
            isinstance(spec, dict)
            and spec.get("authority") == "canonical_capability_definition"
            and spec.get("legacy_writer")
        ):
            findings.append(f"{field}:canonical_field_has_legacy_writer")
    return findings, fields


def main() -> int:
    findings, fields = inspect()
    if findings:
        print("capability_authority_completeness: FAIL")
        for x in findings:
            print(" ", x)
        return 1
    print(f"capability_authority_completeness_ok fields={len(fields)} unclassified=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
