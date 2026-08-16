#!/usr/bin/env python3
"""A′-4c — source-level ratchet for writers of the legacy compatibility projection."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
LINKER = ROOT / "scripts/ci/capability_linker.py"
RUNTIME_APPLY = ROOT / "scripts/ci/runtime_verification_apply.py"


def _assigned_literal_fields(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = set()

    def targets(node):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            return node.targets if isinstance(node, ast.Assign) else [node.target]
        return []

    for node in ast.walk(tree):
        for target in targets(node):
            for sub in ast.walk(target):
                if (
                    isinstance(sub, ast.Subscript)
                    and isinstance(sub.slice, ast.Constant)
                    and isinstance(sub.slice.value, str)
                ):
                    out.add(sub.slice.value)
    return out


def inspect(root: Path = ROOT) -> list[str]:
    policy = json.loads((root / POLICY.relative_to(ROOT)).read_text(encoding="utf-8"))
    canonical = {
        k
        for k, v in policy["field_authority"].items()
        if isinstance(v, dict)
        and v.get("authority") == "canonical_capability_definition"
        and "." not in k
    }
    linker = _assigned_literal_fields(root / LINKER.relative_to(ROOT))
    runtime = _assigned_literal_fields(root / RUNTIME_APPLY.relative_to(ROOT))
    findings = []
    for f in sorted(canonical & linker):
        findings.append(f"capability_linker:unauthorized_canonical_write:{f}")
    # certification authority is deliberately not runtime verification.
    if "production_certified" in runtime:
        findings.append(
            "runtime_verification_apply:unauthorized_certification_write:production_certified"
        )
    required = {
        "services",
        "apis",
        "tests",
        "ui_consumers",
        "mobile_consumers",
        "confidence",
        "rationale",
    }
    for f in sorted(required - linker):
        findings.append(f"capability_linker:missing_traceability_writer:{f}")
    if "runtime_verified" not in runtime:
        findings.append("runtime_verification_apply:missing_runtime_verified_writer")
    return findings


def main() -> int:
    findings = inspect()
    if findings:
        print("capability_writer_authority: FAIL")
        [print(" ", x) for x in findings]
        return 1
    print("capability_writer_authority_ok unauthorized=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
