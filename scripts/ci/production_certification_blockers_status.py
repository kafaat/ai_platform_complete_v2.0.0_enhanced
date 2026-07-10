#!/usr/bin/env python3
"""Print the current status of the four production certification blockers.

This script is intentionally read-only. It does not promote certification and
it does not convert local/sandbox checks into deployment evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "certification" / "evidence"

BLOCKERS = [
    ("P-CERT-1", "Full branch CI", "ci_summary.json", False),
    ("P-CERT-2", "Connected transitive lock generation", "transitive_locks_summary.json", False),
    ("P-CERT-3", "Redis live integration", "redis_live_test_summary.json", True),
    ("P-CERT-4", "ONNX/SAM2 model provisioning", "model_provisioning_summary.json", False),
]


def _load(path: Path) -> dict:
    if not path.exists():
        return {"status": "missing", "timestamp_utc": None}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    rows = []
    for blocker_id, name, filename, waivable in BLOCKERS:
        payload = _load(EVIDENCE_DIR / filename)
        status = payload.get("status", "unknown")
        rows.append(
            {
                "blocker_id": blocker_id,
                "name": name,
                "status": status,
                "waivable": waivable,
                "file": f"certification/evidence/{filename}",
                "timestamp_utc": payload.get("timestamp_utc"),
            }
        )
    certified = all(row["status"] == "verified" or (row["waivable"] and row["status"] == "waived_with_reason") for row in rows)
    print(json.dumps({"production_certified": certified, "blockers": rows}, indent=2, ensure_ascii=False))
    if certified:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
