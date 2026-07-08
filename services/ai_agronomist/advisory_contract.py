"""advisory_contract.py — مظروف استجابة استشاريّة **مُهيكَل ومُتحقَّق** فوق ``answer_ar``.

M2 (تدقيق خارجيّ): النصّ الحرّ للمستشار تفسيريّ لكنّه غير مُهيكَل. هذا يشتقّ مظروفاً ثابت
الشكل من الاستجابة المُؤرَّضة القائمة (أدلّة/ثقة/موافقات) — **منطق صرف، بلا استدعاء نموذج**.

**صدق حاسم:**
  • القرار (``decision``) **لا يخترعه النموذج** أبداً — الافتراضيّ ``advisory_only`` (المستشار
    تفسيريّ)؛ لا يُقبَل ``go/caution/no_go`` إلّا من مُستدعٍ موثوق (محرّك قرار)، لا من نصّ AI.
  • ``evidence_used``/``evidence_missing`` من الأدلّة الفعليّة في الاستجابة (لا تلفيق).
  • ``requires_human_review`` **fail-safe**: افتراضه المراجعة عند أيّ فعل/غموض/نقص دليل.
  • سلطة القرار تبقى ``field_intelligence_coordinator`` (لا AI).
"""

from __future__ import annotations

from typing import Any

_DECISIONS = ("advisory_only", "no_go", "caution", "go")
_DEFAULT_CONFIDENCE_FLOOR = 0.6
_SUMMARY_MAX = 400


def _clamp01(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return max(0.0, min(1.0, f))


def _str_list(v: Any) -> list[str]:
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()]


def _coerce_decision(decision: Any) -> str:
    """يقبل قراراً **فقط** من مُستدعٍ موثوق (محرّك قرار). غيره/شاذّ ⇒ ``advisory_only``."""
    d = str(decision or "").strip().lower()
    return d if d in _DECISIONS else "advisory_only"


def _evidence_missing(response: dict[str, Any], evidence_used: list[str]) -> list[str]:
    """أسباب نقص الدليل (صريحة، لا تلفيق): فجوات مُعلَنة + غياب تأريض + جاهزيّة السياق."""
    out: list[str] = []
    for gap in response.get("knowledge_gaps") or []:
        if isinstance(gap, dict) and gap.get("key"):
            out.append(f"gap:{gap['key']}")
        elif isinstance(gap, str) and gap.strip():
            out.append(f"gap:{gap}")
    if not evidence_used:
        out.append("no_grounding_evidence")
    readiness = response.get("ai_context_pack_readiness")
    if isinstance(readiness, str) and readiness and readiness != "ok":
        out.append(f"context_pack:{readiness}")
    # إزالة التكرار مع الحفاظ على الترتيب.
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _limitations(
    response: dict[str, Any], pending: list, conf: float | None, floor: float
) -> list[str]:
    lim: list[str] = []
    if not response.get("generation_provider"):
        lim.append("generation_disabled_evidence_only")  # لا نموذج مُفعَّل — جواب من الأدلّة.
    if pending:
        lim.append("proposed_actions_await_human_approval")
    if conf is None:
        lim.append("confidence_unavailable")
    elif conf < floor:
        lim.append("low_confidence")
    if response.get("tool_calls_truncated"):
        lim.append("tool_calls_truncated")
    return lim


def build_advisory_envelope(
    response: Any,
    *,
    decision: str | None = None,
    confidence_floor: float = _DEFAULT_CONFIDENCE_FLOOR,
) -> dict[str, Any]:
    """يشتقّ مظروفاً استشاريّاً مُهيكَلاً من ``response`` (مخرَج نقطة الإجابة).

    ``decision`` يُمرَّر **فقط** من محرّك قرار موثوق (لا من النموذج)؛ افتراضه ``advisory_only``.
    الشكل مضمون: ``decision`` ضمن التعداد · ``confidence`` None أو 0..1 · القوائم قوائم ·
    ``requires_human_review`` منطقيّ. مدخل شاذّ ⇒ مظروف متحفّظ (advisory_only + مراجعة مطلوبة).
    """
    r = response if isinstance(response, dict) else {}
    answer = str(r.get("answer_ar") or "").strip()
    summary = answer if len(answer) <= _SUMMARY_MAX else answer[: _SUMMARY_MAX - 1].rstrip() + "…"

    conf = _clamp01(r.get("confidence"))
    dec = _coerce_decision(decision)
    evidence_used = _str_list(r.get("evidence_ids")) or _str_list(r.get("evidence_sources"))
    pending = r.get("pending_approvals") if isinstance(r.get("pending_approvals"), list) else []
    evidence_missing = _evidence_missing(r, evidence_used)
    limitations = _limitations(r, pending, conf, confidence_floor)

    # fail-safe: أيّ فعل مقترَح، أو قرار غير استشاريّ، أو غموض/نقص دليل ⇒ مراجعة بشريّة.
    requires_human_review = bool(
        pending
        or dec != "advisory_only"
        or conf is None
        or conf < confidence_floor
        or evidence_missing
    )

    return {
        "schema": "sahool.advisory_envelope/1",
        "summary": summary,
        "decision": dec,
        "confidence": conf,
        "evidence_used": evidence_used,
        "evidence_missing": evidence_missing,
        "limitations": limitations,
        "requires_human_review": requires_human_review,
        "decision_authority": str(r.get("decision_authority") or "field_intelligence_coordinator"),
    }
