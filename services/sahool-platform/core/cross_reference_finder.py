"""
sahool_core.cross_reference_finder
====================================
مكتشف الأنماط التاريخية — Connection Finder بسياق زراعي.

استلهام محدود من Karpathy: "ملاحظة جديدة تتصل بملاحظة قديمة" → سهول:
"حالة زراعية اليوم تشبه حالة تاريخية" (دون نسخ الإطار الشخصي).

الفجوة المسدودة: لدينا recommendation_log + activity_log + calibration
لكن لا آلية تستعلم عبرها لكشف الأنماط المشابهة. حقل بمشكلة اليوم قد
يكون أوصينا له بنفس المشكلة قبل شهر، أو حقل مجاور حلّها بنجاح،
أو معايرة موسم سابق تكشف الأثر المتوقّع.

التمييز عن Karpathy:
  • هذا ليس "second brain" — لا ينتج مقالات/أفكاراً
  • هذا يُغذّي recommendation_engine بـcontext (لا يستبدله)
  • قياسات + توصيات + معايرات، لا ملاحظات + أفكار
  • output: قائمة similar_events، لا synthesis

المبادئ المحفوظة:
  • الصدق الإحصائي: similarity_score من بيانات فعلية، لا اختراع
  • سيادة tenant: لا تسريب بين المستأجرين أبداً
  • الشفافية: كل match مع why_similar صريح (ليس "خوارزمية سحرية")
  • الذكاء التشغيلي: لا قرارات، فقط context للمحرّك

التكامل:
  ← يقرأ recommendation_log + activity_log + calibration_history
  → يُغذّي field_bundle (context إضافي للـrecommendation_engine)
  → يُغذّي recommendation_replay (الأنماط المشابهة وقت الإصدار)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class SimilarityMatch:
    """تطابق تاريخي — حدث سابق يشبه الحالة الحالية."""
    source_type: str              # "recommendation" / "activity" / "calibration"
    source_id: str
    source_date: str
    tenant_id: str
    field_id: str | None
    crop: str | None
    similarity_score: float       # 0.0-1.0
    why_similar_ar: list[str]    # أسباب التشابه الصريحة
    outcome: str | None = None    # إن وُجد: "successful" / "rejected" / "skipped"
    actual_yield_t_ha: float | None = None
    # جسر مستقبلي للـoutcome-driven learning loop (DEFER التنفيذ):
    # حالياً: محسوب من error_pct (دقّة عالية = جودة عالية)
    # لاحقاً: يُغذّي weight_adjustment_hook حين تتوفّر بيانات outcomes كافية
    outcome_quality: float | None = None   # 0.0-1.0، اختياري


@dataclass
class SearchContext:
    """السياق المُستعلَم عنه — ما الذي نبحث عن مشابه له؟"""
    tenant_id: str
    field_id: str
    crop: str
    season: str | None = None
    growth_stage: str | None = None
    issue_type: str | None = None      # "drought_stress" / "low_ndvi" / "salinity"
    current_indicators: dict | None = None   # {"ndvi": 0.42, "ec": 2.1, ...}
    district_id: str | None = None     # ← مُضاف (إصلاح bug صامت: كان rec.district_id
                                       # يُستخدم بدون مرجع في السياق)


# ─── أوزان التشابه الزراعي ─────────────────────────────────────
# لا "ML سحرية" — أوزان زراعية صريحة قابلة للمراجعة
_WEIGHTS = {
    "same_crop":            0.30,    # نفس المحصول
    "same_growth_stage":    0.20,    # نفس مرحلة النمو
    "same_issue_type":      0.25,    # نفس نوع المشكلة
    "similar_indicators":   0.15,    # NDVI/EC قريبة (±15%)
    "same_district":        0.10,    # نفس المديرية (مناخ متشابه)
}


def _compare_indicators(current: dict, historical: dict,
                        tolerance_pct: float = 15.0) -> tuple[float, list[str]]:
    """يقارن قيم المؤشّرات. يُرجع (score 0-1، أسباب التطابق)."""
    if not current or not historical:
        return 0.0, []
    matches = []
    total = 0
    matched = 0
    for key, cur_val in current.items():
        if key not in historical or historical[key] is None or cur_val is None:
            continue
        total += 1
        try:
            cur_f, hist_f = float(cur_val), float(historical[key])
            if cur_f == 0 and hist_f == 0:
                matched += 1
                matches.append(f"{key}: كلاهما صفر")
                continue
            denom = max(abs(cur_f), abs(hist_f), 1e-9)
            diff_pct = abs(cur_f - hist_f) / denom * 100
            if diff_pct <= tolerance_pct:
                matched += 1
                matches.append(f"{key}: {hist_f:.2f}↔{cur_f:.2f} (فرق {diff_pct:.0f}%)")
        except (ValueError, TypeError):
            continue
    if total == 0:
        return 0.0, []
    return matched / total, matches


def find_similar_recommendations(
    context: SearchContext,
    recommendation_log: list,
    *,
    max_age_days: int = 365,
    min_similarity: float = 0.5,
    top_n: int = 5,
) -> list[SimilarityMatch]:
    """يبحث في سجلّ التوصيات عن حالات مشابهة.

    المبدأ: tenant_id صارم — لا تسريب بين المستأجرين أبداً.
    التصفية: الزمن، الحدّ الأدنى للتشابه، أعلى N نتيجة.

    Performance: pre-filter (tenant_id + age) قبل التشابه — O(matching)
    لا O(all). كافٍ لـin-memory log حتى ~10K سجلّ. عند PostgreSQL
    migration، يُستبدَل بـindex على (tenant_id, issued_date, crop)."""
    matches: list[SimilarityMatch] = []
    cutoff = (datetime.now() - timedelta(days=max_age_days)).date().isoformat()

    # PRE-FILTER: عزل المستأجر + العمر قبل أيّ حساب تشابه
    # هذا يحلّ O(n) full scan: نمرّ مرّة واحدة بـcomparisons رخيصة
    candidates = [
        rec for rec in recommendation_log
        if rec.tenant_id == context.tenant_id     # عزل tenant (حرس صارم)
        and rec.issued_date >= cutoff             # عمر معقول
    ]

    if not candidates:
        return []

    for rec in candidates:
        # حساب التشابه (شفّاف صريح)
        score = 0.0
        reasons: list[str] = []

        if rec.crop == context.crop:
            score += _WEIGHTS["same_crop"]
            reasons.append(f"نفس المحصول ({context.crop})")

        # ✓ إصلاح bug صامت: same_district الآن صريح بـcontext.district_id
        # سابقاً: كان يُحسب بدون مرجع في السياق (نصف وزن ضمني)
        if context.district_id and getattr(rec, "district_id", None):
            if rec.district_id == context.district_id:
                score += _WEIGHTS["same_district"]
                reasons.append(f"نفس المديرية ({context.district_id})")

        # المؤشّرات (إن وُجدت في provenance)
        prov = getattr(rec, "provenance", None)
        if prov and context.current_indicators:
            hist_snapshot = (prov.get("input_snapshot", {})
                            if isinstance(prov, dict)
                            else getattr(prov, "input_snapshot", {}))
            ind_score, ind_matches = _compare_indicators(
                context.current_indicators, hist_snapshot)
            score += _WEIGHTS["similar_indicators"] * ind_score
            if ind_matches:
                reasons.append("مؤشّرات مشابهة: " + "، ".join(ind_matches[:2]))

        if score < min_similarity:
            continue

        # outcome (إن اكتمل) — يُغذّي learning loop المستقبلي
        outcome = None
        outcome_quality = None
        if hasattr(rec, "actual_yield_t_ha") and rec.actual_yield_t_ha is not None:
            outcome = "harvested"
            # outcome_quality: مقياس نجاح ميسّر (للـlearning loop المُؤجَّل)
            if hasattr(rec, "error_pct") and rec.error_pct is not None:
                # دقّة عالية = جودة عالية
                outcome_quality = max(0.0, 1.0 - abs(rec.error_pct))
        elif hasattr(rec, "error_pct") and rec.error_pct is not None:
            outcome = "evaluated"

        matches.append(SimilarityMatch(
            source_type="recommendation",
            source_id=rec.rec_id,
            source_date=rec.issued_date,
            tenant_id=rec.tenant_id,
            field_id=getattr(rec, "zone_id", None),
            crop=rec.crop,
            similarity_score=round(score, 2),
            why_similar_ar=reasons,
            outcome=outcome,
            outcome_quality=outcome_quality,
            actual_yield_t_ha=getattr(rec, "actual_yield_t_ha", None),
        ))

    # رتّب وأعد الأعلى
    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches[:top_n]


def find_similar_activities(
    context: SearchContext,
    activities: list,
    *,
    activity_type: str | None = None,
    max_age_days: int = 180,
    top_n: int = 5,
) -> list[SimilarityMatch]:
    """يبحث في سجلّ الأنشطة عن أنماط تنفيذ مشابهة.

    مفيد لكشف: 'في الموسم الماضي، حقل مماثل نفّذ X وحصل على Y'."""
    matches: list[SimilarityMatch] = []
    cutoff = (datetime.now() - timedelta(days=max_age_days)).date().isoformat()

    for act in activities:
        if act.tenant_id != context.tenant_id:
            continue
        # نوع النشاط
        if activity_type:
            act_type_val = (act.activity_type.value
                           if hasattr(act.activity_type, "value")
                           else str(act.activity_type))
            if act_type_val != activity_type:
                continue
        # العمر
        planned = act.planned_date or act.completed_date
        if not planned or planned < cutoff:
            continue

        # تشابه أساسي: نفس المستأجر، نوع النشاط
        score = 0.3   # baseline
        reasons = [f"نفس tenant ({act.tenant_id})"]
        if activity_type:
            reasons.append(f"نفس نوع النشاط ({activity_type})")
            score += 0.2

        # outcome
        status_val = (act.status.value if hasattr(act.status, "value")
                     else str(act.status))
        matches.append(SimilarityMatch(
            source_type="activity",
            source_id=act.activity_id,
            source_date=act.completed_date or act.planned_date or "",
            tenant_id=act.tenant_id,
            field_id=act.field_id,
            crop=None,
            similarity_score=round(score, 2),
            why_similar_ar=reasons,
            outcome=status_val,
        ))

    matches.sort(key=lambda m: m.source_date, reverse=True)
    return matches[:top_n]


def find_similar_calibrations(
    context: SearchContext,
    calibration_history: list,
    *,
    top_n: int = 3,
) -> list[SimilarityMatch]:
    """يبحث في سجل المعايرات السابقة عن zone_factor لمحاصيل مشابهة.

    حيوي للتوصيات الجديدة: 'هذا المحصول في مديرية X كان zone_factor=0.85'."""
    matches: list[SimilarityMatch] = []

    for cal in calibration_history:
        if cal.get("tenant_id") != context.tenant_id:
            continue
        score = 0.0
        reasons = []
        if cal.get("crop_id") == context.crop:
            score += 0.5
            reasons.append(f"نفس المحصول ({context.crop})")
        if cal.get("zone_factor") is not None:
            reasons.append(f"zone_factor={cal['zone_factor']}")
            score += 0.3

        if score < 0.3:
            continue

        matches.append(SimilarityMatch(
            source_type="calibration",
            source_id=cal.get("calibration_id", "unknown"),
            source_date=cal.get("date", ""),
            tenant_id=cal.get("tenant_id"),
            field_id=cal.get("field_id"),
            crop=cal.get("crop_id"),
            similarity_score=round(score, 2),
            why_similar_ar=reasons,
        ))

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches[:top_n]


def cross_reference_summary(matches: list[SimilarityMatch]) -> dict:
    """ملخّص قابل للقراءة للمحرّك أو الواجهة.

    مبدأ AI Workaholic: لا تُغرق المهندس بكل match — قدّم الأعلى قيمة."""
    if not matches:
        return {
            "count": 0,
            "note_ar": "لا حالات تاريخية مشابهة في سجلّ المستأجر",
            "matches": [],
        }

    by_type: dict[str, int] = {}
    for m in matches:
        by_type[m.source_type] = by_type.get(m.source_type, 0) + 1

    top = matches[0]
    summary_parts = [f"وُجدت {len(matches)} حالة مشابهة"]
    if by_type.get("recommendation"):
        summary_parts.append(f"{by_type['recommendation']} توصيات")
    if by_type.get("activity"):
        summary_parts.append(f"{by_type['activity']} أنشطة")
    if by_type.get("calibration"):
        summary_parts.append(f"{by_type['calibration']} معايرات")

    return {
        "count": len(matches),
        "by_type": by_type,
        "top_similarity": top.similarity_score,
        "top_match_reasons": top.why_similar_ar,
        "note_ar": "؛ ".join(summary_parts),
        "matches": matches[:5],   # حدّ أقصى للسياق
    }
