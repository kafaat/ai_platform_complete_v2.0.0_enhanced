"""routers/observation_feed.py — the pending feed of published observations (W1-11, pull form).

Owner decision of 2026-11-16: indicators-service PULLS published observations from
raster-service; raster-service never calls indicators-service (that push closed a cycle in the
architecture graph). These two service-to-service routes are the only way the outbox
(``raster_observation_outbox``, v286, owned here) leaves this service:

* ``GET /internal/v1/observation-outbox`` — the asserted tenant's entries in ``status``
  (default ``pending``, what the drain reads; ``conflict``, ``rejected`` or ``delivered`` for
  inspection, with ``last_error``, ``attempts`` and ``requeue_history``), oldest first
  (``limit`` 1..200, ``after_id`` cursor). A read: nothing changes.
* ``POST /internal/v1/observation-outbox/acknowledgements`` — settle named entries, each at the
  content it names (``payload_sha256``), from ``pending`` only, with ``delivered``, ``conflict``
  or ``rejected``. Idempotent: the same acknowledgement again answers ``already_acknowledged``.
  Ids that are not the tenant's answer ``not_found``. Nothing is deleted.
* ``POST /internal/v1/observation-outbox/requeue`` — the operator's explicit action that moves
  named ``conflict`` / ``rejected`` entries back to ``pending`` (each at the content it names).
  It needs the service token AND the operator token (``X-Operator-Token`` against
  ``RASTER_OBSERVATION_OUTBOX_OPERATOR_TOKEN``; unset ⇒ 503, the action is off), an ``actor``
  and a ``reason``; who, when and why are appended to the row's ``requeue_history``. Nothing
  in either service calls it on its own.

Auth, as the other owner routes of this service (``routers/registry_writes.py``): the mesh
service token in ``X-Agent-Token`` (``require_service_token``) and the tenant asserted in the
trusted ``X-Tenant-Id`` header (``REQ_TENANT``), which binds every SQL statement (explicit
predicate plus RLS FORCE under ``app.current_tenant``). No database: 503, never an empty success.
"""

from __future__ import annotations

import hmac
import os
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


class OutboxRequeueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OutboxRequeue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[OutboxRequeueEntry] = Field(min_length=1, max_length=50)
    actor: str = Field(pattern=r"^[A-Za-z0-9_.@:-]{2,120}$")
    reason: str = Field(min_length=8, max_length=500)


def _require_operator_token(x_operator_token: str | None) -> None:
    expected = os.getenv("RASTER_OBSERVATION_OUTBOX_OPERATOR_TOKEN", "")
    if not expected:
        raise HTTPException(503, "the observation outbox re-queue is not configured")
    if not hmac.compare_digest(x_operator_token or "", expected):
        raise HTTPException(403, "operator token required to re-queue an outbox entry")


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
    status: Literal["pending", "conflict", "rejected", "delivered"] = Query("pending"),
    x_agent_token: str | None = Header(None),
) -> dict:
    """The asserted tenant's published observations in ``status`` (default pending), oldest
    first."""
    raster_security_context.require_service_token(x_agent_token)
    tenant = _feed_tenant()
    _require_database()
    try:
        if status == observation_outbox.PENDING:
            entries = await observation_outbox.pending_entries(
                tenant, limit=limit, after_id=after_id
            )
        else:
            entries = await observation_outbox.entries_by_status(
                tenant, status=status, limit=limit, after_id=after_id
            )
    except observation_outbox.OutboxUnavailable as exc:
        raise HTTPException(503, "observation outbox unavailable") from exc
    return {
        "tenant_id": tenant,
        "schema_version": observation_outbox.SCHEMA_VERSION,
        "status": status,
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


@router.post("/internal/v1/observation-outbox/requeue")
async def requeue_observations(
    body: OutboxRequeue,
    x_agent_token: str | None = Header(None),
    x_operator_token: str | None = Header(None),
) -> dict:
    """The operator's explicit re-queue of named conflict / rejected entries of the asserted
    tenant; one result per entry, in order. Records who, when and why on each row."""
    raster_security_context.require_service_token(x_agent_token)
    _require_operator_token(x_operator_token)
    tenant = _feed_tenant()
    _require_database()
    ids = [entry.id for entry in body.entries]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "an entry id is named more than once")
    try:
        results = await observation_outbox.requeue(
            tenant,
            [entry.model_dump() for entry in body.entries],
            actor=body.actor,
            reason=body.reason,
        )
    except observation_outbox.OutboxUnavailable as exc:
        raise HTTPException(503, "observation outbox unavailable") from exc
    return {"tenant_id": tenant, "actor": body.actor, "results": results}
