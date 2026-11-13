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


# ── تسميات التعلّم من جهة الخادم (F4 — R09) ─────────────────────────────────────────
# التوقّعُ ونضجُ النتيجة تسميتا تعلّم: كانا يُقبَلان من العميل كما هما فيكتب أيُّ مستخدمٍ
# «توقّعاً» يطابق الحصاد فيُصفِّر الخطأ. حين يوجد السجلّ المُخزَّن (توصية/قرار) يُقرأ التوقّع منه،
# ويُرفَض توقّعُ عميلٍ يخالفه؛ ويُشتقّ النضج من الطوابع الزمنيّة متى أمكن.
LABEL_TOLERANCE = 1e-6


class OutcomeLabelConflict(ValueError):
    """تسميةٌ من العميل تخالف السجلّ المُخزَّن — يُترجِمها المسار إلى 422."""

    def __init__(self, code: str, detail: dict | None = None):
        super().__init__(code)
        self.code = code
        self.detail = {"code": code, **(detail or {})}


def _as_mapping(value) -> dict:
    if isinstance(value, (str, bytes, bytearray)):
        import json

        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def find_stored_value(document, key: str, *, max_depth: int = 2):
    """أوّلُ قيمةٍ غير فارغة لـ``key`` في وثيقة JSON مُخزَّنة (المستوى الأعلى ثمّ المتداخل)."""
    level = [_as_mapping(document)]
    for _ in range(max_depth + 1):
        nested: list[dict] = []
        for node in level:
            if node.get(key) is not None:
                return node[key]
            nested.extend(v for v in node.values() if isinstance(v, dict))
        level = nested
    return None


def labels_differ(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(a - b) > LABEL_TOLERANCE


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def reconcile_recommendation_outcome_labels(
    *,
    stored: dict | None,
    client_predicted,
    client_matured: bool,
    actual,
    crop: str | None,
    field_id: str | None,
    now: str | None = None,
) -> dict:
    """يحسم تسميتَي التعلّم لصفّ ``recommendation_outcomes`` من التوصية المُخزَّنة.

    ``stored``: صفّ ``recommendations`` (field_id · crop · recommendation · issued_at) أو None.
    بلا سجلّ مُخزَّن تبقى قيمُ العميل موسومةً ``client_unverified``. مع السجلّ:
    حقلٌ/محصولٌ مخالف ⇒ تعارض · توقّعُ عميلٍ يخالف المُخزَّن (أو يُختلَق حيث لا توقّع
    مُخزَّن) ⇒ تعارض · غيابُه ⇒ يُملأ من المُخزَّن · النضجُ يُشتقّ من ``issued_at`` ونافذة
    المحصول حين تُعرَف، وادّعاءُ عميلٍ بالنضج يخالف الاشتقاق ⇒ تعارض.
    """
    predicted = _num(client_predicted)
    act = _num(actual)
    out = {
        "predicted_yield_t_ha": predicted,
        "matured_within_lag": bool(client_matured),
        "prediction_source": "client_unverified" if predicted is not None else None,
        "maturity_source": "client_unverified",
    }
    if stored is None:
        return out

    stored_field = stored.get("field_id")
    if stored_field and field_id and str(stored_field) != str(field_id):
        raise OutcomeLabelConflict(
            "field_mismatch", {"stored_field_id": stored_field, "field_id": field_id}
        )
    stored_crop = stored.get("crop")
    if stored_crop and crop and str(stored_crop) != str(crop):
        raise OutcomeLabelConflict("crop_mismatch", {"stored_crop": stored_crop, "crop": crop})

    stored_pred = _finite(
        _num(find_stored_value(stored.get("recommendation"), "predicted_yield_t_ha"))
    )
    if predicted is not None and labels_differ(predicted, stored_pred):
        raise OutcomeLabelConflict(
            "predicted_yield_mismatch",
            {"stored_predicted_yield_t_ha": stored_pred, "predicted_yield_t_ha": predicted},
        )
    out["predicted_yield_t_ha"] = stored_pred
    out["prediction_source"] = "stored_recommendation" if stored_pred is not None else None

    issued = _iso(stored.get("issued_at") or stored.get("created_at"))
    lag_crop = str(stored_crop or crop or "")
    if issued:
        from core.feedback_closure import _DEFAULT_LAG_WINDOWS, is_outcome_ready_for_learning

        if lag_crop in _DEFAULT_LAG_WINDOWS:
            ready, _reason = is_outcome_ready_for_learning(issued, lag_crop, now)
            derived = bool(ready and act is not None)
            if client_matured and not derived:
                raise OutcomeLabelConflict(
                    "maturity_contradicts_timestamps",
                    {"issued_at": issued, "crop": lag_crop, "derived_matured_within_lag": False},
                )
            out["matured_within_lag"] = derived
            out["maturity_source"] = "derived_from_timestamps"
    return out


def authoritative_outcome_label_refusal(labels: dict) -> str | None:
    """ما يرفضه القطع (S4) قبل أن يكتب decision-service تسميةَ تعلّمٍ سلطويّة.

    ``labels`` ناتج ``reconcile_recommendation_outcome_labels`` (التعارض مع التوصية
    المختومة رُفض قبله بـ``OutcomeLabelConflict``). توقّعٌ لم يُطابَق بسجلّ مخزَّن، أو
    ادّعاءُ نضجٍ لم يُشتقّ من الطوابع، لا يصير حقيقةَ تعلّم. ادّعاءُ «لم ينضج» لا يرفع
    تسميةً فلا يُرفَض. يُعيد رمز الرفض أو ``None``.
    """
    if labels.get("prediction_source") == "client_unverified":
        return "unverified_predicted_yield_not_authoritative"
    if (
        labels.get("matured_within_lag")
        and labels.get("maturity_source") != "derived_from_timestamps"
    ):
        return "unverified_maturity_not_authoritative"
    return None


def recommendation_outcome_write_action(existing: dict | None, *, actual_yield_t_ha) -> str:
    """لا صفَّ ثانياً لـ(المستأجِر، recommendation_id) — يقرّر الكاتب ماذا يفعل بالموجود.

    ``insert`` بلا صفّ سابق · ``complete`` صفٌّ معلَّق (بلا فعليّ) يكتمل الآن · ``replay``
    إعادةٌ لا تضيف معلومة (أو الفعليّ نفسه) · ``conflict`` فعليٌّ مختلف لنتيجةٍ مكتملة.
    """
    if existing is None:
        return "insert"
    prev = _num(existing.get("actual_yield_t_ha"))
    new = _num(actual_yield_t_ha)
    if prev is None and new is not None:
        return "complete"
    if new is None or not labels_differ(prev, new):
        return "replay"
    return "conflict"


def reconcile_planned_with_decision(
    *, stored: dict | None, client_planned: dict, field_id: str | None
) -> tuple[dict, dict]:
    """يحسم ``planned`` لنتيجة قرار من ``decision_record`` المُخزَّن (F4).

    يُعيد (planned، مصدر كلّ مفتاح). مفتاحٌ يحمله القرار المُخزَّن ⇒ قيمته هي المعتمدة،
    وقيمةُ عميلٍ تخالفه ⇒ ``OutcomeLabelConflict``؛ مفتاحٌ لا يحمله القرار يبقى من العميل
    موسوماً ``client_unverified`` (``decision_value`` حرّ الشكل فلا يُفترَض ما ليس فيه).
    """
    planned = dict(client_planned or {})
    sources = {k: "client_unverified" for k, v in planned.items() if v is not None}
    if stored is None:
        return planned, sources
    stored_field = stored.get("field_id")
    if stored_field and field_id and str(stored_field) != str(field_id):
        raise OutcomeLabelConflict(
            "field_mismatch", {"stored_field_id": stored_field, "field_id": field_id}
        )
    for key in list(planned):
        stored_value = _finite(_num(find_stored_value(stored.get("decision_value"), key)))
        if stored_value is None:
            continue
        client_value = _num(planned.get(key))
        if client_value is not None and labels_differ(client_value, stored_value):
            raise OutcomeLabelConflict(
                "planned_mismatch",
                {"key": key, "stored_value": stored_value, "client_value": client_value},
            )
        # النوع يُحفَظ (أيّام الإجهاد عددٌ صحيح في النموذج).
        integral = key.endswith("_days") and stored_value.is_integer()
        planned[key] = int(stored_value) if integral else stored_value
        sources[key] = "decision_record"
    return planned, sources


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
