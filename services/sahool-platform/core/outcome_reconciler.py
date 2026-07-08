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


def _derive_rec_success(row: dict) -> bool | None:
    """يشتقّ نجاح توصية بحذر: فقط عند القبول واكتمال الغلّتين (فعليّ ≥ متوقّع). وإلّا None.

    صدق: غير مقبولة/غير مكتملة ⇒ لا حكم (لا يُنسَب نجاح لتوصية لم تُتَّبَع أو لم تنضج).
    """
    if not row.get("accepted"):
        return None
    pred = _num(row.get("predicted_yield_t_ha"))
    act = _num(row.get("actual_yield_t_ha"))
    if pred is None or act is None:
        return None
    return act >= pred


def normalize_recommendation_outcome(row: dict) -> dict:
    """يُطبّع صفّ ``recommendation_outcomes`` (تعلّم الغلّة) إلى الشكل الموحّد."""
    pred = _num(row.get("predicted_yield_t_ha"))
    act = _num(row.get("actual_yield_t_ha"))
    return {
        "source_model": "recommendation_outcomes",
        "kind": "yield_learning",
        "outcome_id": row.get("outcome_id"),
        "field_id": row.get("field_id"),
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
            "crop": row.get("crop"),
        },
        "recorded_at": row.get("outcome_recorded_at") or row.get("issued_at"),
    }


_AUTHORITATIVE_NOTE = (
    "نموذجان متكاملان لا مكرّران: outcome_record مرجعيّ لأثر القرار "
    "(planned/actual/success)؛ recommendation_outcomes مرجعيّ لتعلّم الغلّة "
    "(predicted/actual/acceptance). الربط عبر dispatch_decisions (rec→decision)."
)


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
