"""F8 — the advisor chat shows stored owner-engine proposals for specialist review only.

The platform reads proposals an owning engine already stored for the field
(``/internal/fields/{field_id}/state?engine_proposals=true``, no new route). This client
re-checks the contract and passes on only proposals that are review-only and fully
provenanced. It never sends a proposal to a model, never computes one, never approves,
executes or writes anything. A failure degrades to an empty list with reason codes; the
advice itself continues.

Feature flag ``SAHOOL_ADVISOR_ENGINE_PROPOSALS`` — OFF by default; read at call time.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from shared.ai.engine_proposal_review import (
    FLAG_ENV,
    MAX_PROPOSALS,
    SCHEMA,
    flag_enabled,
    review_envelope,
)

__all__ = ["FLAG_ENV", "accept_proposal", "accept_review", "fetch_engine_proposals", "flag_enabled"]
_PATH = "/internal/fields/{field_id}/state"
_REASON = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_KINDS = frozenset({"irrigation", "fertilization"})
_PROPOSAL_KEYS = (
    "proposal_id",
    "proposal_kind",
    "status",
    "requires_human_review",
    "approved",
    "executable",
    "execution_allowed",
    "recommendation_only",
    "computed_in_request",
    "tenant_id",
    "field_id",
    "owning_service",
    "owning_engine",
    "source_record",
    "method",
    "owner_status",
    "owner_decision",
    "amounts",
    "actions",
    "units",
    "input_snapshot",
    "timestamps",
    "validity",
    "limitations",
    "presentation_ar",
)


def _same_tenant(a: Any, b: Any) -> bool:
    try:
        return UUID(str(a)) == UUID(str(b))
    except (ValueError, TypeError, AttributeError):
        return False


def _envelope(tenant_id: str, field_id: str | None, *, enabled: bool, **parts: Any) -> dict:
    return review_envelope(tenant_id=tenant_id, field_id=field_id, enabled=enabled, **parts)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_until(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def accept_proposal(
    item: Any, *, tenant_id: str, field_id: str, now: datetime
) -> tuple[dict | None, str | None]:
    """Contract check for one proposal from the platform → (copy, None) or (None, reason)."""
    if not isinstance(item, dict):
        return None, "owner_proposal_contract_invalid"
    method, validity = item.get("method"), item.get("validity")
    if not (
        _nonempty_str(item.get("proposal_id"))
        and item.get("proposal_kind") in _KINDS
        and item.get("status") == "awaiting_specialist_review"
        and item.get("requires_human_review") is True
        and item.get("approved") is False
        and item.get("executable") is False
        and item.get("execution_allowed") is False
        and item.get("recommendation_only") is True
        and item.get("computed_in_request") is False
        and _same_tenant(item.get("tenant_id"), tenant_id)
        and item.get("field_id") == field_id
        and _nonempty_str(item.get("owning_service"))
        and isinstance(item.get("source_record"), dict)
        and isinstance(method, dict)
        and _nonempty_str(method.get("version"))
        and isinstance(item.get("amounts"), dict)
        and isinstance(item.get("units"), dict)
        and item["units"]
        and isinstance(item.get("input_snapshot"), dict)
        and item["input_snapshot"]
        and isinstance(item.get("timestamps"), dict)
        and _nonempty_str(item["timestamps"].get("created_at"))
        and isinstance(validity, dict)
        and validity.get("state") == "current"
        and isinstance(item.get("limitations"), list)
    ):
        return None, "owner_proposal_contract_invalid"
    until = _valid_until(validity.get("valid_until"))
    if until is None:
        return None, "owner_proposal_contract_invalid"
    if now >= until:
        return None, "owner_proposal_expired"
    return {key: item.get(key) for key in _PROPOSAL_KEYS}, None


def accept_review(payload: Any, *, tenant_id: str, field_id: str, now: datetime) -> dict:
    """Validate the platform envelope; keep only contract-conforming proposals."""
    review = payload.get("engine_proposals") if isinstance(payload, dict) else None
    if (
        not isinstance(review, dict)
        or review.get("schema_version") != SCHEMA
        or not _same_tenant(review.get("tenant_id"), tenant_id)
        or review.get("field_id") != field_id
        or review.get("read_only") is not True
        or review.get("computed_in_request") is not False
        or not isinstance(review.get("proposals"), list)
    ):
        return _envelope(
            tenant_id, field_id, enabled=True, reason_codes=["owner_proposal_contract_invalid"]
        )
    reasons = [
        code
        for code in review.get("reason_codes") or []
        if isinstance(code, str) and _REASON.fullmatch(code)
    ]
    if review.get("enabled") is not True:
        return _envelope(tenant_id, field_id, enabled=False, reason_codes=reasons)
    proposals = []
    for item in review["proposals"]:
        accepted, reason = accept_proposal(item, tenant_id=tenant_id, field_id=field_id, now=now)
        if accepted is None:
            reasons.append(reason)
        elif len(proposals) < MAX_PROPOSALS:
            proposals.append(accepted)
    if not proposals and "no_stored_owner_proposal" not in reasons:
        reasons.append("no_eligible_stored_owner_proposal")
    sources = [s for s in review.get("sources_checked") or [] if isinstance(s, dict)]
    return _envelope(
        tenant_id,
        field_id,
        enabled=True,
        proposals=proposals,
        reason_codes=reasons,
        sources_checked=sources[:8],
    )


async def fetch_engine_proposals(
    *,
    tenant_id: str,
    field_id: str | None,
    endpoint_mode: str,
    platform_url: str,
    agent_token: str,
    sign: Callable[[str, str, str], dict[str, str] | None],
    voice_read_only: bool = False,
    now: datetime | None = None,
) -> dict:
    """Stored proposals for the chat response. Read-only; empty with reason codes otherwise."""
    if not flag_enabled():
        return _envelope(tenant_id, field_id, enabled=False, reason_codes=["feature_flag_off"])
    if endpoint_mode != "chat":
        return _envelope(tenant_id, field_id, enabled=True, reason_codes=["endpoint_mode_not_chat"])
    if voice_read_only:
        # The voice channel has a zero-read budget beyond its own context; nothing is read.
        return _envelope(
            tenant_id, field_id, enabled=True, reason_codes=["voice_read_only_excluded"]
        )
    if not field_id:
        return _envelope(tenant_id, field_id, enabled=True, reason_codes=["field_id_required"])
    path = _PATH.format(field_id=quote(field_id, safe=""))
    signed = sign(tenant_id, "GET", path) if agent_token else None
    if signed is None:
        return _envelope(
            tenant_id, field_id, enabled=True, reason_codes=["platform_credentials_unavailable"]
        )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                platform_url.rstrip("/") + path,
                params={"tenant_id": tenant_id, "engine_proposals": "true"},
                headers={"X-Agent-Token": agent_token, **signed},
                timeout=10.0,
            )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError("owner", request=resp.request, response=resp)
        payload = resp.json()
    except Exception:  # noqa: BLE001 — upstream body/exception text is never reflected
        return _envelope(
            tenant_id, field_id, enabled=True, reason_codes=["owner_proposal_store_unavailable"]
        )
    return accept_review(
        payload, tenant_id=tenant_id, field_id=field_id, now=now or datetime.now(UTC)
    )
