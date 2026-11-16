"""routers/observation_feed.py — the pending feed of published observations (W1-11, pull form).

Owner decision of 2026-11-16: indicators-service PULLS published observations from
raster-service; raster-service never calls indicators-service (that push closed a cycle in the
architecture graph). These two service-to-service routes are the only way the outbox
(``raster_observation_outbox``, v286, owned here) leaves this service:

* ``GET /internal/v1/observation-outbox`` — the asserted tenant's ``pending`` entries, oldest
  first (``limit`` 1..200, ``after_id`` cursor). A read: nothing changes.
* ``POST /internal/v1/observation-outbox/acknowledgements`` — settle named entries, each at the
  content it names (``payload_sha256``), from ``pending`` only, with ``delivered``, ``conflict``
  or ``rejected``. Idempotent: the same acknowledgement again answers ``already_acknowledged``.
  Ids that are not the tenant's answer ``not_found``. Nothing is deleted.

Auth, as the other owner routes of this service (``routers/registry_writes.py``): the mesh
service token in ``X-Agent-Token`` (``require_service_token``) and the tenant asserted in the
trusted ``X-Tenant-Id`` header (``REQ_TENANT``), which binds every SQL statement (explicit
predicate plus RLS FORCE under ``app.current_tenant``). No database: 503, never an empty success.
"""

from __future__ import annotations

from typing import Literal

import db_persist
import observation_outbox
import raster_security_context
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


class OutboxAcknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["delivered", "conflict", "rejected"]
    detail: str | None = Field(default=None, max_length=500)


class OutboxAcknowledgements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[OutboxAcknowledgement] = Field(min_length=1, max_length=200)


def _feed_tenant() -> str:
    tenant = raster_security_context.REQ_TENANT.get()
    if not tenant:
        raise HTTPException(403, "X-Tenant-Id is required for the observation outbox")
    if not db_persist._valid_uuid_text(str(tenant)):
        raise HTTPException(400, "the asserted tenant is not a UUID")
    return str(tenant)


def _require_database() -> None:
    if not db_persist.DATABASE_URL:
        raise HTTPException(503, "DATABASE_URL is not configured: the observation outbox is off")


@router.get("/internal/v1/observation-outbox")
async def list_pending_observations(
    limit: int = Query(observation_outbox.FEED_LIMIT_DEFAULT, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    x_agent_token: str | None = Header(None),
) -> dict:
    """The asserted tenant's pending published observations, oldest first."""
    raster_security_context.require_service_token(x_agent_token)
    tenant = _feed_tenant()
    _require_database()
    try:
        entries = await observation_outbox.pending_entries(tenant, limit=limit, after_id=after_id)
    except observation_outbox.OutboxUnavailable as exc:
        raise HTTPException(503, "observation outbox unavailable") from exc
    return {
        "tenant_id": tenant,
        "schema_version": observation_outbox.SCHEMA_VERSION,
        "entries": entries,
        "next_after_id": entries[-1]["id"] if entries else after_id,
    }


@router.post("/internal/v1/observation-outbox/acknowledgements")
async def acknowledge_observations(
    body: OutboxAcknowledgements,
    x_agent_token: str | None = Header(None),
) -> dict:
    """Settle the named entries of the asserted tenant; one result per entry, in order."""
    raster_security_context.require_service_token(x_agent_token)
    tenant = _feed_tenant()
    _require_database()
    ids = [entry.id for entry in body.entries]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "an entry id is named more than once")
    try:
        results = await observation_outbox.acknowledge(
            tenant, [entry.model_dump() for entry in body.entries]
        )
    except observation_outbox.OutboxUnavailable as exc:
        raise HTTPException(503, "observation outbox unavailable") from exc
    return {"tenant_id": tenant, "results": results}
