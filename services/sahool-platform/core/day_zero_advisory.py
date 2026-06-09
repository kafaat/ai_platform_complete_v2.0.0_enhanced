"""
sahool_core.day_zero_advisory
==============================
توصية استرشادية فورية لحظة إنشاء الحقل (مشكلة "اللحظة صفر").

الفكرة: المزارع ينشئ حقله ولا يملك تحليلاً مخبرياً بعد. بدل تركه
أمام شاشة BLOCKED فارغة، نستخدم **كل المتاح فوراً** لإعطاء توصية
استرشادية — صريحة في عدم دقّتها — تحفّزه لإكمال الخطوات.

المتاح لحظة الإنشاء (صفر مختبر):
  • المناخ من الإحداثيات (Open-Meteo)
  • NDVI + نسيج التربة التقديري من الأقمار
  • سياق المديرية (من جيرانه المحلّلين)
  • إدخال المزارع: الصنف، الري، تاريخ الزراعة

المبدأ الحاكم: كل بند يحمل "مستوى ثقته" ويذكر "ما الذي يرفع الدقّة".
الحاكمات (ملوحة/pH مخبري) تبقى محجوبة — التوصية استرشادية لا دقيقة.
السلامة (مبيدات) محجوبة دائماً. هذا ليس تخفيفاً للصدق، بل استخدام
صادق للمتاح مع شفافية كاملة عن حدوده.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AdvisoryItem:
    """بند توصية استرشادي — يحمل ثقته وما يرفع دقّته."""
    topic_ar: str               # الري / المناخ / التربة...
    advice_ar: str
    confidence: str             # estimate / district_context / measured
    source_ar: str              # من أين (قمر/مناخ/مديرية)
    upgrade_ar: str = ""        # ما الذي يرفع الدقّة


@dataclass
class DayZeroAdvisory:
    """التوصية الاسترشادية الكاملة لحظة الإنشاء."""
    field_id: str
    items: list[AdvisoryItem] = field(default_factory=list)
    headline_ar: str = "توصية استرشادية أوّلية"
    disclaimer_ar: str = (
        "⚠️ هذه توصية استرشادية مبنية على المتاح فوراً (أقمار + مناخ + سياق "
        "مديريتك). ليست دقيقة — تحاليل التربة والمياه ترفعها لتوصية موثوقة.")
    next_steps_ar: list[str] = field(default_factory=list)
    missing_for_precision_ar: list[str] = field(default_factory=list)


def build_day_zero_advisory(
    field_id: str,
    *,
    climate: dict | None = None,        # من Open-Meteo (متاح من الإحداثيات)
    ndvi: float | None = None,          # من الأقمار
    soil_texture: str | None = None,    # تقدير من BSI
    district_salinity_context: float | None = None,  # سياق المديرية
    crop_id: str | None = None,         # إدخال المزارع
    irrigation_method: str | None = None,
) -> DayZeroAdvisory:
    """يبني توصية استرشادية من كل المتاح لحظة الإنشاء.
    كل بند صريح في ثقته ومصدره وما يرفع دقّته."""
    adv = DayZeroAdvisory(field_id=field_id)
    missing = []

    # ١. المناخ (متاح فوراً من الإحداثيات — ثقة جيدة)
    if climate:
        et0 = climate.get("et0_hint", "متوسط")
        adv.items.append(AdvisoryItem(
            topic_ar="المناخ والطقس",
            advice_ar=f"مناخ موقعك: {climate.get('class_ar', 'غير محدّد')}. "
                      f"الاحتياج المائي المبدئي: {et0}.",
            confidence="measured",  # المناخ قياس فعلي لا تقدير
            source_ar="بيانات الطقس (Open-Meteo) من إحداثيات حقلك",
            upgrade_ar="",
        ))

    # ٢. الري (من النسيج التقديري — استرشادي)
    if soil_texture:
        from core.soil_recommendations import irrigation_hint_from_texture
        ih = irrigation_hint_from_texture(soil_texture)
        if ih:
            adv.items.append(AdvisoryItem(
                topic_ar="الري المبدئي",
                advice_ar=f"نسيج تربتك يبدو {soil_texture} → {ih.pattern_ar}.",
                confidence="estimate",  # تقدير من الأقمار
                source_ar="تقدير نسيج التربة من الأقمار (BSI)",
                upgrade_ar="تحليل نسيج التربة المخبري يؤكّد النوع ويدقّق الجدولة",
            ))
            missing.append("تحليل نسيج التربة")

    # ٣. حالة الغطاء (NDVI — متاح فوراً)
    if ndvi is not None:
        state = ("صحي" if ndvi > 0.5 else "متوسط" if ndvi > 0.3 else "ضعيف/تربة عارية")
        adv.items.append(AdvisoryItem(
            topic_ar="حالة الغطاء النباتي",
            advice_ar=f"NDVI الحالي {ndvi:.2f} → الغطاء {state}.",
            confidence="measured",
            source_ar="صور الأقمار (Sentinel-2)",
            upgrade_ar="",
        ))

    # ٤. سياق الملوحة من المديرية (لا قيمة حقله!)
    if district_salinity_context is not None:
        adv.items.append(AdvisoryItem(
            topic_ar="سياق الملوحة (مديريتك)",
            advice_ar=f"متوسط ملوحة مديريتك ≈ {district_salinity_context}. "
                      f"هذا سياق المنطقة، وليس قيمة حقلك.",
            confidence="district_context",
            source_ar="متوسط المزارع المحلّلة في مديريتك",
            upgrade_ar="تحليل ملوحة تربتك (EC) يعطي قيمتك الفعلية — قد تختلف",
        ))
        missing.append("تحليل ملوحة التربة (EC)")
    else:
        missing.append("تحليل ملوحة التربة (EC)")

    # ٥. ترجيح المحصول (إن أدخل الصنف)
    if crop_id and soil_texture:
        adv.items.append(AdvisoryItem(
            topic_ar="ملاءمة المحصول المبدئية",
            advice_ar=f"محصولك ({crop_id}) مع تربة {soil_texture}: تقييم مبدئي. "
                      f"الملاءمة الدقيقة تحتاج الملوحة وpH.",
            confidence="estimate",
            source_ar="ترجيح من نسيج التربة التقديري",
            upgrade_ar="تحاليل التربة الكاملة تعطي تصنيف ملاءمة موثوقاً (S1/S2/S3/N)",
        ))

    # ما يبقى محجوباً للدقّة + الخطوات التالية المحفّزة
    missing.append("تحليل pH التربة")
    missing.append("تحليل مياه الري")
    adv.missing_for_precision_ar = missing
    adv.next_steps_ar = [
        "احجز تحليل تربة (ملوحة + pH) — يرفع توصيتك من استرشادية إلى دقيقة",
        "أدخل تحليل مياه الري إن توفّر",
        "كل خطوة تكمّلها تفتح توصيات أدقّ وأقيّم",
    ]
    # تذكير السلامة (دائماً)
    adv.items.append(AdvisoryItem(
        topic_ar="🛑 المبيدات",
        advice_ar="توصيات المبيدات محجوبة — تتطلّب بيانات كاملة (سلامة المستهلك).",
        confidence="estimate",
        source_ar="قاعدة السلامة",
        upgrade_ar="أكمل التحاليل لفتح توصيات الوقاية الآمنة",
    ))
    return adv
