"""جسر محكوم من متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC) إلى سلسلة القرار.

P1.1b: يوصل `solve_lexicographic_irrigation` بمركز القرار كمرشّح محكوم من النوع
`irrigation_mpc`. **توصية-فقط** (`execution_allowed=False` بنيويّاً؛ لا تنفيذ تلقائيّ) —
افتراضيّ مُطفأ (`LEXICOGRAPHIC_MPC_BRIDGE_ENABLED`)، فاشل-مُغلَق. النَّسَب يُنشَر بالكامل:
`content_digest` (64-hex) + `idempotency_key` + `solver_version` + `candidate_lineage_id`
تدخل `decision_value` فتنتقل عبر review→execution→outcome→learning.

⚠ محاكاة حتى شهادة staging (نفس وضع `water_decision_bridge`): الانتشار عبر PostgreSQL
والسلسلة الكاملة يُشهَّد على بيئة staging حيّة؛ هنا اختبارات وحدة على شكل المرشّح.
"""

from __future__ import annotations

import os
from typing import Any

from api.lexicographic_irrigation_mpc import (
    LexicographicIrrigationDecision,
    solve_lexicographic_irrigation,
)


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def bridge_enabled() -> bool:
    return _bool("LEXICOGRAPHIC_MPC_BRIDGE_ENABLED", False)


def build_mpc_candidate(
    decision: LexicographicIrrigationDecision,
) -> tuple[str, str, dict[str, Any]]:
    """يبني مرشّح قرار محكوماً من قرار MPC — النَّسَب الكامل يُنشَر في decision_value.

    decision_id مُشتَقّ من content_digest (حتميّ، بلا تصادم). لا يُصدَر أمر مضخّة.
    """
    digest = decision.content_digest
    decision_id = "mpcdec_" + digest[:24]
    lineage = decision.candidate_lineage_id
    value = decision.to_dict()
    value["requires_human_review"] = True  # توصية-فقط
    value["source_type"] = "lexicographic_mpc"
    value["source_id"] = f"{decision.field_id}:{digest[:16]}"
    candidate = {
        "decision_id": decision_id,
        "field_id": decision.field_id,
        "season_id": decision.season_id,
        "decision_type": "irrigation_mpc",
        "stage": "candidate",
        "confidence": decision.confidence,
        "created_by": "lexicographic-mpc-governed-bridge",
        # نَسَب مُنتشِر صراحةً على مستوى القمّة (يسهل ربطه في السلسلة).
        "candidate_lineage_id": lineage,
        "content_digest": digest,
        "idempotency_key": decision.idempotency_key,
        "solver_version": decision.solver_version,
        "decision_value": value,
    }
    return decision_id, lineage, candidate


async def emit_mpc_candidate(
    decision: LexicographicIrrigationDecision,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    """يُصدِر مرشّح MPC إلى مركز القرار (محكوم، توصية-فقط). مُطفأ افتراضيّاً.

    لا يتجاوز مركز القرار ولا يُصدِر أمر تنفيذ — يقف عند `candidate_created` دائماً
    (`execution_allowed=False`). النَّسَب الكامل مُدرَج للانتشار اللاحق في السلسلة.
    """
    if not bridge_enabled():
        return {"status": "disabled"}
    if decision.operating_state.value == "EMERGENCY_FAIL_CLOSED":
        return {"status": "fail_closed", "reason_codes": [c.value for c in decision.reason_codes]}

    from api.decision_service_client import record_decision

    decision_id, lineage, candidate = build_mpc_candidate(decision)
    recorded = await record_decision(candidate, tenant_id=tenant_id)
    if not recorded.get("persisted") or not recorded.get("authoritative"):
        return {"status": "candidate_not_authoritative", "decision_id": decision_id}
    return {
        "status": "candidate_created",
        "decision_id": decision_id,
        "candidate_lineage_id": lineage,
        "content_digest": decision.content_digest,
        "idempotency_key": decision.idempotency_key,
        # توصية-فقط: لا مسار تنفيذ تلقائيّ (execution_allowed=False).
        "execution_allowed": False,
    }


def plan_and_maybe_emit(**solver_kwargs: Any) -> LexicographicIrrigationDecision:
    """غلاف مريح: يحلّ القرار (نقيّ). الإصدار عبر `emit_mpc_candidate` (async) منفصل."""
    return solve_lexicographic_irrigation(**solver_kwargs)
