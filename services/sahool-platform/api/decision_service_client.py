"""Thin sahool-platform client for decision-service boundary calls.

P4 Decision / Outcome / Learning Boundary Extraction:
- decision-service owns loop write semantics and loop-table persistence;
- sahool-platform may keep auth/rate-limit/BFF routes, but should call this facade
  instead of writing decision/outcome/learning loop tables directly.
"""

from __future__ import annotations

import os
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.

DEFAULT_DECISION_SERVICE_URL = "http://sahool-decision-service:8160"


def decision_service_url() -> str:
    return os.getenv("DECISION_SERVICE_URL", DEFAULT_DECISION_SERVICE_URL).rstrip("/")


def decision_service_headers(
    *, tenant_id: str | None = None, authorization: str | None = None
) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    return headers


def _detail_from_response(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return getattr(resp, "text", "decision-service returned an error")


async def decision_get_json(
    path: str,
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    import httpx
    from fastapi import HTTPException

    url = f"{decision_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(
                url,
                params=params or {},
                headers=decision_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"decision-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def decision_post_json(
    path: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    timeout_s: float = 20.0,
) -> dict[str, Any]:
    import httpx
    from fastapi import HTTPException

    url = f"{decision_service_url()}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=decision_service_headers(tenant_id=tenant_id, authorization=authorization),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"decision-service غير متاح: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_detail_from_response(resp))
    data = resp.json()
    return data if isinstance(data, dict) else {"value": data}


async def record_decision(
    payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json("/v1/decisions/record", payload, tenant_id=tenant_id)


async def record_dispatch_decision(
    payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json("/v1/dispatch/decisions", payload, tenant_id=tenant_id)


async def record_outcome(
    payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json("/v1/outcomes/record", payload, tenant_id=tenant_id)


async def record_recommendation_outcome(
    payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json("/v1/recommendation-outcomes", payload, tenant_id=tenant_id)


async def record_learning_update(
    payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json("/v1/learning/updates", payload, tenant_id=tenant_id)


async def get_learning_summary(
    *, tenant_id: str | None = None, field_id: str | None = None, season_id: str | None = None
) -> dict[str, Any]:
    return await decision_get_json(
        "/v1/learning/summary",
        tenant_id=tenant_id,
        params={"field_id": field_id, "season_id": season_id},
    )


async def get_decision_lineage(decision_id: str, *, tenant_id: str | None = None) -> dict[str, Any]:
    return await decision_get_json(f"/v1/decisions/{decision_id}/lineage", tenant_id=tenant_id)
