#!/usr/bin/env python3
"""Production evidence pack guard.

This guard creates and validates a strict evidence manifest for Sahool production
certification. It intentionally keeps the repository in release-candidate state
until external CI/deployment evidence is attached for every blocker.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"
MANIFEST = EVIDENCE_DIR / "production_evidence_manifest.generated.json"
RUNBOOK = ROOT / "docs" / "runbooks" / "PRODUCTION_EVIDENCE_PACK.md"

BLOCKERS = [
    {
        "id": "P-CERT-2",
        "name": "Connected transitive lock generation",
        "required_file": "transitive_locks_summary.json",
        "required_status": "verified",
        "waivable": False,
        "minimum_fields": ["status", "command", "index_url_policy", "lock_files", "timestamp_utc"],
    },
    {
        "id": "P-CERT-1",
        "name": "Full branch CI",
        "required_file": "ci_summary.json",
        "required_status": "verified",
        "waivable": False,
        "minimum_fields": ["status", "branch", "commit", "jobs", "timestamp_utc"],
    },
    {
        "id": "P-CERT-4",
        "name": "ONNX/SAM2 model provisioning",
        "required_file": "model_provisioning_summary.json",
        "required_status": "verified",
        "waivable": False,
        "minimum_fields": [
            "status",
            "edge_readiness_mode",
            "edge_production_required",
            "artifacts",
            "timestamp_utc",
        ],
    },
    {
        "id": "P-CERT-3",
        "name": "Redis live integration",
        "required_file": "redis_live_test_summary.json",
        "required_status": "verified",
        "waivable": True,
        "minimum_fields": [
            "status",
            "redis_url_kind",
            "test_command",
            "readyz_cache_backend",
            "timestamp_utc",
        ],
    },
    {
        "id": "GUARDS",
        "name": "Guard results summary",
        "required_file": "guard_results_summary.json",
        "required_status": "verified",
        "waivable": False,
        "minimum_fields": ["status", "guards", "timestamp_utc"],
    },
]

TEMPLATE_STATUS = {
    "certification_state": "release_candidate_not_production_certified",
    "allowed_states": ["pending", "evidence_attached", "verified", "waived_with_reason", "failed"],
    "non_waivable_blockers": ["P-CERT-1", "P-CERT-2", "P-CERT-4", "GUARDS"],
    "policy": "Do not set production_certified until every non-waivable blocker has verified evidence from target CI/deployment.",
}


def _placeholder(item: dict) -> dict:
    return {
        "blocker_id": item["id"],
        "name": item["name"],
        "status": "pending",
        "required_status": item["required_status"],
        "waivable": item["waivable"],
        "minimum_fields": item["minimum_fields"],
        "timestamp_utc": None,
        "notes": "Attach real CI/deployment evidence here; pending placeholders are not certification evidence.",
    }


def manifest_payload() -> dict:
    evidence_files = []
    for item in BLOCKERS:
        p = EVIDENCE_DIR / item["required_file"]
        status = "missing"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                status = data.get("status", "unknown")
            except Exception:
                status = "invalid_json"
        evidence_files.append(
            {
                "blocker_id": item["id"],
                "name": item["name"],
                "file": f"certification/evidence/{item['required_file']}",
                "current_status": status,
                "required_status": item["required_status"],
                "waivable": item["waivable"],
                "minimum_fields": item["minimum_fields"],
            }
        )
    return {"schema_version": 1, **TEMPLATE_STATUS, "evidence_files": evidence_files}


def write_files() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for item in BLOCKERS:
        p = EVIDENCE_DIR / item["required_file"]
        if not p.exists():
            p.write_text(
                json.dumps(_placeholder(item), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    MANIFEST.write_text(
        json.dumps(manifest_payload(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    RUNBOOK.write_text(runbook_text(), encoding="utf-8")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid evidence JSON {path}: {exc}") from exc


def check_files() -> None:
    if not MANIFEST.exists():
        raise SystemExit("production evidence manifest missing; run with --write")
    for item in BLOCKERS:
        p = EVIDENCE_DIR / item["required_file"]
        if not p.exists():
            raise SystemExit(f"missing evidence placeholder/file: {p}")
        data = _load_json(p)
        for field in ["status", "timestamp_utc"]:
            if field not in data:
                raise SystemExit(f"{p} missing required evidence field {field}")
        status = data.get("status")
        if status == "production_certified":
            raise SystemExit(f"{p} must use verified, not production_certified")
        if status == "waived_with_reason" and not item["waivable"]:
            raise SystemExit(f"{item['id']} is non-waivable")
        if status == "verified":
            missing = [f for f in item["minimum_fields"] if f not in data]
            if missing:
                raise SystemExit(f"{p} verified but missing fields: {', '.join(missing)}")
    expected = json.dumps(manifest_payload(), indent=2, ensure_ascii=False) + "\n"
    actual = MANIFEST.read_text(encoding="utf-8")
    if actual != expected:
        raise SystemExit("production evidence manifest drift; run with --write")
    if (
        not RUNBOOK.exists()
        or "release_candidate_not_production_certified" not in RUNBOOK.read_text(encoding="utf-8")
    ):
        raise SystemExit("production evidence runbook missing or incomplete")
    print("production_evidence_pack_check_ok")


def runbook_text() -> str:
    lines = [
        "# Production Evidence Pack",
        "",
        "This evidence pack prevents report-only certification. The repository remains `release_candidate_not_production_certified` until real CI/deployment artifacts verify every non-waivable blocker.",
        "",
        "## Evidence files",
        "",
    ]
    for item in BLOCKERS:
        lines.extend(
            [
                f"### {item['id']} — {item['name']}",
                "",
                f"- File: `certification/evidence/{item['required_file']}`",
                f"- Required status: `{item['required_status']}`",
                f"- Waivable: `{str(item['waivable']).lower()}`",
                f"- Minimum fields when verified: `{', '.join(item['minimum_fields'])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## State machine",
            "",
            "Allowed evidence states: `pending`, `evidence_attached`, `verified`, `waived_with_reason`, `failed`.",
            "",
            "Non-waivable: `P-CERT-1`, `P-CERT-2`, `P-CERT-4`, and `GUARDS`.",
            "",
            "`P-CERT-3` may be waived only with an explicit reason and only when Redis is not used for correctness/state in the target deployment.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write:
        write_files()
    if args.check or not args.write:
        check_files()


if __name__ == "__main__":
    main()
