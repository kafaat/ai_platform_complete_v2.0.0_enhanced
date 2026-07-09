#!/usr/bin/env python3
"""Generate/check REPORT_INDEX.md for release artifacts and historical reports."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "REPORT_INDEX.md"
SECTIONS = {
    "Current release candidate": [
        "PRODUCTION_CERTIFICATION_PLATFORM_SUBINVENTORY_CORRECTION_REPORT_20260709.md",
        "P2_MAIN_DECOMPOSITION_COMPLETE_REPORT_20260709.md",
        "P1_MAIN_DECOMPOSITION_COMPLETE_REPORT_20260709.md",
        "AI_AGRONOMIST_MAIN_DECOMPOSITION_P0_REPORT_20260709.md",
        "AUTH_MAIN_DECOMPOSITION_P0_REPORT_20260709.md",
        "INDICATORS_CONTAINER_REVIEW_AND_FIX_REPORT_20260709.md",
        "VEGETATION_CONTAINER_REVIEW_AND_FIX_REPORT_20260709.md",
        "PIP_AUDIT_REDIS_RESOLUTION_FIX_REPORT_20260709.md",
        "CONTAINER_FLEET_REVIEW_AND_FIX_REPORT_20260709.md",
        "AI_CONTAINER_REVIEW_AND_FIX_REPORT_20260709.md",
    ],
    "Production certification": [
        "docs/runbooks/PRODUCTION_CERTIFICATION_CHECKLIST.md",
        "docs/runbooks/PRODUCTION_EVIDENCE_PACK.md",
        "production_certification_checklist.generated.json",
        "certification/evidence/production_evidence_manifest.generated.json",
    ],
    "Inventories": [
        "SERVICE_REGISTRY.md",
        "route_inventory.generated.json",
        "service_inventory.generated.json",
        "route_residual_classification.generated.json",
        "platform_main_subinventory.generated.json",
        "route_mount_inventory.generated.json",
        "api_versioning_inventory.generated.json",
        "container_fleet_audit.generated.json",
        "ai_container_audit.generated.json",
    ],
    "Operational runbooks": [
        "docs/runbooks/ALIBABA_PYPI_MIRROR.md",
        "docs/runbooks/EDGE_MODEL_PROVISIONING_CHECKLIST.md",
        "docs/runbooks/WEATHER_REDIS_INTEGRATION.md",
    ],
}


def build_text() -> str:
    lines = [
        "# Sahool Report Index",
        "",
        "This index identifies the current release-candidate evidence and separates it from historical reports. Prefer the files in the first two sections when making release decisions.",
        "",
    ]
    for title, files in SECTIONS.items():
        lines.extend([f"## {title}", ""])
        for file in files:
            exists = "present" if (ROOT / file).exists() else "missing"
            lines.append(f"- `{file}` — {exists}")
        lines.append("")
    historical = sorted(p.name for p in ROOT.glob("*_REPORT*.md") if p.name not in {Path(f).name for files in SECTIONS.values() for f in files})
    lines.extend(["## Historical reports", ""])
    for name in historical[:80]:
        lines.append(f"- `{name}`")
    if len(historical) > 80:
        lines.append(f"- ... {len(historical) - 80} additional historical reports omitted from this index view")
    lines.append("")
    return "\n".join(lines)


def write() -> None:
    REPORT.write_text(build_text(), encoding="utf-8")


def check() -> None:
    expected = build_text()
    if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != expected:
        raise SystemExit("REPORT_INDEX.md drift; run scripts/ci/report_index_guard.py --write")
    for title, files in SECTIONS.items():
        for file in files:
            if not (ROOT / file).exists():
                raise SystemExit(f"report index required file missing: {file}")
    print("report_index_check_ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write()
    if args.check or not args.write:
        check()


if __name__ == "__main__":
    main()
