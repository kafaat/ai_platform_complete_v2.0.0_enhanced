"""vpd.py — منتَج نقص ضغط البخار (VPD) الموحَّد + عقد جودة صريح — WS-C.1a.

**عقد واحد، وحدة واحدة، صيغة واحدة** لـVPD، مبنيّ على بدائيّات الضغط البخاري المشتركة
(``vapor_pressure``) التي يستهلكها ET0 (C.1b) نفسها — فلا تتضارب الصيَغ.

    VPD = es − ea   (kPa)   ؛   es = متوسّط SVP من (Tmax, Tmin) [FAO-56 Eq.12]
    ea = es·RH/100 (مسار RH) أو e°(Tdew) (مسار نقطة النَّدى) [Eq.19 / 14]

عقد الجودة (قرار المستخدم) — لا نتائج مُضلِّلة:
  • **رفض غير-المحدود صراحةً:** NaN/±inf في أيّ مدخل ⇒ ``invalid`` (لا مقارنة نطاق فقط).
  • **مفقود ≠ افتراض:** لا حرارة، أو لا RH ولا نقطة ندى ⇒ ``insufficient`` (``vpd_kpa=None``).
  • **أسبقيّة RH حتميّة:** RH صالح ⇒ المخرَج دائماً ``rh_based`` (لا «الأقرب» غير الحتميّ).
    عند توفّر RH ونقطة النَّدى معاً ⇒ يُحسَب المساران للتحقّق المتقاطع؛ فرق > العتبة
    ⇒ ``inconsistent_inputs`` + علم ``rh_dewpoint_disagreement`` + كتلة ``cross_check``.
  • **قصّ سالب ظاهر متدرّج:** VPD خام سالب صغير (rounding) ⇒ 0 + ``degraded``؛ سالب
    كبير (تعارُض) ⇒ 0 + ``inconsistent_inputs``. ``raw_vpd_kpa`` يبقى مرئيّاً.
  • **completeness ≠ consistency:** محوران منفصلان (اكتمال المدخلات مقابل اتّساقها).
  • **وحدات صريحة في المخرَج** (لا توثيق خارجيّ فقط) — لا Kelvin ولا كسر RH.

نقيّ حتميّ (لا I/O). المفردات المحدودة لـ``quality_status``:
    validated · degraded · inconsistent_inputs · insufficient · invalid
"""

from __future__ import annotations

import math

from vapor_pressure import (
    actual_vapor_pressure_from_dewpoint_kpa,
    actual_vapor_pressure_from_rh_kpa,
    mean_saturation_vapor_pressure_kpa,
    saturation_vapor_pressure_kpa,
)

PRODUCT_ID = "vpd"
PRODUCT_VERSION = "1.0.0"
FORMULA_VERSION = "vpd/fao56/1.0.0"

# وحدات العقد الصريحة (مُثبَّتة، لا توثيق خارجيّ). لا يُقبَل Kelvin أو كسر RH.
TEMPERATURE_UNIT = "degC"
RELATIVE_HUMIDITY_UNIT = "percent"
VAPOUR_PRESSURE_UNIT = "kPa"

# عتبة تباعُد مساري RH/نقطة النَّدى (kPa) — في العقد لا في env (تغييرها = إصدار جديد).
RH_DEWPOINT_VPD_TOLERANCE_KPA = 0.20
# هامش القصّ السالب المقبول كـrounding (أصغر منه = degraded؛ أكبر = inconsistent).
NEGATIVE_VPD_ROUNDING_TOLERANCE_KPA = 0.01

# حدود معقوليّة فيزيائيّة (تحقّق النطاق بعد تحقّق المحدوديّة).
_T_MIN_C, _T_MAX_C = -60.0, 70.0

# ترتيب شدّة حالات الجودة (لأخذ الأسوأ عند تراكب أسباب).
_SEVERITY = {"validated": 0, "degraded": 1, "inconsistent_inputs": 2, "invalid": 3}


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _coerce(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _units_block() -> dict:
    return {
        "inputs": {
            "temperature_unit": TEMPERATURE_UNIT,
            "relative_humidity_unit": RELATIVE_HUMIDITY_UNIT,
            "dew_point_unit": TEMPERATURE_UNIT,
        },
        "output_unit": VAPOUR_PRESSURE_UNIT,
    }


def _shell(status: str, *, flags=None, limitations=None) -> dict:
    return {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "formula_version": FORMULA_VERSION,
        "units": _units_block(),
        "vpd_kpa": None,
        "raw_vpd_kpa": None,
        "es_kpa": None,
        "ea_kpa": None,
        "method": "insufficient" if status in ("insufficient", "invalid") else None,
        "input_completeness": 0.0,
        "input_consistency": None,
        "quality_status": status,
        "quality_flags": list(flags or []),
        "limitations": list(limitations or []),
        "cross_check": None,
    }


def compute_vpd(
    *,
    t_max_c: float | None,
    t_min_c: float | None = None,
    rh_mean_pct: float | None = None,
    dew_point_c: float | None = None,
) -> dict:
    """يحسب VPD من الحرارة + (RH أو نقطة النَّدى) بعقد جودة صريح. لا يرمي أبداً.

    Returns dict (المفاتيح الجوهريّة): ``vpd_kpa``/``raw_vpd_kpa``/``es_kpa``/``ea_kpa`` ·
    ``method`` (rh_based|dewpoint_based|insufficient) · ``input_completeness`` (0..1) ·
    ``input_consistency`` (0..1|None) · ``quality_status`` (المفردات المحدودة) ·
    ``quality_flags`` · ``limitations`` · ``cross_check`` · ``units`` · ``formula_version``.
    """
    raws = {
        "t_max_c": _coerce(t_max_c),
        "t_min_c": _coerce(t_min_c),
        "rh_mean_pct": _coerce(rh_mean_pct),
        "dew_point_c": _coerce(dew_point_c),
    }

    # (1) رفض غير-المحدود صراحةً — NaN/±inf ⇒ invalid (لا يكفي فحص النطاق).
    for name, val in raws.items():
        if val is not None and not math.isfinite(val):
            return _shell(
                "invalid",
                flags=["non_finite_input"],
                limitations=[f"{name} is not finite (NaN/inf) — rejected."],
            )

    tmax, tmin, rh, dew = (
        raws["t_max_c"],
        raws["t_min_c"],
        raws["rh_mean_pct"],
        raws["dew_point_c"],
    )

    # (2) الاكتمال — حرارة إلزاميّة + مصدر رطوبة (RH أو نقطة ندى). مفقود ≠ افتراض.
    if tmax is None or (rh is None and dew is None):
        return _shell("insufficient", limitations=["missing temperature or humidity source"])

    # (3) تحقّق النطاق الفيزيائيّ (بعد المحدوديّة) ⇒ invalid.
    temps = [t for t in (tmax, tmin, dew) if t is not None]
    if not all(_T_MIN_C <= t <= _T_MAX_C for t in temps) or (
        rh is not None and not (-1.0 <= rh <= 101.0)
    ):
        return _shell(
            "invalid", flags=["out_of_physical_range"], limitations=["input out of range"]
        )

    # es: متوسّط الحدّين إن توفّرا، وإلّا من قيمة واحدة (اكتمال أقلّ، لا كسر).
    if tmin is not None:
        es = mean_saturation_vapor_pressure_kpa(tmax, tmin)
    else:
        es = saturation_vapor_pressure_kpa(tmax)
    present = sum(x is not None for x in (tmax, tmin)) + (
        1 if (rh is not None or dew is not None) else 0
    )
    completeness = round(present / 3.0, 2)

    # المسار الأساسيّ حتميّاً: RH إن توفّر، وإلّا نقطة النَّدى.
    if rh is not None:
        ea = actual_vapor_pressure_from_rh_kpa(es, rh)
        method = "rh_based"
    else:
        ea = actual_vapor_pressure_from_dewpoint_kpa(dew)
        method = "dewpoint_based"

    raw_vpd = es - ea
    flags: list[str] = []
    limitations: list[str] = []

    # قصّ سالب متدرّج ظاهر (لا صفر صامت).
    if raw_vpd >= 0.0:
        vpd = raw_vpd
        quality = "validated"
    elif raw_vpd >= -NEGATIVE_VPD_ROUNDING_TOLERANCE_KPA:
        vpd = 0.0
        quality = "degraded"
        flags.append("negative_vpd_clamped")
        limitations.append("Small negative VPD clamped to zero (rounding).")
    else:
        vpd = 0.0
        quality = "inconsistent_inputs"
        flags.append("negative_vpd_clamped")
        limitations.append("Computed VPD was significantly negative — inconsistent inputs.")

    consistency: float | None = 1.0
    cross_check = None

    # التحقّق المتقاطع حين يتوفّر المساران (لا يغيّر المخرَج الأساسيّ — حتميّة).
    if rh is not None and dew is not None:
        vpd_rh = max(0.0, es - actual_vapor_pressure_from_rh_kpa(es, rh))
        vpd_dew = max(0.0, es - actual_vapor_pressure_from_dewpoint_kpa(dew))
        diff = abs(vpd_rh - vpd_dew)
        cross_check = {
            "rh_based_vpd_kpa": round(vpd_rh, 3),
            "dewpoint_based_vpd_kpa": round(vpd_dew, 3),
            "difference_kpa": round(diff, 3),
            "tolerance_kpa": RH_DEWPOINT_VPD_TOLERANCE_KPA,
        }
        if diff > RH_DEWPOINT_VPD_TOLERANCE_KPA:
            quality = _worse(quality, "inconsistent_inputs")
            flags.append("rh_dewpoint_disagreement")
            # اتّساق مُشتقّ من الفرق (محور منفصل عن الاكتمال).
            consistency = round(
                max(
                    0.0,
                    1.0
                    - (diff - RH_DEWPOINT_VPD_TOLERANCE_KPA)
                    / (2.0 * RH_DEWPOINT_VPD_TOLERANCE_KPA),
                ),
                2,
            )

    return {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "formula_version": FORMULA_VERSION,
        "units": _units_block(),
        "vpd_kpa": round(vpd, 3),
        "raw_vpd_kpa": round(raw_vpd, 3),
        "es_kpa": round(es, 3),
        "ea_kpa": round(ea, 3),
        "method": method,
        "input_completeness": completeness,
        "input_consistency": consistency,
        "quality_status": quality,
        "quality_flags": flags,
        "limitations": limitations,
        "cross_check": cross_check,
    }
