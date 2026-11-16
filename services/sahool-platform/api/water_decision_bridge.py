"""Governed bridge from canonical water-ledger deficit to decision/execution lifecycle.

Default-off and fail-closed. A deficit creates exactly one deterministic candidate. Optional
policy auto-approval can continue through review and an execution plan, but only when explicitly
enabled and a concrete target device/task is configured.

W2-04 (owner decision 2026-11-16): the bridge stops at an approved plan. It never authorises
dispatch and never requests execution: it returns ``awaiting_human_authorization`` with the
decision, review and plan ids, and a human authoriser (an identity other than the policy actor
that reviewed) authorises through decision-service's existing
``POST /v1/execution-plans/{id}/authorize-dispatch`` and then requests execution through
``POST /v1/dispatch-authorizations/{id}/execute``. One actor reviewing and authorising is what
decision-service refuses under separation of duties
(``DECISION_REQUIRE_SEPARATION_OF_DUTIES``, on by default in production).
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

from shared.security.decision_service_auth import (
    DecisionServiceAuthUnavailable,
    decision_service_auth_headers,
)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _stable(prefix: str, *parts: object, size: int = 24) -> str:
    raw = "|".join(str(p) for p in parts)
    return prefix + hashlib.sha256(raw.encode()).hexdigest()[:size]


def bridge_enabled() -> bool:
    return _bool("WATER_DEFICIT_DECISION_BRIDGE_ENABLED", False)


def water_ledger_identity_startup_error() -> str | None:
    """CT-03 (تدقيق الحاويات V21): هويّة الخدمة إلزاميّة للعامل في الإنتاج متى فُعّل الجسر.

    متى فُعّل ``WATER_DEFICIT_DECISION_BRIDGE_ENABLED`` يدفع عامل دفتر المياه مرشّحات
    قرار إلى decision-service مُصادَقاً عليها بـ``Bearer``/``DECISION_SERVICE_TOKEN``.
    بلا التوكن يرفض decision-service (401) ويظلّ العامل يطرق الباب بلا هويّة. في الإنتاج
    (``SAHOOL_ENV=production``) نرفض الإقلاع رفضاً صارماً كي لا يحاول عاملٌ مجهول الهويّة
    دفع مرشّحات قرار محكومة أصلاً. التطوير (أو الجسر مُعطَّل) يبقى قابلاً للتشغيل. علَمٌ
    صريح ``WATER_LEDGER_REQUIRE_IDENTITY`` يُسلّح الفحص خارج الإنتاج. يعيد رسالة الرفض
    أو ``None`` عند الرضا — ولا يطبع قيمة التوكن أبداً، بل غيابه فقط.
    """
    require = os.getenv("WATER_LEDGER_REQUIRE_IDENTITY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not bridge_enabled():
        return None
    try:
        decision_service_auth_headers(required=require)
    except DecisionServiceAuthUnavailable:
        pass
    else:
        return None
    return (
        "DECISION_SERVICE_TOKEN is required when the water-deficit decision bridge is enabled in "
        "production (or when WATER_LEDGER_REQUIRE_IDENTITY / DECISION_REQUIRE_AUTH_TOKEN is set) "
        "but is unavailable — refusing to "
        "start an unidentified water-ledger worker that would push governed decision candidates "
        "to decision-service. Configure the decision-service bearer before deployment."
    )


def auto_execution_enabled() -> bool:
    """``WATER_DEFICIT_AUTO_EXECUTION_ENABLED`` (name kept, env contract unchanged).

    W2-04: since the owner decision of 2026-11-16 the flag means *auto-plan only*: policy
    approval of the candidate plus an execution plan, then a stop at
    ``awaiting_human_authorization``. It never makes the bridge authorise or request execution.
    """
    return _bool("WATER_DEFICIT_AUTO_EXECUTION_ENABLED", False)


#: W2-04: the state the bridge ends in once the plan exists. Authorisation and the execution
#: request belong to a human through decision-service's existing routes.
AWAITING_HUMAN_AUTHORIZATION = "awaiting_human_authorization"


def deficit_threshold_mm() -> float:
    try:
        return max(0.0, float(os.getenv("WATER_DEFICIT_DECISION_THRESHOLD_MM", "10")))
    except ValueError:
        return 10.0


def entry_applied_water_status(entry: dict[str, Any]) -> str | None:
    """حالةُ الماء المضاف كما يُعلِنها القيد — ``None`` حين لا يُعلِنها (لا تُفترَض).

    ``UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01``: القيدُ يقول صراحةً إن كان
    حدُّ الريّ في الميزان مقيساً. قيدٌ أقدم بلا المفتاح تُشتقّ حالتُه من ``notes`` إن
    حملها؛ وقيدٌ بلا هذا ولا ذاك **لا يُقرأ «مُسجَّلاً»** — الغيابُ لا يصير قياساً.
    """
    status = entry.get("applied_water_status")
    if isinstance(status, str) and status:
        return status
    notes = entry.get("notes")
    if isinstance(notes, (list, tuple)):
        from api.water_ledger_auto import applied_water_status

        return applied_water_status(notes)
    return None


def applied_water_is_recorded(entry: dict[str, Any]) -> bool:
    from api.water_ledger_auto import APPLIED_WATER_RECORDED

    return entry_applied_water_status(entry) == APPLIED_WATER_RECORDED


def build_candidate(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    ledger_date: date,
    entry: dict[str, Any],
    policy_version: str,
) -> tuple[str, str, dict[str, Any]]:
    lineage = _stable("wtrlin_", tenant_id, field_id, ledger_date.isoformat(), policy_version)
    decision_id = _stable("wtrdec_", tenant_id, field_id, ledger_date.isoformat(), policy_version)
    payload = {
        "decision_id": decision_id,
        "field_id": field_id,
        "season_id": season_id,
        "decision_type": "irrigation_deficit",
        "stage": "candidate",
        "confidence": entry.get("confidence"),
        "created_by": "water-ledger-governed-bridge",
        "decision_value": {
            "candidate_lineage_id": lineage,
            "policy_version": policy_version,
            "source_type": "water_ledger",
            "source_id": f"{field_id}:{ledger_date.isoformat()}",
            "ledger_date": ledger_date.isoformat(),
            "deficit_mm": entry.get("deficit_mm"),
            "depletion_mm": entry.get("depletion_mm"),
            "taw_mm": entry.get("taw_mm"),
            "raw_mm": entry.get("raw_mm"),
            "recommended_irrigation_mm": entry.get("deficit_mm"),
            # عجزٌ بُنِي على ريٍّ مجهول (لا صفَّ، أو حجمٌ غائب) هو **حدٌّ أعلى** للحاجة لا
            # قياسُها: يُسمّى للمراجِع ولا يُعتمَد آليّاً. ``undeclared`` = القيد لم يُعلِن.
            "applied_water_status": entry_applied_water_status(entry) or "undeclared",
            "data_quality_flags": list(entry.get("notes") or []),
            "requires_human_review": (
                not auto_execution_enabled() or not applied_water_is_recorded(entry)
            ),
        },
    }
    return decision_id, lineage, payload


def _ledger_features(field_id: str, ledger_date: date, entry: dict[str, Any]) -> list[dict]:
    """The ledger's own values for the composed context: a derived daily balance, never a
    measurement (``accepted_with_warning``); an absent value is simply not stated."""
    ref = {
        "source_snapshot_id": f"water_ledger:{field_id}:{ledger_date.isoformat()}",
        "formula_version": "water_ledger.daily_balance",
        "temporal_scope": f"ledger_date:{ledger_date.isoformat()}",
        "unit": "mm",
    }
    return [
        {
            "group": "irrigation",
            "name": "root_zone_depletion_mm",
            "value": entry.get("depletion_mm"),
            **ref,
        },
        {"group": "irrigation", "name": "deficit_mm", "value": entry.get("deficit_mm"), **ref},
        {"group": "soil", "name": "total_available_water_mm", "value": entry.get("taw_mm"), **ref},
        {
            "group": "soil",
            "name": "readily_available_water_mm",
            "value": entry.get("raw_mm"),
            **ref,
        },
    ]


async def process_water_deficit(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    ledger_date: date,
    entry: dict[str, Any],
    crop: str | None = None,
    cultivar_id: str | None = None,
) -> dict[str, Any]:
    if not bridge_enabled():
        return {"status": "disabled"}
    deficit = entry.get("deficit_mm")
    if deficit is None or float(deficit) < deficit_threshold_mm():
        return {"status": "below_threshold"}

    from api.decision_service_client import (
        create_execution_plan,
        governed_candidate_lineage,
        review_decision,
        submit_governed_candidate,
    )

    policy = os.getenv("WATER_DEFICIT_POLICY_VERSION", "water-deficit.v1")
    decision_id, lineage, candidate = build_candidate(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        ledger_date=ledger_date,
        entry=entry,
        policy_version=policy,
    )
    # W2-02 (decision-2): the candidate carries its AC-1 lineage, or the bridge names the gap
    # (blocked:lineage_missing) instead of meeting decision-service's 422.
    binding = await governed_candidate_lineage(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        crop=crop,
        cultivar_id=cultivar_id,
        producer="water-ledger-governed-bridge",
        features=_ledger_features(field_id, ledger_date, entry),
    )
    submitted = await submit_governed_candidate(candidate, binding, tenant_id=tenant_id)
    if submitted["status"] != "recorded":
        return {**submitted, "decision_id": decision_id, "candidate_lineage_id": lineage}
    recorded = submitted["record"]
    if not recorded.get("persisted") or not recorded.get("authoritative"):
        return {"status": "candidate_not_authoritative", "decision_id": decision_id}

    result: dict[str, Any] = {
        "status": "candidate_created",
        "decision_id": decision_id,
        "candidate_lineage_id": lineage,
        "applied_water_status": candidate["decision_value"]["applied_water_status"],
    }
    if not auto_execution_enabled():
        return result
    if not applied_water_is_recorded(entry):
        # UNRECORDED-IRRIGATION-READ-AS-ZERO-APPLIED-WATER-01: الاعتمادُ الآليّ يصرف ماءً
        # بمقدار ``deficit_mm`` — وهو هنا مبنيٌّ على ريٍّ **قُرِئ صفراً لأنّه مجهول**
        # (مزرعةٌ تروي من بئرٍ ولا تسجّل). فالمرشّحُ يبقى للمراجِع البشريّ ولا يُنفَّذ آليّاً.
        # القرارُ المحافظ إلى أن يُعلَن مصدرُ الماء لكلّ حقلٍ وموسم (شرطُ إغلاق الفجوة).
        return {**result, "status": "held_for_review_applied_water_unknown"}

    target_id = os.getenv("WATER_DEFICIT_EXECUTION_TARGET_ID", "").strip()
    target_type = os.getenv("WATER_DEFICIT_EXECUTION_TARGET_TYPE", "equipment").strip()
    if not target_id or target_type not in {"equipment", "task"}:
        return {**result, "status": "awaiting_target_configuration"}

    actor = os.getenv("WATER_DEFICIT_POLICY_ACTOR", "water-deficit-policy")
    review = await review_decision(
        decision_id,
        {
            "action": "approve",
            "reason": "approved by explicit water-deficit automation policy",
            "expected_state": "pending_approval",
            "candidate_lineage_id": lineage,
            # The automation approves the version decision-service stored and reported — not a
            # digest computed here (035, IRRIGATION-APPROVAL-NOT-BOUND-TO-DECISION-VERSION-01).
            "decision_value_digest": recorded.get("decision_value_digest"),
            "idempotency_key": _stable("wtrrev_", decision_id),
            "policy_version": policy,
        },
        tenant_id=tenant_id,
        reviewed_by=actor,
    )
    review_id = review.get("review_id")
    if not review_id:
        return {**result, "status": "review_failed"}

    now = datetime.now(UTC)
    plan = await create_execution_plan(
        decision_id,
        {
            "review_id": review_id,
            "candidate_lineage_id": lineage,
            "operation_type": "irrigation",
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=2)).isoformat(),
            "target_zone_ids": [],
            "required_resources": [{"target_id": target_id}],
            "constraints": {"max_irrigation_mm": float(deficit)},
            "safety_conditions": {"killswitch_required": True, "stale_telemetry_forbidden": True},
            "idempotency_key": _stable("wtrplan_", decision_id),
        },
        tenant_id=tenant_id,
        created_by=actor,
    )
    plan_id = plan.get("execution_plan_id")
    if not plan_id:
        return {**result, "status": "plan_failed", "review_id": review_id}

    # W2-04 (owner decision 2026-11-16): stop here. The policy actor reviewed, so it may not
    # authorise (decision-service refuses reviewer == authoriser under separation of duties);
    # authorisation and the execution request are a human's, through decision-service's
    # existing authorize-dispatch and execute routes. No authorisation or execution call is
    # made from this bridge.
    return {
        **result,
        "status": AWAITING_HUMAN_AUTHORIZATION,
        "review_id": review_id,
        "execution_plan_id": plan_id,
        "reviewed_by": actor,
        "execution_target": {"target_type": target_type, "target_id": target_id},
        "recommended_irrigation_mm": float(deficit),
    }
