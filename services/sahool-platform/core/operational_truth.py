"""Pure canonicalization helpers for S3 historical weather and S11 ERP reconciliation."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def content_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reconciliation_status(expected: Decimal | None, actual: Decimal | None, claimed: str) -> str:
    if claimed == "rejected":
        return claimed
    if expected is None or actual is None:
        raise ValueError("matched/difference reconciliation requires expected and actual amounts")
    calculated = "matched" if expected == actual else "difference"
    if claimed != calculated:
        raise ValueError(f"claimed status {claimed!r} conflicts with calculated {calculated!r}")
    return calculated
