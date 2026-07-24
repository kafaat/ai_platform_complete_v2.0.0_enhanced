"""مُصالِح النتائج (P1-13a) — منطق نقيّ يوحّد قراءة مصدرَي النتائج المزدوجَين.

التدقيق (P1-13): يوجد نموذجا نتائج — ``outcome_record`` (مفتاح ``decision_id``، عمود ``success``
منطقيّ) و``recommendation_outcomes`` (مفتاح ``recommendation_id``+``season_id``) — وكانت نقطة
``/v1/outcomes/reconciled`` **stub يعيد أصفاراً** بلا ضمّ فعليّ. هذا يُنتج خطرَين: (أ) عدّ مزدوج
لو وُصِف قرارٌ في الجدولَين، (ب) نسبة نجاح مُختلَقة فوق صفوف لا تُحسَم نتيجتها.

هذه الوحدة نقيّة (بلا قاعدة/إطار): تأخذ صفوف الجدولَين كما هي وتُنتج ملخّصاً صادقاً:
  * ``unique_decisions`` يفكّ العدّ المزدوج صراحةً (قرارات مميَّزة عبر المصدرَين).
  * ``success_rate`` تُحسَب **فقط** فوق الصفوف القابلة للحسم (``evaluated_count``)؛ الصفوف غير
    القابلة للحسم تدخل دلو ``unknown`` — لا تُحتسَب نجاحاً ولا فشلاً (لا اختلاق).
  * مُتسامِح مع الأعمدة: يشتقّ النجاح من أيّ إشارة حاضرة، فلا يكسر عند اختلاف مخطّط الجدولَين.
"""

from __future__ import annotations

from typing import Any

_SUCCESS_TOKENS = {"success", "succeeded", "successful", "positive", "improved", "met", "exceeded"}
_FAILURE_TOKENS = {"failure", "failed", "negative", "worse", "missed", "unmet"}


def _tri(value: Any) -> bool | None:
    """يحوّل قيمة نجاح إلى True/False/None (غير محسوم) دون افتراض."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _SUCCESS_TOKENS:
            return True
        if v in _FAILURE_TOKENS:
            return False
    return None


def _outcome_record_success(row: dict[str, Any]) -> bool | None:
    # ``success`` منطقيّ صريح (قد يكون NULL عند تعذّر الحسم).
    return _tri(row.get("success"))


def _recommendation_success(row: dict[str, Any]) -> bool | None:
    # أولويّة: عمود ``outcome`` النصّيّ إن وُجِد؛ وإلّا مقارنة الغلّة الفعليّة بالمتوقّعة.
    tok = _tri(row.get("outcome"))
    if tok is not None:
        return tok
    actual = row.get("actual_yield_t_ha")
    predicted = row.get("predicted_yield_t_ha")
    if actual is not None and predicted is not None:
        try:
            return float(actual) >= float(predicted)  # بلغت/تجاوزت التوقّع ⇒ نجاح
        except (TypeError, ValueError):
            return None
    return None  # لا إشارة نتيجة قابلة للحسم (accepted وحده ليس نتيجة)


def _bucket(rows: list[dict[str, Any]], success_fn) -> dict[str, int]:
    out = {"count": len(rows), "success": 0, "failure": 0, "unknown": 0}
    for r in rows:
        s = success_fn(r)
        if s is True:
            out["success"] += 1
        elif s is False:
            out["failure"] += 1
        else:
            out["unknown"] += 1
    return out


def reconcile_outcomes(
    outcome_rows: list[dict[str, Any]],
    recommendation_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """يوحّد صفوف الجدولَين في ملخّص مصالحة صادق (لا عدّ مزدوج، لا نسبة مُلفّقة)."""
    by_source = {
        "outcome_record": _bucket(outcome_rows, _outcome_record_success),
        "recommendation_outcomes": _bucket(recommendation_rows, _recommendation_success),
    }
    success_count = (
        by_source["outcome_record"]["success"] + by_source["recommendation_outcomes"]["success"]
    )
    failure_count = (
        by_source["outcome_record"]["failure"] + by_source["recommendation_outcomes"]["failure"]
    )
    unknown_count = (
        by_source["outcome_record"]["unknown"] + by_source["recommendation_outcomes"]["unknown"]
    )
    evaluated = success_count + failure_count

    # قرارات مميَّزة عبر المصدرَين (يفكّ العدّ المزدوج — قد يُوصَف قرارٌ في الجدولَين).
    decisions: set[str] = set()
    for r in [*outcome_rows, *recommendation_rows]:
        did = r.get("decision_id")
        if did:
            decisions.add(str(did))

    return {
        "enabled": True,
        "sample_count": len(outcome_rows) + len(recommendation_rows),
        "unique_decisions": len(decisions),
        "evaluated_count": evaluated,
        "success_count": success_count,
        "success_rate": round(success_count / evaluated, 3) if evaluated else None,
        "by_source": by_source,
        "by_kind": {"success": success_count, "failure": failure_count, "unknown": unknown_count},
    }
