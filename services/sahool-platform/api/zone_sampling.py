"""
services/sahool-platform/api/zone_sampling.py — مرشد أخذ عيّنات التربة

البند ٣ (تكملة). المرجع: docs/history/ZONE_SAMPLING_RESEARCH.md.

الفكرة: grid sampling في حقل 50 هكتار = 40-60 عيّنة (مكلف جدّاً). zone
sampling = 3-6 مناطق × عيّنة مركّبة (composite) = 3-6 تحاليل مخبريّة فقط.

هذه الوحدة تُرشد **استراتيجيّة** أخذ العيّنات (نوعها + عددها)، وهي منطق
حتمي خالص. التقسيم التلقائي للمناطق (k-means على صور القمر) مؤجّل بـtrigger
صريح (يحتاج scikit-learn + مناطق تربة متعدّدة) — موثّق أدناه.

⚠️ تقديري: التوصيات إرشاديّة من أدبيّات (Iowa State / OSU / GeoPard).
العدد النهائي للعيّنات قرار المزارع حسب ميزانيّته وتباين حقله.
"""

from __future__ import annotations


def recommend_sampling_strategy(
    area_ha: float,
    has_field_history: bool = False,
    variability: str = "unknown",  # low | medium | high | unknown
) -> dict:
    """يوصي باستراتيجيّة أخذ العيّنات (zone أو grid) + عدد العيّنات.

    القاعدة (من البحث):
    - zone أفضل عند: تاريخ معرفة بالحقل + تباين واضح (topography/خصوبة)
    - grid مرّة كل 3-5 سنوات للمعايرة، zone كلّ موسم
    """
    # اختيار النوع
    if has_field_history and variability in ("medium", "high"):
        method = "zone"
        rationale = "تاريخ معرفة بالحقل + تباين واضح → مناطق إدارة أكفأ من الشبكة"
    elif variability == "low":
        method = "grid_coarse"
        rationale = "تباين منخفض → شبكة خشنة تكفي"
    else:
        method = "grid"
        rationale = "بلا تاريخ كافٍ → شبكة منتظمة للمسح الأوّلي (ثمّ zone لاحقاً)"

    # عدد العيّنات
    if method == "zone":
        # 3-6 مناطق حسب المساحة، عيّنة مركّبة لكلّ منطقة
        zones = max(3, min(6, round(area_ha / 15)))
        samples = zones  # عيّنة composite لكلّ منطقة
        cores_per_sample = 8  # 8-12 core لتكوين العيّنة المركّبة
        note = f"{zones} مناطق × عيّنة مركّبة (من ~{cores_per_sample} cores) = {samples} تحليل مخبري"
    else:
        # grid: ~عيّنة لكلّ 1 هكتار (cell ~2.5 acre ≈ 1 ha) — مكلف
        samples = max(4, round(area_ha))
        zones = None
        cores_per_sample = 1
        note = f"شبكة ~عيّنة/هكتار = {samples} تحليل (مكلف؛ فكّر بـzone لو لديك تاريخ بالحقل)"

    return {
        "method": method,
        "rationale_ar": rationale,
        "recommended_zones": zones,
        "recommended_samples": samples,
        "cores_per_composite": cores_per_sample,
        "note_ar": note,
        "is_estimate": True,
        "calibration_advice_ar": "اجمع grid مرّة كل 3-5 سنوات للمعايرة، وzone كلّ موسم",
        "deferred": {
            "auto_zoning": "تقسيم المناطق تلقائيّاً بـk-means على صور القمر — "
            "مؤجّل (يحتاج scikit-learn + تباين كافٍ)",
        },
    }


def sampling_depth_advice(crop: str | None = None) -> dict:
    """عمق أخذ العيّنة حسب نوع الجذور (إرشادي)."""
    # عمق قياسي 0-30 سم للأغلب؛ أعمق للجذور العميقة
    deep_root = {"alfalfa", "sorghum", "faba_bean", "cowpea"}
    if crop in deep_root:
        depths = ["0-30 سم", "30-60 سم"]
        note = "محصول عميق الجذور → عيّنتان (سطحيّة + عميقة)"
    else:
        depths = ["0-30 سم"]
        note = "عمق قياسي 0-30 سم (منطقة الجذور النشطة)"
    return {"depths_cm": depths, "note_ar": note, "is_estimate": True}
