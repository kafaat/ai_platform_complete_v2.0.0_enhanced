"""api/learning_summary.py — تلخيص حلقة التعلّم للوحات الرصد (Learning Dashboard data)

يُجمِّع حالة حلقة التعلّم المُدامة (Decision→Outcome→Evidence) في لقطة لكلّ منطقة
لتُغذّي لوحة الرصد: كم قراراً أُدِيم؟ كم نتيجة قِيست؟ ما نسبة نجاحها؟ أيّ مستوى دليل
بلغته المنطقة نحو «مُتحقَّق ميدانيّاً»؟ متى آخر نشاط؟

نقيّ حتميّ (لا I/O، لا قاعدة، لا ساعة): الموجِّه يقرأ الصفوف عبر tenant_connection
(معزولة بـRLS) ويُمرّرها هنا للتجميع. هذا يجعل المنطق قابلاً للاختبار وحدويّاً بلا قاعدة.

الصدق:
  • counts/success_rate حقيقيّة من القاعدة لا تُفبرَك: success_rate من `outcome_record.success`
    (نتائج محسومة فقط)؛ النتائج المُعلّقة (success IS NULL) تُحصى منفصلةً ولا تُدخَل البسط/المقام.
  • الناقص ⇒ None/0 لا تلفيق: منطقة بلا نتائج ⇒ success_rate=None وأصفار.
  • مستوى الدليل عبر evidence_from_persisted_outcomes (مصدر واحد لعتبة field_verified الموسومة).
  • calibrated=false: العتبات (field_verified) تقديريّة غير معايَرة — تُعلَن لا تُخفى.
"""

from __future__ import annotations

from api.evidence_registry import evidence_from_persisted_outcomes

# تسمية مجموعة الصفوف بلا منطقة (region NULL/فارغ) — تُكشَف لا تُخفى.
_UNSPECIFIED_REGION = "_unspecified"


def _max_stamp(*stamps):
    """أحدث طابع زمنيّ غير-None من مجموعة (آخر نشاط) — نقيّ، لا ساعة."""
    present = [s for s in stamps if s is not None]
    return max(present) if present else None


def _success_breakdown(outcome_rows: list[dict]) -> tuple[int, int, int]:
    """يقسّم نتائج المنطقة إلى (محسومة-ناجحة، محسومة-فاشلة، معلّقة) من `success`.

    صدق: success=True ⇒ ناجحة، success=False ⇒ فاشلة، success=None ⇒ معلّقة (لم تُحسَم —
    لا تدخل نسبة النجاح). لا حكم مُختلق على المعلّقة.
    """
    succeeded = failed = pending = 0
    for r in outcome_rows:
        s = r.get("success")
        if s is True:
            succeeded += 1
        elif s is False:
            failed += 1
        else:
            pending += 1
    return succeeded, failed, pending


def summarize_region(
    region: str,
    decision_rows: list[dict],
    outcome_rows: list[dict],
    expert_calibrated: bool = False,
) -> dict:
    """يُلخّص حلقة التعلّم لمنطقة واحدة — نقيّ حتميّ.

    decision_rows: صفوف decision_record لهذه المنطقة (كلّ صفّ {created_at?, …}).
    outcome_rows: صفوف outcome_record لهذه المنطقة (كلّ صفّ {success?, metrics?, created_at?}).
    expert_calibrated: هل للمنطقة قيم خبير مُسبقاً (يرفع المستوى من none إلى expert_opinion).

    يعيد لقطة: عدد القرارات، عدد النتائج (إجماليّ + محسوم/معلّق)، نسبة النجاح من
    `success` (None إن لا نتيجة محسومة)، مستوى الدليل/العيّنات نحو field_verified
    (عبر evidence_from_persisted_outcomes)، وآخر نشاط (أحدث created_at عبر الجدولين).
    """
    decision_count = len(decision_rows)
    outcome_count = len(outcome_rows)
    succeeded, failed, pending = _success_breakdown(outcome_rows)
    decided = succeeded + failed
    # نسبة النجاح من النتائج المحسومة فقط (success non-NULL) — لا تُفبرَك من المعلّقة.
    success_rate = round(succeeded / decided, 3) if decided else None

    # الدليل التراكميّ نحو عتبة field_verified — مصدر واحد لمنطق العتبة (لا تكرار).
    evidence = evidence_from_persisted_outcomes(
        region, outcome_rows, expert_calibrated=expert_calibrated
    )

    last_decision_at = _max_stamp(*(r.get("created_at") for r in decision_rows))
    last_outcome_at = _max_stamp(*(r.get("created_at") for r in outcome_rows))
    last_activity_at = _max_stamp(last_decision_at, last_outcome_at)

    return {
        "region": region,
        "decision_count": decision_count,
        "outcome_count": outcome_count,
        "outcomes_decided": decided,  # محسومة (success non-NULL) — أساس نسبة النجاح
        "outcomes_succeeded": succeeded,
        "outcomes_failed": failed,
        "outcomes_pending": pending,  # success IS NULL — لم تُحسَم بعد (لا تدخل النسبة)
        "success_rate": success_rate,  # None إن لا نتيجة محسومة (لا تلفيق)
        "evidence_level": evidence["evidence_level"],
        "sample_count": evidence["sample_count"],
        "samples_to_verified": evidence["samples_to_verified"],
        "field_verified_min_samples": evidence["field_verified_min_samples"],
        "last_decision_at": last_decision_at,
        "last_outcome_at": last_outcome_at,
        "last_activity_at": last_activity_at,
        "calibrated": False,  # العتبات تقديريّة غير معايَرة — تُعلَن لا تُخفى
    }


def _region_key(row: dict) -> str:
    """مفتاح تجميع المنطقة من صفّ — region NULL/فارغ ⇒ المجموعة غير المحدّدة (تُكشَف لا تُخفى)."""
    region = row.get("region")
    if region is None or (isinstance(region, str) and not region.strip()):
        return _UNSPECIFIED_REGION
    return region


def summarize_learning(
    decision_rows: list[dict],
    outcome_rows: list[dict],
    expert_calibrated_regions: set[str] | None = None,
) -> dict:
    """يُجمِّع حلقة التعلّم عبر كلّ المناطق + إجماليّ — نقيّ حتميّ (لا قاعدة).

    decision_rows/outcome_rows: صفوف الجدولين للمستأجِر (مقروءة بالموجِّه عبر RLS).
    expert_calibrated_regions: مناطق لها قيم خبير (لرفع مستوى دليلها). تُجمَّع الصفوف
    بـregion (NULL ⇒ مجموعة غير محدّدة تُكشَف)، ولكلّ مجموعة summarize_region؛ والإجماليّ
    summarize_region على كلّ الصفوف (region="_overall").

    الصدق: لا منطقة ⇒ regions=[] وإجماليّ أصفار/None؛ counts/success_rate حقيقيّة من القاعدة.
    """
    expert = expert_calibrated_regions or set()

    # تجميع الصفوف تحت مناطقها (مفاتيح من كلا الجدولين — منطقة قراراتها بلا نتائج تظهر، والعكس).
    by_region_decisions: dict[str, list[dict]] = {}
    by_region_outcomes: dict[str, list[dict]] = {}
    for r in decision_rows:
        by_region_decisions.setdefault(_region_key(r), []).append(r)
    for r in outcome_rows:
        by_region_outcomes.setdefault(_region_key(r), []).append(r)

    region_keys = sorted(set(by_region_decisions) | set(by_region_outcomes))
    regions = [
        summarize_region(
            key,
            by_region_decisions.get(key, []),
            by_region_outcomes.get(key, []),
            expert_calibrated=(key in expert),
        )
        for key in region_keys
    ]

    overall = summarize_region(
        "_overall",
        decision_rows,
        outcome_rows,
        expert_calibrated=bool(expert),
    )

    return {
        "regions": regions,
        "region_count": len(regions),
        "overall": overall,
        "calibrated": False,  # العتبات تقديريّة — اللقطة وصفيّة لا توجيهيّة معايَرة
    }


def _learning_row_from_unified_outcome(item: dict) -> dict:
    """Converts a reconciled outcome item into the compact row used by learning summary.

    Truthfulness rules:
      * success is copied from the reconciler; unresolved/immature outcomes stay None.
      * region is copied from the source row when available; missing region remains unspecified.
      * metrics are evidence counters only: one evaluated sample when the outcome is decided,
        zero when pending. This prevents yield-learning rows from inflating evidence before maturity.
    """
    success = item.get("success")
    decided = success is True or success is False
    result = item.get("result") or {}
    return {
        "region": item.get("region") or result.get("region"),
        "success": success,
        "metrics": {
            "n_evaluated": 1 if decided else 0,
            "n_success": 1 if success is True else 0,
            "source_model": item.get("source_model"),
            "kind": item.get("kind"),
        },
        "created_at": item.get("recorded_at"),
    }


def summarize_learning_with_reconciled_outcomes(
    decision_rows: list[dict],
    outcome_records: list[dict],
    recommendation_outcomes: list[dict] | None = None,
    *,
    dispatch_links: dict | None = None,
    expert_calibrated_regions: set[str] | None = None,
) -> dict:
    """Summarizes learning after reconciling the two outcome models.

    This is the read-path bridge for the previously pure ``core.outcome_reconciler``:
    ``outcome_record`` remains authoritative for decision effects, while
    ``recommendation_outcomes`` contributes yield-learning outcomes when present. Both are exposed
    under ``outcome_reconciliation`` so dashboards can see the source mix rather than silently
    merging incompatible models.
    """
    from core.outcome_reconciler import reconcile_outcomes

    reconciled = reconcile_outcomes(
        outcome_records or [],
        recommendation_outcomes or [],
        dispatch_links=dispatch_links or {},
    )
    learning_outcomes = [_learning_row_from_unified_outcome(u) for u in reconciled["unified"]]
    summary = summarize_learning(
        decision_rows,
        learning_outcomes,
        expert_calibrated_regions=expert_calibrated_regions,
    )
    summary["outcome_reconciliation"] = {
        "enabled": True,
        "total": reconciled["total"],
        "by_source": reconciled["by_source"],
        "by_kind": reconciled["by_kind"],
        "linked_group_count": len(reconciled["linked_groups"]),
        "authoritative_note": reconciled["authoritative_note"],
    }
    return summary
