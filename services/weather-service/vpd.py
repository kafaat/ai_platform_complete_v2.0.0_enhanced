"""vpd.py — منتَج نقص ضغط البخار (VPD) الموحَّد — WS-C.1a.

**عقد واحد، وحدة واحدة، صيغة واحدة** لـVPD — بديلٌ لقراءته من حقل المزوّد أو حسابه
مبعثراً. يُبنى على بدائيّات الضغط البخاري المشتركة (``vapor_pressure``) نفسها التي
يستخدمها ET0 (WS-C.1b) — فلا تتضارب الصيغتان.

    VPD = es − ea        (kPa)
    es = متوسّط SVP من (Tmax, Tmin)          [FAO-56 Eq. 12]
    ea = es · RH/100  (مسار RH)  أو  e°(Tdew)  (مسار نقطة النَّدى)  [Eq. 19 / 14]

**صدق fail-closed:** مدخل ناقص (لا حرارة، أو لا RH ولا نقطة ندى) ⇒ ``insufficient``
مع ``vpd_kpa=None`` — لا افتراض «طبيعيّ» يُوهِم قيمة. المخرَج يحمل ``method`` و
``input_completeness`` و``quality_status`` ليقرأ المستهلك مصدر القيمة وموثوقيّتها.

نقيّ حتميّ (لا I/O) — قابل للاختبار offline.
"""

from __future__ import annotations

from vapor_pressure import (
    FORMULA_VERSION,
    actual_vapor_pressure_from_dewpoint_kpa,
    actual_vapor_pressure_from_rh_kpa,
    mean_saturation_vapor_pressure_kpa,
    saturation_vapor_pressure_kpa,
)

PRODUCT_ID = "vpd"
PRODUCT_VERSION = "1.0.0"

# حدود معقوليّة (تحقّق المدى، لا قصّ صامت للقيمة الناتجة).
_T_MIN_C, _T_MAX_C = -60.0, 70.0


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _in_temp_range(*ts: float) -> bool:
    return all(_T_MIN_C <= t <= _T_MAX_C for t in ts)


def compute_vpd(
    *,
    t_max_c: float | None,
    t_min_c: float | None = None,
    rh_mean_pct: float | None = None,
    dew_point_c: float | None = None,
) -> dict:
    """يحسب VPD من الحرارة + (RH أو نقطة النَّدى). fail-closed عند النقص.

    ``t_min_c`` اختياريّ: عند غيابه يُستخدم ``t_max_c`` كتقدير للحدّ الأدنى (es من قيمة
    واحدة) — يُعلَن ``input_completeness="partial"``. أولويّة المسار: RH إن توفّر (أدقّ
    للرطوبة النسبيّة)، وإلّا نقطة النَّدى.

    Returns dict:
        ``vpd_kpa`` (float|None) · ``es_kpa`` · ``ea_kpa`` · ``method``
        (rh_based|dewpoint_based|insufficient) · ``input_completeness``
        (full|partial|none) · ``quality_status`` (ok|out_of_range|insufficient_inputs) ·
        ``formula_version`` · ``product``/``version``.
    """
    tmax = _num(t_max_c)
    tmin = _num(t_min_c)
    rh = _num(rh_mean_pct)
    dew = _num(dew_point_c)

    base = {
        "product": PRODUCT_ID,
        "version": PRODUCT_VERSION,
        "formula_version": FORMULA_VERSION,
        "vpd_kpa": None,
        "es_kpa": None,
        "ea_kpa": None,
    }

    # (1) الاكتمال — حرارة إلزاميّة + (RH أو نقطة ندى). مفقود ≠ افتراض.
    if tmax is None or (rh is None and dew is None):
        return {
            **base,
            "method": "insufficient",
            "input_completeness": "none",
            "quality_status": "insufficient_inputs",
        }

    # (2) تحقّق المدى — قيَم خارج المعقول ⇒ لا نُنتِج رقماً مُضلِّلاً.
    temps = [tmax] + ([tmin] if tmin is not None else []) + ([dew] if dew is not None else [])
    if not _in_temp_range(*temps) or (rh is not None and not (-1.0 <= rh <= 101.0)):
        return {
            **base,
            "method": "insufficient",
            "input_completeness": "none",
            "quality_status": "out_of_range",
        }

    # es: متوسّط الحدّين إن توفّرا، وإلّا من قيمة واحدة (partial).
    if tmin is not None:
        es = mean_saturation_vapor_pressure_kpa(tmax, tmin)
        completeness = "full"
    else:
        es = saturation_vapor_pressure_kpa(tmax)
        completeness = "partial"

    # ea: أولويّة RH (أدقّ لقياس الرطوبة)، وإلّا نقطة النَّدى.
    if rh is not None:
        ea = actual_vapor_pressure_from_rh_kpa(es, rh)
        method = "rh_based"
    else:
        ea = actual_vapor_pressure_from_dewpoint_kpa(dew)  # dew ليس None هنا
        method = "dewpoint_based"
        # نقطة ندى أعلى من es (شذوذ رصد) ⇒ VPD سالب؛ نُثبّته عند 0 ونُعلن القيد.
        if ea > es:
            ea = es

    vpd = max(0.0, es - ea)
    return {
        **base,
        "vpd_kpa": round(vpd, 3),
        "es_kpa": round(es, 3),
        "ea_kpa": round(ea, 3),
        "method": method,
        "input_completeness": completeness,
        "quality_status": "ok",
    }
