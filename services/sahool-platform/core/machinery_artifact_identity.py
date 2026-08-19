"""Canonical identity digests for persisted machinery export artifacts.

These helpers are shared by the export producer and as-applied verifier so the
content/lineage identity contract has exactly one implementation.  They are pure
and contain no transport or persistence authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def prescription_content_digest(prescription: dict[str, Any]) -> str:
    """Digest the exact saved prescription content frozen into a machine artifact."""
    return _sha256_json(
        {
            "prescription_id": prescription.get("prescription_id"),
            "field_id": prescription.get("field_id"),
            "season_id": prescription.get("season_id"),
            "name": prescription.get("name"),
            "product_type": prescription.get("product_type"),
            "zones": prescription.get("zones") or [],
        }
    )


def zone_lineage_digest(prescription: dict[str, Any]) -> str:
    """Digest only the zone->source-lineage mapping frozen at export time."""
    lineage = [
        {
            "zone_id": zone.get("zone_id"),
            "source_lineage": zone.get("source_lineage") or {},
        }
        for zone in (prescription.get("zones") or [])
        if isinstance(zone, dict)
    ]
    return _sha256_json(lineage)
