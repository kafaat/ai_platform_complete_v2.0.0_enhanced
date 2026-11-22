"""Where the text of a supervisor answer came from, and what its numbers do not mean.

A skill result names its own origin (``source``, ``generation_status``); the route used to
drop both and publish the intent classifier's score as ``confidence``. This module turns a
skill result into the fields the channel answer carries, and the Arabic line a chat shows.
It never raises an answer above what the skill declared: an origin it does not recognise is
``undeclared``, and no answer is calibrated or exempt from human review.
"""

from __future__ import annotations

from typing import Any

# Text origins a channel may show. ``system_notice`` is a refusal or an outage message,
# not advice; ``undeclared`` is a skill that did not say where its text came from.
TEXT_SOURCES = ("template", "validated_facts", "evidence_only", "system_notice", "undeclared")
GENERATION_STATUSES = (
    "not_attempted",
    "attempted_failed",
    "suppressed_unvalidated_output",
    "validated_structured_facts",
    "not_reported",
)
_SYSTEM_NOTICE_TYPES = frozenset({"unavailable", "governance_pending", "error", "degraded"})

_SOURCE_AR = {
    "template": "قالب نصّي ثابت بلا مصدر مُراجَع",
    "validated_facts": "حقائق مُتحقَّق منها مقابل حالة الحقل المعتمدة",
    "evidence_only": "عرض أدلّة فقط بلا توصية",
    "system_notice": "إشعار من النظام وليس نصيحة زراعيّة",
    "undeclared": "مصدر النصّ غير مُعلَن",
}
_GENERATION_AR = {
    "not_attempted": "لم يُستخدَم توليد آليّ",
    "attempted_failed": "تعذّر التوليد الآليّ",
    "suppressed_unvalidated_output": "حُجب نصّ مولَّد آليّاً لم يُتحقَّق منه",
    "validated_structured_facts": "ناتج آليّ تُحقِّق من حقائقه",
    "not_reported": "حالة التوليد غير مُعلَنة",
}
_REVIEW_AR = "الثقة غير مُعايَرة، وتلزم مراجعة مهندس زراعيّ مختصّ قبل الاعتماد."


def text_source(result: dict[str, Any]) -> str:
    """Map what the skill declared to one of ``TEXT_SOURCES``."""
    if result.get("type") in _SYSTEM_NOTICE_TYPES:
        return "system_notice"
    declared = result.get("source")
    if declared == "template":
        return "template"
    if declared == "llm-rag":
        # Only output that passed the structured-claims checker is called validated.
        validated = result.get("generation_status") == "validated_structured_facts"
        return "validated_facts" if validated else "undeclared"
    if declared == "platform-diagnose":
        return "evidence_only"
    return "undeclared"


def generation_status(result: dict[str, Any]) -> str:
    status = result.get("generation_status")
    return status if status in GENERATION_STATUSES else "not_reported"


def provenance_note_ar(source: str, status: str) -> str:
    """The one line a chat shows under the answer."""
    return (
        f"المصدر: {_SOURCE_AR.get(source, _SOURCE_AR['undeclared'])}. "
        f"التوليد: {_GENERATION_AR.get(status, _GENERATION_AR['not_reported'])}. "
        f"{_REVIEW_AR}"
    )


def answer_provenance(
    result: dict[str, Any], intent_confidence: float | None = None
) -> dict[str, Any]:
    """Fields of the channel answer that say where ``result``'s text came from.

    ``intent_confidence`` is the router's score for *which skill to call*. It is carried
    under its own name; ``confidence`` (confidence in the answer) is 0.0 because nothing
    on this route produces a calibrated one, whatever the skill result claims.
    """
    source = text_source(result)
    status = generation_status(result)
    return {
        "confidence": 0.0,
        "intent_confidence": intent_confidence,
        "text_source": source,
        "generation_status": status,
        "provenance_note_ar": provenance_note_ar(source, status),
    }
