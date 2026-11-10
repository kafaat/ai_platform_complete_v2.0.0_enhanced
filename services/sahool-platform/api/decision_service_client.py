"""Thin sahool-platform client for decision-service boundary calls.

P0 Decision / Outcome / Learning SoR Strangler:
- before cutover, sahool-platform remains the temporary authoritative writer and mirrors here;
- after DECISION_SERVICE_SOR_ENABLED + real DB verification, decision-service owns persistence;
- sahool-platform keeps auth/rate-limit/BFF orchestration and calls this facade.
"""

from __future__ import annotations

import os
from typing import Any

from shared.security.decision_service_auth import (
    DecisionServiceAuthUnavailable,
    decision_service_auth_headers,
)

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
    # The legacy authorization argument is accepted for caller compatibility.
    # End-user JWTs are verified at the API boundary; this hop uses service auth.
    try:
        headers = decision_service_auth_headers()
    except DecisionServiceAuthUnavailable as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if tenant_id:
        headers["X-Tenant-Id"] = str(tenant_id)
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
        async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
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
        async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
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


async def latest_vegetation_snapshot(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    available_before: str,
) -> dict[str, Any]:
    """AC-6 point-in-time read: newest vegetation snapshot available by the decision cutoff.
    decision-service answers 404 when none exists; never a substitute snapshot."""
    return await decision_get_json(
        "/v1/evidence/vegetation-snapshots/latest",
        tenant_id=tenant_id,
        params={
            "field_id": field_id,
            "available_before": available_before,
            **({"season_id": season_id} if season_id else {}),
        },
        timeout_s=3.0,
    )


def _http_reason(exc: Any) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        detail = detail.get("reason") or detail.get("code") or detail
    return f"{getattr(exc, 'status_code', '?')}:{detail}"


async def irrigation_candidate_lineage(
    user: Any,
    field_id: str,
    season: Any,
    inputs: dict[str, Any],
    weather: dict[str, Any],
    et0: dict[str, Any],
    ledger_date: Any,
    days_since_sowing: Any,
) -> Any:
    """AC-1/AC-6 lineage for the field irrigation candidate (EX-WATER-01, path B).

    Only runs the composition when the server-side composer is enabled
    (``AGRONOMIC_CONTEXT_COMPOSE_ENABLED``); otherwise nothing is called and, where AC-1 is
    enforced, the candidate is blocked with that reason instead of failing in decision-service.
    Every identity comes from its owner; anything missing is named, never filled in.
    """
    from datetime import UTC, datetime

    from core.season_phenology import resolve_crop_id
    from fastapi import HTTPException

    from api.agronomic_context_composer import (
        REQUIRED_LINEAGE_FIELDS,
        Ac1Binding,
        agronomic_context_compose_enabled,
        agronomic_context_required,
        canonical_soil_profile_for_context,
        irrigation_candidate_compose_payload,
        irrigation_candidate_features,
        lineage_binding,
    )
    from api.canonical_soil_state import resolve_canonical_soil_state

    tenant_id = str(getattr(user, "tenant_id", "") or "")
    season_id = season.get("season_id") if season else None
    cultivar_id = season.get("cultivar") if season else None
    crop_id = resolve_crop_id(inputs.get("crop"))
    detail: dict[str, Any] = {}
    context = vegetation = None
    if not agronomic_context_compose_enabled():
        # Nothing is attached while the operator has not enabled the composer: the request is
        # exactly what it was before, and an enforcing environment gets a named block.
        return Ac1Binding(
            record_fields={},
            missing=REQUIRED_LINEAGE_FIELDS,
            required=agronomic_context_required(),
            detail={
                "composer": "server-side composer disabled (AGRONOMIC_CONTEXT_COMPOSE_ENABLED)"
            },
        )
    if not season_id:
        detail["season_id"] = "no active season for the field"
    else:
        cutoff = datetime.now(UTC)
        soil_profile, soil_gap = canonical_soil_profile_for_context(
            await resolve_canonical_soil_state(tenant_id=tenant_id, field_id=field_id),
            cutoff=cutoff,
        )
        if soil_gap is not None:
            # Not fatal here: decision-service decides whether the profile is required and
            # names the violation; this records why none was attached.
            detail["soil_profile"] = soil_gap
        payload = irrigation_candidate_compose_payload(
            tenant_id=tenant_id,
            field_id=field_id,
            season_id=season_id,
            cutoff=cutoff,
            inputs=inputs,
            ledger_date=ledger_date,
            soil_profile=soil_profile,
            features=irrigation_candidate_features(
                cutoff=cutoff,
                field_id=field_id,
                crop_id=crop_id,
                cultivar_id=cultivar_id,
                days_since_sowing=days_since_sowing,
                inputs=inputs,
                ledger_date=ledger_date,
                weather=weather,
                et0=et0,
            ),
        )
        try:
            context = await compose_context_snapshot(
                payload, tenant_id=tenant_id, requested_by=str(getattr(user, "user_id", "") or "")
            )
        except HTTPException as exc:
            detail["context"] = _http_reason(exc)
            if isinstance(exc.detail, dict) and exc.detail.get("violations"):
                detail["context_violations"] = exc.detail["violations"]
        try:
            vegetation = await latest_vegetation_snapshot(
                tenant_id=tenant_id,
                field_id=field_id,
                season_id=season_id,
                available_before=payload["decision_cutoff_time"],
            )
        except HTTPException as exc:
            detail["vegetation"] = (
                "no snapshot available by the cutoff"
                if exc.status_code == 404
                else _http_reason(exc)
            )
    return lineage_binding(
        season_id=season_id,
        crop_id=crop_id,
        cultivar_id=cultivar_id,
        context=context,
        vegetation=vegetation,
        required=agronomic_context_required(),
        detail=detail,
    )


async def list_review_queue(
    *,
    tenant_id: str | None = None,
    limit: int = 100,
    field_id: str | None = None,
    season_id: str | None = None,
) -> dict[str, Any]:
    """WX-10.8 authoritative pending-candidate queue owned by decision-service."""
    return await decision_get_json(
        "/v1/decisions/review-queue",
        tenant_id=tenant_id,
        params={
            "limit": limit,
            **({"field_id": field_id, "season_id": season_id} if field_id and season_id else {}),
        },
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


async def get_execution_plan_state(
    execution_plan_id: str, *, tenant_id: str | None = None
) -> dict[str, Any]:
    """Live plan state for the manual start/confirm re-check (read-only). decision-service owns
    the verdict (``bound``); mirror mode is 503 there and must fail the caller closed."""
    return await decision_get_json(
        f"/v1/execution-plans/{execution_plan_id}",
        tenant_id=tenant_id,
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
