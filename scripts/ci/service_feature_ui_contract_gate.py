#!/usr/bin/env python3
"""SAHOOL service-feature-ui-contract-gate.

Static CI guard: every runtime service with exposed features must have at least
one demonstrable consumer contract:
  * UI/mobile client or screen,
  * platform/gateway proxy, or
  * internal consumer contract test/job contract.

The gate intentionally uses repository text evidence instead of generated docs.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".dart",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".toml",
    ".env",
    ".conf",
    ".sh",
    ".sql",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}


@dataclass(frozen=True)
class Match:
    root: str
    path: str
    pattern: str
    line: int


def _iter_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            p = Path(current) / name
            # الملفّات المولَّدة لا تصلح دليلاً — دليل مولَّد يثبت كتالوجه بنفسه.
            if ".generated." in p.name:
                continue
            if p.suffix.lower() in TEXT_EXTENSIONS or p.name.startswith("docker-compose"):
                yield p


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _find_patterns(repo: Path, roots: list[str], patterns: list[str]) -> list[Match]:
    matches: list[Match] = []
    for root_name in roots:
        root = repo / root_name
        for file_path in _iter_files(root):
            text = _read_text(file_path)
            for pattern in patterns:
                if pattern in text:
                    line = text[: text.index(pattern)].count("\n") + 1
                    matches.append(
                        Match(
                            root=root_name,
                            path=str(file_path.relative_to(repo)),
                            pattern=pattern,
                            line=line,
                        )
                    )
    return matches


def _path_exists(repo: Path, rel: str) -> bool:
    return (repo / rel).exists()


# U3: تصنيف السلك الصريح — «مستهلَك» أو «غير-مستهلَك عمداً» (بمُحفِّز إعادة فتح)
# أو «مهمّة مستقلّة». لا قيمة رابعة؛ الغياب = consumed (الوضع الافتراضيّ الأصرم).
_WIRING_DISPOSITIONS = {
    "consumed",
    "intentional-unconsumed",
    "standalone-job",
}


# أسماء بديلة: خدمة في سجلّ الجرد باسم دليلها، ولها عقد باسم وظيفيّ مختلف (نفس الخدمة).
# odoo-bridge (دليل/جرد) ≡ erp-bridge (العقد + خدمة compose sahool-erp-bridge).
_INVENTORY_ALIASES = {"odoo-bridge": "erp-bridge"}


def _inventory_service_names(repo: Path) -> list[str]:
    """أسماء خدمات سجلّ الجرد المُولَّد (مصدر الحقيقة لِما يعمل فعلاً)."""
    inv_path = repo / "service_inventory.generated.json"
    if not inv_path.exists():
        return []
    doc = json.loads(inv_path.read_text(encoding="utf-8"))
    services = doc.get("services", doc) if isinstance(doc, dict) else doc
    out = []
    for entry in services:
        name = entry.get("service") if isinstance(entry, dict) else entry
        if name:
            out.append(str(name))
    return out


def run_gate(repo: Path, manifest_path: Path) -> tuple[bool, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    failures: list[str] = []

    seen_contracts: set[str] = set()
    for service in manifest["services"]:
        name = service["service"]
        if name in seen_contracts:
            failures.append(f"{name}: duplicate consumer contract")
        seen_contracts.add(name)
        source_paths = service.get("source", [])
        missing_sources = [p for p in source_paths if not _path_exists(repo, p)]
        evidence_rows = []
        evidence_failures: list[str] = []
        disposition = str(service.get("wiring_disposition") or "consumed")

        # U3 fail-closed: كلّ مجموعة أدلّة إلزاميّة بكاملها — جذورها موجودة وأنماطها
        # كلّها مطابِقة لمصدر غير-مولَّد. مجموعة صالحة لا تُخفي مجموعة ثانية بائتة.
        for evidence in service.get("evidence", []):
            roots = [str(item) for item in evidence.get("roots") or []]
            patterns = [str(item) for item in evidence.get("patterns") or []]
            missing_roots = [item for item in roots if not _path_exists(repo, item)]
            matches = _find_patterns(repo, roots, patterns)
            matched_patterns = sorted({match.pattern for match in matches})
            missing_patterns = sorted(set(patterns) - set(matched_patterns))
            if not roots:
                evidence_failures.append(f"{name}/{evidence.get('kind')}: roots missing")
            if not patterns:
                evidence_failures.append(f"{name}/{evidence.get('kind')}: patterns missing")
            if missing_roots:
                evidence_failures.append(
                    f"{name}/{evidence.get('kind')}: missing root(s): " + ", ".join(missing_roots)
                )
            if missing_patterns:
                evidence_failures.append(
                    f"{name}/{evidence.get('kind')}: unmatched pattern(s): "
                    + ", ".join(missing_patterns)
                )
            evidence_rows.append(
                {
                    "kind": evidence["kind"],
                    "roots": roots,
                    "patterns": patterns,
                    "missing_roots": missing_roots,
                    "matched_patterns": matched_patterns,
                    "missing_patterns": missing_patterns,
                    "matches": [m.__dict__ for m in matches[:12]],
                    "match_count": len(matches),
                }
            )

        if disposition not in _WIRING_DISPOSITIONS:
            evidence_failures.append(f"{name}: unsupported wiring_disposition {disposition!r}")
        if not evidence_rows:
            evidence_failures.append(f"{name}: no evidence groups declared")
        evidence_kinds = {row["kind"] for row in evidence_rows}
        if disposition == "intentional-unconsumed":
            if not service.get("reopen_trigger"):
                evidence_failures.append(f"{name}: intentional-unconsumed requires reopen_trigger")
            if "activation-safety-contract" not in evidence_kinds:
                evidence_failures.append(
                    f"{name}: intentional-unconsumed requires activation-safety-contract"
                )
        if disposition == "standalone-job" and "job-contract" not in evidence_kinds:
            evidence_failures.append(f"{name}: standalone-job requires job-contract")

        status = "pass" if not missing_sources and not evidence_failures else "fail"
        if missing_sources:
            failures.append(f"{name}: missing source path(s): {', '.join(missing_sources)}")
        failures.extend(evidence_failures)

        # wired: أدلّة الاستهلاك تثبته للمستهلَك؛ «غير-مستهلَك عمداً» = False صراحةً؛
        # «مهمّة مستقلّة» = null (السلك لا ينطبق عليها، لا ادّعاء).
        wired: bool | None
        if disposition == "intentional-unconsumed":
            wired = False
        elif disposition == "standalone-job":
            wired = None
        else:
            wired = status == "pass"

        rows.append(
            {
                "service": name,
                "classification": service.get("classification", "unknown"),
                "wiring_disposition": disposition,
                "wired": wired,
                "reopen_trigger": service.get("reopen_trigger"),
                "status": status,
                "missing_sources": missing_sources,
                "evidence": evidence_rows,
            }
        )

    # عقد الشمول (P0 من تدقيق البوّابة): كلّ خدمة في سجلّ الجرد يجب أن يكون لها عقد
    # مستهلك. الحارس سابقاً يفحص العقود المسجّلة فقط (contracts ⊆ present) لا الجرد
    # (inventory ⊆ contracts)، فمرّت خدمات غير مسجّلة (decision/model-registry/…). نُغلقها.
    contract_names = {s["service"] for s in manifest["services"]}
    missing_contracts = []
    for inv_name in _inventory_service_names(repo):
        mapped = _INVENTORY_ALIASES.get(inv_name, inv_name)
        if mapped not in contract_names:
            missing_contracts.append(inv_name)
    for inv_name in sorted(missing_contracts):
        failures.append(f"totality: inventory service '{inv_name}' has no consumer contract")

    result = {
        "gate": "service-feature-ui-contract-gate",
        "version": manifest.get("version"),
        "inventory_totality": "pass" if not missing_contracts else "fail",
        "service_count": len(rows),
        "passed": sum(1 for r in rows if r["status"] == "pass"),
        "failed": sum(1 for r in rows if r["status"] == "fail"),
        "failures": failures,
        "services": rows,
    }
    return not failures, result


def _write_report(result: dict, output: Path) -> None:
    lines = [
        "# service-feature-ui-contract-gate report",
        "",
        f"- services: {result['service_count']}",
        f"- passed: {result['passed']}",
        f"- failed: {result['failed']}",
        "",
    ]
    if result["failures"]:
        lines.append("## Failures")
        lines.append("")
        for failure in result["failures"]:
            lines.append(f"- {failure}")
        lines.append("")
    lines.append("## Service evidence")
    lines.append("")
    for row in result["services"]:
        lines.append(f"### `{row['service']}` — {row['status']}")
        lines.append(f"classification: `{row['classification']}`")
        lines.append(f"wiring disposition: `{row['wiring_disposition']}`")
        lines.append(f"wired: `{row['wired']}`")
        if row["reopen_trigger"]:
            lines.append(f"reopen trigger: `{row['reopen_trigger']}`")
        for evidence in row["evidence"]:
            lines.append(f"- {evidence['kind']}: {evidence['match_count']} match(es)")
            for match in evidence["matches"][:5]:
                lines.append(f"  - `{match['path']}:{match['line']}` ← `{match['pattern']}`")
        lines.append("")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--manifest", default="config/service_feature_ui_contracts.json")
    parser.add_argument(
        "--report", default="docs/backend/service_feature_ui_contract_gate.generated.md"
    )
    parser.add_argument(
        "--json-report", default="docs/backend/service_feature_ui_contract_gate.generated.json"
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    ok, result = run_gate(repo, repo / args.manifest)
    _write_report(result, repo / args.report)
    (repo / args.json_report).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if ok:
        print(
            f"service-feature-ui-contract-gate: PASS ({result['passed']}/{result['service_count']})"
        )
        return 0
    print("service-feature-ui-contract-gate: FAIL")
    for failure in result["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
