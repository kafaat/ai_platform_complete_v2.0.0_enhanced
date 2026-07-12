"""Point-in-time field history composer; rejects future data leakage.

``compose`` keeps only records whose availability timestamp is at or before the
decision cutoff, sorts them deterministically, and stamps the body with a
content hash — the same PIT discipline enforced by the decision-service AC-1
composer, applied at the AgriAI boundary.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _dt(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(UTC)


def compose(
    field_id: str, season_id: str, decision_at: str, records: list[dict[str, Any]]
) -> dict[str, Any]:
    cutoff = _dt(decision_at)
    accepted = []
    for r in records:
        available = r.get("data_available_at") or r.get("created_at")
        if not available:
            continue  # no availability evidence -> excluded, never assumed
        if _dt(str(available)) <= cutoff:
            accepted.append(r)
    accepted.sort(key=lambda r: (str(r.get("observed_at") or ""), str(r.get("id") or "")))
    body = {
        "contract_version": "field-history.v1",
        "field_id": field_id,
        "season_id": season_id,
        "decision_at": decision_at,
        "records": accepted,
        "record_count": len(accepted),
    }
    body["snapshot_hash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return body
