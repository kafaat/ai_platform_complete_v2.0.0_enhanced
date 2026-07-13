"""Strict client for soil-service governed hydraulic products."""

from __future__ import annotations

import os
from typing import Any

import httpx


async def get_soil_hydraulic_profile(*, tenant_id: str, field_id: str) -> dict[str, Any] | None:
    """Read the latest governed profile. Never synthesize a profile on errors."""
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
                f"{base}/v1/fields/{field_id}/soil/hydraulic-profile",
                headers=headers,
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError, TypeError):
        return None
