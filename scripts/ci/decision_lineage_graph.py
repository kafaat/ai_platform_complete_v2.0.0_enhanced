#!/usr/bin/env python3
"""Generate a deterministic static decision-lineage knowledge graph.

The graph is repository evidence only. It never claims that a runtime event occurred.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "decision-lineage" / "generated"
GRAPH = OUT / "decision_lineage_graph.json"
NODES = OUT / "decision_lineage_nodes.csv"
EDGES = OUT / "decision_lineage_edges.csv"
SUMMARY = OUT / "decision_lineage_summary.json"
REPORT = OUT / "DECISION_LINEAGE_REPORT.md"

STAGES = [
    ("evidence", re.compile(r"evidence|observation|agronomic_context|input_snapshot", re.I)),
    ("candidate", re.compile(r"candidate|recommendation", re.I)),
    ("decision", re.compile(r"decision_record|decision_id|decision_sor|promotion_decision", re.I)),
    ("review", re.compile(r"review|approval_state|approved_by|human_review", re.I)),
    ("plan", re.compile(r"execution_plan|dispatch_plan", re.I)),
    ("authorization", re.compile(r"dispatch_authorization|authorization", re.I)),
    ("request", re.compile(r"execution_request", re.I)),
    ("receipt", re.compile(r"delivery_receipt|execution_receipt|receipt_id", re.I)),
    ("outcome", re.compile(r"execution_outcome|outcome_id|outcome_reconcile", re.I)),
    ("learning", re.compile(r"learning_attribution|learning_source|calibration|replay", re.I)),
]
RELATIONS = [
    ("candidate_from_evidence", "evidence", "candidate"),
    ("decision_from_candidate", "candidate", "decision"),
    ("review_of_decision", "decision", "review"),
    ("plan_from_review", "review", "plan"),
    ("authorization_for_plan", "plan", "authorization"),
    ("request_from_authorization", "authorization", "request"),
    ("receipt_for_request", "request", "receipt"),
    ("outcome_from_receipt", "receipt", "outcome"),
    ("learning_from_outcome", "outcome", "learning"),
]
SCAN_ROOTS = ["services", "shared", "migrations"]
TEXT_SUFFIXES = {".py", ".sql", ".json", ".yaml", ".yml"}


EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "generated",
}


def files() -> Iterable[Path]:
    """Yield candidate files without traversing generated/vendor trees.

    os.walk is materially faster than Path.rglob on this repository and keeps the
    governance gate bounded in CI.
    """
    collected: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for current, dirs, names in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS)
            base = Path(current)
            for name in sorted(names):
                path = base / name
                if path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    if path.stat().st_size <= 2_000_000:
                        collected.append(path)
                except OSError:
                    continue
    yield from sorted(collected)


def owner_for(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "services":
        return parts[1]
    if parts and parts[0] == "migrations":
        return "database"
    return parts[0] if parts else "unknown"


def build() -> dict:
    stage_evidence: dict[str, list[str]] = defaultdict(list)
    file_stages: dict[str, set[str]] = {}
    for path in files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits = {
            name for name, pattern in STAGES if pattern.search(text) or pattern.search(path.name)
        }
        if hits:
            file_stages[rel] = hits
            for stage in sorted(hits):
                stage_evidence[stage].append(rel)

    nodes = []
    for order, (stage, _) in enumerate(STAGES, 1):
        evidence = sorted(set(stage_evidence.get(stage, [])))
        owners = Counter(owner_for(p) for p in evidence)
        nodes.append(
            {
                "id": f"stage:{stage}",
                "kind": "lineage_stage",
                "stage": stage,
                "order": order,
                "evidence_count": len(evidence),
                "owners": sorted(owners),
                "primary_owner": owners.most_common(1)[0][0] if owners else None,
                "repository_evidence": evidence,
                "runtime_verified": False,
            }
        )

    edges = []
    for relation, source, target in RELATIONS:
        shared_files = sorted(
            rel for rel, hits in file_stages.items() if source in hits and target in hits
        )
        # Migration continuity is strong static evidence even if terms are split across files.
        src = next(n for n in nodes if n["stage"] == source)
        dst = next(n for n in nodes if n["stage"] == target)
        evidence = shared_files[:100]
        edges.append(
            {
                "id": f"edge:{source}:{target}",
                "source": f"stage:{source}",
                "target": f"stage:{target}",
                "relation": relation,
                "repository_evidence": evidence,
                "source_evidence_count": src["evidence_count"],
                "target_evidence_count": dst["evidence_count"],
                "static_supported": bool(src["evidence_count"] and dst["evidence_count"]),
                "runtime_verified": False,
            }
        )

    gaps = [n["stage"] for n in nodes if n["evidence_count"] == 0]
    unsupported = [e["relation"] for e in edges if not e["static_supported"]]
    complete_static_chain = not gaps and not unsupported
    payload = {
        "schema_version": "1.0.0",
        "scope": "static_repository_evidence",
        "runtime_verified": False,
        "production_certified": False,
        "nodes": nodes,
        "edges": edges,
        "gaps": {"missing_stages": gaps, "unsupported_relations": unsupported},
        "complete_static_chain": complete_static_chain,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def render(graph: dict) -> dict[Path, str]:
    summary = {
        "stages": len(graph["nodes"]),
        "relations": len(graph["edges"]),
        "stages_with_evidence": sum(n["evidence_count"] > 0 for n in graph["nodes"]),
        "static_supported_relations": sum(e["static_supported"] for e in graph["edges"]),
        "complete_static_chain": graph["complete_static_chain"],
        "runtime_verified": False,
        "production_certified": False,
        "missing_stages": graph["gaps"]["missing_stages"],
        "unsupported_relations": graph["gaps"]["unsupported_relations"],
    }
    node_rows = [
        [n["id"], n["order"], n["stage"], n["primary_owner"] or "", n["evidence_count"], "false"]
        for n in graph["nodes"]
    ]
    edge_rows = [
        [
            e["id"],
            e["source"],
            e["target"],
            e["relation"],
            str(e["static_supported"]).lower(),
            len(e["repository_evidence"]),
            "false",
        ]
        for e in graph["edges"]
    ]

    def csv_text(header, rows):
        import io

        s = io.StringIO()
        w = csv.writer(s, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
        return s.getvalue()

    lines = [
        "# Decision Lineage Knowledge Graph",
        "",
        "> Static repository evidence only. This report does not prove runtime execution or production operation.",
        "",
        "## Summary",
        "",
        f"- Stages: **{summary['stages']}**",
        f"- Stages with repository evidence: **{summary['stages_with_evidence']}**",
        f"- Static-supported relations: **{summary['static_supported_relations']} / {summary['relations']}**",
        f"- Complete static chain: **{'yes' if summary['complete_static_chain'] else 'no'}**",
        "- Runtime verified: **no**",
        "- Production certified: **no**",
        "",
        "## Stage coverage",
        "",
        "| Order | Stage | Primary owner | Evidence files |",
        "|---:|---|---|---:|",
    ]
    lines += [
        f"| {n['order']} | `{n['stage']}` | `{n['primary_owner'] or 'unassigned'}` | {n['evidence_count']} |"
        for n in graph["nodes"]
    ]
    lines += ["", "## Remaining static gaps", ""]
    if not summary["missing_stages"] and not summary["unsupported_relations"]:
        lines.append(
            "No missing stage or unsupported adjacent relation was found by the static scanner."
        )
    else:
        lines.append(f"- Missing stages: {', '.join(summary['missing_stages']) or 'none'}")
        lines.append(
            f"- Unsupported relations: {', '.join(summary['unsupported_relations']) or 'none'}"
        )
    lines += [
        "",
        "## Certification boundary",
        "",
        "A complete static chain means only that repository artifacts exist for each stage. Runtime verification requires correlated live identifiers, persisted records, telemetry, and execution receipts from a running stack.",
        "",
    ]
    return {
        GRAPH: json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        SUMMARY: json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        NODES: csv_text(
            ["id", "order", "stage", "primary_owner", "evidence_count", "runtime_verified"],
            node_rows,
        ),
        EDGES: csv_text(
            [
                "id",
                "source",
                "target",
                "relation",
                "static_supported",
                "shared_evidence_count",
                "runtime_verified",
            ],
            edge_rows,
        ),
        REPORT: "\n".join(lines),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = p.parse_args()
    rendered = render(build())
    if args.generate:
        OUT.mkdir(parents=True, exist_ok=True)
        for path, content in rendered.items():
            path.write_text(content, encoding="utf-8")
        print(f"PASS generated {len(rendered)} decision-lineage artifacts")
        return 0
    drift = []
    for path, content in rendered.items():
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            drift.append(path.relative_to(ROOT).as_posix())
    if drift:
        print("FAIL decision-lineage drift: " + ", ".join(drift))
        return 1
    print("PASS decision-lineage graph is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
