"""Plan-point origin resolution for the platform's lab-sample route (gap P6).

The origin of a sample that names a plan point is resolved and verified by soil-service from its
stored plan copy; the client's claim is never stored. Kept out of ``routers/soil_sampling.py``
so that router stays under the router-size ceiling.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api import soil_hydraulic_client


async def resolve_plan_origin(payload: Any, user: Any, claimed: dict | None) -> dict:
    """The plan-point origin soil-service resolves and verifies, or an HTTP refusal.

    Unknown or other-tenant plan, point not in the plan, collection beyond the tolerance without
    a reason ⇒ 422 with soil-service's typed code. soil-service unreachable or answering
    anything but a verified origin ⇒ 503: a sample that claims a plan is never stored on the
    strength of the claim alone (fail closed)."""
    try:
        return await soil_hydraulic_client.resolve_sampling_origin(
            tenant_id=str(user.tenant_id),
            field_id=payload.field_id,
            plan_id=payload.sampling_plan_id,
            point_id=payload.sampling_origin.point_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            gps_accuracy_m=payload.gps_accuracy_m,
            deviation_reason=payload.deviation_reason,
            claimed=claimed,
        )
    except soil_hydraulic_client.SamplingOriginRefused as exc:
        raise HTTPException(422, exc.detail) from exc
    except soil_hydraulic_client.SamplingPlanVerificationUnavailable as exc:
        raise HTTPException(
            503,
            {
                "code": "sampling_plan_verification_unavailable",
                "message": "the sampling plan could not be verified; retry later",
            },
        ) from exc
