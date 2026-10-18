"""Adapters for the durable follow-up scheduler; no user tokens survive admission."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from fastapi import HTTPException
from follow_up_store import FollowUpStore
from follow_up_worker import PermanentFailure, RetryLater
from imagery_product_identity import canonical_processing_version
from raster_date_geo import bbox_from_geojson

from shared.contracts.imagery_followup import POLICY_VERSION, ImageryFollowUpRequest

store = FollowUpStore()


def configured_tenants() -> tuple[str, ...]:
    # Explicit worker partition. No cross-tenant enumeration or BYPASSRLS role.
    return tuple(
        sorted(
            {
                str(UUID(t.strip()))
                for t in os.getenv("RASTER_FOLLOWUP_TENANTS", "").split(",")
                if t.strip()
            }
        )
    )


def aware_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(UTC)


async def receipt_context(tenant: str, execution: str) -> dict:
    from urllib.parse import quote

    bearer = os.getenv("DECISION_SERVICE_AUTH_TOKEN", "").strip()
    if not bearer:
        raise HTTPException(503, "authoritative_receipt_source_unconfigured")
    base = os.getenv("DECISION_SERVICE_URL", "http://sahool-decision-service:8160").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.get(
                f"{base}/v1/execution-requests/{quote(execution, safe='')}/observation-context",
                headers={"Authorization": f"Bearer {bearer}", "X-Tenant-Id": tenant},
            )
        if response.status_code == 404:
            raise HTTPException(409, "accepted_execution_receipt_required")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "authoritative_receipt_source_unavailable") from exc


async def geometry_snapshot(tenant: str, field: str) -> dict:
    async with store.transaction(tenant) as conn:
        row = await conn.fetchrow(
            """SELECT h.revision,h.geometry FROM fields f
            JOIN field_geometry_history h ON h.tenant_id=f.tenant_id AND h.field_id=f.field_id
            WHERE f.tenant_id=$1::uuid AND f.field_id=$2 AND h.geometry=f.geometry::jsonb
            ORDER BY h.revision DESC LIMIT 1""",
            tenant,
            field,
        )
    if row is None:
        raise HTTPException(409, "visible_versioned_field_geometry_required")
    geometry = json.loads(row["geometry"]) if isinstance(row["geometry"], str) else row["geometry"]
    bbox = bbox_from_geojson(geometry)
    if not bbox or len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise HTTPException(409, "invalid_field_geometry")
    return {"geometry_revision": row["revision"], "geometry": geometry, "bbox": bbox}


def bind_receipt(tenant: str, field: str, request: ImageryFollowUpRequest, context: dict):
    expected = {
        "tenant_id": tenant,
        "field_id": field,
        "season_id": request.season_id,
        "execution_request_id": request.execution_request_id,
        "time_basis": "delivery_receipt_received_at",
    }
    if any(context.get(k) != v for k, v in expected.items()) or not context.get("receipt_id"):
        raise HTTPException(409, "execution_receipt_scope_mismatch")
    try:
        anchor = aware_time(context["received_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(503, "invalid_authoritative_receipt_time") from exc
    if anchor > datetime.now(UTC):
        raise HTTPException(409, "execution_receipt_in_future")
    due = anchor + timedelta(days=request.days_after)
    expires = due + timedelta(days=request.window_days)
    return due, expires


async def admission_payload(tenant: str, field: str, request: ImageryFollowUpRequest):
    context = await receipt_context(tenant, request.execution_request_id)
    due, expires = bind_receipt(tenant, field, request, context)
    if expires <= datetime.now(UTC):
        raise HTTPException(409, "observation_window_already_expired")
    geometry = await geometry_snapshot(tenant, field)
    return (
        {
            **request.model_dump(),
            **geometry,
            "receipt_id": context["receipt_id"],
            "anchor_at": context["received_at"],
            "time_basis": context["time_basis"],
            "policy_version": POLICY_VERSION,
            "processing_version": canonical_processing_version(),
        },
        due,
        expires,
    )


def select_scene(items: list[dict], start: datetime, end: datetime) -> dict | None:
    eligible = []
    for item in items:
        try:
            at = aware_time(item["datetime"])
            cloud = float(item["cloud_cover_pct"])
            if (
                item.get("cloud_cover_known") is True
                and not isinstance(item["cloud_cover_pct"], bool)
                and item.get("provider") in {"cdse", "element84"}
                and item.get("item_id")
                and start <= at <= end
                and math.isfinite(cloud)
                and 0 <= cloud <= 30
            ):
                eligible.append((cloud, at, item["item_id"], item))
        except (KeyError, TypeError, ValueError):
            continue  # Missing quality is unknown, never zero cloud.
    return min(eligible, key=lambda v: v[:3])[3] if eligible else None


async def process(row: dict, lease_store: FollowUpStore) -> dict:
    import db_persist
    from stac_search import stac_search

    payload = row["request_payload"]
    tenant = str(row["tenant_id"])
    # Verify ownership again after days of waiting, using a scoped DB query, not a cached header.
    async with lease_store.transaction(tenant) as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM fields WHERE tenant_id=$1::uuid AND field_id=$2",
            tenant,
            row["field_id"],
        )
    if not owned:
        raise PermanentFailure("field_not_visible")
    if payload["processing_version"] != canonical_processing_version():
        raise PermanentFailure("processing_version_changed")
    progress = row.get("result_payload") or {}
    if not progress.get("scene"):
        end = min(datetime.now(UTC), row["expires_at"])
        try:
            found = await stac_search(
                payload["bbox"],
                row["due_at"].isoformat(),
                end.isoformat(),
                30,
                100,
                geometry=payload["geometry"],
            )
        except (httpx.HTTPError, HTTPException) as exc:
            if isinstance(exc, HTTPException) and exc.status_code in {400, 401, 403, 422}:
                raise PermanentFailure("catalog_configuration_rejected") from exc
            raise RetryLater("catalog_unavailable") from exc
        scene = select_scene(found.get("items", []), row["due_at"], end)
        if scene is None:
            raise RetryLater("no_suitable_scene", no_scene=True)
        progress = {
            "scene": {k: scene[k] for k in ("item_id", "datetime", "provider", "cloud_cover_pct")},
            "jobs": [],
            "observation_verified": False,
        }
        if not await lease_store.save_progress(row, progress):
            raise PermanentFailure("lease_lost")
    scene = progress["scene"]
    completed = {job["indicator"] for job in progress["jobs"]}
    for indicator in payload["indicators"]:
        if indicator in completed:
            continue
        if not await lease_store.owns(row):
            raise PermanentFailure("lease_lost")
        job = await db_persist.enqueue_single_scene_process(
            tenant_id=tenant,
            field_id=row["field_id"],
            acquisition_date=scene["datetime"][:10],
            index_name=indicator,
            scene_id=scene["item_id"],
            provider=scene["provider"],
            geometry_revision=payload["geometry_revision"],
            clip_polygon_geojson=payload["geometry"],
            max_cloud_pct=30,
            apply_cloud_mask=True,
        )
        if not job:
            raise RetryLater("raster_enqueue_unavailable")
        if job.get("status") == "radiometry_unresolved":
            raise PermanentFailure("radiometry_unresolved")
        if job.get("status") not in {"already_ready", "in_progress", "planned"}:
            raise PermanentFailure("raster_enqueue_contract_mismatch")
        if job["status"] == "already_ready" and not job.get("item_id"):
            # Legacy asset preflight does not bind provider/processing version.
            # Only accept the existing canonical queue item's durable reference.
            raise PermanentFailure("ready_product_identity_unproven")
        if not job.get("item_id"):
            raise RetryLater("raster_durable_reference_missing")
        # already_ready with an item ID is an existing persisted canonical queue item.
        progress["jobs"].append(
            {
                "indicator": indicator,
                **{k: job.get(k) for k in ("status", "run_id", "item_id", "reused_existing_job")},
            }
        )
        if not await lease_store.save_progress(row, progress):
            raise PermanentFailure("lease_lost")
    return progress


async def startup_check(tenants: tuple[str, ...]):
    if not tenants:
        return
    async with store.transaction(tenants[0]) as conn:
        role = await conn.fetchrow(
            "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
        )
        if not role or role["rolsuper"] or role["rolbypassrls"]:
            raise RuntimeError("follow_up_requires_restricted_database_role")
        table = await conn.fetchrow(
            "SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=to_regclass('public.raster_follow_up_requests')"
        )
        if not table or not table["relrowsecurity"] or not table["relforcerowsecurity"]:
            raise RuntimeError("follow_up_requires_v236_force_rls")
        await conn.fetchval("SELECT count(*) FROM raster_follow_up_requests")
