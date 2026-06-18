"""core/crop_risk.py — محرّك المخاطر الزراعيّة لكلّ محصول (نقيّ، حتميّ).

طبقة فوق ذكاء الطقس (weather_overlay.FieldWeatherScores): تأخذ إشارات الطقس القراريّة
(خطر المرض الفطريّ، ساعات الإجهاد الحراريّ، ساعات خطر الصقيع، الرطوبة) وتُسقطها على
**حسّاسيّة المحصول** عبر ملفّات تعريف صريحة لكلّ محصول (قمح/طماطم/بطاطس/نخيل/ذرة...).
الناتج قائمة مخاطر مُحفَّزة (CropRisk) بشدّة ودرجة [0,1] وسبب عربيّ — يُغذّي محرّك
التوصية بمخاطر قابلة للتبرير، خاصّة بالمحصول لا عامّة.

العتبات/الحسّاسيّات إرشاديّة (FAO/أدبيّات أمراض النبات) قابلة للمعايرة المحلّيّة لاحقاً.
نقيّ: لا I/O ولا عشوائيّة؛ كلّ الدرجات مقصوصة إلى [0,1].
"""

from __future__ import annotations

from dataclasses import dataclass

# ── حدود الشدّة (نِسَب من نطاق التحفيز فوق العتبة) ──
_HIGH_SEVERITY = 0.66  # درجة ≥ هذا ⇒ شدّة عالية
_MODERATE_SEVERITY = 0.33  # درجة ≥ هذا ⇒ شدّة متوسّطة (وإلّا منخفضة)


@dataclass(frozen=True)
class CropRisk:
    """خطر زراعيّ مُحفَّز لمحصول مُعيَّن: نوعه وشدّته ودرجته وسببه العربيّ."""

    risk_type: str  # fungal_disease | heat_stress | frost_damage
    crop: str
    severity: str  # low | moderate | high
    score: float  # [0,1] شدّة الخطر القراريّة
    reason_ar: str


@dataclass(frozen=True)
class _CropProfile:
    """ملفّ حسّاسيّة محصول: عتبات تحفيز كلّ خطر + نطاق التشبُّع (للدرجة)."""

    name_ar: str
    # المرض الفطريّ: عتبة خطر المرض [0,1] التي يبدأ عندها التحفيز، ومدى التشبُّع.
    disease_threshold: float
    disease_span: float
    # الإجهاد الحراريّ: أدنى ساعات إجهاد للتحفيز، ومدى التشبُّع (ساعات).
    heat_hours_threshold: int
    heat_hours_span: int
    # الصقيع: أدنى ساعات صقيع للتحفيز، ومدى التشبُّع (ساعات).
    frost_hours_threshold: int
    frost_hours_span: int


# ── ملفّات تعريف المحاصيل ──
# بطاطس/طماطم: حسّاسيّة عالية للفطريّات (اللفحة) ⇒ عتبة مرض منخفضة، وحسّاسيّة للصقيع.
# نخيل: تحمّل حراريّ عالٍ ⇒ عتبة ساعات حرارة مرتفعة. قمح/ذرة: متوسّطة.
_CROP_PROFILES: dict[str, _CropProfile] = {
    "wheat": _CropProfile(
        name_ar="قمح",
        disease_threshold=0.45,
        disease_span=0.45,
        heat_hours_threshold=6,
        heat_hours_span=18,
        frost_hours_threshold=8,
        frost_hours_span=16,
    ),
    "tomato": _CropProfile(
        name_ar="طماطم",
        disease_threshold=0.25,  # حسّاسيّة عالية للّفحة المتأخّرة
        disease_span=0.45,
        heat_hours_threshold=4,
        heat_hours_span=16,
        frost_hours_threshold=2,  # حسّاس جدّاً للصقيع
        frost_hours_span=10,
    ),
    "potato": _CropProfile(
        name_ar="بطاطس",
        disease_threshold=0.22,  # حسّاسيّة عالية جدّاً للّفحة (Phytophthora)
        disease_span=0.45,
        heat_hours_threshold=4,
        heat_hours_span=16,
        frost_hours_threshold=2,  # حسّاس جدّاً للصقيع
        frost_hours_span=10,
    ),
    "date_palm": _CropProfile(
        name_ar="نخيل",
        disease_threshold=0.6,  # تحمّل عالٍ للفطريّات
        disease_span=0.4,
        heat_hours_threshold=14,  # تحمّل حراريّ عالٍ — يلزم ساعات أكثر للتحفيز
        heat_hours_span=24,
        frost_hours_threshold=12,
        frost_hours_span=20,
    ),
    "maize": _CropProfile(
        name_ar="ذرة",
        disease_threshold=0.45,
        disease_span=0.45,
        heat_hours_threshold=6,
        heat_hours_span=18,
        frost_hours_threshold=6,
        frost_hours_span=14,
    ),
}

# ملفّ افتراضيّ عامّ لأيّ محصول غير معروف (لا يتعطّل المحرّك).
_DEFAULT_PROFILE = _CropProfile(
    name_ar="محصول عامّ",
    disease_threshold=0.4,
    disease_span=0.45,
    heat_hours_threshold=6,
    heat_hours_span=18,
    frost_hours_threshold=6,
    frost_hours_span=14,
)

# تعزيز خطر المرض عند الرطوبة العالية (تُفضّل العدوى الفطريّة).
_HUMID_BOOST_RH = 85.0  # رطوبة % تُعدّ عالية
_HUMID_BOOST_MAX = 0.15  # أقصى زيادة على درجة المرض عند الرطوبة العالية


def _clamp01(x: float) -> float:
    """يقصّ القيمة إلى [0,1]."""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _severity_for(score: float) -> str:
    """يشتقّ الشدّة من الدرجة [0,1] حتميّاً."""
    if score >= _HIGH_SEVERITY:
        return "high"
    if score >= _MODERATE_SEVERITY:
        return "moderate"
    return "low"


def _normalized_excess(value: float, threshold: float, span: float) -> float:
    """درجة [0,1] = مقدار التجاوز فوق العتبة مقسوماً على مدى التشبُّع، مقصوصاً."""
    if value <= threshold:
        return 0.0
    if span <= 0.0:
        return 1.0
    return _clamp01((value - threshold) / span)


def assess_crop_risk(
    crop: str,
    *,
    disease_risk_score: float,
    heat_stress_hours: int,
    frost_risk_hours: int,
    humidity_avg_percent: float | None = None,
) -> list[CropRisk]:
    """يُقيّم مخاطر الطقس على محصول مُعيَّن ويُعيد قائمة المخاطر المُحفَّزة (نقيّ).

    `disease_risk_score`: درجة خطر المرض الفطريّ [0,1] من تراكب الطقس. `heat_stress_hours`
    و`frost_risk_hours`: عدّادات ساعات الإجهاد/الصقيع من التراكب. `humidity_avg_percent`:
    رطوبة وسطيّة اختياريّة تُعزّز خطر المرض عند ارتفاعها.

    لكلّ محصول ملفّ حسّاسيّة (عتبة + مدى تشبُّع) لكلّ خطر؛ المحصول غير المعروف يستخدم
    الملفّ الافتراضيّ العامّ (لا تعطُّل). تُحفَّز المخاطر فقط عند تجاوز عتبتها؛ طقس حميد ⇒
    قائمة فارغة. كلّ الدرجات مقصوصة إلى [0,1].
    """
    profile = _CROP_PROFILES.get(crop, _DEFAULT_PROFILE)
    risks: list[CropRisk] = []

    # ── خطر المرض الفطريّ ──
    disease_input = _clamp01(float(disease_risk_score))
    disease_score = _normalized_excess(
        disease_input, profile.disease_threshold, profile.disease_span
    )
    if disease_score > 0.0 and humidity_avg_percent is not None:
        if float(humidity_avg_percent) >= _HUMID_BOOST_RH:
            disease_score = _clamp01(disease_score + _HUMID_BOOST_MAX)
    if disease_score > 0.0:
        sev = _severity_for(disease_score)
        risks.append(
            CropRisk(
                risk_type="fungal_disease",
                crop=crop,
                severity=sev,
                score=round(disease_score, 4),
                reason_ar=(
                    f"خطر مرض فطريّ على ال{profile.name_ar}: درجة خطر الطقس "
                    f"{disease_input:.2f} تجاوزت عتبة الحسّاسيّة "
                    f"{profile.disease_threshold:.2f}."
                ),
            )
        )

    # ── الإجهاد الحراريّ ──
    heat_score = _normalized_excess(
        float(heat_stress_hours),
        float(profile.heat_hours_threshold),
        float(profile.heat_hours_span),
    )
    if heat_score > 0.0:
        sev = _severity_for(heat_score)
        risks.append(
            CropRisk(
                risk_type="heat_stress",
                crop=crop,
                severity=sev,
                score=round(heat_score, 4),
                reason_ar=(
                    f"إجهاد حراريّ على ال{profile.name_ar}: {int(heat_stress_hours)} ساعة "
                    f"تجاوزت حدّ التحمّل {profile.heat_hours_threshold} ساعة."
                ),
            )
        )

    # ── ضرر الصقيع ──
    frost_score = _normalized_excess(
        float(frost_risk_hours),
        float(profile.frost_hours_threshold),
        float(profile.frost_hours_span),
    )
    if frost_score > 0.0:
        sev = _severity_for(frost_score)
        risks.append(
            CropRisk(
                risk_type="frost_damage",
                crop=crop,
                severity=sev,
                score=round(frost_score, 4),
                reason_ar=(
                    f"خطر ضرر صقيع على ال{profile.name_ar}: {int(frost_risk_hours)} ساعة "
                    f"تجاوزت حسّاسيّة الصقيع {profile.frost_hours_threshold} ساعة."
                ),
            )
        )

    return risks
