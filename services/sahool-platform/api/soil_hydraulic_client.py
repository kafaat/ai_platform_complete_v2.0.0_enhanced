"""Strict client for soil-service governed hydraulic products.

Covers the hydraulic profile and the drainage (waterlogging) assessment. Both tables belong
to soil-service; the platform reads them over HTTP only and never synthesizes a product.
"""

from __future__ import annotations

import math
import os
from typing import Any

import httpx

_DRAINAGE_NEEDS = frozenset({"none", "monitor", "surface", "subsurface", "combined"})


async def _soil_get_json(path: str, *, tenant_id: str) -> dict | None:
    """GET a soil-service product path; ``None`` on absence or any failure (never synthesized)."""
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
            response = await client.get(f"{base}{path}", headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def get_soil_hydraulic_profile(*, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    """Read the latest governed profile. Never synthesize a profile on errors."""
    return await _soil_get_json(
        f"/v1/fields/{field_id}/soil/hydraulic-profile", tenant_id=tenant_id
    )


def parse_drainage_assessment(payload: object) -> dict | None:
    """soil-service ``DrainageAssessmentProduct`` JSON ⇒ irrigation policy ``waterlogging`` input.

    Pure. Returns ``{"risk", "drainage_need", "assessment_id", "generated_at"}`` or ``None``
    when the payload carries neither a valid ``waterlogging_risk`` in [0, 1] nor a known
    ``drainage_need`` — an unreadable assessment is *unknown*, never "no risk".
    """
    if not isinstance(payload, dict):
        return None
    raw_risk = payload.get("waterlogging_risk")
    risk = None
    if isinstance(raw_risk, (int, float)) and not isinstance(raw_risk, bool):
        value = float(raw_risk)
        if math.isfinite(value) and 0.0 <= value <= 1.0:
            risk = value
    raw_need = payload.get("drainage_need")
    need = raw_need.strip().lower() if isinstance(raw_need, str) else None
    if need not in _DRAINAGE_NEEDS:
        need = None
    if risk is None and need is None:
        return None
    return {
        "risk": risk,
        "drainage_need": need,
        "assessment_id": payload.get("product_id"),
        "generated_at": payload.get("generated_at"),
    }


async def get_field_waterlogging(tenant_id: object, field_id: str) -> dict | None:
    """Latest soil-service drainage assessment for the field, parsed; ``None`` if unavailable.

    No tenant ⇒ ``None`` (unknown): the read is tenant-scoped and is never made unscoped.
    """
    if tenant_id is None or not str(tenant_id):
        return None
    payload = await _soil_get_json(
        f"/v1/fields/{field_id}/soil/drainage-assessment", tenant_id=str(tenant_id)
    )
    return parse_drainage_assessment(payload)
