"""core/loop_referential_integrity.py — سلامة مرجعيّة حلقة التوصية (جسر #5) — كشف لا فرض.

تدقيق إغلاق الحلقة رصد «لا FK على جداول الحلقة ⇒ أيتام ممكنة». الفحص الأعمق أثبت أنّ غياب
الـFK **مقصود معماريّاً لا إهمال**:

  • ``recommendation_id`` نصّيّ (VARCHAR/TEXT) في كلّ الحلقة، لكنّ ``recommendations.id`` من نوع
    **UUID** ⇒ عدم توافق نوع، فالمعرّف **مُعرِّف ربط ليّن عبر الخدمات** لا FK.
  • ``outcome_record.decision_id`` مُصرَّح صراحةً (COMMENT v79) «ربط نَسَب ليّن … يحفظ RLS».
  • كُتّاب متعدّدو الخدمات + عزل RLS + ``lineage_link`` (v82) كعمود نَسَب — فرض FID صلب يكسر
    الإدراج عبر الخدمات ويناقض المعماريّة.

لذا الحماية الصحيحة ليست FK صلباً (يكسر المرونة)، بل **كشف الأيتام** (مصالحة دوريّة): دالّات نقيّة
تكشف طفلاً يشير إلى أبٍ غائب — للمراجعة/التنبيه، لا للحجب. تستقبل صفوفاً مقروءةً مسبقاً وتُخرِج
تقرير الأيتام. لا شبكة/قاعدة.

صدق: الكشف لا يُصلح ولا يخترع؛ الغياب يُعلَن. المُعرِّف الفارغ لا يُعَدّ يتيماً (لا مرجع ليُفحَص).
"""

from __future__ import annotations


def find_orphan_outcomes(
    outcome_rows: list[dict] | None, known_decision_ids: set | list | None
) -> list[dict]:
    """صفوف نتائج تشير إلى ``decision_id`` غير موجود في المجموعة المعروفة (يتيمة).

    المُعرِّف الفارغ/None لا يُعَدّ يتيماً (لا مرجع). المقارنة نصّيّة صرفة.
    """
    known = set(known_decision_ids or [])
    out = []
    for r in outcome_rows or []:
        did = r.get("decision_id")
        if did and did not in known:
            out.append(r)
    return out


def find_orphan_dispatches(
    dispatch_rows: list[dict] | None, known_recommendation_ids: set | list | None
) -> list[dict]:
    """صفوف قرارات إرسال تشير إلى ``recommendation_id`` غير معروف (يتيمة)."""
    known = set(known_recommendation_ids or [])
    out = []
    for r in dispatch_rows or []:
        rid = r.get("recommendation_id")
        if rid and rid not in known:
            out.append(r)
    return out


def reconciliation_report(
    *,
    outcome_rows: list[dict] | None = None,
    known_decision_ids: set | list | None = None,
    dispatch_rows: list[dict] | None = None,
    known_recommendation_ids: set | list | None = None,
) -> dict:
    """تقرير مصالحة مرجعيّة: يجمع أيتام النتائج/الإرسال + النِّسَب. للمراجعة لا الحجب.

    يُعيد أعداد الأيتام لكلّ نوع + نسبتها + ``clean`` (خالٍ من الأيتام) + ملاحظة الطبيعة الكشفيّة.
    """
    orphan_outcomes = find_orphan_outcomes(outcome_rows, known_decision_ids)
    orphan_dispatches = find_orphan_dispatches(dispatch_rows, known_recommendation_ids)
    n_out = len(outcome_rows or [])
    n_disp = len(dispatch_rows or [])
    return {
        "orphan_outcomes": orphan_outcomes,
        "orphan_outcome_count": len(orphan_outcomes),
        "orphan_dispatches": orphan_dispatches,
        "orphan_dispatch_count": len(orphan_dispatches),
        "total_outcomes": n_out,
        "total_dispatches": n_disp,
        "orphan_outcome_ratio": (round(len(orphan_outcomes) / n_out, 3) if n_out else None),
        "orphan_dispatch_ratio": (round(len(orphan_dispatches) / n_disp, 3) if n_disp else None),
        "clean": not orphan_outcomes and not orphan_dispatches,
        "note_ar": (
            "كشف لا فرض: الروابط ليّنة معماريّاً (معرّفات نصّيّة عبر خدمات + RLS + lineage_link) — "
            "لا FK صلب. الأيتام تُراجَع/تُنبَّه دوريّاً، لا تُحجَب."
        ),
    }
