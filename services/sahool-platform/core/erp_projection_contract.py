
"""Provider-neutral Farm Ledger -> ERP projection identity.

This module creates no ERP write. It freezes the exact projection payload so a later
provider receipt can be reconciled against what SAHOOL actually intended to post.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_VERSION = "farm_ledger_erp_projection.v1"


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def build_projection_envelope(
    *,
    season_id: str,
    lines: list[dict[str, Any]],
    provider: str = "none",
    currency: str | None = None,
) -> dict[str, Any]:
    """Freeze a read-only ERP projection.

    ``posting_eligible`` deliberately remains false for provider=none or an empty
    projection. Actual transmission belongs to the ERP bridge/provider adapter.
    """
    if not str(season_id or "").strip():
        raise ValueError("season_id is required")
    clean_lines = [dict(line) for line in lines if isinstance(line, dict)]
    provider_name = str(provider or "none").strip().lower() or "none"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "season_id": season_id,
        "provider": provider_name,
        "currency": str(currency).upper() if currency else None,
        "lines": clean_lines,
    }
    return {
        **payload,
        "projection_digest": canonical_digest(payload),
        "posting_eligible": provider_name != "none" and bool(clean_lines),
        "erp_write": False,
        "authority": "farm_ledger_projection_only",
    }


def verify_reconciliation_binding(
    *,
    stored_payload: dict[str, Any],
    stored_provider: str,
    stored_status: str,
    stored_sent_at: Any,
    receipt_provider: str,
    evidence: dict[str, Any],
) -> str:
    """Return the bound projection digest or fail closed.

    Reconciliation proves equality to the stored projection, not merely existence
    of an outbox identifier.
    """
    if not isinstance(stored_payload, dict):
        raise ValueError("stored ERP projection payload is invalid")
    expected = canonical_digest(stored_payload)
    supplied = str((evidence or {}).get("projection_digest") or "").strip().lower()
    if not supplied:
        raise ValueError("projection_digest evidence is required")
    if supplied != expected:
        raise ValueError("projection_digest_mismatch")
    delivery_status = str(stored_status or "").strip().lower()
    if delivery_status != "sent":
        raise ValueError("erp_projection_not_sent")
    if stored_sent_at is None:
        raise ValueError("erp_projection_missing_sent_at")
    configured = str(stored_provider or "none").strip().lower()
    actual = str(receipt_provider or "").strip().lower()
    if configured == "none":
        raise ValueError("erp_projection_has_no_provider")
    if actual != configured:
        raise ValueError("erp_provider_mismatch")
    return expected
