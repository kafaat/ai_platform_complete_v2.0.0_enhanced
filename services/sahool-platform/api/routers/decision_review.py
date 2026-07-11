"""api/routers/decision_review.py — WX-10.7 reviewer/policy action on a decision candidate.

# DECISION-PATH: reviewer/policy transition of a pending_approval candidate to a terminal
# approved|rejected Decision Record. The AUTHORITATIVE state machine, append-only audit, and
# transaction are OWNED BY decision-service — this platform route is a thin, authenticated BFF
# proxy: it enforces *who* may review (role permission) and forwards to decision-service, then
# fails closed unless the service proves an authoritative transition. It never mutates the
# decision itself, and never dispatches / creates tasks / executes equipment.

Ownership split (continuation of WX-10.6): Crop Intelligence interprets; decision-service owns
the decision, its approval, and the review audit. Reopen/correction is a future increment with
its own audit contract — this route only performs the single terminal transition.
"""

from __future__ import annotations

from core.authorization import Permission
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.decision_service_client import review_decision as ds_review_decision
from api.main import UserSchema, require_permission

router = APIRouter()

_ENGINE_DOWN_CODES = {502, 503, 504}
_TERMINAL_STATES = {"approved", "rejected"}


class DecisionReviewRequest(BaseModel):
    """طلب مراجعة مرشّح قرار (approve/reject) بضوابط التزامن والنَّسَب."""

    action: str  # "approve" | "reject"
    reason: str = ""
    expected_state: str = "pending_approval"
    candidate_lineage_id: str
    idempotency_key: str
    policy_version: str | None = None


@router.post("/api/v1/decisions/{decision_id}/review")
async def review_decision_candidate(
    decision_id: str,
    req: DecisionReviewRequest,
    user: UserSchema = Depends(require_permission(Permission.DECISION_APPROVE)),
):
    """WX-10.7 — مراجعة مُصرَّح بها لمرشّح ``pending_approval`` → ``approved|rejected``.

    الملكيّة: decision-service يملك الانتقال الآمِر (state machine + audit + transaction). هذه
    النقطة تفرض *مَن* يراجع (``DECISION_APPROVE``) وتُمرّر فقط؛ tenant من الـJWT، ``reviewed_by``
    من المستخدم. **fail-closed:** لا نجاح إلّا إذا أثبت ردّ الخدمة الانتقال الآمِر (authoritative
    ∧ persisted ∧ decision_id مطابق ∧ previous_state=pending_approval ∧ state∈{approved,rejected}
    ∧ review_id/reviewed_by/reviewed_at غير فارغة ∧ candidate_lineage_id مطابق). mirror/SoR-off ⇒
    ردّ غير آمِر ⇒ 503. الخدمة ساقطة ⇒ 503. لا تنفيذ (dispatch/task/معدّات)."""
    payload = {
        "action": req.action,
        "reason": req.reason,
        "expected_state": req.expected_state,
        "candidate_lineage_id": req.candidate_lineage_id,
        "idempotency_key": req.idempotency_key,
        "policy_version": req.policy_version,
    }
    try:
        result = await ds_review_decision(
            decision_id,
            payload,
            tenant_id=str(user.tenant_id) if user.tenant_id else None,
            reviewed_by=user.user_id,
        )
    except HTTPException as exc:
        # decision-service unavailable → fail closed as 503; 404/409/422 propagate verbatim.
        if exc.status_code in _ENGINE_DOWN_CODES:
            raise HTTPException(
                status_code=503, detail="decision-service unavailable — review not applied"
            ) from exc
        raise

    # fail-closed proof — a review is successful ONLY when the service proves the authoritative
    # transition of the same record with a real audit row. The platform never synthesizes this.
    proven = (
        result.get("authoritative") is True
        and result.get("persisted") is True
        and result.get("decision_id") == decision_id
        and result.get("previous_state") == "pending_approval"
        and result.get("state") in _TERMINAL_STATES
        and bool(result.get("review_id"))
        and bool(result.get("reviewed_by"))
        and bool(result.get("reviewed_at"))
        and result.get("candidate_lineage_id") == req.candidate_lineage_id
    )
    if not proven:
        raise HTTPException(
            status_code=503,
            detail="decision-service did not confirm an authoritative review — fail-closed",
        )
    return {
        "decision_id": decision_id,
        "state": result["state"],
        "previous_state": result["previous_state"],
        "review_id": result["review_id"],
        "reviewed_by": result["reviewed_by"],
        "reviewed_at": result["reviewed_at"],
        "candidate_lineage_id": result["candidate_lineage_id"],
        "replay": bool(result.get("replay", False)),
    }
