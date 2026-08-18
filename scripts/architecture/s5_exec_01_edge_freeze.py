#!/usr/bin/env python3
"""Generate/verify S5-EXEC-01 Decision edge freeze from the canonical dependency graph.

This freezes the *platform migration surface* for the five Decision SoR identities while
retaining decision-service edges as the destination witness set.  edge_class is emitted
here once and downstream consumers must not re-derive it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "dependency_graph.generated.json"
OUT = ROOT / "docs/architecture/s5_exec_01_edge_freeze.json"
IDENTITIES = (
    "recommendation_outcomes",
    "outcome_record",
    "decision_record",
    "dispatch_decisions",
    "online_learning_updates",
)
SELECT_FIELDS = ("from", "relation", "resource", "protocol", "to", "evidence")

# The original v2 receipt fingerprint covered the entire selected graph, including test
# witnesses and decision-service destination edges.  That made a *new end-state test* or a
# new read inside the destination service look like platform migration-surface growth.  Keep
# the historical value for receipt compatibility, but freeze authority on the only surface
# S5 is actually shrinking: sahool-platform runtime READS/WRITES to the five Decision SoR
# identities.  These constants are measured on the same 71108f2e S4/S5 cut and can only move
# through an explicit shrink/adjudication update.
LEGACY_FULL_GRAPH_FREEZE_FINGERPRINT = "34f240e7e3ca33dcdcc3b54dd88e3ce6c9052b4bb540ee3901ad2f3801088c1a"
FROZEN_RUNTIME_MIGRATION_FINGERPRINT = "bb8565c7a42368ee57cb01a3b4ec42dec1d2b5c676425b6b62b45df38d7ef7a7"
FROZEN_RUNTIME_WRITER_FINGERPRINT = "c6820171e88b4f785d49f88023828bc59fd32a5b260a42d52a1f0d952376786a"
FROZEN_RUNTIME_COUNTS = {"total": 31, "reads": 25, "writes": 6}
NON_MIGRATION_WITNESS_FLOOR = {"test_witness_total": 19, "decision_service_total": 24}


def _norm_evidence(value: Any) -> str:
    return posixpath.normpath(str(value or "").replace("\\", "/"))


def _edge_class(evidence: str) -> str:
    parts = evidence.split("/")
    base = parts[-1] if parts else ""
    return (
        "test_witness"
        if "tests" in parts or "tests_v9" in parts or base.startswith("test_")
        else "runtime"
    )


def _identity(edge: dict[str, Any]) -> str | None:
    resource = str(edge.get("resource", ""))
    to = str(edge.get("to", ""))
    for identity in IDENTITIES:
        if resource == f"db://{identity}" or to == f"db://{identity}":
            return identity
    return None


def selected_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edge in graph.get("edges", []):
        identity = _identity(edge)
        if identity is None or edge.get("relation") not in {"READS", "WRITES"}:
            continue
        item = {field: edge.get(field, "") for field in SELECT_FIELDS}
        item["evidence"] = _norm_evidence(item["evidence"])
        item["edge_class"] = _edge_class(item["evidence"])
        item["identity"] = identity
        out.append(item)
    return out


def fingerprint(edges: list[dict[str, Any]]) -> str:
    rows = [{field: edge.get(field, "") for field in SELECT_FIELDS} for edge in edges]
    rows.sort(key=lambda row: tuple(str(row[field]) for field in SELECT_FIELDS))
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _surface(edges: list[dict[str, Any]], identity: str, edge_class: str, relation: str) -> list[dict[str, Any]]:
    rows = []
    for edge in edges:
        if (
            edge["from"] == "sahool-platform"
            and edge["identity"] == identity
            and edge["edge_class"] == edge_class
            and edge["relation"] == relation
        ):
            rows.append(
                {
                    "resource": edge["resource"],
                    "evidence": edge["evidence"],
                    "protocol": edge["protocol"],
                    "to": edge["to"],
                    "edge_class": edge["edge_class"],
                }
            )
    rows.sort(key=lambda row: (row["evidence"], row["resource"], row["to"]))
    return rows


def build() -> dict[str, Any]:
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    edges = selected_edges(graph)
    platform = [edge for edge in edges if edge["from"] == "sahool-platform"]
    decision = [edge for edge in edges if edge["from"] == "decision-service"]

    def count(items: list[dict[str, Any]], *, relation: str | None = None, cls: str | None = None) -> int:
        return sum(
            1
            for edge in items
            if (relation is None or edge["relation"] == relation)
            and (cls is None or edge["edge_class"] == cls)
        )

    batches: dict[str, Any] = {}
    writers: list[dict[str, Any]] = []
    for identity in IDENTITIES:
        batches[identity] = {
            "runtime": {
                "reads": _surface(platform, identity, "runtime", "READS"),
                "writes": _surface(platform, identity, "runtime", "WRITES"),
            },
            "test_witness": {
                "reads": _surface(platform, identity, "test_witness", "READS"),
                "writes": _surface(platform, identity, "test_witness", "WRITES"),
            },
        }
        runtime_writers = sorted(
            {
                edge["evidence"]
                for edge in platform
                if edge["identity"] == identity
                and edge["edge_class"] == "runtime"
                and edge["relation"] == "WRITES"
            }
        )
        writers.append({"table": identity, "writers": runtime_writers})

    runtime_platform = [edge for edge in platform if edge["edge_class"] == "runtime"]
    runtime_writers = [edge for edge in runtime_platform if edge["relation"] == "WRITES"]
    runtime_counts = {
        "total": count(runtime_platform),
        "reads": count(runtime_platform, relation="READS"),
        "writes": count(runtime_platform, relation="WRITES"),
    }

    return {
        "schema": "sahool.s5-exec-01.edge-freeze/v2",
        "measured_on_tree": "main 71108f2e (S4); regenerate on current tree before each shrink batch",
        "identity_set": list(IDENTITIES),
        "edge_class_rule": (
            "deterministic, emitted by this generator: evidence path normalized (posix); "
            "test_witness iff a path segment is tests|tests_v9 or basename starts with test_; "
            "else runtime. Downstream guards consume edge_class, never re-derive lexically."
        ),
        "fingerprint_algorithm": {
            "select_fields": list(SELECT_FIELDS),
            "normalize": "evidence path posix-normalized",
            "sort": "lexicographic by all selected fields as strings",
            "serialize": 'JSON UTF-8, separators (",",":"), ensure_ascii=false',
            "hash": "sha256(bytes)",
        },
        "counts": {
            "graph_total": count(platform),
            "graph_reads": count(platform, relation="READS"),
            "graph_writes": count(platform, relation="WRITES"),
            "runtime_total": count(platform, cls="runtime"),
            "runtime_reads": count(platform, relation="READS", cls="runtime"),
            "runtime_writes": count(platform, relation="WRITES", cls="runtime"),
            "test_witness_total": count(platform, cls="test_witness"),
            "test_witness_reads": count(platform, relation="READS", cls="test_witness"),
            "test_witness_writes": count(platform, relation="WRITES", cls="test_witness"),
            "decision_service_total": count(decision),
        },
        # Compatibility receipt only: this is the historical full-graph fingerprint from the
        # original freeze.  It is deliberately NOT recomputed when non-migration witnesses grow.
        "edge_fingerprint_sha256": LEGACY_FULL_GRAPH_FREEZE_FINGERPRINT,
        "edge_fingerprint_scope": "historical full selected graph at the original S5-EXEC-01 freeze; compatibility receipt only",
        "observed_edge_fingerprint_sha256": fingerprint(edges),
        "runtime_migration_surface_frozen_sha256": FROZEN_RUNTIME_MIGRATION_FINGERPRINT,
        "runtime_migration_surface_fingerprint_sha256": fingerprint(runtime_platform),
        "runtime_writer_surface_frozen_sha256": FROZEN_RUNTIME_WRITER_FINGERPRINT,
        "runtime_writer_surface_fingerprint_sha256": fingerprint(runtime_writers),
        "runtime_migration_surface_counts": runtime_counts,
        "frozen_runtime_migration_surface_counts": dict(FROZEN_RUNTIME_COUNTS),
        "non_migration_witness_floor": dict(NON_MIGRATION_WITNESS_FLOOR),
        "writer_cutover_set_runtime_only": writers,
        "test_witness_policy": (
            "test witnesses are NOT migration surface; they may grow as end-state protection is "
            "added, but the original witness floor must not shrink merely because legacy SQL disappears."
        ),
        "projection_read_rule": (
            "a legitimate projection read is reclassified in the graph to non-authoritative "
            "projection READ rather than force-deleted; the invariant is authoritative platform reads == 0."
        ),
        "migration_batches": batches,
    }


def invariant_findings(current: dict[str, Any]) -> list[str]:
    """Authority-bearing freeze checks; non-migration witness growth is informational only."""
    findings: list[str] = []
    if current.get("runtime_migration_surface_fingerprint_sha256") != FROZEN_RUNTIME_MIGRATION_FINGERPRINT:
        findings.append("RUNTIME_MIGRATION_SURFACE_FINGERPRINT_DRIFT")
    if current.get("runtime_writer_surface_fingerprint_sha256") != FROZEN_RUNTIME_WRITER_FINGERPRINT:
        findings.append("RUNTIME_WRITER_SURFACE_FINGERPRINT_DRIFT")
    if current.get("runtime_migration_surface_counts") != FROZEN_RUNTIME_COUNTS:
        findings.append("RUNTIME_MIGRATION_SURFACE_COUNT_DRIFT")
    counts = current.get("counts") or {}
    for key, floor in NON_MIGRATION_WITNESS_FLOOR.items():
        if int(counts.get(key, 0)) < floor:
            findings.append(f"NON_MIGRATION_WITNESS_FLOOR_BREACH {key} {counts.get(key, 0)}<{floor}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = build()
    authority_findings = invariant_findings(current)
    if authority_findings:
        print("S5_EXEC_01_RUNTIME_MIGRATION_SURFACE_DRIFT")
        for finding in authority_findings:
            print(f"- {finding}")
        return 1
    rendered = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(rendered, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} legacy_fingerprint={current['edge_fingerprint_sha256']} runtime_fingerprint={current['runtime_migration_surface_fingerprint_sha256']}")
        return 0
    if not OUT.exists():
        print(f"missing freeze artifact: {OUT.relative_to(ROOT)}")
        return 2
    existing = json.loads(OUT.read_text(encoding="utf-8"))
    if existing != current:
        print("S5_EXEC_01_EDGE_FREEZE_DRIFT")
        print(f"expected={existing.get('edge_fingerprint_sha256')} current={current.get('edge_fingerprint_sha256')}")
        print(f"expected_counts={existing.get('counts')} current_counts={current.get('counts')}")
        return 1
    print(f"s5_exec_01_edge_freeze_ok legacy_fingerprint={current['edge_fingerprint_sha256']} runtime_fingerprint={current['runtime_migration_surface_fingerprint_sha256']} counts={current['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
