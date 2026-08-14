#!/usr/bin/env python3
"""Generate a fail-closed evidence matrix and evidence-derived maturity baseline.

The engine never upgrades canonical maturity or asserts runtime/production evidence.
It computes a separate assessed_maturity from repository evidence and records drift.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/capability-registry/generated/capability_registry.json"
MAPPING = ROOT / "docs/capability-registry/generated/mapping/capability_mapping.json"
RUNTIME_CSV = ROOT / "capabilities/generated/capability_runtime_evidence.csv"
CERT_CSV = ROOT / "capabilities/generated/capability_certification_matrix.csv"
RUNTIME_AUTHORITY = ROOT / "runtime-verification/generated/runtime_certification_summary.json"
FIELD_AUTHORITY_POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
OUT = ROOT / "docs/capability-registry/generated/evidence"

FILES = (
    "capability_evidence_matrix.json",
    "capability_evidence_matrix.csv",
    "capability_maturity_baseline.json",
    "capability_maturity_baseline.csv",
    "domain_maturity_summary.json",
    "CAPABILITY_EVIDENCE_MATURITY_REPORT.md",
)

INTEGRATION_TOKENS = ("integration", "e2e", "contract", "workflow", "acceptance", "smoke")
UNIT_TOKENS = ("test_", "/tests/", "_test.")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path, key: str = "id") -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {row[key]: row for row in csv.DictReader(f) if row.get(key)}


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def runtime_authority_by_id() -> dict[str, dict[str, Any]]:
    policy = load_json(FIELD_AUTHORITY_POLICY)
    fields = policy.get("field_authority", {})
    if policy.get("schema") != "sahool.capability-field-authority/v1":
        raise ValueError("capability field authority policy schema mismatch")
    if fields.get("runtime_verified", {}).get("authority") != "runtime_verification":
        raise ValueError("runtime_verified authority must be runtime_verification")
    summary = load_json(RUNTIME_AUTHORITY)
    rows = summary.get("capabilities")
    if not isinstance(rows, list):
        raise ValueError("runtime authority summary has no capabilities list")
    result = {str(row.get("id")): row for row in rows if isinstance(row, dict) and row.get("id")}
    if len(result) != len(rows):
        raise ValueError("runtime authority summary has duplicate or missing capability IDs")
    return result


def classify_tests(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    unit, integration = [], []
    for item in items:
        path = str(item.get("path") or item.get("value") or "")
        low = path.lower()
        if any(tok in low for tok in INTEGRATION_TOKENS):
            integration.append(path)
        elif any(tok in low for tok in UNIT_TOKENS):
            unit.append(path)
    return sorted(set(unit)), sorted(set(integration))


def assessed_maturity(
    e: dict[str, bool], decision_linked: bool, learning_linked: bool
) -> tuple[int, list[str]]:
    """Conservative 0..5 model; runtime is mandatory for level 4 and production for level 5."""
    reasons: list[str] = []
    implementation = e["backend"] or e["database"] or e["web"] or e["mobile"] or e["events"]
    if not implementation and not e["api"] and not e["unit_tests"] and not e["integration_tests"]:
        if e["documentation"]:
            return 1, ["documentation_only"]
        return 0, ["no_repository_implementation_evidence"]
    level = 1
    reasons.append("repository_implementation_present")
    if (e["api"] or e["web"] or e["mobile"]) and (e["unit_tests"] or e["integration_tests"]):
        level = 2
        reasons.append("exposed_surface_and_test_evidence")
    if e["api"] and e["unit_tests"] and e["integration_tests"]:
        level = 3
        reasons.append("api_unit_and_integration_evidence")
    if level >= 3 and e["runtime"] and decision_linked:
        level = 4
        reasons.append("runtime_verified_closed_workflow_evidence")
    if level >= 4 and e["production"] and learning_linked:
        level = 5
        reasons.append("production_verified_learning_loop_evidence")
    if not e["runtime"]:
        reasons.append("runtime_not_verified_caps_maturity_at_3")
    if not e["production"]:
        reasons.append("production_not_certified_caps_maturity_below_5")
    return level, reasons


def build() -> dict[str, bytes]:
    registry = load_json(REGISTRY)
    mapping = load_json(MAPPING)
    runtime = load_csv(RUNTIME_CSV)
    cert = load_csv(CERT_CSV)
    authority = runtime_authority_by_id()
    map_by_id = {c["capability_id"]: c for c in mapping["capabilities"]}
    ids = {c["id"] for c in registry["capabilities"]}
    if set(authority) != ids:
        raise ValueError("runtime authority/registry identity mismatch")
    records = []

    for cap in sorted(registry["capabilities"], key=lambda x: x["id"]):
        cid = cap["id"]
        m = map_by_id.get(cid)
        if m is None:
            raise ValueError(f"missing mapping for {cid}")
        unit, integration = classify_tests(m.get("tests", []))
        rt = runtime.get(cid, {})
        ce = cert.get(cid, {})
        # Runtime truth comes from the normalized authority result: governed promotion claim
        # + verified services + append-only attested application receipt. A raw registry boolean
        # or generic certification-readiness flag is not sufficient.
        runtime_verified = authority[cid].get("runtime_authority_verified") is True
        production = truthy(ce.get("certified", False)) and truthy(
            rt.get("production_certified", False)
        )
        dependencies = cap.get("dependencies") or []
        decision_linked = (
            cap.get("domain") == "decision"
            or any(str(d).startswith("DEC-") for d in dependencies)
            or bool(cap.get("decision", False))
        )
        learning_linked = cid in {"DEC-009", "DEC-010"} or any(
            str(d) in {"DEC-009", "DEC-010"} for d in dependencies
        )
        evidence = {
            "documentation": bool(cap.get("business_goal") or cap.get("title")),
            "backend": bool(m.get("backend")),
            "api": bool(m.get("routes")) or bool(cap.get("apis")),
            "database": bool(m.get("database")),
            "events": bool(m.get("events")),
            "web": bool(m.get("web")) or bool(cap.get("ui_consumers")),
            "mobile": bool(m.get("mobile")) or bool(cap.get("mobile_consumers")),
            "unit_tests": bool(unit),
            "integration_tests": bool(integration),
            "runtime_instrumentation": any(
                int(rt.get(k, 0) or 0) > 0
                for k in ("metrics", "traces", "receipts", "audit_events", "runtime_surfaces")
            ),
            "runtime": runtime_verified,
            "production": production,
        }
        level, reasons = assessed_maturity(evidence, decision_linked, learning_linked)
        declared = int(cap.get("maturity", 0))
        delta = level - declared
        records.append(
            {
                "capability_id": cid,
                "title": cap.get("title", {}).get("en", "")
                if isinstance(cap.get("title"), dict)
                else cap.get("title", ""),
                "domain": cap["domain"],
                "declared_maturity": declared,
                "assessed_maturity": level,
                "maturity_delta": delta,
                "maturity_alignment": "aligned"
                if delta == 0
                else ("declared_above_evidence" if delta < 0 else "evidence_above_declared"),
                "evidence": evidence,
                "evidence_score": sum(1 for v in evidence.values() if v),
                "unit_test_paths": unit,
                "integration_test_paths": integration,
                "decision_linked": decision_linked,
                "learning_linked": learning_linked,
                "assessment_reasons": reasons,
                "runtime_verified": runtime_verified,
                "production_certified": production,
                "automatic_registry_update": False,
            }
        )

    if {r["capability_id"] for r in records} != ids:
        raise ValueError("registry/evidence matrix identity mismatch")
    if any(r["assessed_maturity"] >= 4 and not r["runtime_verified"] for r in records):
        raise ValueError("level 4 requires runtime verification")
    if any(r["assessed_maturity"] == 5 and not r["production_certified"] for r in records):
        raise ValueError("level 5 requires production certification")

    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_domain[r["domain"]].append(r)
    domain_summary = []
    for domain, rs in sorted(by_domain.items()):
        counts = Counter(r["assessed_maturity"] for r in rs)
        domain_summary.append(
            {
                "domain": domain,
                "capability_count": len(rs),
                "average_declared_maturity": round(
                    sum(r["declared_maturity"] for r in rs) / len(rs), 2
                ),
                "average_assessed_maturity": round(
                    sum(r["assessed_maturity"] for r in rs) / len(rs), 2
                ),
                "runtime_verified": sum(r["runtime_verified"] for r in rs),
                "production_certified": sum(r["production_certified"] for r in rs),
                "declared_above_evidence": sum(
                    r["maturity_alignment"] == "declared_above_evidence" for r in rs
                ),
                "maturity_distribution": {str(i): counts.get(i, 0) for i in range(6)},
            }
        )

    summary = {
        "schema_version": "1.0",
        "source_registry": str(REGISTRY.relative_to(ROOT)),
        "source_mapping": str(MAPPING.relative_to(ROOT)),
        "constraints": {
            "fail_closed": True,
            "automatic_registry_update": False,
            "runtime_required_for_level_4": True,
            "production_required_for_level_5": True,
        },
        "summary": {
            "capability_count": len(records),
            "aligned": sum(r["maturity_alignment"] == "aligned" for r in records),
            "declared_above_evidence": sum(
                r["maturity_alignment"] == "declared_above_evidence" for r in records
            ),
            "evidence_above_declared": sum(
                r["maturity_alignment"] == "evidence_above_declared" for r in records
            ),
            "runtime_verified": sum(r["runtime_verified"] for r in records),
            "production_certified": sum(r["production_certified"] for r in records),
            "average_assessed_maturity": round(
                sum(r["assessed_maturity"] for r in records) / len(records), 2
            ),
        },
        "capabilities": records,
    }
    maturity = {
        "schema_version": "1.0",
        "policy": "evidence-derived-fail-closed",
        "summary": summary["summary"],
        "capabilities": [
            {
                k: r[k]
                for k in (
                    "capability_id",
                    "title",
                    "domain",
                    "declared_maturity",
                    "assessed_maturity",
                    "maturity_delta",
                    "maturity_alignment",
                    "assessment_reasons",
                    "runtime_verified",
                    "production_certified",
                )
            }
            for r in records
        ],
    }

    def j(obj: Any) -> bytes:
        return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

    outputs: dict[str, bytes] = {
        "capability_evidence_matrix.json": j(summary),
        "capability_maturity_baseline.json": j(maturity),
        "domain_maturity_summary.json": j({"schema_version": "1.0", "domains": domain_summary}),
    }
    import io

    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(
        [
            "capability_id",
            "title",
            "domain",
            "declared_maturity",
            "assessed_maturity",
            "alignment",
            "evidence_score",
            "documentation",
            "backend",
            "api",
            "database",
            "events",
            "web",
            "mobile",
            "unit_tests",
            "integration_tests",
            "runtime_instrumentation",
            "runtime_verified",
            "production_certified",
        ]
    )
    for r in records:
        e = r["evidence"]
        w.writerow(
            [
                r["capability_id"],
                r["title"],
                r["domain"],
                r["declared_maturity"],
                r["assessed_maturity"],
                r["maturity_alignment"],
                r["evidence_score"],
                *[
                    e[k]
                    for k in (
                        "documentation",
                        "backend",
                        "api",
                        "database",
                        "events",
                        "web",
                        "mobile",
                        "unit_tests",
                        "integration_tests",
                        "runtime_instrumentation",
                        "runtime",
                        "production",
                    )
                ],
            ]
        )
    outputs["capability_evidence_matrix.csv"] = sio.getvalue().encode()
    sio = io.StringIO()
    w = csv.writer(sio)
    w.writerow(
        [
            "capability_id",
            "domain",
            "declared_maturity",
            "assessed_maturity",
            "maturity_delta",
            "alignment",
            "runtime_verified",
            "production_certified",
            "reasons",
        ]
    )
    for r in records:
        w.writerow(
            [
                r["capability_id"],
                r["domain"],
                r["declared_maturity"],
                r["assessed_maturity"],
                r["maturity_delta"],
                r["maturity_alignment"],
                r["runtime_verified"],
                r["production_certified"],
                ";".join(r["assessment_reasons"]),
            ]
        )
    outputs["capability_maturity_baseline.csv"] = sio.getvalue().encode()
    lines = [
        "# Capability Evidence & Maturity Baseline",
        "",
        "> Static, fail-closed assessment. It does not modify canonical maturity and does not certify runtime or production.",
        "",
        "## Summary",
        "",
        f"- Capabilities: **{len(records)}**",
        f"- Average assessed maturity: **{summary['summary']['average_assessed_maturity']} / 5**",
        f"- Aligned: **{summary['summary']['aligned']}**",
        f"- Declared above current evidence: **{summary['summary']['declared_above_evidence']}**",
        f"- Evidence above declared: **{summary['summary']['evidence_above_declared']}**",
        f"- Runtime verified: **{summary['summary']['runtime_verified']}**",
        f"- Production certified: **{summary['summary']['production_certified']}**",
        "",
        "## Domain baseline",
        "",
        "| Domain | Capabilities | Declared avg | Assessed avg | Declared above evidence |",
        "|---|---:|---:|---:|---:|",
    ]
    for d in domain_summary:
        lines.append(
            f"| {d['domain']} | {d['capability_count']} | {d['average_declared_maturity']} | {d['average_assessed_maturity']} | {d['declared_above_evidence']} |"
        )
    lines += [
        "",
        "## Policy",
        "",
        "- Level 4 requires live runtime evidence plus a decision/workflow link.",
        "- Level 5 requires production certification plus a learning-loop link.",
        "- Repository instrumentation is recorded separately and is not runtime proof.",
        "- Canonical registry maturity is never changed automatically.",
        "",
    ]
    outputs["CAPABILITY_EVIDENCE_MATURITY_REPORT.md"] = ("\n".join(lines)).encode()
    return outputs


def write(outputs: dict[str, bytes]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (OUT / name).write_bytes(data)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}
    (OUT / "evidence_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


def check(outputs: dict[str, bytes]) -> list[str]:
    errors = []
    for name, data in outputs.items():
        p = OUT / name
        if not p.exists():
            errors.append(f"missing:{name}")
        elif p.read_bytes() != data:
            errors.append(f"drift:{name}")
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}
    mp = OUT / "evidence_manifest.json"
    if not mp.exists() or load_json(mp) != expected:
        errors.append("drift:evidence_manifest.json")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        outputs = build()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.generate:
        write(outputs)
        print(
            f"Capability evidence/maturity generated: {len(load_json(REGISTRY)['capabilities'])} capabilities"
        )
        return 0
    errors = check(outputs)
    if errors:
        print("Capability evidence/maturity drift:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print("Capability evidence/maturity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
