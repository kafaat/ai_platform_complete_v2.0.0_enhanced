"""api/learning_feedback.py — حلقة التغذية الراجعة للتعلّم (Learning Feedback Loop)

#385: تقرأ دليل المعايرة المتراكم (evidence_registry) لكلّ منطقة وتقترح **أين**
المعايرة ضعيفة و**أيّ** المعاملات تحتاج مراجعة بشريّة — **بلا أيّ تعديل آليّ**.
القرار يبقى للإنسان حتى Adaptive Calibration (#387).

لكلّ منطقة: إجراء مقترَح (جمع بيانات / مراجعة معايرة / تحقّق / مراقبة)، أولويّة،
وأهداف مراجعة (عائلات معاملات مُرشَّحة) مستنبَطة من **أضعف جوانب النجاح**.

نقيّ حتميّ (لا I/O). صدق: اقتراحات لا أوامر؛ `auto_adjust=False` صريح؛ العتبات
تقديريّة موسومة؛ ما يندر قياسه لا يُحاكَم (يُوجَّه لجمع البيانات لا للوم المعايرة).
"""

from __future__ import annotations

# عتبة نسبة النجاح التي تحت‌ها تُقترَح مراجعة المعايرة. ⚠ تقديريّة.
_LOW_SUCCESS_THRESHOLD = 0.6

# أعلام النجاح ⇒ عائلات معاملات مُرشَّحة للمراجعة البشريّة (تلميح لا إصلاح).
_FLAG_REVIEW_TARGETS: dict[str, list[str]] = {
    "stress_avoided": ["raw_fraction", "root_depth_m"],
    "stress_better": ["raw_fraction", "root_depth_m"],
    "yield_met": ["kc_dyn_max", "uptake_fractions"],
    "water_within_budget": ["forecast_infiltration"],
    # irrigation_followed سلوك مزارع لا فيزياء ⇒ يراجَع واقعيّة السياسة لا المعايرة.
    "irrigation_followed": [],
}


def _region_feedback(ev: dict) -> dict:
    """تغذية راجعة لمنطقة واحدة من سجلّ دليلها — اقتراح لا أمر."""
    region = ev.get("region", "_generic")
    level = ev.get("evidence_level", "none")
    n = ev.get("sample_count", 0)
    rate = ev.get("success_rate")
    flag_counts = ev.get("success_flag_counts", {}) or {}

    review_targets: list[str] = []
    if n == 0:
        action = "collect_data"
        priority = 3
        rec = f"لا دليل ميدانيّ لـ{region} — ابدأ جمع قياسات النتائج (ريّ/إجهاد/إنتاج)"
    elif rate is not None and rate < _LOW_SUCCESS_THRESHOLD:
        action = "review_calibration"
        priority = 3
        # أضعف جوانب النجاح ⇒ عائلات معاملات مُرشَّحة (الأندر تكراراً).
        weak = sorted(_FLAG_REVIEW_TARGETS, key=lambda f: flag_counts.get(f, 0))
        for f in weak:
            if flag_counts.get(f, 0) <= n * _LOW_SUCCESS_THRESHOLD:
                review_targets.extend(_FLAG_REVIEW_TARGETS[f])
        review_targets = list(dict.fromkeys(review_targets))  # إزالة التكرار
        rec = f"نسبة نجاح القرار منخفضة في {region} ({rate}) — راجِع المعاملات يدويّاً"
    elif level == "field_preliminary":
        action = "verify"
        priority = 2
        need = ev.get("samples_to_verified", 0)
        rec = f"دليل أوّليّ لـ{region} — اجمع {need} عيّنة إضافيّة للتحقّق الميدانيّ"
    else:  # field_verified بنسبة نجاح جيّدة
        action = "monitor"
        priority = 1
        rec = f"معايرة {region} مدعومة ميدانيّاً وأداؤها جيّد — راقِب فقط"

    return {
        "region": region,
        "evidence_level": level,
        "sample_count": n,
        "success_rate": rate,
        "action": action,
        "priority": priority,
        "review_targets": review_targets,
        "recommendation_ar": rec,
    }


def learning_feedback(evidence_records: list[dict]) -> dict:
    """يحوّل دليل المناطق إلى أولويّات مراجعة بشريّة — نقيّ حتميّ، بلا تعديل آليّ.

    evidence_records: قائمة مخرجات aggregate_evidence لكلّ منطقة. يرتّب تنازليّاً
    بالأولويّة (الأعلى أوّلاً). صدق: اقتراحات فقط؛ auto_adjust=False صريح.
    """
    regions = [_region_feedback(ev) for ev in evidence_records]
    regions.sort(key=lambda r: (-r["priority"], r["region"]))

    rates = [r["success_rate"] for r in regions if r["success_rate"] is not None]
    summary = {
        "n_regions": len(regions),
        "n_none": sum(r["evidence_level"] == "none" for r in regions),
        "n_preliminary": sum(r["evidence_level"] == "field_preliminary" for r in regions),
        "n_verified": sum(r["evidence_level"] == "field_verified" for r in regions),
        "mean_success_rate": round(sum(rates) / len(rates), 3) if rates else None,
        "regions_needing_data": [r["region"] for r in regions if r["action"] == "collect_data"],
        "regions_needing_review": [
            r["region"] for r in regions if r["action"] == "review_calibration"
        ],
    }

    return {
        "regions": regions,
        "summary": summary,
        "auto_adjust": False,  # صريح: لا تعديل آليّ — القرار للإنسان (#387 لاحقاً)
        "calibrated": False,
        "warnings_ar": [
            "عتبات الأولويّة/النجاح تقديريّة؛ هذه اقتراحات مراجعة بشريّة لا أوامر تعديل",
        ],
    }
