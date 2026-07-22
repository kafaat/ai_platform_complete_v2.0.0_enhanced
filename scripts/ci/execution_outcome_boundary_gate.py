#!/usr/bin/env python3
"""WX-10.12 guard: outcome verification must not perform learning updates."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "services/decision-service/main.py").read_text()
persistence = (ROOT / "services/decision-service/persistence.py").read_text()
migration = (
    ROOT / "services/decision-service/migrations/007_execution_outcome_verification.sql"
).read_text()
required = [
    "verify-outcome",
    "verify_execution_outcome",
    "EXECUTION_OUTCOME_VERIFIED",
    "execution_request_id",
    "evidence_snapshot_id",
]
missing = [x for x in required if x not in main + persistence + migration]
forbidden = ["persist_learning_update(", "ONLINE_LEARNING_UPDATE", "model.fit(", "partial_fit("]
segment = persistence[persistence.index("async def verify_execution_outcome") :]
hits = [x for x in forbidden if x in segment]
if missing or hits:
    print(f"WX-10.12 boundary FAILED missing={missing} forbidden={hits}", file=sys.stderr)
    raise SystemExit(1)
print("WX-10.12 execution-outcome boundary: LOCKED")
