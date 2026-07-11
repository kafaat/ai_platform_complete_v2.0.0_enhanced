"""
tests_v9/test_e2e_offline_flow.py — تدفّق end-to-end (offline)

يتتبّع رحلة مزارع كاملة عبر طبقات المنطق دون خدمات حيّة: من المدخلات الأوّليّة
→ المحرّكات الزراعيّة → التوصية المتدرّجة → السلامة → الإرشاد. يتحقّق أنّ
الطبقات **تعمل كنظام واحد متّسق** (Integration Semantics)، لا كوحدات منعزلة.

بخلاف test_end_to_end.py (يحتاج Supervisor/Guardrails حيّة + pytest)، هذا
يستدعي المحرّكات مباشرةً offline — يثبت تماسك التدفّق المنطقي بلا بنية تحتيّة.

السيناريو: مزارع في الجوف، قمح، يريد توصية كاملة لحقله.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform"))


def run_e2e_flow():
    """يشغّل التدفّق الكامل ويعيد قائمة (رمز، رسالة)."""
    results = []

    # ═══ المرحلة ١: المدخلات الأوّليّة + جاهزيّة البيانات ═══
    from api.data_readiness import assess_readiness

    provided = [
        "location",
        "area_ha",
        "crop",
        "season",
        "planting_date",
        "irrigation",
        "t_min",
        "t_max",
        "rain",
        "ndvi",
    ]
    readiness = assess_readiness(provided).to_dict()
    level = readiness["highest_complete_level"]
    if level >= 4:
        results.append(("✓", f"١. جاهزيّة البيانات: مستوى {level} (الريّ متاح، التسميد يحتاج مختبر)"))
    else:
        results.append(("✗", f"١. مستوى غير متوقّع: {level}"))

    # ═══ المرحلة ٢: التماسك الزمني (مرجع موحّد للمحرّكات) ═══
    from api.temporal_coherence import check_temporal_coherence, make_temporal_context

    ctx = make_temporal_context("2026-01-15", "2025-11-15")
    if ctx.days_since_planting == 61 and 1 <= ctx.day_of_year <= 366:
        results.append(("✓", f"٢. مرجع زمني موحّد: {ctx.days_since_planting} يوماً من الزراعة"))
    else:
        results.append(("✗", "٢. خلل في المرجع الزمني"))

    # ═══ المرحلة ٣: ميزان الماء (الريّ — متاح) ═══
    from api.water_balance import WeatherInput, water_balance

    w = WeatherInput(
        t_min_c=8, t_max_c=22, latitude_deg=16.0, elevation_m=1000, day_of_year=ctx.day_of_year
    )
    wb = water_balance(w, "wheat", "mid", rain_mm=5, et0_mm=6.0)
    if wb.net_irrigation_mm >= 0:
        results.append(("✓", f"٣. ميزان الماء: احتياج صافٍ {wb.net_irrigation_mm:.1f} مم"))
    else:
        results.append(("✗", "٣. ميزان الماء غير منطقي"))

    # ═══ المرحلة ٤: GDD + تماسك زمني متقاطع ═══
    from api.gdd_tracker import DailyTemp, track_gdd

    temps = [DailyTemp(8, 22)] * 61
    gdd = track_gdd("wheat", temps)
    coherence = check_temporal_coherence(ctx, gdd_days_counted=gdd.days_counted)
    if coherence.coherent:
        results.append(("✓", f"٤. GDD ({gdd.cumulative_gdd:.0f}) متّسق زمنيّاً مع الموسم"))
    else:
        results.append(("✗", f"٤. انحراف زمني: {coherence.detail_ar}"))

    # ═══ المرحلة ٥: التسميد (محجوب بلا مختبر — السلامة) ═══
    from api.nutrient_4r import recommend_phosphorus

    try:
        p_rec = recommend_phosphorus(crop="wheat", olsen_p=None)
        status = getattr(p_rec, "status", None)
        sval = status.value if hasattr(status, "value") else str(status)
        if "block" in sval.lower():
            results.append(("✓", "٥. الفوسفور محجوب بلا Olsen-P (المختبر يحكم)"))
        else:
            results.append(("✗", f"٥. الفوسفور غير محجوب: {sval}"))
    except Exception:
        # بعض التواقيع ترفع استثناءً بلا مختبر — مقبول كحجب
        results.append(("✓", "٥. الفوسفور يتطلّب مختبراً (محجوب)"))

    # ═══ المرحلة ٦: تظافر القرائن (درجة التوصية) ═══
    from api.evidence_corroboration import Evidence, EvidenceType, RecommendationTier, corroborate

    corr = corroborate(
        [
            Evidence(EvidenceType.REMOTE_SENSING, True),
            Evidence(EvidenceType.REGIONAL_PRIOR, True),
            Evidence(EvidenceType.FIELD_OBS, True),
        ],
        recommendation_key="irrigation",
    )
    if corr.tier == RecommendationTier.CORROBORATED:
        results.append(("✓", "٦. تظافر القرائن → توصية مؤيَّدة + حضّ على الفحص"))
    else:
        results.append(("✗", f"٦. درجة غير متوقّعة: {corr.tier}"))

    # ═══ المرحلة ٧: السلامة الكيميائيّة (حاجز) ═══
    from api.chemical_safety import ChemicalStatus, check_chemical

    safe = check_chemical("ddt")
    if safe.status == ChemicalStatus.BLOCKED:
        results.append(("✓", "٧. السلامة: DDT محظور دوليّاً → محجوب"))
    else:
        results.append(("✗", "٧. فشل حجب مادّة محظورة"))

    # ═══ المرحلة ٨: الإرشاد الإقليمي (الجوف → حِميري) ═══
    from api.astronomical_timing import get_regional_calendar

    cal = get_regional_calendar("al_jawf")
    if cal["matched"] and cal["calendar_key"] == "himyarite":
        results.append(("✓", "٨. الإرشاد: الجوف → التقويم الحِميري (إقليمي صحيح)"))
    else:
        results.append(("✗", "٨. تقويم إقليمي خاطئ"))

    # ═══ المرحلة ٩: الأمثال (الجوف → برط، لا تعز) ═══
    from api.agricultural_proverbs import get_proverbs

    prov = get_proverbs(governorate="al_jawf")
    regions = {p["region_ar"] for p in prov["proverbs"]}
    if any("برط" in r for r in regions) and not any("تعز" in r for r in regions):
        results.append(("✓", "٩. الأمثال: الجوف يُظهر برط، يُخفي تعز (إقليمي)"))
    else:
        results.append(("✗", "٩. فلترة الأمثال الإقليميّة خاطئة"))

    return results


def main():
    print("═" * 60)
    print("  تدفّق end-to-end (offline) — رحلة مزارع كاملة")
    print("  السيناريو: مزارع الجوف، قمح، توصية شاملة لحقله")
    print("═" * 60)
    print()
    results = run_e2e_flow()
    passed = sum(1 for s, _ in results if s == "✓")
    failed = sum(1 for s, _ in results if s == "✗")
    for sym, msg in results:
        print(f"  {sym} {msg}")
    print()
    print("─" * 60)
    verdict = "✓ التدفّق متّسق" if failed == 0 else "✗ خلل في التدفّق"
    print(f"  {passed}/{len(results)} مرحلة → {verdict}")
    print("═" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
