"""SAHOOL agriai-engine — wofost_adapter.py (وحدة صرفة، بلا FastAPI).

مُحوِّل محاكاة المحصول: ``simulate(crop, weather, soil, agromanagement)`` يُرجع دائماً
مخطّطاً موحّداً: ``{yield_kg_ha, biomass, water_use, stages, provenance}`` — الغلّة والكتلة
بـكغ/هـ، و``water_use`` **بالملّيمتر في المحرّكين** (``CTRAT`` في PCSE بالسنتيمتر ويُحوَّل هنا).

- ``pcse`` تبعيّة ثقيلة اختياريّة. خلف ``SIM_PCSE_ENABLED`` يُشغَّل ``Wofost72_WLP_CWB`` حقيقيّاً
  **بلا شبكة**: معاملات المحصول من ``pcse_data/`` المحزوم، والبُنى من ``pcse_inputs`` (نقصٌ ⇒
  ``SimulationInputError`` ⇒ 422 باسمه). الراية مطفأة ⇒ بديل حتميّ (heuristic) موثّق يُرجع نفس
  المخطّط بـ ``provenance="deterministic_fallback"``. في وضع الإنتاج (`AGRIAI_PRODUCTION_MODE`)
  تصبح pcse مطلوبة: الغياب/النقص = فشل مُغلَق مُصنَّف
  (`agriai_production_simulation_unavailable`)، والبديل الحتميّ تطويريّ/اختباريّ فقط.

بديل الغلّة الحتميّ (قانون الحدّ الأدنى — Liebig): الغلّة = أدنى قيد بين
    (١) سقف حراريّ: max_yield * min(1, GDD/GDD_to_maturity)
    (٢) قيد مائيّ: (مطر + ريّ + ماء تربة متاح) * كفاءة استخدام الماء (WUE)
ثمّ الكتلة الحيويّة = الغلّة / معامل الحصاد، واستهلاك الماء = الغلّة / WUE.
رتابة مضمونة: مزيد من الماء أو حرارة أفضل ⇒ غلّة ≥ (حتّى بلوغ السقف الآخر).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import logging
import os
import sys
import types
from typing import Any

import pcse_inputs
import sim_crop_registry

SimulationInputError = pcse_inputs.SimulationInputError  # main.py يُحوّله إلى 422

logger = logging.getLogger("agriai-engine.wofost")

# ── pcse: وجودُها يُفحَص هنا، واستيرادُها مؤجَّل حتى تنخرط الراية ──
# مقيس (pcse 6.0.13): ``import pcse`` يستدعي ``logging.config.dictConfig`` بـ
# ``disable_existing_loggers=True`` فيُعطِّل ``uvicorn.error``/``uvicorn.access`` وكلّ مُسجِّل سبقه،
# ويستبدل معالجات الجذر بمعالجَي PCSE (شاشة ERROR + ملفّ INFO في ``~/.pcse/logs``)، ويبني
# ``~/.pcse/pcse.db`` (2,744,320 بايت) ويُلحِق ``~/.pcse`` بـ``sys.path``. استيرادُها عند تحميل
# الوحدة كان سيُصيب كلّ إقلاعٍ لـagriai بمجرّد تثبيتها — والراية مطفأة.
_PCSE_AVAILABLE = importlib.util.find_spec("pcse") is not None
_PCSE: types.SimpleNamespace | None = None
_PCSE_IMPORT_ERROR: str | None = None


def sim_pcse_enabled() -> bool:
    """الراية الحاكمة (SIM-PCSE-01، افتراضيّة-مطفأة): بلا الراية لا يُشغَّل PCSE أبداً."""
    return os.getenv("SIM_PCSE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def _crop_name(crop: dict[str, Any] | None) -> str:
    c = crop or {}
    return str(c.get("name") or c.get("crop") or c.get("crop_name") or "").strip().lower()


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
    """هل pcse مثبَّتة ولم يفشل استيرادها في هذه العمليّة؟ (تُبقي الاختبارات صريحة).

    الوجود يُقاس بـ``find_spec`` بلا استيراد (انظر أعلاه)؛ فشلُ أوّل استيراد فعليّ يُسقطها.
    """
    return _PCSE_AVAILABLE and _PCSE_IMPORT_ERROR is None


def sim_pcse_integration_verified() -> bool:
    """هل قرّر المالك أنّ المسار العلميّ (PCSE/WOFOST) مُثبَتٌ لبيئته؟ (افتراضيّاً مُطفأ).

    توفّر ``pcse`` شرط **لازم غير كافٍ**. البُناة (``pcse_inputs``) مكتملة ومُشهَّدة دون شبكة
    (``tests_v9/test_wofost_pcse_offline_integration.py``)، لكنّ المعاملات أوروبيّة المعايرة
    والمخرَج غير مُعايَر حتى SIM-GOLDEN-01 — فرفع هذه الراية قرار مالكٍ **بعد برهان حيّ في
    بيئته**، فلا يدّعي ``/readyz`` جاهزيّةً علميّةً على مجرّد توفّر المكتبة.
    """
    return os.getenv("SIM_PCSE_INTEGRATION_VERIFIED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def scientific_path_status() -> dict[str, Any]:
    """حالة صادقة للمسار العلميّ PCSE/WOFOST — بلا مبالغة.

    ``scientific_ready`` يتطلّب الثلاثة معاً: المكتبة متاحة **و** الراية مُفعَّلة **و** التكامل
    مُثبَت حيّاً. أيّ نقص ⇒ المحاكاة تلجأ للبديل الحتميّ الموثّق (``simulate`` لا ينهار).
    """
    importable = pcse_available()
    enabled = sim_pcse_enabled()
    verified = sim_pcse_integration_verified()
    return {
        "pcse_importable": importable,
        "pcse_enabled": enabled,
        "integration_verified": verified,
        "scientific_ready": bool(importable and enabled and verified),
        "pcse_import_error": _PCSE_IMPORT_ERROR,
        "note": (
            "pcse_importable = installed and not known to fail importing (the import itself is "
            "deferred until SIM_PCSE_ENABLED engages). The offline PCSE path is implemented but "
            "uncalibrated; set SIM_PCSE_INTEGRATION_VERIFIED=1 only after a live proof in this "
            "environment; otherwise the deterministic fallback is used."
        ),
    }


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

    # ``_pcse_run`` يوسم ``pcse_wofost_uncalibrated`` لا ``pcse_wofost``: المساواة الحرفيّة كانت
    # تُلصِق ``deterministic_fallback_model`` بمُخرَج PCSE حقيقيّ — وسمُ محرّكٍ كاذب في الموجِّهات.
    is_pcse = str(prov or "").startswith("pcse_wofost")
    u = 0.12 if is_pcse else 0.25
    drivers: list[str] = [] if is_pcse else ["deterministic_fallback_model"]

    w = weather if isinstance(weather, dict) else {}
    has_daily = isinstance(w.get("daily"), list) and bool(w.get("daily"))
    if w.get("gdd") is None and not has_daily:
        u += 0.08
        drivers.append("missing_daily_weather")
    # PCSE لا يبلغ هنا بلا ``rain_mm`` في كلّ يوم (``pcse_inputs`` يرفض اليوم الناقص)، فوسمُ
    # ``missing_rainfall`` لغياب المجموع الموسميّ كان موجِّهاً كاذباً على مُخرَجه.
    if not is_pcse and w.get("total_rain_mm") is None:
        u += 0.04
        drivers.append("missing_rainfall")
    if not (isinstance(soil, dict) and soil.get("available_water_mm") is not None):
        u += 0.05
        drivers.append("missing_soil_water")
    am = agromanagement if isinstance(agromanagement, dict) else {}
    # خطّة PCSE أحداثٌ مؤرَّخة (``irrigation_events``)؛ البديل يقرأ المجموع ``irrigation_mm`` وحده.
    if am.get("irrigation_mm") is None and not (is_pcse and am.get("irrigation_events")):
        u += 0.03
        drivers.append("missing_irrigation_plan")
    # تربةُ PCSE الافتراضيّة (EC3) ليست تربة الحقل: وزنُها وزنُ موجِّه التربة القائم أعلاه.
    if is_pcse and any(str(d).startswith("soil.") for d in diag.get("defaults_applied") or ()):
        u += 0.05
        drivers.append("default_soil_hydraulics")
    # ``{"name": "wheat"}`` ليس معاملات: البديل يقرأ مفاتيح ``_CROP_DEFAULTS`` وحدها، فمحصولٌ
    # مُسمّى بلا أيٍّ منها يُحسَب بالافتراضات نفسها ويجب أن يُسمّى كذلك (كان يُسقَط الموجِّه).
    # مسار PCSE يأخذ معاملاته من YAMLCropDataProvider بالاسم، فلا ينطبق عليه.
    if not is_pcse and not (isinstance(crop, dict) and any(k in crop for k in _CROP_DEFAULTS)):
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


def _restore_host_logging(
    root: logging.Logger,
    handlers: list[logging.Handler],
    level: int,
    disabled: dict[str, bool],
) -> None:
    """يُعيد ما غيّره ``dictConfig`` في pcse: معالجات الجذر ومستواه وتعطيل المُسجِّلات السابقة."""
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    for handler in handlers:
        if handler not in root.handlers:
            root.addHandler(handler)
    root.setLevel(level)
    for name, was_disabled in disabled.items():
        existing = logging.Logger.manager.loggerDict.get(name)
        if isinstance(existing, logging.Logger):
            existing.disabled = was_disabled


def _load_pcse() -> types.SimpleNamespace:  # pragma: no cover - يتطلّب pcse (اختبار التكامل)
    """يستورد pcse مرّةً في العمليّة **دون** أن يُعيد تهيئة سجلّات المُضيف أو ``sys.path``.

    يُعاد بعده: معالجات الجذر ومستواه، وعلم ``disabled`` لكلّ مُسجِّل سبق الاستيراد، و``sys.path``
    (``setup()`` في pcse يُلحِق ``~/.pcse`` ثمّ يستورد منه ``user_settings.py``). ما طبعته pcse
    على stdout (بناء قاعدة العرض) يُعاد عبر المُسجِّل كي لا يكسر سطرٌ خامّ سجلّاتِ JSON. ثرثرة
    INFO من مُسجِّلات ``pcse.*`` (بدء المحصول، الأحداث المؤقّتة) تُرفَع إلى WARNING.
    """
    global _PCSE, _PCSE_IMPORT_ERROR
    if _PCSE is not None:
        return _PCSE
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    saved_disabled = {
        name: lg.disabled
        for name, lg in logging.Logger.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    saved_path = list(sys.path)
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            import pcse  # type: ignore
            from pcse.base import (  # type: ignore
                MultiCropDataProvider,
                ParameterProvider,
                WeatherDataContainer,
                WeatherDataProvider,
            )
            from pcse.input import (  # type: ignore
                NASAPowerWeatherDataProvider,
                WOFOST72SiteDataProvider,
                YAMLCropDataProvider,
            )
            from pcse.models import Wofost72_WLP_CWB  # type: ignore
            from pcse.util import reference_ET, wind10to2  # type: ignore
    except Exception as exc:
        _PCSE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        _restore_host_logging(root, saved_handlers, saved_level, saved_disabled)
        sys.path[:] = saved_path
    logging.getLogger("pcse").setLevel(logging.WARNING)
    if captured.getvalue().strip():
        logger.info("pcse import output: %s", captured.getvalue().strip()[:300])

    class VendoredCropDataProvider(YAMLCropDataProvider):
        """``YAMLCropDataProvider`` على ``pcse_data/wofost72_crop`` — بلا شبكة وبلا pickle.

        بلا ``fpath`` يجلب المُنشئ الأصليّ ``crops.yaml`` من raw.githubusercontent.com وقت التشغيل
        (مقيس: ``PCSEError`` دون شبكة). ومع ``fpath`` **يكتب** ``YAMLCropDataProvider.pkl`` داخل
        الدليل المحزوم ثمّ يقرؤه بـ``pickle.load`` في الإقلاع التالي (مقيس: ملفّ جديد في الدليل)
        — كتابةٌ تفشل على صورة للقراءة فقط وتُلوِّث الشجرة. فيُتجاوَز المُنشئ إلى
        ``read_local_repository`` (قارئ PCSE نفسه + فحص النسخة)، ويُحلَّل الـYAML مرّةً في العمليّة
        (~٩٠ ms مقيسة) ويُتشارك قراءةً فقط: ``set_active_crop`` يقرأ ``_store`` ولا يكتبه.
        """

        _parsed_store: dict[str, Any] | None = None

        def __init__(self) -> None:
            MultiCropDataProvider.__init__(self)
            self.repository = os.path.abspath(pcse_inputs.CROP_DIR)
            if VendoredCropDataProvider._parsed_store is None:
                self.read_local_repository(pcse_inputs.CROP_DIR)
                VendoredCropDataProvider._parsed_store = self._store
            else:
                self._store = VendoredCropDataProvider._parsed_store

        def variety_metadata(self, crop_name: str, variety_name: str) -> dict[str, Any]:
            return dict(self._store[crop_name][variety_name].get("Metadata") or {})

    class RequestWeatherDataProvider(WeatherDataProvider):
        """موفِّر طقس **مملوء** من سلسلة الطلب (كان الباني يُعيد الصنف نفسه لا نسخة).

        E0/ES0/ET0 من ``reference_ET`` (Penman لـE0/ES0، Penman-Monteith لـET0) بوحدة mm/يوم ثمّ
        ÷10 إلى cm/يوم — نفس ما يفعله ``CSVWeatherDataProvider`` في PCSE. أنغستروم من الطلب، وإلّا
        ثابتا PCSE الاحتياطيّان في موفِّرَي NASA POWER وOpen-Meteo (0.29/0.49) — يُسمّى افتراضاً.
        """

        def __init__(self, wx: dict[str, Any]) -> None:
            WeatherDataProvider.__init__(self)
            site = wx["site"]
            self.latitude, self.longitude, self.elevation = site["LAT"], site["LON"], site["ELEV"]
            if wx["angstrom"]["from"] == "request":
                self.angstA, self.angstB = wx["angstrom"]["A"], wx["angstrom"]["B"]
            else:
                self.angstA = NASAPowerWeatherDataProvider.angstA
                self.angstB = NASAPowerWeatherDataProvider.angstB
            self.ETmodel = "PM"
            self.description = ["SAHOOL agriai /v1/simulate request weather (daily series)"]
            for rec in wx["days"]:
                wind = rec["WIND"] if rec["WIND_HEIGHT_M"] == 2 else wind10to2(rec["WIND"])
                e0, es0, et0 = reference_ET(
                    DAY=rec["DAY"],
                    LAT=self.latitude,
                    ELEV=self.elevation,
                    TMIN=rec["TMIN"],
                    TMAX=rec["TMAX"],
                    IRRAD=rec["IRRAD"],
                    VAP=rec["VAP"],
                    WIND=wind,
                    ANGSTA=self.angstA,
                    ANGSTB=self.angstB,
                    ETMODEL=self.ETmodel,
                )
                container = WeatherDataContainer(
                    LAT=self.latitude,
                    LON=self.longitude,
                    ELEV=self.elevation,
                    DAY=rec["DAY"],
                    IRRAD=rec["IRRAD"],
                    TMIN=rec["TMIN"],
                    TMAX=rec["TMAX"],
                    VAP=rec["VAP"],
                    RAIN=rec["RAIN"],
                    WIND=wind,
                    E0=e0 / 10.0,
                    ES0=es0 / 10.0,
                    ET0=et0 / 10.0,
                )
                self._store_WeatherDataContainer(container, rec["DAY"])

    _PCSE = types.SimpleNamespace(
        version=pcse.__version__,
        ParameterProvider=ParameterProvider,
        WOFOST72SiteDataProvider=WOFOST72SiteDataProvider,
        Wofost72_WLP_CWB=Wofost72_WLP_CWB,
        CropDataProvider=VendoredCropDataProvider,
        WeatherDataProvider=RequestWeatherDataProvider,
    )
    return _PCSE


# مراحل PCSE في مُخرَج الملخّص (تواريخ) ⇐ DVS: الإنبات 0 · الإزهار 1 · النضج 2.
_PCSE_STAGES = (
    ("sowing", "DOS", None),
    ("emergence", "DOE", 0.0),
    ("anthesis", "DOA", 1.0),
    ("maturity", "DOM", 2.0),
)
_PCSE_SITE_DEFAULTS = ("IFUNRN", "NOTINF", "SSI", "SSMAX")
# مجاميع توازن الماء (``TERMINAL_OUTPUT_VARS`` في Wofost72_WLP_CWB.conf) — كلّها سنتيمتر.
_WATER_BALANCE_CM = {
    "rain": "RAINT",
    "irrigation_effective": "TOTIRR",
    "infiltration": "TOTINF",
    "surface_runoff": "TSR",
    "percolation_root_zone": "PERCT",
    "loss_below_root_zone": "LOSST",
    "soil_evaporation": "EVST",
    "transpiration": "WTRAT",
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _pcse_stages(summary: dict[str, Any], plan: pcse_inputs.PcseRunInputs) -> list[dict[str, Any]]:
    """مراحلٌ من تواريخ PCSE الفعليّة — كان الباني يُعلن ``maturity: reached`` دون فحص."""
    wanted = [
        s
        for s in _PCSE_STAGES
        if not (s[0] == "sowing" and plan.season["crop_start_type"] == "emergence")
    ]
    if plan.season["crop_end_type"] == "earliest":
        wanted.append(("harvest", "DOH", None))
    return [
        {
            "stage": name,
            "reached": summary.get(key) is not None,
            "date": _iso(summary.get(key)),
            "at_dvs": dvs,
        }
        for name, key, dvs in wanted
    ]


def _pcse_run(  # غراؤه مغطّى بلا pcse (مساحة أسماء مزيّفة)؛ التشغيل الحقيقيّ: اختبار التكامل
    pcse_ns: types.SimpleNamespace, plan: pcse_inputs.PcseRunInputs
) -> dict[str, Any]:
    """تشغيل ``Wofost72_WLP_CWB`` (الاسم الإرثيّ ``Wofost72_WLP_FD``) موصَّلاً ببنى PCSE الفعليّة.

    مقيس قبل هذا الإصلاح (2026-09-29، pcse 6.0.13): ``YAMLCropDataProvider()`` بلا ``fpath`` يجلب
    المعاملات من GitHub وقت التشغيل (``PCSEError`` دون شبكة)، ومع الشبكة يسقط ``AgroManager`` على
    dict خامّ، والطقس صنفٌ لا نسخة، و``sitedata={}``، و``CTRAT`` بالسنتيمتر يُعاد كأنّه ملّيمتر.
    الآن: معاملاتٌ محزومة · حملةٌ بشكل AgroManager · موفِّرٌ مملوء · موقعٌ بـ``WOFOST72SiteDataProvider``
    · تربةٌ مُسمّاة المصدر · والماء بالملّيمتر. المخرَج ``pcse_wofost_uncalibrated`` حتى SIM-GOLDEN.
    """
    crop = plan.crop
    cropdata = pcse_ns.CropDataProvider()
    cropdata.set_active_crop(crop.pcse_crop, crop.pcse_variety)  # يفشل مبكراً إن غاب الصنف
    variety_meta = cropdata.variety_metadata(crop.pcse_crop, crop.pcse_variety)
    sitedata = pcse_ns.WOFOST72SiteDataProvider(WAV=plan.site["WAV"], SMLIM=plan.site["SMLIM"])
    parameters = pcse_ns.ParameterProvider(
        cropdata=cropdata, soildata=dict(plan.soil["params"]), sitedata=sitedata
    )
    weather = pcse_ns.WeatherDataProvider(plan.weather)
    model = pcse_ns.Wofost72_WLP_CWB(parameters, weather, plan.agromanagement)
    model.run_till_terminate()
    summaries = model.get_summary_output()
    if len(summaries) != 1:
        raise RuntimeError(f"pcse_expected_one_crop_cycle:{len(summaries)}")
    summary = summaries[0]
    terminal = model.get_terminal_output() or {}  # dict (pcse/engine.py) لا قائمة كالملخّص

    matured = summary.get("DOM") is not None
    if matured:
        cycle_end = "maturity"
    elif summary.get("DOH") is not None:
        cycle_end = "harvest_date"
    else:
        cycle_end = plan.season["end_limit_from"]  # weather_series_end | max_duration_days
    twso, tagp = _num(summary.get("TWSO")), _num(summary.get("TAGP"))
    ctrat_cm, cevst_cm = _num(summary.get("CTRAT")), _num(summary.get("CEVST"))
    coverage = variety_meta.get("Coverage") or {}
    return {
        "yield_kg_ha": round(twso, _ROUND),
        "biomass": round(tagp, _ROUND),
        "water_use": round(ctrat_cm * 10.0, _ROUND),  # CTRAT cm ⇒ mm (عقد المخطّط)
        "stages": _pcse_stages(summary, plan),
        "provenance": "pcse_wofost_uncalibrated",
        "state": {
            "TWSO": twso,
            "TAGP": tagp,
            "DVS": _num(summary.get("DVS")),
            "LAIMAX": _num(summary.get("LAIMAX")),
            "CTRAT_cm": ctrat_cm,
            "CEVST_cm": cevst_cm,
            "RD_cm": _num(summary.get("RD")),
        },
        "diagnostics": {
            "engine": f"pcse {pcse_ns.version} Wofost72_WLP_CWB (WOFOST 7.2, water-limited, free drainage)",
            "crop": crop.name,
            "pcse_variety": crop.pcse_variety,
            "parameter_source": crop.parameter_source,
            "parameter_version": crop.parameter_version,
            "variety_calibration_region": coverage.get("Region"),
            "calibrated_for_this_field": False,
            "units": {
                "yield_kg_ha": "kg/ha storage-organ dry matter (TWSO)",
                "biomass": "kg/ha total above-ground dry matter (TAGP)",
                "water_use": "mm crop transpiration over the crop cycle (CTRAT x 10)",
            },
            "soil_evaporation_mm": round(cevst_cm * 10.0, _ROUND),
            "water_balance_mm": {
                name: round(_num(terminal.get(var)) * 10.0, _ROUND)
                for name, var in _WATER_BALANCE_CM.items()
                if terminal.get(var) is not None
            },
            "crop_cycle_end": cycle_end,
            "matured": matured,
            "defaults_applied": list(plan.defaults_applied),
            "inputs": plan.provenance(),
            "pcse_site_defaults": {k: sitedata[k] for k in _PCSE_SITE_DEFAULTS},
            "reference_et": "pcse.util.reference_ET (E0/ES0 Penman, ET0 Penman-Monteith)",
            "angstrom": {"A": weather.angstA, "B": weather.angstB},
            "co2_response": "none: WOFOST 7.2 assimilation has no CO2 term and no CO2 value is set",
        },
    }


def simulate(
    crop: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
    soil: dict[str, Any] | None = None,
    agromanagement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """يُحاكي المحصول ويُرجع المخطّط الموحّد، أو يفشل فشلاً مُغلَقاً **مُسمّى**.

    الراية مشعلة: محصول خارج السجلّ / pcse غائبة أو فشل استيرادها / فشل المحرّك ⇒ RuntimeError
    (503 في main)؛ مدخلٌ ناقص ⇒ ``SimulationInputError`` (422). لا استبدال صامت بالبديل.
    الراية مطفأة: إنتاج ⇒ فشل مُغلَق؛ تطوير ⇒ البديل الحتميّ الموثّق.
    """
    crop = crop or {}
    weather = weather or {}
    soil = soil or {}
    agromanagement = agromanagement or {}

    production_mode = os.getenv("AGRIAI_PRODUCTION_MODE", "0").lower() in {"1", "true", "yes", "on"}

    # ── SIM-PCSE-01: الراية الحاكمة (default-off) هي بوّابة PCSE الوحيدة ──
    if sim_pcse_enabled():
        # المحرّك العلميّ مُنخرِط: المحصول المدعوم بالاسم **بوّابة صلبة** (لا معاملات مقترَضة) —
        # محصول خارج السجلّ ⇒ fail-closed دائماً (لا افتراض صامت، شرط المالك).
        sim_crop = sim_crop_registry.get(_crop_name(crop))
        if sim_crop is None:
            raise RuntimeError("sim_pcse_unsupported_crop:" + _crop_name(crop))
        # المحرّك قبل المدخلات: غيابُه يحكم الجواب (503) أيّاً كانت المدخلات.
        if not pcse_available():
            raise RuntimeError("simulation_unavailable:pcse_unavailable")
        try:
            pcse_ns = _load_pcse()
        except Exception as exc:  # noqa: BLE001 - مثبَّتة لكن لا تُستورَد ⇒ غير متاحة، باسمها
            raise RuntimeError("simulation_unavailable:pcse_import_failed") from exc
        # SimulationInputError يعبر كما هو (422): نقصُ المُنادي ليس عطلَ المحرّك.
        plan = pcse_inputs.build_run_inputs(sim_crop, weather, soil, agromanagement)
        try:
            result = _pcse_run(pcse_ns, plan)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("pcse_simulation_failed") from exc
    else:
        # الراية مطفأة ⇒ **السلوك الصادق القائم يبقى**: إنتاج بلا محرّك ⇒ fail-closed؛ تطوير ⇒ بديل حتميّ.
        if production_mode:
            raise RuntimeError("agriai_production_simulation_unavailable:sim_pcse_disabled")
        result = _fallback_simulate(crop, weather, soil, agromanagement)

    # «لا غلّة بلا عدم يقين»: كلّ مخرَج simulate يحمل نطاقاً نموذجيّاً (نقطة مصحوبة بحدود).
    result["yield_interval"] = _yield_uncertainty(result, crop, weather, soil, agromanagement)
    return result
