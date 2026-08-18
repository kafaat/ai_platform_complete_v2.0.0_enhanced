"""Thin sahool-platform client for decision-service boundary calls.

P0 Decision / Outcome / Learning SoR Strangler:
- before cutover, sahool-platform remains the temporary authoritative writer and mirrors here;
- after DECISION_SERVICE_SOR_ENABLED + real DB verification, decision-service owns persistence;
- sahool-platform keeps auth/rate-limit/BFF orchestration and calls this facade.
"""

from __future__ import annotations

import os
from typing import Any

# NOTE: fastapi is imported lazily inside the functions that raise/catch HTTPException.

DEFAULT_DECISION_SERVICE_URL = "http://sahool-decision-service:8160"


def decision_service_url() -> str:
    return os.getenv("DECISION_SERVICE_URL", DEFAULT_DECISION_SERVICE_URL).rstrip("/")


def decision_service_headers(
    *,
    tenant_id: str | None = None,
    authorization: str | None = None,
    reviewed_by: str | None = None,
    created_by: str | None = None,
    authorized_by: str | None = None,
    verified_by: str | None = None,
    attributed_by: str | None = None,
    evaluated_by: str | None = None,
    decided_by: str | None = None,
    requested_by: str | None = None,
    recorded_by: str | None = None,
) -> dict[str, str]:
    headers = {"X-Agent-Token": os.getenv("SAHOOL_AGENT_TOKEN", "")}
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
    if authorization:
        headers["Authorization"] = authorization
    if reviewed_by:
        headers["X-Reviewed-By"] = str(reviewed_by)
    if created_by:
        headers["X-Created-By"] = str(created_by)
    if authorized_by:
        headers["X-Authorized-By"] = str(authorized_by)
    if verified_by:
        headers["X-Verified-By"] = str(verified_by)
    if attributed_by:
        headers["X-Attributed-By"] = str(attributed_by)
    if evaluated_by:
        headers["X-Evaluated-By"] = str(evaluated_by)
    if decided_by:
        headers["X-Decided-By"] = str(decided_by)
    if requested_by:
        headers["X-Requested-By"] = str(requested_by)
    if recorded_by:
        headers["X-Recorded-By"] = str(recorded_by)
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
    reviewed_by: str | None = None,
    created_by: str | None = None,
    authorized_by: str | None = None,
    verified_by: str | None = None,
    attributed_by: str | None = None,
    evaluated_by: str | None = None,
    decided_by: str | None = None,
    requested_by: str | None = None,
    recorded_by: str | None = None,
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
                headers=decision_service_headers(
                    tenant_id=tenant_id,
                    authorization=authorization,
                    reviewed_by=reviewed_by,
                    created_by=created_by,
                    authorized_by=authorized_by,
                    verified_by=verified_by,
                    attributed_by=attributed_by,
                    evaluated_by=evaluated_by,
                    decided_by=decided_by,
                    requested_by=requested_by,
                    recorded_by=recorded_by,
                ),
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


async def compose_context_snapshot(
    payload: dict[str, Any],
    *,
    tenant_id: str,
    requested_by: str,
) -> dict[str, Any]:
    """Persist the existing AC-1 historical context; this never creates a decision."""
    return await decision_post_json(
        "/v1/context-snapshots",
        payload,
        tenant_id=tenant_id,
        requested_by=requested_by,
        timeout_s=3.0,
    )


async def list_review_queue(*, tenant_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """WX-10.8 authoritative pending-candidate queue owned by decision-service."""
    return await decision_get_json(
        "/v1/decisions/review-queue",
        tenant_id=tenant_id,
        params={"limit": limit},
    )


async def get_decision_agronomic_evidence(
    decision_id: str, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """Phase E — authoritative read of one decision's agronomic evidence chain
    (context/historical/manifest/vegetation). decision-service owns the truth;
    mirror mode is a 503 there and propagates here untouched."""
    return await decision_get_json(
        f"/v1/decisions/{decision_id}/agronomic-evidence",
        tenant_id=tenant_id,
    )


async def review_decision(
    decision_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.7 — reviewer/policy action on a pending_approval candidate. decision-service owns
    the authoritative transition; this facade only transports (it must NOT synthesize
    authoritative/persisted — those are proven by the service response)."""
    return await decision_post_json(
        f"/v1/decisions/{decision_id}/review",
        payload,
        tenant_id=tenant_id,
        reviewed_by=reviewed_by,
    )


async def create_execution_plan(
    decision_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.9 thin transport; decision-service owns validation and persistence."""
    return await decision_post_json(
        f"/v1/decisions/{decision_id}/execution-plan",
        payload,
        tenant_id=tenant_id,
        created_by=created_by,
    )


async def authorize_dispatch(
    execution_plan_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    authorized_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.10 thin transport; decision-service owns authorization persistence."""
    return await decision_post_json(
        f"/v1/execution-plans/{execution_plan_id}/authorize-dispatch",
        payload,
        tenant_id=tenant_id,
        authorized_by=authorized_by,
    )


async def create_execution_request(
    dispatch_authorization_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.11a thin transport; decision-service owns authoritative persistence."""
    return await decision_post_json(
        f"/v1/dispatch-authorizations/{dispatch_authorization_id}/execute",
        payload,
        tenant_id=tenant_id,
        requested_by=requested_by,
    )


async def verify_execution_outcome(
    execution_request_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    verified_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.12 thin transport; decision-service owns canonical outcome verification."""
    return await decision_post_json(
        f"/v1/execution-requests/{execution_request_id}/verify-outcome",
        payload,
        tenant_id=tenant_id,
        verified_by=verified_by,
    )


async def create_learning_attribution(
    outcome_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    attributed_by: str | None = None,
) -> dict[str, Any]:
    """WX-10.13 thin transport; decision-service owns immutable attribution lineage."""
    return await decision_post_json(
        f"/v1/outcomes/{outcome_id}/learning-attribution",
        payload,
        tenant_id=tenant_id,
        attributed_by=attributed_by,
    )


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


# P4.6 read-side facade helpers.  These are intentionally thin; sahool-platform may shape
# BFF responses (auth/flag/validation) but must not own loop-table read semantics.
async def list_decisions(
    *,
    tenant_id: str | None = None,
    field_id: str | None = None,
    decision_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    return await decision_get_json(
        "/v1/decisions",
        tenant_id=tenant_id,
        params={"field_id": field_id, "decision_type": decision_type, "limit": limit},
    )


async def get_field_lineage(
    field_id: str, *, tenant_id: str | None = None, limit: int = 50
) -> dict[str, Any]:
    return await decision_get_json(
        f"/v1/fields/{field_id}/lineage", tenant_id=tenant_id, params={"limit": limit}
    )


async def get_reconciled_outcomes(
    *, tenant_id: str | None = None, field_id: str | None = None, season_id: str | None = None
) -> dict[str, Any]:
    return await decision_get_json(
        "/v1/outcomes/reconciled",
        tenant_id=tenant_id,
        params={"field_id": field_id, "season_id": season_id},
    )


async def get_calibration_dataset(
    *,
    model_id: str,
    feature_set_id: str | None = None,
    field_id: str | None = None,
    season_id: str | None = None,
    limit: int = 500,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """WX-11.1 thin transport for the authoritative read-only calibration dataset."""
    return await decision_get_json(
        "/v1/learning/calibration-dataset",
        tenant_id=tenant_id,
        params={
            "model_id": model_id,
            "feature_set_id": feature_set_id,
            "field_id": field_id,
            "season_id": season_id,
            "limit": limit,
        },
    )


async def create_model_evaluation_run(
    payload: dict[str, Any], *, tenant_id: str | None = None, evaluated_by: str | None = None
) -> dict[str, Any]:
    """WX-11.2 thin transport for immutable evaluation-run registration."""
    return await decision_post_json(
        "/v1/learning/evaluation-runs", payload, tenant_id=tenant_id, evaluated_by=evaluated_by
    )


async def create_model_promotion_decision(
    payload: dict[str, Any], *, tenant_id: str | None = None, decided_by: str | None = None
) -> dict[str, Any]:
    """WX-11.3 thin transport for immutable governed promotion decisions."""
    return await decision_post_json(
        "/v1/learning/promotion-decisions", payload, tenant_id=tenant_id, decided_by=decided_by
    )


async def create_model_activation_request(
    payload: dict[str, Any], *, tenant_id: str | None = None, requested_by: str | None = None
) -> dict[str, Any]:
    """WX-11.4 thin transport for immutable pending activation requests."""
    return await decision_post_json(
        "/v1/learning/activation-requests", payload, tenant_id=tenant_id, requested_by=requested_by
    )


async def review_model_activation_request(
    activation_request_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    reviewed_by: str | None = None,
) -> dict[str, Any]:
    """WX-11.5 thin transport for governed activation approval/rejection."""
    return await decision_post_json(
        f"/v1/learning/activation-requests/{activation_request_id}/review",
        payload,
        tenant_id=tenant_id,
        reviewed_by=reviewed_by,
    )


async def claim_model_registry_activation_command(
    command_id: str, payload: dict[str, Any], *, tenant_id: str | None = None
) -> dict[str, Any]:
    return await decision_post_json(
        f"/v1/learning/activation-commands/{command_id}/claim", payload, tenant_id=tenant_id
    )


async def record_model_registry_activation_receipt(
    command_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    recorded_by: str | None = None,
) -> dict[str, Any]:
    return await decision_post_json(
        f"/v1/learning/activation-commands/{command_id}/receipt",
        payload,
        tenant_id=tenant_id,
        recorded_by=recorded_by,
    )


async def create_model_registry_rollback_command(
    receipt_id: str,
    payload: dict[str, Any],
    *,
    tenant_id: str | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    return await decision_post_json(
        f"/v1/learning/activation-receipts/{receipt_id}/rollback-command",
        payload,
        tenant_id=tenant_id,
        requested_by=requested_by,
    )
