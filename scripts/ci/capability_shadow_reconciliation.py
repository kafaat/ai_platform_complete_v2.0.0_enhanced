#!/usr/bin/env python3
"""Shadow reconciliation between the canonical registry and the legacy projection.

Report-only by design: a finding never blocks anything. The only thing that blocks
is staleness — the committed report must equal a regeneration from current inputs.
The comparison plan (which fields compare raw, which are excluded and why) comes
from the field authority policy, never from this script: the report is a witness
of disagreement, not a third value source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "docs/capability-registry/generated/capability_registry.json"
LEGACY = ROOT / "capabilities/registry/capabilities.json"
FIELD_AUTHORITY_POLICY = ROOT / "docs/capability-registry/field_authority_policy.json"
OUT = ROOT / "docs/capability-registry/generated/reconciliation"
SCHEMA = "sahool.capability-shadow-reconciliation/v1"

FILES = (
    "shadow_reconciliation_report.json",
    "SHADOW_RECONCILIATION_REPORT.md",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def comparison_plan() -> tuple[list[str], list[str], dict[str, Any]]:
    """The plan is policy data. The engine refuses to invent or widen it."""
    policy = load_json(FIELD_AUTHORITY_POLICY)
    if policy.get("schema") != "sahool.capability-field-authority/v1":
        raise ValueError("field authority policy schema mismatch")
    reconciliation = policy.get("reconciliation")
    if not isinstance(reconciliation, dict):
        raise ValueError("policy has no reconciliation block; shadow comparison refused")
    compare = reconciliation.get("compare_raw")
    exclude = reconciliation.get("exclude_raw")
    if not isinstance(compare, list) or not compare:
        raise ValueError("policy compare_raw missing or empty")
    if not isinstance(exclude, list):
        raise ValueError("policy exclude_raw missing")
    duplicates = sorted(
        {f for f in compare if compare.count(f) > 1} | {f for f in exclude if exclude.count(f) > 1}
    )
    if duplicates:
        # A duplicated field would emit two findings sharing one finding_id,
        # breaking the stable-identity contract the ratchet phase anchors on.
        raise ValueError(f"policy declares duplicate fields: {duplicates}")
    overlap = sorted(set(compare) & set(exclude))
    if overlap:
        raise ValueError(f"policy compares and excludes the same fields: {overlap}")
    if reconciliation.get("no_third_value_registry") is not True:
        raise ValueError("policy must forbid a third value registry")
    authority = policy.get("field_authority", {})
    # The authority policy gives the comparison its meaning: a field compared without a
    # declared authority and legacy role is a raw diff, not a governed reconciliation.
    for field in compare:
        spec = authority.get(field)
        if not isinstance(spec, dict) or not spec.get("authority") or not spec.get("legacy_role"):
            raise ValueError(f"compared field lacks a declared authority/legacy_role: {field}")
    for field in exclude:
        if not (authority.get(field) or {}).get("reconciliation"):
            raise ValueError(f"excluded field lacks an explicit reconciliation reason: {field}")
    return list(compare), list(exclude), authority


def _by_id(registry: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
    rows = registry.get("capabilities")
    if not isinstance(rows, list):
        raise ValueError(f"{label} registry has no capabilities list")
    result = {str(r.get("id")): r for r in rows if isinstance(r, dict) and r.get("id")}
    if len(result) != len(rows):
        raise ValueError(f"{label} registry has duplicate or missing capability IDs")
    return result


def build() -> dict[str, bytes]:
    compare, exclude, authority = comparison_plan()
    canonical = _by_id(load_json(CANONICAL), "canonical")
    legacy = _by_id(load_json(LEGACY), "legacy")

    findings: list[dict[str, Any]] = []
    for cid in sorted(set(canonical) - set(legacy)):
        findings.append(
            {
                "finding_id": f"{cid}:identity",
                "kind": "identity",
                "capability_id": cid,
                "canonical": "present",
                "legacy": "absent",
            }
        )
    for cid in sorted(set(legacy) - set(canonical)):
        findings.append(
            {
                "finding_id": f"{cid}:identity",
                "kind": "identity",
                "capability_id": cid,
                "canonical": "absent",
                "legacy": "present",
            }
        )
    for cid in sorted(set(canonical) & set(legacy)):
        for field in compare:
            canonical_value = canonical[cid].get(field)
            legacy_value = legacy[cid].get(field)
            if canonical_value != legacy_value:
                spec = authority[field]
                findings.append(
                    {
                        "finding_id": f"{cid}:{field}",
                        "kind": "field_drift",
                        "capability_id": cid,
                        "field": field,
                        "canonical": canonical_value,
                        "legacy": legacy_value,
                        "authority": spec["authority"],
                        "legacy_role": spec["legacy_role"],
                    }
                )
    findings.sort(key=lambda f: f["finding_id"])

    excluded = [{"field": field, "reason": authority[field]["reconciliation"]} for field in exclude]
    report = {
        "schema": SCHEMA,
        "mode": "shadow-report-only",
        "no_third_value_registry": True,
        "policy_source": str(FIELD_AUTHORITY_POLICY.relative_to(ROOT)),
        "canonical_source": str(CANONICAL.relative_to(ROOT)),
        "legacy_source": str(LEGACY.relative_to(ROOT)),
        "fields_compared_raw": compare,
        "fields_excluded": excluded,
        "summary": {
            "capabilities_canonical": len(canonical),
            "capabilities_legacy": len(legacy),
            "capabilities_shared": len(set(canonical) & set(legacy)),
            "identity_findings": sum(1 for f in findings if f["kind"] == "identity"),
            "field_drift_findings": sum(1 for f in findings if f["kind"] == "field_drift"),
            "findings_total": len(findings),
        },
        "findings": findings,
        "$honesty_ar": (
            "التقرير يشهد الاختلاف ولا يُحكِّم: السلطة لكلّ حقل تقولها السياسة، "
            "ولا قيمة ثالثة تُنشأ هنا. ظلّيّ بالتصميم — النتيجة لا تحجب، "
            "وبياتُ التقرير وحده هو ما يحجب."
        ),
    }

    lines = [
        "# Shadow Reconciliation — canonical vs legacy",
        "",
        "> Report-only. Findings never block; only report staleness blocks.",
        "> The comparison plan is policy data (`field_authority_policy.json`).",
        "",
        f"- Capabilities: canonical **{len(canonical)}** · legacy **{len(legacy)}**"
        f" · shared **{len(set(canonical) & set(legacy))}**",
        f"- Findings: **{len(findings)}**"
        f" (identity {report['summary']['identity_findings']}"
        f" · field drift {report['summary']['field_drift_findings']})",
        f"- Fields compared raw: {', '.join(compare)}",
        f"- Fields excluded (no raw normalization yet): {', '.join(exclude)}",
        "",
    ]
    if findings:
        lines += [
            "| Finding | Kind | Field | Canonical | Legacy | Authority |",
            "|---|---|---|---|---|---|",
        ]
        for f in findings:
            lines.append(
                f"| {f['finding_id']} | {f['kind']} | {f.get('field', '—')} "
                f"| {json.dumps(f['canonical'], ensure_ascii=False)} "
                f"| {json.dumps(f['legacy'], ensure_ascii=False)} "
                f"| {f.get('authority', '—')} |"
            )
        lines.append("")
    outputs = {
        "shadow_reconciliation_report.json": (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode(),
        "SHADOW_RECONCILIATION_REPORT.md": ("\n".join(lines)).encode(),
    }
    if set(outputs) != set(FILES):
        # FILES is the single name registry write()/check() trust; a divergent build
        # would silently produce artifacts the staleness gate never inspects.
        raise ValueError("build outputs diverge from the FILES contract")
    return outputs


def write(outputs: dict[str, bytes]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (OUT / name).write_bytes(data)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}
    (OUT / "reconciliation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def check(outputs: dict[str, bytes]) -> list[str]:
    """Read-only staleness check: every companion compared by content, manifest included."""
    errors = []
    for name, data in outputs.items():
        p = OUT / name
        if not p.exists():
            errors.append(f"missing:{name}")
        elif p.read_bytes() != data:
            errors.append(f"stale:{name}")
    expected = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(outputs.items())}
    mp = OUT / "reconciliation_manifest.json"
    if not mp.exists() or load_json(mp) != expected:
        errors.append("stale:reconciliation_manifest.json")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    try:
        outputs = build()
    except Exception as exc:
        print(f"shadow_reconciliation ERROR: {exc}", file=sys.stderr)
        return 2
    report = json.loads(outputs["shadow_reconciliation_report.json"])
    summary = report["summary"]
    if args.generate:
        write(outputs)
        print(
            "shadow_reconciliation_generated "
            f"findings={summary['findings_total']} "
            f"(identity={summary['identity_findings']} field={summary['field_drift_findings']}) "
            "mode=shadow-report-only"
        )
        return 0
    errors = check(outputs)
    if errors:
        print(
            "shadow reconciliation report is stale — regenerate with --generate:\n- "
            + "\n- ".join(errors),
            file=sys.stderr,
        )
        return 1
    print(
        "shadow_reconciliation_ok "
        f"findings={summary['findings_total']} mode=shadow-report-only (findings never block)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
