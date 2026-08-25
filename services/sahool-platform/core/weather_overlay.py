"""core/weather_overlay.py — منطق تراكب الطقس على الحقل (درجات قراريّة، نقيّ حتميّ).

طبقة ذكاء الطقس: تُحوّل تنبّؤاً ساعيّاً (مُجمَّعاً على خلايا شبكة الطقس داخل مضلّع الحقل)
إلى **درجات قراريّة** يفهمها المزارع/محرّك التوصية: صلاحيّة الرشّ، خطر المرض، صلاحيّة
مرور الآليّات، ساعات الإجهاد الحراريّ/الصقيع. منطق زراعيّ صريح (عتبات موثّقة من الأدبيّات)
— لا I/O ولا قاعدة ولا نموذج صندوق أسود؛ تُختبَر بـdicts عاديّة وتُغذّي خدمة التراكب.

العتبات إرشاديّة (FAO/أدبيّات الرشّ) قابلة للمعايرة اليمنيّة المحلّيّة لاحقاً.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.thresholds import FROST_RISK_C, HEAT_STRESS_HOURLY_C

# ── عتبات الرشّ (drift/inversion) ──
_DELTA_T_MIN, _DELTA_T_MAX = 2.0, 8.0  # °C: <2 خطر انقلاب حراريّ، >8 تبخّر مفرط للرذاذ
_WIND_MIN_MS, _WIND_MAX_MS = 0.8, 4.2  # م/ث ≈ 3–15 كم/س: أقلّ=انجراف انقلاب، أكثر=انجراف ريح
_SPRAY_RAIN_MM = 0.2  # مطر يُلغي الرشّ

# ── عتبات المرض الفطريّ ──
_DISEASE_RH = 85.0  # رطوبة % تُفضّل العدوى الفطريّة
_DISEASE_T_MIN, _DISEASE_T_MAX = 10.0, 30.0  # °C نافذة حرارة مواتية لأغلب الممرضات

# ── عتبات الإجهاد (من المصدر الموحّد core.thresholds — نفس القيم) ──
_HEAT_C = HEAT_STRESS_HOURLY_C  # عدّ ساعات الإجهاد الحراريّ (أساس ساعيّ)
_FROST_C = FROST_RISK_C  # °C خطر صقيع
_TRAFFIC_PRECIP_CAP_MM = 40.0  # تراكم مطر يُشبِع التربة فتنعدم صلاحيّة المرور


@dataclass(frozen=True)
class HourlyWeather:
    """سجلّ ساعيّ مُجمَّع على الحقل (القيم المتاحة؛ None يُتجاهَل في الدرجات)."""

    temp_avg_c: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    precip_mm: float | None = None
    delta_t_c: float | None = None


@dataclass(frozen=True)
class FieldWeatherScores:
    spray_suitability_score: float  # [0,1] نسبة الساعات الصالحة للرشّ
    disease_risk_score: float  # [0,1] نسبة ساعات الخطر الفطريّ
    trafficability_score: float  # [0,100] صلاحيّة مرور الآليّات
    heat_stress_hours: int
    frost_risk_hours: int
    hours_evaluated: int  # ساعاتٌ **حاضرة** في السلسلة — لا تصلح مقاماً لثقّة حدث
    # ── مقاماتٌ مخصوصة لكلّ حدث: الفرصُ التي كان الحدثُ قابلاً للرصد فيها ──
    #
    # `hours_evaluated` يعدّ كلّ ساعةٍ حاضرة، بينما `frost_risk_hours` يشترط
    # `temp_min_c is not None`. فالساعةُ الحاضرة بلا `temp_min` تدخل المقامَ ولا
    # يمكنها أن تدخل البسطَ **أبداً** — بسطٌ ومقامٌ من فضاءَي ملاحظةٍ مختلفَين.
    #
    # مقيس: ٢٤ ساعة حاضرة · ١٢ منها بلا `temp_min` · ٦ صقيع ⇒ الثقة تُبخَس
    # الضعفَ (6/24 بدل 6/12). والاتّجاهُ معاكسٌ لعطلِ الاختراع الأصليّ ونفسُ الخطأ.
    #
    # حقلان صريحان لا تجريدٌ عامّ (`evaluated_hours_by_metric`): أوضحُ وأقلُّ خطراً.
    frost_evaluable_hours: int = 0
    heat_evaluable_hours: int = 0


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _spray_ok(h: HourlyWeather) -> bool:
    """ساعة صالحة للرشّ: Δ-T وريح ضمن النطاق ولا مطر يُذكَر."""
    if h.delta_t_c is None or h.wind_speed_ms is None:
        return False
    if not (_DELTA_T_MIN <= h.delta_t_c <= _DELTA_T_MAX):
        return False
    if not (_WIND_MIN_MS <= h.wind_speed_ms <= _WIND_MAX_MS):
        return False
    return (h.precip_mm or 0.0) < _SPRAY_RAIN_MM


def _disease_hour(h: HourlyWeather) -> bool:
    """ساعة خطر فطريّ: رطوبة عالية + حرارة ضمن النافذة المواتية."""
    if h.humidity_pct is None or h.temp_avg_c is None:
        return False
    return h.humidity_pct >= _DISEASE_RH and _DISEASE_T_MIN <= h.temp_avg_c <= _DISEASE_T_MAX


def compute_scores(hours: list[HourlyWeather]) -> FieldWeatherScores:
    """يحسب درجات تراكب الطقس من تنبّؤ ساعيّ (نقيّ). قائمة فارغة ⇒ درجات محايدة صفر."""
    n = len(hours)
    if n == 0:
        return FieldWeatherScores(0.0, 0.0, 0.0, 0, 0, 0)

    spray_ok = sum(1 for h in hours if _spray_ok(h))
    disease_h = sum(1 for h in hours if _disease_hour(h))
    # الفرصُ أوّلاً ثمّ الوقوعُ داخلها — فالبسطُ مجموعةٌ جزئيّة من مقامه بالبناء.
    heat_evaluable = sum(1 for h in hours if h.temp_max_c is not None)
    frost_evaluable = sum(1 for h in hours if h.temp_min_c is not None)
    heat_h = sum(1 for h in hours if h.temp_max_c is not None and h.temp_max_c > _HEAT_C)
    frost_h = sum(1 for h in hours if h.temp_min_c is not None and h.temp_min_c < _FROST_C)
    precip_sum = sum(h.precip_mm or 0.0 for h in hours)

    # صلاحيّة المرور: تتناقص أُسّيّاً مع تراكب المطر (تربة مُشبَعة ⇒ لا مرور آليّات).
    traffic = 100.0 * math.exp(-precip_sum / _TRAFFIC_PRECIP_CAP_MM)

    return FieldWeatherScores(
        spray_suitability_score=round(spray_ok / n, 4),
        disease_risk_score=round(disease_h / n, 4),
        trafficability_score=round(_clamp(traffic, 0.0, 100.0), 2),
        heat_stress_hours=heat_h,
        frost_risk_hours=frost_h,
        hours_evaluated=n,
        frost_evaluable_hours=frost_evaluable,
        heat_evaluable_hours=heat_evaluable,
    )
