"""
sahool_core.soil_recommendations
=================================
يربط خصائص التربة بالتوصيات الثلاث (فكرة المستخدم: الاستفادة المثلى من الطبيعة
وتقنين التكاليف). المبدأ الحاكم لكلٍّ:

  ١. pH (حمضي/قلوي)  → توصية تسميد   [يحتاج pH مخبري — حاكم صارم]
  ٢. النسيج          → توصية ري       [موجود في fao56: TAW حسب النسيج]
  ٣. النسيج          → ترجيح المحصول  [عامل مُرجِّح لا حاكم وحيد]

تحذير معماري حاسم: النسيج وحده لا يقرّر المحصول. هذه الوحدة تُنتج
"ترجيحاً" (bias) يُغذّي evaluate_suitability، لا قراراً نهائياً.
القرار النهائي = نظام البوّابات (النسيج + ملوحة + pH + ماء + مناخ).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ════════════════════════════════════════════════════════════
# ١. pH → توصية تسميد (يتطلّب pH مخبري — حاكم صارم)
# ════════════════════════════════════════════════════════════
@dataclass
class FertilizerHint:
    soil_ph: float | None
    ph_class: str  # حمضي / متعادل / قلوي / غير معروف
    hints_ar: list[str] = field(default_factory=list)
    requires_lab: bool = True
    note_ar: str = ""


def fertilizer_hint_from_ph(soil_ph: float | None) -> FertilizerHint:
    """يحوّل pH التربة لإرشادات تسميد. pH حاكم صارم → null بلا مختبر.
    لا يُنتج جرعات (تتطلب تحليلاً كاملاً) بل توجيهات عامة."""
    if soil_ph is None:
        return FertilizerHint(
            soil_ph=None,
            ph_class="غير معروف",
            hints_ar=["أدخل تحليل pH المخبري لتوصية تسميد دقيقة"],
            note_ar="pH حاكم صارم — لا توصية تسميد دون تحليل مخبري",
        )
    if soil_ph < 6.0:
        cls = "حمضي"
        hints = [
            "التربة حمضية: قد تحتاج جيراً (CaCO₃) لرفع pH",
            "الفوسفور أقل توفّراً في الحموضة — راقب أعراض نقصه",
        ]
    elif soil_ph > 8.0:
        cls = "قلوي"
        hints = [
            "التربة قلوية: قد تحتاج جبساً أو كبريتاً لخفض pH",
            "الحديد والزنك أقل توفّراً في القلوية — قد تلزم إضافة مخلّبية",
            "تجنّب الأسمدة القلوية (نترات الكالسيوم) — فضّل كبريتات الأمونيوم",
        ]
    else:
        cls = "متعادل"
        hints = ["pH متعادل مثالي — معظم المغذّيات متوفّرة، تسميد متوازن"]
    return FertilizerHint(
        soil_ph=soil_ph,
        ph_class=cls,
        hints_ar=hints,
        requires_lab=False,
        note_ar=f"pH={soil_ph} ({cls}). إرشادات عامة — الجرعات تحتاج تحليلاً كاملاً.",
    )


# ════════════════════════════════════════════════════════════
# ٢. النسيج → توصية ري (يكمّل fao56: سعة الاحتفاظ بالماء)
# ════════════════════════════════════════════════════════════
@dataclass
class IrrigationHint:
    texture: str
    pattern_ar: str
    rationale_ar: str


_IRRIGATION_BY_TEXTURE = {
    "رملي": IrrigationHint(
        "رملي",
        "ري متكرّر بكمّيات صغيرة",
        "الرمل يحتفظ بماء قليل (TAW منخفض) ويصرف سريعاً — دفعات صغيرة متقاربة تقلّل الفقد بالتسرّب",
    ),
    "طمي-رملي": IrrigationHint(
        "طمي-رملي", "ري معتدل التكرار", "سعة احتفاظ متوسطة-منخفضة — توازن بين التكرار والكمّية"
    ),
    "طميي": IrrigationHint(
        "طميي", "ري متوازن (الأمثل)", "الطمي أمثل سعة احتفاظ — جدولة مريحة، أقل إجهاد مائي"
    ),
    "طيني": IrrigationHint(
        "طيني",
        "ري أقل تكراراً بكمّيات أكبر",
        "الطين يحتفظ بماء كثير (TAW عالٍ) لكن يتشبّع — دفعات أكبر متباعدة مع حذر الصرف",
    ),
}


def irrigation_hint_from_texture(texture: str) -> IrrigationHint | None:
    """يربط نسيج التربة بنمط الري. يكمّل fao56 (الذي يحسب الكمّية الدقيقة)."""
    for key, hint in _IRRIGATION_BY_TEXTURE.items():
        if key in texture:
            return hint
    return None


# ════════════════════════════════════════════════════════════
# ٣. النسيج → ترجيح المحصول (عامل مُرجِّح لا حاكم وحيد)
# ════════════════════════════════════════════════════════════
@dataclass
class CropBias:
    texture: str
    favored_ar: list[str]  # أنواع مُرجَّحة (ميل، لا قرار)
    cautioned_ar: list[str]  # أنواع تحتاج حذراً
    warning_ar: str = (
        "⚠️ النسيج عامل واحد فقط. القرار النهائي يحتاج الملوحة وpH والماء والمناخ عبر نظام الملاءمة."
    )


_CROP_BIAS_BY_TEXTURE = {
    "رملي": CropBias(
        "رملي",
        favored_ar=[
            "محاصيل جذرية (بطاطس، جزر)",
            "أشجار متحمّلة للجفاف (نخيل، لوز)",
            "بقوليات خفيفة",
        ],
        cautioned_ar=["القمح (يحتاج ريّاً مكثّفاً في الرمل)", "الأرز (غير مناسب)"],
    ),
    "طميي": CropBias(
        "طميي", favored_ar=["معظم المحاصيل (الأمثل)", "خضروات", "حبوب"], cautioned_ar=[]
    ),
    "طيني": CropBias(
        "طيني",
        favored_ar=["الحبوب (قمح، شعير)", "الأعلاف", "محاصيل تتحمّل الرطوبة"],
        cautioned_ar=["المحاصيل الجذرية (صعوبة النمو في الطين الثقيل)", "محاصيل حسّاسة للتشبّع"],
    ),
}


def crop_bias_from_texture(texture: str) -> CropBias | None:
    """يُنتج *ترجيحاً* للمحاصيل من النسيج — لا قراراً نهائياً.
    يُغذّي evaluate_suitability كعامل مُعدِّل، لا يستبدله.
    تحقيق فكرة 'الاستفادة المثلى' دون خطر التبسيط المُضلِّل."""
    for key, bias in _CROP_BIAS_BY_TEXTURE.items():
        if key in texture:
            return bias
    return None


# ════════════════════════════════════════════════════════════
# التجميع: من خصائص التربة → التوصيات الثلاث
# ════════════════════════════════════════════════════════════
def soil_to_recommendations(texture: str | None, soil_ph: float | None) -> dict:
    """يجمع التوصيات الثلاث من خصائص التربة (فكرة المستخدم المتكاملة).
    تقنين التكاليف: الري حسب النسيج (لا إفراط)، التسميد حسب pH (لا هدر)،
    المحصول المُرجَّح (استثمار أمثل للطبيعة) — كله مع احترام الحاكمات."""
    out = {
        "irrigation": None,
        "fertilizer": None,
        "crop_bias": None,
        "principle_ar": "النسيج يوجّه الري والمحصول؛ pH يوجّه التسميد؛ "
        "الحاكمات (ملوحة/pH) تحتاج مختبراً؛ القرار النهائي للملاءمة الكاملة.",
    }
    if texture:
        ih = irrigation_hint_from_texture(texture)
        out["irrigation"] = ih.__dict__ if ih else None
        cb = crop_bias_from_texture(texture)
        out["crop_bias"] = cb.__dict__ if cb else None
    out["fertilizer"] = fertilizer_hint_from_ph(soil_ph).__dict__
    return out
