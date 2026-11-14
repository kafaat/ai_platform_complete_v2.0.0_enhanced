"""Strict client for soil-service governed products.

Covers the hydraulic profile, the drainage (waterlogging) assessment and the soil-sampling plan
copies with their plan-point origin resolution (gap P6). Those tables belong to soil-service; the
platform reaches them over HTTP only and never synthesizes a product or a plan origin.
"""

from __future__ import annotations

import math
import os
from typing import Any
from urllib.parse import quote

import httpx

_DRAINAGE_NEEDS = frozenset({"none", "monitor", "surface", "subsurface", "combined"})


def _soil_base() -> str:
    return os.getenv("SOIL_SERVICE_URL", "http://sahool-soil-service:8000").rstrip("/")


def _soil_token() -> str | None:
    return (
        os.getenv("INTERNAL_SERVICE_TOKEN")
        or os.getenv("SOIL_SERVICE_TOKEN")
        or os.getenv("SAHOOL_AGENT_TOKEN")
    )


async def _soil_get_json(path: str, *, tenant_id: str) -> dict | None:
    """GET a soil-service product path; ``None`` on absence or any failure (never synthesized)."""
    base = _soil_base()
    token = _soil_token()
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


# ── Soil-sampling plan provenance (gap P6) ──────────────────────────────────────────────────
# A lab sample that names a plan point is stored with the origin soil-service resolves from its
# stored plan copy. The client's planned position, zone and imagery are never stored as the
# origin. Unlike the product reads above, a failure here is never "absent": the caller must
# refuse the sample (fail closed), so every outcome is either a verified origin, a typed
# refusal, or ``SamplingPlanVerificationUnavailable``.

_ORIGIN_REFUSALS = frozenset(
    {
        "sampling_plan_not_found",
        "sampling_point_not_in_plan",
        "sampling_origin_out_of_tolerance",
        "sampling_collection_position_invalid",
    }
)


class SamplingPlanVerificationUnavailable(RuntimeError):
    """soil-service could not verify the plan point (unreachable, misconfigured or malformed)."""


class SamplingOriginRefused(ValueError):
    """soil-service refused the plan point; ``detail`` carries its typed ``code``."""

    def __init__(self, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("code"))
        self.detail = detail


def _plan_copy_path(field_id: str, plan_id: str | None = None) -> str:
    path = f"/v1/fields/{quote(field_id, safe='')}/soil/sampling-plan-copies"
    return path if plan_id is None else f"{path}/{quote(plan_id, safe='')}/origin"


async def _soil_post(path: str, *, tenant_id: str, body: dict[str, Any]) -> httpx.Response:
    token = _soil_token()
    if not token:
        raise SamplingPlanVerificationUnavailable("soil-service token is not configured")
    headers = {"X-Agent-Token": token, "X-Tenant-Id": tenant_id}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            return await client.post(f"{_soil_base()}{path}", json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise SamplingPlanVerificationUnavailable(type(exc).__name__) from exc


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _verified_origin(
    payload: Any, *, plan_id: str, point_id: str, latitude: float, longitude: float
) -> dict[str, Any]:
    """The resolved origin if soil-service's answer is one, else ``Unavailable`` (never stored)."""
    collection = payload.get("collection") if isinstance(payload, dict) else None
    if not (
        isinstance(payload, dict)
        and payload.get("plan_id") == plan_id
        and payload.get("point_id") == point_id
        and payload.get("verification") == "stored_plan"
        and payload.get("resolved_by") == "soil-service"
        and isinstance(payload.get("plan_digest"), str)
        and _number(payload.get("latitude"))
        and _number(payload.get("longitude"))
        and isinstance(collection, dict)
        and collection.get("latitude") == latitude
        and collection.get("longitude") == longitude
        and _number(collection.get("deviation_m"))
        and isinstance(collection.get("on_plan"), bool)
    ):
        raise SamplingPlanVerificationUnavailable("soil-service returned no verified origin")
    return payload


async def resolve_sampling_origin(
    *,
    tenant_id: str,
    field_id: str,
    plan_id: str,
    point_id: str,
    latitude: float,
    longitude: float,
    gps_accuracy_m: float | None,
    deviation_reason: str | None,
    claimed: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ask soil-service for the origin of a plan-point sample, resolved from its stored copy."""
    response = await _soil_post(
        _plan_copy_path(field_id, plan_id),
        tenant_id=tenant_id,
        body={
            "point_id": point_id,
            "latitude": latitude,
            "longitude": longitude,
            "gps_accuracy_m": gps_accuracy_m,
            "deviation_reason": deviation_reason,
            "claimed": claimed,
        },
    )
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code in (404, 422):
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict) and detail.get("code") in _ORIGIN_REFUSALS:
            raise SamplingOriginRefused(detail)
        raise SamplingPlanVerificationUnavailable(f"soil-service answered {response.status_code}")
    if response.status_code != 200:
        raise SamplingPlanVerificationUnavailable(f"soil-service answered {response.status_code}")
    return _verified_origin(
        payload, plan_id=plan_id, point_id=point_id, latitude=latitude, longitude=longitude
    )


async def store_sampling_plan_copies(
    *, tenant_id: str, field_id: str, plans: list[dict[str, Any]], source: str
) -> dict[str, Any]:
    """Hand the planner's plans to soil-service, which stores the copies it owns."""
    response = await _soil_post(
        _plan_copy_path(field_id), tenant_id=tenant_id, body={"plans": plans, "source": source}
    )
    if response.status_code != 201:
        raise SamplingPlanVerificationUnavailable(f"soil-service answered {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise SamplingPlanVerificationUnavailable("soil-service answered no JSON") from exc
    if not isinstance(payload, dict) or not _number(payload.get("stored")):
        raise SamplingPlanVerificationUnavailable("soil-service answered no plan-copy receipt")
    return payload
