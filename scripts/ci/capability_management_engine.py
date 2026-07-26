#!/usr/bin/env python3
"""Generate the unified SAHOOL Capability Management Layer.

This engine is intentionally downstream of the canonical registry and existing
forensic engines. It never promotes runtime or production state by inference.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/capability-registry"
OUT = BASE / "generated/management"
REG = BASE / "generated/capability_registry.json"
MAPPING = BASE / "generated/mapping/capability_mapping.json"
EVIDENCE = BASE / "generated/evidence/capability_evidence_matrix.json"
PARITY = BASE / "generated/benchmark/capability_parity_matrix.json"
INVEST = BASE / "generated/benchmark/capability_investment_matrix.json"
POLICIES = (
    BASE / "lifecycle.yaml",
    BASE / "maturity_levels.yaml",
    BASE / "parity_levels.yaml",
    BASE / "investment_levels.yaml",
)
SCHEMA_VERSION = "1.0.0"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    import yaml  # lazy: importing this module must not require PyYAML (only YAML reads do)

    return yaml.safe_load(path.read_text(encoding="utf-8"))


# Registry-declared evidence field -> coverage dimension. A capability that
# *declares* an on-disk file is genuinely covered even when the content-scanning
# mapper heuristic did not attribute the file to it; crediting the declared
# path is truthful (its existence is separately enforced by the traceability
# gate). Pure scaffolds that declare no specific-dimension evidence (only a
# catch-all other_evidence bucket, e.g. the synthetic ZZ-999 test) stay unmapped.
_REGISTRY_DIMENSION = {
    "services": "backend",
    "apis": "routes",
    "tests": "tests",
    "ui_consumers": "web",
    "mobile_consumers": "mobile",
}


def _pointer_path(pointer: str) -> str:
    # ``METHOD /route @ services/x/main.py:120`` -> ``services/x/main.py``; a
    # plain ``services/x/main.py`` is returned unchanged (minus any ``:line``).
    tail = pointer.split(" @ ")[-1].strip()
    if ":" in tail and not tail.startswith(("http://", "https://")):
        head = tail.rsplit(":", 1)
        if head[1].isdigit():
            tail = head[0]
    return tail


def registry_covered_dimensions(cap: dict) -> set[str]:
    covered = set()
    for field, dimension in _REGISTRY_DIMENSION.items():
        for pointer in cap.get(field, []) or []:
            if not isinstance(pointer, str):
                continue
            if (ROOT / _pointer_path(pointer)).exists():  # fail-closed: only existing paths credit
                covered.add(dimension)
                break
    return covered


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(obj: Any) -> list[dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("capabilities", "rows", "items"):
            if isinstance(obj.get(key), list):
                return obj[key]
    return []


def by_id(items: list[dict], keys=("capability_id", "id")) -> dict[str, dict]:
    out = {}
    for item in items:
        for key in keys:
            if item.get(key):
                out[str(item[key])] = item
                break
    return out


def validate(reg: dict, mapping: dict, evidence: dict, parity: dict, investment: dict) -> list[str]:
    errors = []
    caps = rows(reg)
    ids = [str(c.get("id")) for c in caps]
    known = set(ids)
    if len(ids) != len(known):
        errors.append("duplicate capability IDs")
    if len(caps) != 81:
        errors.append(f"official capability count drift: expected 81, got {len(caps)}")
    for policy in POLICIES:
        if not policy.exists():
            errors.append(f"missing policy: {policy.relative_to(ROOT)}")
        elif load_yaml(policy).get("schema_version") != "1.0.0":
            errors.append(f"invalid policy schema: {policy.name}")
    for name, obj in [
        ("mapping", mapping),
        ("evidence", evidence),
        ("parity", parity),
        ("investment", investment),
    ]:
        item_ids = set(by_id(rows(obj)))
        unknown = item_ids - known
        if unknown:
            errors.append(f"{name}: unknown capability IDs: {sorted(unknown)}")
    graph = {c["id"]: list(c.get("dependencies", [])) for c in caps}
    for cid, deps in graph.items():
        for dep in deps:
            if dep not in known:
                errors.append(f"{cid}: unknown dependency {dep}")
    indeg = {x: 0 for x in known}
    rev = defaultdict(list)
    for cid, deps in graph.items():
        for dep in deps:
            indeg[cid] += 1
            rev[dep].append(cid)
    q = deque(sorted(x for x, v in indeg.items() if v == 0))
    seen = []
    while q:
        x = q.popleft()
        seen.append(x)
        for nxt in sorted(rev[x]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if len(seen) != len(known):
        errors.append("capability dependency graph contains a cycle")
    for c in caps:
        if c.get("production_certified") and (
            c.get("maturity") != 5 or c.get("evidence_level") != 5
        ):
            errors.append(f"{c['id']}: invalid production certification")
    # Fail-closed registry reconciliation: every registry-declared evidence pointer must
    # resolve to a real file on disk. A stale/typo'd path is a hard error — never a silently
    # dropped credit — so the mapper can neither invent nor lose declared evidence.
    for c in caps:
        for field in ("services", "apis", "tests", "ui_consumers", "mobile_consumers"):
            for ptr in c.get(field, []) or []:
                if isinstance(ptr, str) and not (ROOT / _pointer_path(ptr)).exists():
                    errors.append(
                        f"{c['id']}: declared {field} evidence missing on disk: {_pointer_path(ptr)}"
                    )
    return errors


def generate_payload(reg, mapping, evidence, parity, investment):
    caps = sorted(rows(reg), key=lambda x: x["id"])
    mm = by_id(rows(mapping))
    ee = by_id(rows(evidence))
    pp = by_id(rows(parity))
    ii = by_id(rows(investment))
    nodes = []
    edges = []
    matrix = []
    dependents = defaultdict(list)
    for c in caps:
        for dep in c.get("dependencies", []):
            edges.append({"from": dep, "to": c["id"], "type": "enables"})
            dependents[dep].append(c["id"])
    for c in caps:
        cid = c["id"]
        m = mm.get(cid, {})
        e = ee.get(cid, {})
        p = pp.get(cid, {})
        inv = ii.get(cid, {})
        # union: content-scanner-derived evidence ∪ registry-declared evidence that
        # exists on disk. coverage_dimensions is an explicit {name: bool} map (never
        # a count) so the schema is stable and comparisons stay well-typed.
        reg_covered = registry_covered_dimensions(c)
        dimensions = {
            k: bool((m.get(k, []) or []) or (k in reg_covered))
            for k in (
                "backend",
                "routes",
                "database",
                "events",
                "web",
                "mobile",
                "tests",
                "governance",
                "other_evidence",
            )
        }
        # ``mapped`` is decided by SPECIFIC, high-signal dimensions only. ``governance`` and
        # ``other_evidence`` are catch-all buckets that the token scanner fills from bare
        # capability-ID mentions (self-reference / narrative), so they are reported but never
        # promote a capability on their own — a genuine scaffold (INT-004: no service/route/
        # db/event/web/mobile/test) stays unmapped rather than being lifted by a stray mention.
        specific = ("backend", "routes", "database", "events", "web", "mobile", "tests")
        coverage_dimension_count = sum(dimensions[k] for k in specific)
        mapped = coverage_dimension_count > 0
        runtime_verified = bool(e.get("runtime_verified", False))
        production_certified = bool(
            c.get("production_certified", False) or e.get("production_certified", False)
        )
        row = {
            "id": cid,
            "title": c["title"]["en"],
            "domain": c["domain"],
            "owner": c["owner"],
            "lifecycle": c.get("lifecycle", "implemented"),
            "status": c.get("status", ""),
            "maturity": c["maturity"],
            "evidence_level": c["evidence_level"],
            "mapped": mapped,
            "coverage_dimensions": dimensions,
            "coverage_dimension_count": coverage_dimension_count,
            "dependency_count": len(c.get("dependencies", [])),
            "dependent_count": len(dependents[cid]),
            "runtime_verified": runtime_verified,
            "production_certified": production_certified,
            "parity": p.get(
                "classification",
                p.get("parity_classification", c.get("parity_classification", "unassessed")),
            ),
            "investment": inv.get(
                "strategy",
                inv.get("investment_strategy", c.get("investment_strategy", "unassessed")),
            ),
            "priority": c.get("priority", "unassessed"),
            "business_value": c.get("business_value", "unassessed"),
        }
        matrix.append(row)
        nodes.append(
            {
                k: row[k]
                for k in (
                    "id",
                    "title",
                    "domain",
                    "owner",
                    "maturity",
                    "evidence_level",
                    "mapped",
                    "runtime_verified",
                    "production_certified",
                    "parity",
                    "investment",
                )
            }
        )
    domains = []
    for domain in sorted({r["domain"] for r in matrix}):
        rs = [r for r in matrix if r["domain"] == domain]
        n = len(rs)
        domains.append(
            {
                "domain": domain,
                "capabilities": n,
                "mapped": sum(r["mapped"] for r in rs),
                "average_maturity": round(sum(r["maturity"] for r in rs) / n, 2),
                "average_evidence": round(sum(r["evidence_level"] for r in rs) / n, 2),
                "runtime_verified": sum(r["runtime_verified"] for r in rs),
                "production_certified": sum(r["production_certified"] for r in rs),
                "unassessed_parity": sum(r["parity"] == "unassessed" for r in rs),
            }
        )
    # Honest tri-state accounting: a capability is either evidence-``mapped`` (real
    # scanned or registry-declared existing evidence), explicitly ``adjudicated``
    # (accepted with a documented reason though unmapped — none today), or an
    # unresolved ``unmapped`` gap. ``accounted_for`` = mapped + adjudicated; it is
    # NEVER inflated to total, and unmapped>0 is reported honestly, not hidden.
    total = len(matrix)
    mapped_n = sum(r["mapped"] for r in matrix)
    adjudicated_n = 0
    unmapped_n = total - mapped_n - adjudicated_n
    dashboard = {
        "schema_version": SCHEMA_VERSION,
        "capabilities_total": total,
        "mapped": mapped_n,
        "adjudicated": adjudicated_n,
        "unmapped": unmapped_n,
        "accounted_for": mapped_n + adjudicated_n,
        "unmapped_capabilities": sorted(r["id"] for r in matrix if not r["mapped"]),
        "mapping_coverage_pct": round(100 * mapped_n / total, 2),
        "runtime_verified": sum(r["runtime_verified"] for r in matrix),
        "production_certified": sum(r["production_certified"] for r in matrix),
        "maturity_distribution": dict(sorted(Counter(str(r["maturity"]) for r in matrix).items())),
        "parity_distribution": dict(sorted(Counter(r["parity"] for r in matrix).items())),
        "investment_distribution": dict(sorted(Counter(r["investment"] for r in matrix).items())),
        "domains": domains,
    }
    graph = {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": sorted(edges, key=lambda x: (x["from"], x["to"])),
    }
    return matrix, graph, dashboard


def write_all(matrix, graph, dashboard):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "capability_management_matrix.json").write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "capabilities": matrix}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    fields = [
        "id",
        "title",
        "domain",
        "owner",
        "lifecycle",
        "status",
        "maturity",
        "evidence_level",
        "mapped",
        "dependency_count",
        "dependent_count",
        "runtime_verified",
        "production_certified",
        "parity",
        "investment",
        "priority",
        "business_value",
    ]
    with (OUT / "capability_management_matrix.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in matrix:
            w.writerow({k: r[k] for k in fields})
    (OUT / "capability_knowledge_graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    dot = ["digraph capabilities {", "  rankdir=LR;", "  node [shape=box];"]
    for n in graph["nodes"]:
        dot.append(f'  "{n["id"]}" [label="{n["id"]}\\n{n["title"].replace(chr(34), chr(39))}"];')
    for e in graph["edges"]:
        dot.append(f'  "{e["from"]}" -> "{e["to"]}" [label="{e["type"]}"];')
    dot.append("}")
    (OUT / "capability_knowledge_graph.dot").write_text("\n".join(dot) + "\n", encoding="utf-8")
    (OUT / "coverage_dashboard.json").write_text(
        json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    heat = [
        "# Capability Domain Heat Map",
        "",
        "| Domain | Coverage | Maturity | Evidence | Runtime | Production |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for d in dashboard["domains"]:
        heat.append(
            f"| {d['domain']} | {d['mapped']}/{d['capabilities']} | {d['average_maturity']:.2f} | {d['average_evidence']:.2f} | {d['runtime_verified']} | {d['production_certified']} |"
        )
    (OUT / "CAPABILITY_HEAT_MAP.md").write_text("\n".join(heat) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            str(p.relative_to(ROOT)): sha(p)
            for p in (REG, MAPPING, EVIDENCE, PARITY, INVEST, *POLICIES)
        },
        "outputs": {},
    }
    for p in sorted(OUT.iterdir()):
        if p.name != "management_manifest.json" and p.is_file():
            manifest["outputs"][p.name] = sha(p)
    (OUT / "management_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    objs = [load_json(p) for p in (REG, MAPPING, EVIDENCE, PARITY, INVEST)]
    errs = validate(*objs)
    if errs:
        print("\n".join(errs), file=sys.stderr)
        return 1
    matrix, graph, dashboard = generate_payload(*objs)
    if args.check:
        expected = {
            "capability_management_matrix.json": {
                "schema_version": SCHEMA_VERSION,
                "capabilities": matrix,
            },
            "capability_knowledge_graph.json": graph,
            "coverage_dashboard.json": dashboard,
        }
        for name, obj in expected.items():
            p = OUT / name
            if not p.exists() or load_json(p) != obj:
                print(f"capability management drift: {name}; run --generate", file=sys.stderr)
                return 1
        manifest = OUT / "management_manifest.json"
        if not manifest.exists():
            print("missing management manifest", file=sys.stderr)
            return 1
    if args.generate or not args.check:
        write_all(matrix, graph, dashboard)
    print(
        f"capability_management_ok total={dashboard['capabilities_total']} mapped={dashboard['mapped']} runtime={dashboard['runtime_verified']} production={dashboard['production_certified']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
