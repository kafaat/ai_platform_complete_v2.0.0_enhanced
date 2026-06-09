"""
sahool_core.measurement
========================
مبدأ القياس (المبدأ السابع المُضمر): كل قيمة تدخل النواة يجب أن تكون
موحّدة الوحدة، مُعايرة المرجع، موثّقة الحدود.

جزآن:
  ١. توحيد الوحدات — يرفض الوحدات المحلية الغامضة (لتر/فدان بلا مساحة)،
     يحوّل للوحدات الموحّدة (SI/FAO). يمنع خطأ المقارنة.
  ٢. التحلّل المكاني — يقرّر هل قياس الجار صالح للاستخدام كإشارة، حسب
     طول الارتباط (الماء 2كم صالح، التربة 50م نادراً). لا يعطي قيمة
     الحقل المزعومة — يقرّر الصلاحية والسقف فقط.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ════════════════════════════════════════════════════════════
# ١. توحيد الوحدات (يرفض المحلية الغامضة)
# ════════════════════════════════════════════════════════════
# عوامل التحويل للوحدة الموحّدة (المصدر: FAO-56 / SI)
_UNIT_CONVERSIONS = {
    # (من, إلى): عامل
    ("mS/cm", "dS/m"): 1.0,        # متطابقان (كلاهما 0.1 S/m) — الوثيقة قالت 10 وهو خطأ شائع
    ("ppm", "mg/kg"): 1.0,         # متطابقان
    ("mmHg", "kPa"): 0.1333,
    ("ton/ha", "kg/ha"): 1000.0,
}

# الوحدات الموحّدة المقبولة في النواة
_CANONICAL_UNITS = {"mm/day", "mg/kg", "dS/m", "kg/ha", "C", "kPa", "pct", "pH"}

# وحدات محلية غامضة تُرفض (تحتاج سياقاً إضافياً)
_AMBIGUOUS_UNITS = {"liter/feddan", "لتر/فدان", "liter", "لتر", "صاع", "كيس"}


@dataclass
class UnitResult:
    value: float | None
    unit: str
    ok: bool
    note_ar: str


def harmonize_unit(value: float, from_unit: str) -> UnitResult:
    """يحوّل لوحدة موحّدة، أو يرفض الغامضة. يمنع خطأ المقارنة."""
    u = from_unit.strip()
    if u in _AMBIGUOUS_UNITS:
        return UnitResult(None, u, False,
            f"وحدة غامضة ({u}) — تحتاج سياقاً (مثلاً المساحة) للتحويل. مرفوضة.")
    if u in _CANONICAL_UNITS:
        return UnitResult(value, u, True, f"وحدة موحّدة ({u})")
    # ابحث عن تحويل لوحدة موحّدة
    for (src, dst), factor in _UNIT_CONVERSIONS.items():
        if src == u and dst in _CANONICAL_UNITS:
            return UnitResult(round(value * factor, 4), dst, True,
                f"حُوّلت {u}→{dst} (×{factor})")
    return UnitResult(None, u, False,
        f"وحدة غير قابلة للتتبّع إلى SI/FAO ({u}) — مرفوضة")


# ════════════════════════════════════════════════════════════
# ٢. التحلّل المكاني (صلاحية قياس الجار)
# ════════════════════════════════════════════════════════════
# طول الارتباط بالأمتار لكل نوع قياس (المصدر: الوثيقة + علم التربة)
_CORRELATION_LENGTH_M = {
    "weather": 10000.0,    # الطقس: نفس المحطة تغطّي 10كم
    "water_ec": 2000.0,    # ماء الري: نفس المصدر/البئر
    "soil_moisture": 100.0,
    "soil_n": 50.0,        # نيتروجين التربة: تباين عالٍ
    "soil_ph": 30.0,       # pH: الأعلى تبايناً
}


@dataclass
class SpatialValidity:
    valid: bool
    confidence_ceiling: str        # none / low / medium
    decay_factor: float            # exp(-d/L)
    note_ar: str


def spatial_substitution_validity(measurement_type: str, distance_m: float,
                                  base_confidence: str = "medium") -> SpatialValidity:
    """يقرّر هل قياس الجار صالح كإشارة، حسب المسافة وطول الارتباط.

    ⚠️ لا يعطي قيمة الحقل المزعومة — يقرّر الصلاحية والسقف فقط.
    الماء (L=2كم) يُقبل لمسافات أكبر؛ التربة (L=30-50م) نادراً.
    تجاوز طول الارتباط → مرفوض (NONE)."""
    L = _CORRELATION_LENGTH_M.get(measurement_type)
    if L is None:
        return SpatialValidity(False, "none", 0.0,
            f"نوع قياس غير معروف ({measurement_type}) — لا إحلال مكاني")
    decay = math.exp(-distance_m / L)
    # تجاوز طول الارتباط (decay < ~0.37) → مرفوض
    if distance_m > L:
        return SpatialValidity(False, "none", round(decay, 3),
            f"المسافة ({distance_m}م) تتجاوز طول الارتباط ({L}م) — مرفوض، "
            f"لا إحلال. أجرِ قياساً خاصاً.")
    # ضمن النطاق: السقف يخفض بالمسافة، ولا يتجاوز سقف القرينة الطيفية
    ceiling = "medium" if decay >= 0.6 else "low"
    # التربة لا تتجاوز low مهما قربت (تباين دقيق)
    if measurement_type.startswith("soil"):
        ceiling = "low"
    return SpatialValidity(True, ceiling, round(decay, 3),
        f"قياس الجار صالح كإشارة (مسافة {distance_m}م ضمن {L}م، "
        f"تحلّل {decay:.2f}). سقف {ceiling} — جسر حتى قياسك الخاص، لا بديل.")
