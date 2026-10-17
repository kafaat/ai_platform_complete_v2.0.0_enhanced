"""core/outcome_reconciler.py — توحيد نموذجَي النتائج (Outcome Reconciler) — جسر #3.

كشف التدقيق نموذجَي نتائج متوازيَين، **مختلفَين دلاليّاً لا مكرّرَين**:

  • ``outcome_record`` (v79، مفتاح ``decision_id``): «أثر القرار» — planned/actual/metrics/success.
  • ``recommendation_outcomes`` (v49، مفتاح ``recommendation_id``): «تعلّم الغلّة» —
    توقّع مقابل فعليّ، قبول المزارع، النضج ضمن النافذة.

الموحِّد يُطبِّع كلًّا في شكل موحّد (بوسم ``source_model`` + ``kind``)، ويربطهما عبر جسر
``dispatch_decisions`` (recommendation_id → decision_id) متى توفّر، ويُعلن أنّ **كلّاً مرجعيّ
لسؤاله** (لا دمج مُفقِد للدلالة):
  • ``outcome_record`` مرجعيّ لأثر القرار (planned/actual/success).
  • ``recommendation_outcomes`` مرجعيّ لتعلّم الغلّة (predicted/actual/acceptance).

صدق: ``success`` لا يُختلَق — يُمرَّر مباشرةً من outcome_record، ويُشتَقّ بحذر من
recommendation_outcomes (فقط عند القبول واكتمال الغلّتين) وإلّا ``None``. لا شبكة/قاعدة — يستقبل
صفوفاً مقروءةً مسبقاً ويُخرِج العرض الموحّد. يستهلكه إسقاط الحقل-الموسم والذكاء.
"""

from __future__ import annotations

import math


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_outcome_record(row: dict) -> dict:
    """يُطبّع صفّ ``outcome_record`` (أثر القرار) إلى الشكل الموحّد."""
    return {
        "source_model": "outcome_record",
        "kind": "decision_effect",
        "outcome_id": row.get("outcome_id"),
        "field_id": row.get("field_id"),
        "farm_id": row.get("farm_id"),  # v79 لا يحمله ⇒ None (لا يُختلَق)
        "tenant_id": row.get("tenant_id"),  # لعدّ استقلال المستأجِرين (Copilot على #1001)
        "region": row.get("region"),
        "season_id": None,  # v79 لا يحمل season_id مباشرةً
        "decision_id": row.get("decision_id"),
        "recommendation_id": None,
        "success": row.get("success"),  # عمود مباشر (bool أو None)
        "result": {
            "planned": row.get("planned"),
            "actual": row.get("actual"),
            "metrics": row.get("metrics"),
            "stage": row.get("stage"),
            "region": row.get("region"),
        },
        "recorded_at": row.get("created_at"),
    }


def recommendation_outcome_eligibility(row: dict, *, require_acceptance: bool = True) -> dict:
    """سياسةُ أهليّةٍ واحدة لصفّ ``recommendation_outcomes`` قبل أيّ مقارنة أو ترشيح (U02).

    تُعيد ``{"eligible": bool, "reason": str | None}``. الأسباب بالترتيب:
    ``missing_prediction`` · ``missing_actual`` · ``non_finite_value`` · ``immature``
    (``matured_within_lag`` ليس صادقاً) · ``not_accepted`` (فقط حين يُطلَب القبول — أثرُ
    توصيةٍ لم تُتَّبَع لا يُنسَب، لكنّ دقّةَ توقّع الغلّة تُدرَس ولو رُفِضت التوصية).

    صدق (التدقيق الموحَّد 2026-09-13): قيمةٌ فعليّة مبكّرة قبل النضج كانت تدخل النجاح
    والدليل؛ الاختبار القديم غطّى ``actual=None`` وحدَه.
    """
    pred = _num(row.get("predicted_yield_t_ha"))
    act = _num(row.get("actual_yield_t_ha"))
    if pred is None:
        return {"eligible": False, "reason": "missing_prediction"}
    if act is None:
        return {"eligible": False, "reason": "missing_actual"}
    if not (math.isfinite(pred) and math.isfinite(act)):
        return {"eligible": False, "reason": "non_finite_value"}
    if not row.get("matured_within_lag"):
        return {"eligible": False, "reason": "immature"}
    if require_acceptance and not row.get("accepted"):
        return {"eligible": False, "reason": "not_accepted"}
    return {"eligible": True, "reason": None}


def _derive_rec_success(row: dict) -> bool | None:
    """يشتقّ نجاح توصية بحذر: فقط عند القبول والنضج واكتمال الغلّتين (فعليّ ≥ متوقّع).
    وإلّا None.

    صدق: غير مقبولة/غير مكتملة/غير ناضجة ⇒ لا حكم (لا يُنسَب نجاح لتوصية لم تُتَّبَع
    أو لم تنضج).
    """
    if not recommendation_outcome_eligibility(row)["eligible"]:
        return None
    return _num(row.get("actual_yield_t_ha")) >= _num(row.get("predicted_yield_t_ha"))


def _finite(v: float | None) -> float | None:
    """قيمةٌ منتهية أو ``None`` — NaN/Infinity لا تتسرّب إلى حمولة JSON (Copilot على #1001)."""
    return v if v is not None and math.isfinite(v) else None


def normalize_recommendation_outcome(row: dict) -> dict:
    """يُطبّع صفّ ``recommendation_outcomes`` (تعلّم الغلّة) إلى الشكل الموحّد.

    القيمُ غير المنتهية تُطبَّع إلى ``None`` في الحمولة (التوقّع والفعليّ والفرق معاً)؛ سببُ
    الاستبعاد يبقى معلَناً في ``eligibility`` المحسوبة من الصفّ الخام.
    """
    pred = _finite(_num(row.get("predicted_yield_t_ha")))
    act = _finite(_num(row.get("actual_yield_t_ha")))
    return {
        "source_model": "recommendation_outcomes",
        "kind": "yield_learning",
        "outcome_id": row.get("outcome_id"),
        "field_id": row.get("field_id"),
        # v49 يحمل farm_id (وحدةُ التكرار) — كان يُسقَط هنا فتبقى أعدادُ استقلال المزارع صفراً
        # (Copilot على #1001).
        "farm_id": row.get("farm_id"),
        "tenant_id": row.get("tenant_id"),
        "region": row.get("region"),
        "season_id": row.get("season_id"),
        "decision_id": None,
        "recommendation_id": row.get("recommendation_id"),
        "success": _derive_rec_success(row),
        "result": {
            "predicted_yield_t_ha": pred,
            "actual_yield_t_ha": act,
            "yield_delta_t_ha": (
                round(act - pred, 3) if pred is not None and act is not None else None
            ),
            "accepted": bool(row.get("accepted")),
            "matured_within_lag": bool(row.get("matured_within_lag")),
            # سببُ الاستبعاد يُعلَن مع الصفّ (لا None صامتة) — U02.
            "eligibility": recommendation_outcome_eligibility(row),
            "crop": row.get("crop"),
            "region": row.get("region"),
        },
        "recorded_at": row.get("outcome_recorded_at") or row.get("issued_at"),
    }


_AUTHORITATIVE_NOTE = (
    "نموذجان متكاملان لا مكرّران: outcome_record مرجعيّ لأثر القرار "
    "(planned/actual/success)؛ recommendation_outcomes مرجعيّ لتعلّم الغلّة "
    "(predicted/actual/acceptance). الربط عبر dispatch_decisions (rec→decision)."
)


SOURCE_MODELS = ("outcome_record", "recommendation_outcomes")

_SOURCE_SPLIT_NOTE = (
    "نسبة كلّ مصدر = ناجحة ÷ محسومة من صفوف ذلك المصدر وحده (success صريح True/False)؛ "
    "غير المحسومة تُستبعَد من المقام وتُعدّ بأسبابها؛ مقام صفر ⇒ success_rate=None. "
    "الحالة المربوطة عبر المصدرين تدخل مقام كلٍّ منهما مرّةً (سؤالان مختلفان) وتُعلَن في "
    "linked_overlap؛ أمّا overall.success_rate فيجمع صفوف المصدرين (أساس الصفوف)."
)


def _unsettled_reason(item: dict) -> str:
    """سببُ عدم حسم صفٍّ موحَّد — يُعلَن لا يُخفى (لا None صامتة).

    ``recommendation_outcomes``: سببُ الأهليّة نفسه (U02: missing_prediction · missing_actual ·
    non_finite_value · immature · not_accepted). ``outcome_record``: عمود ``success`` غائب
    (``success_missing``) أو ليس قيمةً منطقيّة صريحة (``success_not_boolean``).
    """
    if item.get("source_model") == "recommendation_outcomes":
        eligibility = (item.get("result") or {}).get("eligibility") or {}
        return eligibility.get("reason") or "success_not_derived"
    return "success_missing" if item.get("success") is None else "success_not_boolean"


def settled_success_by_source(unified: list[dict] | None) -> dict:
    """نسبة نجاح الصفوف المحسومة **لكلّ مصدر بمقامه** — نقيّ حتميّ.

    REPORT4-LEARNING-SUCCESS-RATE-SOURCE-SPLIT-01. ``unified``: العناصر المُطبَّعة من
    ``reconcile_outcomes``. لكلّ مصدر في ``SOURCE_MODELS``:
      • ``rows``: كلّ صفوف المصدر · ``settled_rows`` (المقام): ``success`` صريح True/False ·
        ``succeeded`` (البسط) · ``failed`` · ``unsettled_rows`` = rows − settled_rows (خارج المقام)
        مع ``unsettled_by_reason`` · ``success_rate`` = succeeded/settled_rows مقرّبة لثلاث، و``None``
        (لا صفر) حين المقام صفر.
    تُحسَب النسبة من قيمة ``success`` لكلّ صفّ لا من عدّادات (``metrics.n_success``/``by_source``).

    ``linked_overlap``: قرارات (``decision_id``) لها صفوف في **المصدرين معاً** بعد الربط عبر
    dispatch_decisions — تُعلَن ولا تُطرَح: كلّ مصدر يحسب صفوفه هو. مجموعةٌ من مصدر واحد (صفّا
    outcome_record للقرار نفسه) ليست تداخلاً بين المصدرين.
    """
    sources: dict[str, dict] = {
        name: {
            "rows": 0,
            "settled_rows": 0,
            "succeeded": 0,
            "failed": 0,
            "unsettled_rows": 0,
            "unsettled_by_reason": {},
        }
        for name in SOURCE_MODELS
    }
    # decision_id → مصدر → قائمة قيم success (لكشف التداخل بين المصدرين).
    by_decision: dict[str, dict[str, list]] = {}
    for item in unified or []:
        source = item.get("source_model")
        if source not in sources:
            continue
        bucket = sources[source]
        bucket["rows"] += 1
        success = item.get("success")
        if success is True:
            bucket["succeeded"] += 1
            bucket["settled_rows"] += 1
        elif success is False:
            bucket["failed"] += 1
            bucket["settled_rows"] += 1
        else:
            bucket["unsettled_rows"] += 1
            reasons = bucket["unsettled_by_reason"]
            reason = _unsettled_reason(item)
            reasons[reason] = reasons.get(reason, 0) + 1
        decision_id = item.get("decision_id")
        if decision_id:
            by_decision.setdefault(decision_id, {}).setdefault(source, []).append(success)

    for bucket in sources.values():
        settled = bucket["settled_rows"]
        bucket["success_rate"] = round(bucket["succeeded"] / settled, 3) if settled else None

    overlap_rows = dict.fromkeys(SOURCE_MODELS, 0)
    overlap_cases = 0
    settled_in_both = 0
    for per_source in by_decision.values():
        if not all(name in per_source for name in SOURCE_MODELS):
            continue
        overlap_cases += 1
        for name in SOURCE_MODELS:
            overlap_rows[name] += len(per_source[name])
        if all(any(s is True or s is False for s in per_source[name]) for name in SOURCE_MODELS):
            settled_in_both += 1

    return {
        "basis": "settled_rows_per_source",
        "sources": sources,
        "linked_overlap": {
            "linked_via": "decision_id (dispatch_decisions)",
            "cases": overlap_cases,
            "rows_by_source": overlap_rows,
            "settled_in_both_sources": settled_in_both,
            "counted_in_each_source": True,
        },
        "note": _SOURCE_SPLIT_NOTE,
    }


def reconcile_outcomes(
    outcome_records: list[dict] | None,
    recommendation_outcomes: list[dict] | None,
    *,
    dispatch_links: dict | None = None,
) -> dict:
    """يوحّد النموذجَين في عرض واحد + يربطهما عبر جسر القرار متى توفّر.

    ``dispatch_links``: تعيين ``recommendation_id -> decision_id`` (من dispatch_decisions) للربط.
    يُعيد: ``unified`` (كلّ العناصر مُطبَّعة)، ``by_source``/``by_kind``، ``linked_groups`` (عناصر
    تشترك decision_id بعد الربط)، ``authoritative_note``.
    """
    links = dispatch_links or {}
    unified: list[dict] = []
    for r in outcome_records or []:
        unified.append(normalize_outcome_record(r))
    for r in recommendation_outcomes or []:
        item = normalize_recommendation_outcome(r)
        # ربط ليّن: إن عرفنا decision لهذه التوصية عبر الجسر، اربطه (لا اختلاق).
        dec = links.get(item["recommendation_id"]) if item["recommendation_id"] else None
        if dec:
            item["decision_id"] = dec
            item["linked_via"] = "dispatch_decisions"
        unified.append(item)

    by_source: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for u in unified:
        by_source[u["source_model"]] = by_source.get(u["source_model"], 0) + 1
        by_kind[u["kind"]] = by_kind.get(u["kind"], 0) + 1

    # مجموعات مربوطة: عناصر تشترك decision_id (سلسلة سببيّة واحدة عبر النموذجَين).
    groups: dict[str, list[dict]] = {}
    for u in unified:
        did = u.get("decision_id")
        if did:
            groups.setdefault(did, []).append(u)
    linked_groups = [
        {"decision_id": did, "members": members}
        for did, members in groups.items()
        if len(members) > 1
    ]

    return {
        "unified": unified,
        "total": len(unified),
        "by_source": by_source,
        "by_kind": by_kind,
        "linked_groups": linked_groups,
        "authoritative_note": _AUTHORITATIVE_NOTE,
    }
