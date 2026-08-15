#!/usr/bin/env python3
"""Extract conservative runtime observability evidence for SAHOOL capabilities.

This tool does not claim that production telemetry is live. It records repository-level
instrumentation evidence only, with exact source pointers. Production certification remains
blocked until externally collected runtime/production artifacts are attached.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
GENERATED = ROOT / "capabilities/generated"
FIELD_AUTHORITY_POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
AUTH_RECEIPT_TYPE = "attested-runtime-verification"

METRIC_PATTERNS = [
    re.compile(r"(?:Counter|Gauge|Histogram|Summary)\s*\(\s*[rubf]*[\"']([^\"']+)[\"']"),
    re.compile(r"(?:counter|gauge|histogram)\s*\(\s*[rubf]*[\"']([^\"']+)[\"']", re.I),
]
TRACE_PATTERNS = [
    re.compile(r"start_as_current_span\s*\(\s*[rubf]*[\"']([^\"']+)[\"']"),
    re.compile(r"start_span\s*\(\s*[rubf]*[\"']([^\"']+)[\"']"),
]
AUDIT_PATTERNS = [
    re.compile(
        r"(?:event_type|audit_event|action)\s*=\s*[rubf]*[\"']([^\"']*(?:audit|approved|rejected|dispatched|executed|activated|rollback|login|logout)[^\"']*)[\"']",
        re.I,
    ),
]


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def load_authority_policy() -> dict:
    policy = json.loads(FIELD_AUTHORITY_POLICY.read_text(encoding="utf-8"))
    if policy.get("schema") != "sahool.capability-field-authority/v1":
        raise ValueError("capability field authority policy schema mismatch")
    expected = {
        "runtime.metrics": "repository_runtime_instrumentation",
        "runtime.traces": "repository_runtime_instrumentation",
        "runtime.audit_events": "repository_runtime_instrumentation",
        "runtime.repository_receipts": "repository_runtime_instrumentation",
        "runtime.verification_receipts": "runtime_verification",
        "runtime_verified": "runtime_verification",
        "production_certified": "certification",
    }
    fields = policy.get("field_authority", {})
    for field, authority in expected.items():
        if fields.get(field, {}).get("authority") != authority:
            raise ValueError(f"field authority mismatch for {field}")
    if fields["runtime.verification_receipts"].get("receipt_type") != AUTH_RECEIPT_TYPE:
        raise ValueError("runtime verification receipt type mismatch")
    if fields["runtime.verification_receipts"].get("append_only") is not True:
        raise ValueError("runtime verification receipts must be append-only")
    return policy


def governed_verification_receipts(cap: dict) -> list[dict]:
    """Preserve receipts owned by runtime verification; instrumentation may not rewrite them."""
    preserved: list[dict] = []
    for receipt in cap.get("runtime", {}).get("receipts", []) or []:
        if not isinstance(receipt, dict):
            continue
        if receipt.get("type") != AUTH_RECEIPT_TYPE:
            raise ValueError(
                f"{cap.get('id')}: unknown structured runtime receipt type {receipt.get('type')!r}"
            )
        preserved.append(json.loads(json.dumps(receipt)))
    return sorted(
        preserved,
        key=lambda r: (
            str(r.get("application_id", "")),
            str(r.get("candidate_id", "")),
            str(r.get("target_sha", "")),
        ),
    )


def source_files(cap: dict) -> list[Path]:
    pointers: set[str] = set(cap.get("services", []))
    pointers.update(
        e.get("path", "") for e in cap.get("evidence", []) if e.get("type") == "repository"
    )
    for api in cap.get("apis", []):
        if " @ " in api:
            pointer = api.split(" @ ", 1)[1].rsplit(":", 1)[0]
            pointers.add(pointer)
    result = []
    for pointer in sorted(pointers):
        p = ROOT / pointer
        if p.is_file() and p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".dart"}:
            result.append(p)
    return result


def pointer(kind: str, name: str, path: Path, line: int) -> str:
    rel = path.relative_to(ROOT).as_posix()
    clean = re.sub(r"\s+", "_", name.strip())[:120]
    return f"{kind}:{clean}@{rel}:{line}"


def extract_from_file(path: Path) -> dict[str, list[str]]:
    out = {"metrics": [], "traces": [], "audit_events": []}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for lineno, line in enumerate(lines, 1):
        for pat in METRIC_PATTERNS:
            for match in pat.finditer(line):
                out["metrics"].append(pointer("metric", match.group(1), path, lineno))
        for pat in TRACE_PATTERNS:
            for match in pat.finditer(line):
                out["traces"].append(pointer("trace", match.group(1), path, lineno))
        for pat in AUDIT_PATTERNS:
            for match in pat.finditer(line):
                out["audit_events"].append(pointer("audit", match.group(1), path, lineno))
    return out


def receipt_evidence(cap: dict) -> list[str]:
    values: list[str] = []
    for api in cap.get("apis", []):
        route = api.split(" @ ", 1)[0]
        if re.search(r"receipt|verification|outcome", route, re.I):
            values.append(f"receipt:api:{route.replace(' ', '_')}")
    for test in cap.get("tests", []):
        if re.search(r"receipt|verification|outcome", test, re.I):
            values.append(f"receipt:test:{test}")
    return values


def derive(data: dict) -> dict:
    # Binding this writer to the field-authority policy makes the ownership split executable,
    # not documentary. Repository instrumentation owns its derived pointers only; governed
    # verification receipts/runtime_verified and certification remain outside this writer.
    load_authority_policy()
    result = json.loads(json.dumps(data))
    for cap in result["capabilities"]:
        authoritative_receipts = governed_verification_receipts(cap)
        runtime = {"metrics": [], "traces": [], "receipts": [], "audit_events": []}
        for path in source_files(cap):
            extracted = extract_from_file(path)
            for key in ("metrics", "traces", "audit_events"):
                runtime[key].extend(extracted[key])
        repository_receipts = sorted(set(receipt_evidence(cap)))[:25]
        for key in ("metrics", "traces", "audit_events"):
            runtime[key] = sorted(set(runtime[key]))[:25]
        # Keep the compatibility shape while preserving authority by value type. Static
        # repository pointers are regenerated; attested dictionaries are append-only inputs
        # owned by runtime_verification_apply and survive every instrumentation refresh.
        runtime["receipts"] = repository_receipts + authoritative_receipts
        cap["runtime"] = runtime
        # Deliberately do not write status, runtime_verified, maturity, evidence_level, or
        # production_certified here. This tool derives repository instrumentation only.
    return result


def report(data: dict, generated_dir: Path = GENERATED) -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    caps = data["capabilities"]
    rows = []
    for c in caps:
        r = c["runtime"]
        rows.append(
            {
                "id": c["id"],
                "title": c["title"],
                "metrics": len(r["metrics"]),
                "traces": len(r["traces"]),
                "receipts": len(r["receipts"]),
                "audit_events": len(r["audit_events"]),
                "runtime_surfaces": sum(bool(r[k]) for k in r),
                "production_certified": c["production_certified"],
            }
        )
    summary = {
        "capabilities_total": len(caps),
        "with_metrics": sum(x["metrics"] > 0 for x in rows),
        "with_traces": sum(x["traces"] > 0 for x in rows),
        "with_receipts": sum(x["receipts"] > 0 for x in rows),
        "with_audit_events": sum(x["audit_events"] > 0 for x in rows),
        "with_all_repository_runtime_surfaces": sum(x["runtime_surfaces"] == 4 for x in rows),
        "production_certified": sum(x["production_certified"] for x in rows),
        "surface_distribution": dict(sorted(Counter(x["runtime_surfaces"] for x in rows).items())),
        "interpretation": "Pointers prove repository instrumentation only; they do not prove live telemetry or production operation.",
    }
    (generated_dir / "capability_runtime_evidence_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    import csv

    with (generated_dir / "capability_runtime_evidence.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lines = [
        "# SAHOOL Capability Runtime Evidence",
        "",
        "> Repository instrumentation evidence only; not production proof.",
        "",
        "| Capability | Metrics | Traces | Receipts | Audit | Surfaces |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for x in rows:
        lines.append(
            f"| {x['id']} | {x['metrics']} | {x['traces']} | {x['receipts']} | {x['audit_events']} | {x['runtime_surfaces']}/4 |"
        )
    (generated_dir / "CAPABILITY_RUNTIME_EVIDENCE_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    original = load()
    derived = derive(original)
    if args.check:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="sahool-runtime-evidence-check-") as tmp:
            candidate = Path(tmp)
            report(derived, candidate)
            report_names = [
                "capability_runtime_evidence_summary.json",
                "capability_runtime_evidence.csv",
                "CAPABILITY_RUNTIME_EVIDENCE_REPORT.md",
            ]
            reports_drift = any(
                not (GENERATED / name).exists()
                or (GENERATED / name).read_bytes() != (candidate / name).read_bytes()
                for name in report_names
            )
        if derived != original or reports_drift:
            print("capability_runtime_evidence_drift_detected")
            return 1
    else:
        report(derived)
    if args.apply:
        REGISTRY.write_text(
            json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("capability_runtime_evidence_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
