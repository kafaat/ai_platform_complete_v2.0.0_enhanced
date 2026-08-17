"""Strict client for soil-service's governed profile snapshot.

Never synthesizes a profile on errors; absence must propagate as ``None``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


async def resolve_canonical_soil_state(*, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    """Read the latest governed soil profile and normalize its schema key.

    soil-service publishes ``contract_version: "soil-profile.v1"`` at the top level;
    ``canonical_field_state``'s schema check only recognizes ``schema_version``/``schema``.
    This adds ``schema_version`` from ``contract_version`` without dropping the original
    field. Never synthesizes a profile — returns ``None`` on any failure or absence.
    """
    base = os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000").rstrip("/")
    token = (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("SOIL_SERVICE_TOKEN")
        or os.getenv("SAHOOL_AGENT_TOKEN")
    )
    if not token:
        return None
    headers = {"X-Agent-Token": token, "X-Tenant-Id": tenant_id}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{base}/v1/fields/{field_id}/soil/profile",
                headers=headers,
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    contract_version = payload.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version:
        if "schema_version" not in payload and "schema" not in payload:
            return None
    normalized = dict(payload)
    if "schema_version" not in normalized and "schema" not in normalized:
        normalized["schema_version"] = contract_version
    # Translate soil-service's governed quality gate into the shared owner declaration.
    # Do not promote a non-executable profile to healthy: it remains present for diagnosis
    # but cannot silently make ``propose`` eligible.
    gate = (
        normalized.get("quality_gate") if isinstance(normalized.get("quality_gate"), dict) else {}
    )
    executable = gate.get("executable")
    passed = gate.get("passed")
    if "quality_status" not in normalized:
        normalized["quality_status"] = (
            "verified" if passed is True and executable is True else "degraded"
        )
    reasons = list(gate.get("reasons") or [])
    if reasons and "limitations" not in normalized:
        normalized["limitations"] = reasons
    if executable is False:
        normalized["operational_eligible"] = False
    return normalized
