#!/usr/bin/env python3
"""A′-4c — deny unclassified direct consumers of capabilities/registry/capabilities.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/capability-registry/legacy_access_policy.json"
NEEDLE = "capabilities/registry/capabilities.json"
# Guard itself intentionally does not embed NEEDLE as one literal in discovery candidates.


def discovered(root: Path = ROOT) -> set[str]:
    out = set()
    for p in (root / "scripts/ci").glob("*.py"):
        if p.name == "capability_legacy_access_guard.py":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if NEEDLE in text:
            out.add(p.relative_to(root).as_posix())
    return out


def inspect(root: Path = ROOT) -> list[str]:
    doc = json.loads((root / POLICY.relative_to(ROOT)).read_text(encoding="utf-8"))
    if doc.get("schema") != "sahool.capability-legacy-access/v1" or doc.get("default") != "deny":
        return ["policy:not_fail_closed"]
    entries = doc.get("entries")
    if not isinstance(entries, dict):
        return ["policy:entries_missing"]
    actual = discovered(root)
    allowed = set(entries)
    findings = []
    for p in sorted(actual - allowed):
        findings.append("unclassified_direct_access:" + p)
    for p in sorted(allowed - actual):
        findings.append("stale_access_allowance:" + p)
    for p, role in entries.items():
        if not isinstance(role, str) or not role:
            findings.append("empty_role:" + p)
    return findings


def main() -> int:
    f = inspect()
    if f:
        print("capability_legacy_access: FAIL")
        [print(" ", x) for x in f]
        return 1
    print(f"capability_legacy_access_ok classified={len(discovered())} unclassified=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
