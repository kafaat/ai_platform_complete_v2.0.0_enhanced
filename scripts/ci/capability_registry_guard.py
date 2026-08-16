#!/usr/bin/env python3
"""Validate the canonical SAHOOL capability registry and generate governance outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

try:
    from capability_authority_view import load_authoritative_capabilities
except ModuleNotFoundError:  # pragma: no cover
    from scripts.ci.capability_authority_view import load_authoritative_capabilities

ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "capabilities/generated"


def load_registry() -> dict:
    """Compatibility-shaped view resolved field-by-field from declared authorities."""
    return {"schema_version": "1.0.0", "capabilities": load_authoritative_capabilities(ROOT)}


def _file_exists(pointer: str) -> bool:
    # URLs and explicit runtime identifiers are not repository paths.
    return (
        pointer.startswith(("http://", "https://", "metric:", "trace:", "receipt:", "audit:"))
        or (ROOT / pointer).exists()
    )


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        return errors + ["capabilities must be a list"]
    ids = [c.get("id") for c in caps]
    duplicates = [i for i, n in Counter(ids).items() if n > 1]
    if duplicates:
        errors.append(f"duplicate capability ids: {duplicates}")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    for cap in caps:
        cid = cap.get("id", "<missing>")
        maturity = cap.get("maturity")
        evidence_level = cap.get("evidence_level")
        if not isinstance(maturity, int) or not 0 <= maturity <= 5:
            errors.append(f"{cid}: maturity must be 0..5")
        if not isinstance(evidence_level, int) or not 0 <= evidence_level <= 5:
            errors.append(f"{cid}: evidence_level must be 0..5")
        if evidence_level > maturity and maturity < 5:
            errors.append(f"{cid}: evidence_level cannot exceed maturity before certification")
        deps = cap.get("dependencies", [])
        graph[cid] = deps
        for dep in deps:
            if dep not in known:
                errors.append(f"{cid}: unknown dependency {dep}")
            if dep == cid:
                errors.append(f"{cid}: self dependency")
        for field in ("services", "tests", "ui_consumers", "mobile_consumers"):
            for path in cap.get(field, []):
                if not _file_exists(path):
                    errors.append(f"{cid}: missing {field} path {path}")
        for ev in cap.get("evidence", []):
            path = ev.get("path", "")
            if ev.get("type") == "repository" and not _file_exists(path):
                errors.append(f"{cid}: missing evidence path {path}")
        if cap.get("production_certified"):
            runtime = cap.get("runtime", {})
            required = ["metrics", "traces", "receipts", "audit_events"]
            empty = [key for key in required if not runtime.get(key)]
            if maturity != 5 or evidence_level != 5 or empty:
                errors.append(
                    f"{cid}: production certification requires maturity=5, evidence_level=5 and runtime evidence; missing={empty}"
                )
        if maturity >= 4 and not cap.get("tests"):
            errors.append(f"{cid}: maturity >=4 requires at least one test path")
    # Cycle detection using Kahn's algorithm.
    indegree = {node: 0 for node in graph}
    reverse: dict[str, list[str]] = defaultdict(list)
    for node, deps in graph.items():
        for dep in deps:
            if dep in graph:
                indegree[node] += 1
                reverse[dep].append(node)
    q = deque([n for n, d in indegree.items() if d == 0])
    seen = 0
    while q:
        node = q.popleft()
        seen += 1
        for nxt in reverse[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                q.append(nxt)
    if seen != len(graph):
        errors.append("capability dependency graph contains a cycle")
    return errors


def generate(data: dict) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    caps = data["capabilities"]
    summary = {
        "schema_version": data["schema_version"],
        "capabilities_total": len(caps),
        "maturity_distribution": dict(sorted(Counter(c["maturity"] for c in caps).items())),
        "evidence_distribution": dict(sorted(Counter(c["evidence_level"] for c in caps).items())),
        "unassigned_owners": sorted(c["id"] for c in caps if c["owner"] == "UNASSIGNED"),
        "production_certified": sorted(c["id"] for c in caps if c["production_certified"]),
        "orphan_capabilities": sorted(
            c["id"]
            for c in caps
            if not c["services"]
            and not c["apis"]
            and not c["ui_consumers"]
            and not c["mobile_consumers"]
        ),
    }
    (GENERATED / "capability_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (GENERATED / "capability_registry.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "title",
                "domain",
                "owner",
                "lifecycle",
                "maturity",
                "evidence_level",
                "status",
                "confidence",
                "production_certified",
                "dependencies",
            ],
        )
        writer.writeheader()
        for c in caps:
            writer.writerow(
                {k: (",".join(c[k]) if k == "dependencies" else c[k]) for k in writer.fieldnames}
            )
    graph = {c["id"]: c["dependencies"] for c in caps}
    (GENERATED / "capability_graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    data = load_registry()
    errors = validate(data)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if args.generate or not args.check:
        generate(data)
    print("capability_registry_guard_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
