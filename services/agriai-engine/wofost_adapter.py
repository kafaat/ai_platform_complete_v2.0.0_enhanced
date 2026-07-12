"""SAHOOL agriai-engine — wofost_adapter.py (وحدة صرفة، بلا FastAPI).

مُحوِّل محاكاة المحصول: ``simulate(crop, weather, soil, agromanagement)`` يُرجع دائماً
مخطّطاً موحّداً: ``{yield_kg_ha, biomass, water_use, stages, provenance}``.

- ``pcse`` تبعيّة ثقيلة اختياريّة، مُحاطة بحارس استيراد. عند توفّرها وكفاية المدخلات
  نُشغّل تشغيل PCSE/WOFOST حقيقيّاً؛ عند غيابها نلجأ إلى بديل حتميّ (heuristic) موثّق
  يُرجع نفس المخطّط بـ ``provenance="deterministic_fallback"``. لا ننهار أبداً على غياب pcse.

بديل الغلّة الحتميّ (قانون الحدّ الأدنى — Liebig): الغلّة = أدنى قيد بين
    (١) سقف حراريّ: max_yield * min(1, GDD/GDD_to_maturity)
    (٢) قيد مائيّ: (مطر + ريّ + ماء تربة متاح) * كفاءة استخدام الماء (WUE)
ثمّ الكتلة الحيويّة = الغلّة / معامل الحصاد، واستهلاك الماء = الغلّة / WUE.
رتابة مضمونة: مزيد من الماء أو حرارة أفضل ⇒ غلّة ≥ (حتّى بلوغ السقف الآخر).
"""

from __future__ import annotations

import os
from typing import Any

# ── حارس استيراد pcse (تبعيّة ثقيلة اختياريّة — ليست تبعيّة صلبة) ──
try:  # pragma: no cover - المسار الثقيل غير مُفعَّل في طبقة الوحدات/CI
    import pcse  # type: ignore  # noqa: F401

    _PCSE_AVAILABLE = True
except Exception:  # noqa: BLE001 - أيّ فشل استيراد ⇒ نلجأ للبديل الحتميّ بأمان
    _PCSE_AVAILABLE = False


# قيم افتراضيّة زراعيّة معقولة للبديل الحتميّ (تُستبدل بقيم crop عند توفّرها).
_CROP_DEFAULTS: dict[str, float] = {
    "base_temp_c": 5.0,  # عتبة النموّ الحراريّ
    "max_yield_kg_ha": 8000.0,  # سقف الغلّة عند اكتمال الوقت الحراريّ والماء
    "gdd_to_maturity": 1500.0,  # درجات حراريّة تراكميّة حتّى النضج
    "water_use_efficiency": 18.0,  # WUE: كغ/هـ لكلّ ملّم ماء
    "harvest_index": 0.45,  # نسبة الغلّة إلى الكتلة الحيويّة
}

_ROUND = 6


def pcse_available() -> bool:
    """هل تبعيّة pcse متاحة في هذه البيئة؟ (تُبقي الاختبارات صريحة)."""
    return _PCSE_AVAILABLE


def _num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if out == out and out not in (float("inf"), float("-inf")) else default


def _crop_param(crop: dict[str, Any], key: str) -> float:
    return (
        _num(crop.get(key), _CROP_DEFAULTS[key]) if isinstance(crop, dict) else _CROP_DEFAULTS[key]
    )


def _accumulate_gdd(weather: dict[str, Any], base_temp: float) -> float:
    """يجمّع GDD من ``weather['gdd']`` مباشرةً، أو من قائمة أيّام ``daily``.

    كلّ يوم: max(0, tavg - base)، حيث tavg = (tmax+tmin)/2 إن غاب tavg.
    """
    if not isinstance(weather, dict):
        return 0.0
    if weather.get("gdd") is not None:
        return max(0.0, _num(weather.get("gdd")))
    daily = weather.get("daily")
    if not isinstance(daily, list):
        return 0.0
    total = 0.0
    for day in daily:
        if not isinstance(day, dict):
            continue
        if day.get("tavg") is not None:
            tavg = _num(day.get("tavg"))
        else:
            tavg = (_num(day.get("tmax")) + _num(day.get("tmin"))) / 2.0
        total += max(0.0, tavg - base_temp)
    return total


def _stages_from_fraction(frac: float) -> list[dict[str, Any]]:
    """مراحل نموّ تقريبيّة مشتقّة من نسبة الوقت الحراريّ المُنجَز (حتميّة)."""
    thresholds = [
        ("emergence", 0.05),
        ("vegetative", 0.35),
        ("flowering", 0.65),
        ("grain_filling", 0.90),
        ("maturity", 1.00),
    ]
    return [{"stage": name, "reached": frac >= t, "at_fraction": t} for name, t in thresholds]


def _fallback_simulate(
    crop: dict[str, Any],
    weather: dict[str, Any],
    soil: dict[str, Any],
    agromanagement: dict[str, Any],
) -> dict[str, Any]:
    """البديل الحتميّ الموثّق (لا pcse). نفس المخطّط، أرقام قابلة لإعادة الإنتاج."""
    base_temp = _crop_param(crop, "base_temp_c")
    max_yield = _crop_param(crop, "max_yield_kg_ha")
    gdd_to_maturity = _crop_param(crop, "gdd_to_maturity")
    wue = _crop_param(crop, "water_use_efficiency")
    harvest_index = _crop_param(crop, "harvest_index")

    gdd = _accumulate_gdd(weather, base_temp)
    thermal_fraction = min(1.0, gdd / gdd_to_maturity) if gdd_to_maturity > 0 else 0.0

    rain = _num((weather or {}).get("total_rain_mm")) if isinstance(weather, dict) else 0.0
    irrigation = (
        _num((agromanagement or {}).get("irrigation_mm"))
        if isinstance(agromanagement, dict)
        else 0.0
    )
    soil_water = _num((soil or {}).get("available_water_mm")) if isinstance(soil, dict) else 0.0
    water_available = max(0.0, rain + irrigation + soil_water)

    thermal_yield = max_yield * thermal_fraction
    water_limited_yield = water_available * wue if wue > 0 else 0.0
    # قانون الحدّ الأدنى: العامل المُقيِّد يحكم الغلّة.
    yield_kg_ha = max(0.0, min(thermal_yield, water_limited_yield))

    biomass = yield_kg_ha / harvest_index if harvest_index > 0 else 0.0
    water_use = yield_kg_ha / wue if wue > 0 else 0.0

    limiting = "thermal" if thermal_yield <= water_limited_yield else "water"

    return {
        "yield_kg_ha": round(yield_kg_ha, _ROUND),
        "biomass": round(biomass, _ROUND),
        "water_use": round(water_use, _ROUND),
        "stages": _stages_from_fraction(thermal_fraction),
        "provenance": "deterministic_fallback",
        "diagnostics": {
            "gdd": round(gdd, _ROUND),
            "thermal_fraction": round(thermal_fraction, _ROUND),
            "water_available_mm": round(water_available, _ROUND),
            "thermal_yield_kg_ha": round(thermal_yield, _ROUND),
            "water_limited_yield_kg_ha": round(water_limited_yield, _ROUND),
            "limiting_factor": limiting,
        },
    }


def _yield_uncertainty(
    base_result: dict[str, Any],
    crop: dict[str, Any],
    weather: dict[str, Any],
    soil: dict[str, Any],
    agromanagement: dict[str, Any],
) -> dict[str, Any]:
    """نطاق غلّة نموذجيّ (لا نقطة عارية) — «لا غلّة بلا عدم يقين».

    **صدق:** هذا **نطاق نموذجيّ** مشتقّ من ثقة النموذج، لا نطاق مُعايَر تجريبيّاً
    (conformal) — ذاك يتطلّب بيانات حصاد محلّية ويعيش في
    ``core/engines/yield_interval.py``. يتّسع النطاق بأمانة كلّما:
      • قلّت المدخلات (طقس يوميّ/مطر/ماء تربة/إدارة/وسائط محصول مفقودة)،
      • اقترب العامل المُقيِّد من عتبة التبدّل (تغيّر طفيف يقلب النظام حراريّ↔مائيّ)،
      • كان المصدر بديلاً حتميّاً لا PCSE حقيقيّاً.
    كلّ موسِّع مُدرَج في ``drivers`` (لا رقم بلا سبب).
    """
    y = _num(base_result.get("yield_kg_ha"))
    prov = base_result.get("provenance")
    diag = base_result.get("diagnostics") or {}

    is_pcse = prov == "pcse_wofost"
    u = 0.12 if is_pcse else 0.25
    drivers: list[str] = [] if is_pcse else ["deterministic_fallback_model"]

    w = weather if isinstance(weather, dict) else {}
    has_daily = isinstance(w.get("daily"), list) and bool(w.get("daily"))
    if w.get("gdd") is None and not has_daily:
        u += 0.08
        drivers.append("missing_daily_weather")
    if w.get("total_rain_mm") is None:
        u += 0.04
        drivers.append("missing_rainfall")
    if not (isinstance(soil, dict) and soil.get("available_water_mm") is not None):
        u += 0.05
        drivers.append("missing_soil_water")
    if not (isinstance(agromanagement, dict) and agromanagement.get("irrigation_mm") is not None):
        u += 0.03
        drivers.append("missing_irrigation_plan")
    if not (isinstance(crop, dict) and crop):
        u += 0.05
        drivers.append("default_crop_params")

    # قرب عتبة العامل المُقيِّد ⇒ عدم يقين أعلى (تبدّل النظام يقلب الغلّة).
    ty = _num(diag.get("thermal_yield_kg_ha"))
    wy = _num(diag.get("water_limited_yield_kg_ha"))
    if ty > 0 and wy > 0:
        closeness = 1.0 - abs(ty - wy) / max(ty, wy)
        add = round(0.10 * max(0.0, closeness), _ROUND)
        if add > 0:
            u += add
            drivers.append("near_limiting_factor_crossover")

    u = min(0.6, round(u, _ROUND))  # سقف 60٪ — لا نطاق عبثيّ
    low = max(0.0, round(y * (1.0 - u), _ROUND))
    high = round(y * (1.0 + u), _ROUND)
    confidence = "high" if u < 0.20 else "medium" if u < 0.35 else "low"
    return {
        "point_kg_ha": round(y, _ROUND),
        "low_kg_ha": low,
        "high_kg_ha": high,
        "relative_uncertainty": u,
        "confidence": confidence,
        "method": "deterministic_model_band",
        "drivers": drivers,
        "note_ar": (
            "نطاق نموذجيّ لا نقطة وهميّة — يتّسع بنقص المدخلات وقرب عتبة العامل المُقيِّد. "
            "النطاق المُعايَر إحصائيّاً (conformal) يتطلّب بيانات حصاد محلّية."
        ),
    }


def _inputs_sufficient_for_pcse(
    crop: dict[str, Any],
    weather: dict[str, Any],
    soil: dict[str, Any],
    agromanagement: dict[str, Any],
) -> bool:
    """كفاية دنيا لتشغيل PCSE حقيقيّ: بيانات يوميّة + تربة + إدارة زراعيّة."""
    return (
        isinstance(weather, dict)
        and isinstance(weather.get("daily"), list)
        and bool(weather.get("daily"))
        and isinstance(soil, dict)
        and bool(soil)
        and isinstance(agromanagement, dict)
        and bool(agromanagement)
        and isinstance(crop, dict)
        and bool(crop)
    )


def _pcse_simulate(  # pragma: no cover - يتطلّب تبعيّة pcse الثقيلة (خارج طبقة CI)
    crop: dict[str, Any],
    weather: dict[str, Any],
    soil: dict[str, Any],
    agromanagement: dict[str, Any],
) -> dict[str, Any]:
    """تشغيل PCSE/WOFOST حقيقيّ. مُؤجَّل خلف الحارس؛ عند أيّ فشل نرجع للبديل الحتميّ."""
    from pcse.base import ParameterProvider  # type: ignore
    from pcse.models import Wofost72_WLP_FD  # type: ignore

    # ملاحظة: بناء موفِّرات PCSE (طقس/تربة/محصول/إدارة) من dict خارج نطاق طبقة الوحدات.
    # نُبقي البنية صريحة؛ التنفيذ الكامل يُفعَّل حين تُركَّب pcse في بيئة التكامل.
    provider = ParameterProvider(cropdata=crop, soildata=soil, sitedata={})
    model = Wofost72_WLP_FD(provider, weather, agromanagement)
    model.run_till_terminate()
    output = model.get_summary_output()[0]
    yield_kg_ha = _num(output.get("TWSO"))
    biomass = _num(output.get("TAGP"))
    return {
        "yield_kg_ha": round(yield_kg_ha, _ROUND),
        "biomass": round(biomass, _ROUND),
        "water_use": round(_num(output.get("CTRAT")), _ROUND),
        "stages": [{"stage": "maturity", "reached": True, "at_fraction": 1.0}],
        "provenance": "pcse_wofost",
        "diagnostics": {"raw_summary_keys": sorted(str(k) for k in output)},
    }


def simulate(
    crop: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
    soil: dict[str, Any] | None = None,
    agromanagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """يُحاكي المحصول ويُرجع المخطّط الموحّد. لا ينهار أبداً على غياب pcse.

    يختار PCSE حين يكون متاحاً والمدخلات كافية؛ وإلّا (أو عند فشل التشغيل الثقيل)
    يلجأ إلى البديل الحتميّ الموثّق.
    """
    crop = crop or {}
    weather = weather or {}
    soil = soil or {}
    agromanagement = agromanagement or {}

    # وضع الإنتاج: المحاكاة العلميّة (PCSE/WOFOST) بمدخلات كاملة إلزاميّة — البديل
    # الحتميّ تطويريّ فقط. الفشل هنا مُغلَق وصريح، لا استبدال صامت.
    production_mode = os.getenv("AGRIAI_PRODUCTION_MODE", "0").lower() in {"1", "true", "yes", "on"}
    sufficient = _inputs_sufficient_for_pcse(crop, weather, soil, agromanagement)
    if production_mode and (not _PCSE_AVAILABLE or not sufficient):
        reasons = []
        if not _PCSE_AVAILABLE:
            reasons.append("pcse_unavailable")
        if not sufficient:
            reasons.append("scientific_inputs_incomplete")
        raise RuntimeError("agriai_production_simulation_unavailable:" + ",".join(reasons))

    result: dict[str, Any] | None = None
    if _PCSE_AVAILABLE and sufficient:
        try:  # pragma: no cover - يتطلّب pcse
            result = _pcse_simulate(crop, weather, soil, agromanagement)
        except Exception as exc:  # noqa: BLE001 - fail-safe في التطوير فقط
            if production_mode:
                raise RuntimeError("pcse_simulation_failed") from exc
            result = None
    if result is None:
        result = _fallback_simulate(crop, weather, soil, agromanagement)

    # «لا غلّة بلا عدم يقين»: كلّ مخرَج simulate يحمل نطاقاً نموذجيّاً (نقطة مصحوبة بحدود).
    result["yield_interval"] = _yield_uncertainty(result, crop, weather, soil, agromanagement)
    return result
