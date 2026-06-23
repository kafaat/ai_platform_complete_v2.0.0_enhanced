"""
api/field_state_projection.py — إسقاط الحالة القانونيّة الموحّدة (Phase 2)

يرفع بوّابة القراءة (field_state_gateway) إلى **read model مُخزَّن** (جدول
field_state، هجرة v53): يُعيد الحساب من المصادر القانونيّة ثمّ يحفظ النتيجة
(UPSERT) كي يقرأها كلّ المستهلكين (التوصيات/التنبيهات/guardrails) بسرعة وبتدقيق.

ما يفعله (وما لا يفعله — صدق):
  ✓ يجمع المدخلات من قاعدة المنصّة (نفس مصادر البوّابة) ضمن tenant_connection (RLS).
  ✓ يركّب الحالة عبر resolve_field_state (لا يكرّر التركيب).
  ✓ يحفظ الإسقاط (UPSERT) ويُرجِع changed=هل تبدّلت الصلاحيّة/نمط التنفيذ — كي
    يقرّر المتّصِل إصدار حدث field.state_changed (لا حدث على كلّ قراءة).
  ✗ لا منطق أحداث هنا (لتفادي دورة استيراد مع main) — الإصدار في المتّصِل.
  ✗ لا يختلق مدخلات: غياب المصدر ⇒ None ⇒ resolve_field_state يعلن INSUFFICIENT.

يُستدعى دائماً ضمن tenant_connection (app.current_tenant مضبوط) — UPSERT يمرّ
سياسة عزل المستأجِر (tenant_id = المستأجِر الحاليّ).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

from .boundary_confidence import CONFIDENCE_REVIEW_THRESHOLD
from .canonical_boundary import canonical_boundary
from .canonical_water import canonical_water
from .canonical_water_stress import canonical_water_stress
from .feature_registry import is_enabled
from .field_operational_state import resolve_field_state
from .field_state_gateway import build_state_inputs

# علم تصعيد الإجهاد المائيّ (D2b) — default OFF (قرار المستخدم 2026-06-23): مراقبة
# ميدانيّة قبل تغيير القرار الإنتاجيّ. ليس علم راوتر ⇒ لا يُسجَّل في feature_registry.
_WATER_STRESS_ESCALATION_FLAG = "FEATURE_WATER_STRESS_ESCALATION"

# علم ETc-dual في الحالة الكنسيّة — default OFF (إطار implemented-but-off-by-default):
# عند التفعيل تُحسب ETc بالنهج المزدوج (Kcb·Ks+Ke)·ET0 بدل single (Kc·ET0). ليس علم راوتر.
_CANONICAL_ETC_DUAL_FLAG = "FEATURE_CANONICAL_ETC_DUAL"

# علم عتبات NDVI (C5) — default OFF: NDVI معلوماتيّ لا يحكم الصلاحيّة ما لم تُفعَّل عتبات
# **معايَرة ميدانيّاً** (غير موجودة بعد). OFF ⇒ تُعلَن insufficient_field_calibration صراحةً.
_APPLY_NDVI_THRESHOLDS_FLAG = "APPLY_NDVI_THRESHOLDS"

logger = logging.getLogger("sahool.field_state")


def _derive_alerts_from_state(state: dict) -> list[dict]:
    """يشتقّ تنبيهات صادقة (للعرض فقط) من dict الحالة القانونيّة الموحّدة.

    دالّة نقيّة بلا I/O (قابلة للاختبار بلا قاعدة): تقرأ الحقائق الزراعيّة من
    agronomic.operational_truths + نمط التنفيذ، فتشتقّ تنبيهات بسيطة لا تُلفِّق:
      • salinity_class == "critical" ⇒ تنبيه critical «ملوحة تربة حرجة».
      • execution_mode في (blocked, human_review) ⇒ تنبيه warning «القرار يحتاج مراجعة».
    صدق: غياب الحقائق ⇒ قائمة فارغة (لا تنبيه مُلفَّق). لا تُكتب في جدول alerts.
    كلّ تنبيه يحمل source="canonical_field_state" (مصدر الاشتقاق صريح للتدقيق).
    """
    if not isinstance(state, dict):
        return []
    alerts: list[dict] = []
    # تحصين: أيّ مستوى متداخل غير قاموس (list/str) لا يكسر الاشتقاق (fail-safe).
    _agro = state.get("agronomic")
    truths = _agro.get("operational_truths") if isinstance(_agro, dict) else None
    if not isinstance(truths, dict):
        truths = {}

    if truths.get("salinity_class") == "critical":
        alerts.append(
            {
                "alert_type": "salinity_critical",
                "severity": "critical",
                "title_ar": "ملوحة تربة حرجة",
                "message_ar": (
                    "الحالة القانونيّة الموحّدة تُظهر ملوحة تربة حرجة — غسيل وتحسين "
                    "الصرف عاجلاً، وتجنّب الريّ المالح."
                ),
                "source": "canonical_field_state",
            }
        )

    if state.get("execution_mode") in ("blocked", "human_review"):
        alerts.append(
            {
                "alert_type": "human_review_required",
                "severity": "warning",
                "title_ar": "القرار يحتاج مراجعة بشريّة",
                "message_ar": (
                    "نمط تنفيذ الحالة القانونيّة الموحّدة ليس تلقائيّاً — يلزم تأكيد "
                    "المهندس/المزارع قبل التنفيذ."
                ),
                "source": "canonical_field_state",
            }
        )

    return alerts


async def gather_field_freshness(conn, field_id: str) -> dict:
    """يقرأ مصادر النضارة القانونيّة للحقل من قاعدة المنصّة.

    يُرجِع {last_image_date, latest_soil_sampled_on, weather_age_hours, ndvi_mean,
    ndvi_date} — أيّ مصدر غائب يكون None (يدع resolve_field_state يعلن «بيانات
    ناقصة» بصدق، وتُعلَن قيمة NDVI غير متاحة بدل رقم مُلفَّق).
    """
    # نضارة الصورة (عمود قديم دائم الوجود) — استعلام أساسيّ لا يفشل.
    last_image_date = await conn.fetchval(
        "SELECT last_image_date FROM imagery_automation_fields WHERE field_id = $1",
        field_id,
    )
    # Stage D: قيمة NDVI الحقيقيّة (أعمدة v54) — داخل SAVEPOINT كي لا يكسر فشلُها
    # (UndefinedColumn قبل تطبيق v54 في نشر متدرّج) المعاملةَ الخارجيّة ⇒ تراجع رشيق
    # إلى لا-قيمة (fail-safe، صدق: NULL لا رقم مُلفَّق).
    ndvi_mean = None
    ndvi_date = None
    try:
        async with conn.transaction():  # SAVEPOINT
            row = await conn.fetchrow(
                "SELECT last_ndvi_mean, last_ndvi_date "
                "FROM imagery_automation_fields WHERE field_id = $1",
                field_id,
            )
            if row:
                ndvi_mean = row["last_ndvi_mean"]
                ndvi_date = row["last_ndvi_date"]
    except Exception:  # noqa: BLE001 — v54 غير مطبّقة بعد ⇒ تخطٍّ آمن
        ndvi_mean = None
        ndvi_date = None
    # D2b: NDMI/MSI (أعمدة v99) — SAVEPOINT منفصل عن NDVI كي لا يُسقِط فشلُ v99 (نشر
    # متدرّج) قيمةَ NDVI أيضاً. تراجع رشيق إلى None (صدق: NULL لا رقم مُلفَّق).
    ndmi_mean = None
    msi_mean = None
    try:
        async with conn.transaction():  # SAVEPOINT
            srow = await conn.fetchrow(
                "SELECT last_ndmi_mean, last_msi_mean "
                "FROM imagery_automation_fields WHERE field_id = $1",
                field_id,
            )
            if srow:
                ndmi_mean = srow["last_ndmi_mean"]
                msi_mean = srow["last_msi_mean"]
    except Exception:  # noqa: BLE001 — v99 غير مطبّقة بعد ⇒ تخطٍّ آمن
        ndmi_mean = None
        msi_mean = None
    # آخر فحص تربة معتمَد/منشور — صفّ واحد يعطي النضارة (sampled_on) + EC (من result)،
    # فنتفادى استعلامين ونربط EC بأحدث عيّنة فعلاً (مراجعة Copilot).
    soil_row = await conn.fetchrow(
        "SELECT sampled_on, result FROM soil_lab_tests "
        "WHERE field_id = $1 AND status IN ('approved', 'published') AND sampled_on IS NOT NULL "
        "ORDER BY sampled_on DESC LIMIT 1",
        field_id,
    )
    soil_sampled_on = soil_row["sampled_on"] if soil_row else None
    soil_ec = _extract_ec(soil_row["result"]) if soil_row else None
    weather_age_hours = await conn.fetchval(
        "SELECT EXTRACT(EPOCH FROM (NOW() - c.fetched_at)) / 3600.0 "
        "FROM weather_automation_cache c "
        "JOIN weather_automation_locations l ON l.location_key = c.location_key "
        "WHERE l.field_id = $1 ORDER BY c.fetched_at DESC LIMIT 1",
        field_id,
    )
    return {
        "last_image_date": last_image_date,
        "latest_soil_sampled_on": soil_sampled_on,
        "weather_age_hours": float(weather_age_hours) if weather_age_hours is not None else None,
        "ndvi_mean": float(ndvi_mean) if ndvi_mean is not None else None,
        "ndvi_date": ndvi_date,
        "ndmi_mean": float(ndmi_mean) if ndmi_mean is not None else None,
        "msi_mean": float(msi_mean) if msi_mean is not None else None,
        "soil_ec": soil_ec,
    }


def _extract_ec(soil_result) -> float | None:
    """يستخرج التوصيل الكهربائيّ (EC، dS/m) من نتيجة فحص التربة (JSONB) — قرينة
    الملوحة للنواة الزراعيّة. يتسامح مع أسماء المفاتيح الشائعة. None إن غاب."""
    if not soil_result:
        return None
    if isinstance(soil_result, str):
        try:
            soil_result = json.loads(soil_result)
        except (ValueError, TypeError):
            return None
    if not isinstance(soil_result, dict):
        return None
    for k in ("ec", "ec_ds_m", "ece", "salinity_ec", "ec_dsm"):
        v = soil_result.get(k)
        if isinstance(v, int | float):
            return float(v)
    return None


def _et0_from_weather_payload(data_json, lat, elevation_m, doy: int) -> float | None:
    """يحسب ET0 (مم/يوم) من حمولة طقس Open-Meteo المخزَّنة عبر **المحرّك الموحّد** (H4).

    يستخرج temp_min/max لليوم من ``data_json["daily"]`` ويبني ``WeatherInput`` ثمّ
    ``compute_et0`` (Penman-Monteith إن توفّر إشعاع/رطوبة/رياح، وإلّا Hargreaves — حرارة
    فقط). **صدق + fail-safe صارم:** أيّ نقص/شكل غير متوقَّع/تعذّر ⇒ ``None`` (لا اختلاق،
    لا كسر الإسقاط) — فالحقل ``etc_mm`` ببساطة يغيب. لا صيغة ET0 جديدة (إعادة استخدام H4).
    """
    try:
        from api.water_balance import WeatherInput, compute_et0

        if isinstance(data_json, str):
            data_json = json.loads(data_json)
        daily = (data_json or {}).get("daily") or {}

        def _first(seq):
            return seq[0] if isinstance(seq, list) and seq else None

        tmax = _first(daily.get("temperature_2m_max"))
        tmin = _first(daily.get("temperature_2m_min"))
        if tmax is None or tmin is None:
            return None
        # اختياريّ لـPenman-Monteith (وإلّا يتدرّج compute_et0 إلى Hargreaves):
        rh = _first(daily.get("relative_humidity_2m_mean"))
        wind = _first(daily.get("wind_speed_10m_max"))
        srad = _first(daily.get("shortwave_radiation_sum"))
        w = WeatherInput(
            t_min_c=float(tmin),
            t_max_c=float(tmax),
            solar_rad_mj_m2=float(srad) if srad is not None else None,
            rh_mean_pct=float(rh) if rh is not None else None,
            wind_2m_ms=float(wind) if wind is not None else None,
            latitude_deg=float(lat) if lat is not None else 15.5,
            elevation_m=float(elevation_m) if elevation_m is not None else 2000.0,
            day_of_year=doy,
        )
        et0, _method = compute_et0(w)
        return round(float(et0), 2)
    except Exception:  # noqa: BLE001 — صدق/fail-safe: تعذّر ⇒ None (لا ET0 مُلفَّق)
        return None


def _demand_class(etc_mm: float) -> str:
    """تصنيف طلب ETc — يطابق عتبات النواة (agronomic_state_engine: >8 high / >4 medium)."""
    return "high" if etc_mm > 8.0 else "medium" if etc_mm > 4.0 else "low"


def _weatherday_from_payload(data_json, lat, doy: int):
    """يبني ``WeatherDay`` (core.engines.fao56) من حمولة الطقس المخزَّنة — **نفس مصدر**
    ``_et0_from_weather_payload`` (لا صيغة جديدة). يتطلّب tmin/tmax + rh + wind (لازمة لـKe
    عبر Kc_max)؛ srad غير لازم هنا (ET0 يُمرَّر عبر et0_override فلا يُحسب penman داخليّاً).

    صدق/fail-safe: نقص أيّ من tmin/tmax/rh/wind ⇒ ``None`` (لا تلفيق) ⇒ تراجع إلى single.
    """
    try:
        from core.engines.fao56 import WeatherDay

        if isinstance(data_json, str):
            data_json = json.loads(data_json)
        daily = (data_json or {}).get("daily") or {}

        def _first(seq):
            return seq[0] if isinstance(seq, list) and seq else None

        tmax = _first(daily.get("temperature_2m_max"))
        tmin = _first(daily.get("temperature_2m_min"))
        rh = _first(daily.get("relative_humidity_2m_mean"))
        wind = _first(daily.get("wind_speed_10m_max"))
        if tmax is None or tmin is None or rh is None or wind is None:
            return None  # طقس ناقص لـKe ⇒ تراجع إلى single (صدق)
        srad = _first(daily.get("shortwave_radiation_sum"))
        return WeatherDay(
            temp_max_c=float(tmax),
            temp_min_c=float(tmin),
            humidity_pct=float(rh),
            wind_speed_m_s=float(wind),
            solar_radiation_mj_m2=float(srad) if srad is not None else 0.0,
            latitude_deg=float(lat) if lat is not None else 15.5,
            elevation_m=2000.0,
            day_of_year=doy,
        )
    except Exception:  # noqa: BLE001 — fail-safe: تعذّر ⇒ None
        return None


def _apply_canonical_etc_dual(
    water: dict, crop_id, days_after_planting, et0_mm, weather_payload, lat, ndvi_mean
) -> None:
    """إغلاق ETc-dual في كتلة `water` خلف feature flag (default off) — يُعدّل `water` مكانيّاً.

    العلم OFF (افتراضيّ) ⇒ `etc_source="single_kc"` بلا تغيير (سلوك محفوظ). العلم ON +
    مدخلات كافية ⇒ ETc بالنهج المزدوج `(Kcb·Ks+Ke)·ET0` بنفس ET0 الكنسيّ (et0_override)،
    والملوحة **غير مطبّقة** (soil_ece=None، قرار H5)، وde_mm=0 معلَن كافتراض. مدخلات ناقصة
    ⇒ تراجع إلى single + `etc_disabled_reason="dual_inputs_unavailable"` (declare reason).
    best-effort: أيّ تعذّر ⇒ يبقى single (لا يكسر الحالة).
    """
    if not is_enabled(_CANONICAL_ETC_DUAL_FLAG, os.getenv(_CANONICAL_ETC_DUAL_FLAG)):
        water["etc_source"] = "single_kc"
        return
    # العلم ON: حاول النهج المزدوج إن توفّر الأساس (محصول/عمر/ET0/طقس).
    if crop_id is None or days_after_planting is None or et0_mm is None:
        water.update(etc_source="single_kc", etc_disabled_reason="dual_inputs_unavailable")
        return
    try:
        from core.engines.fao56 import compute_etc_dual
        from core.season_phenology import crop_kc_profile

        wd = _weatherday_from_payload(weather_payload, lat, date.today().timetuple().tm_yday)
        profile = crop_kc_profile(crop_id)
        if wd is None or profile is None:
            water.update(etc_source="single_kc", etc_disabled_reason="dual_inputs_unavailable")
            return
        r = compute_etc_dual(
            wd,
            profile,
            days_after_planting,
            soil_ece=None,  # الملوحة غير مطبّقة افتراضيّاً (قرار H5) — لا تُدخَل ضمنيّاً
            ndvi=ndvi_mean,
            de_mm=0.0,
            et0_override=et0_mm,
        )
        dual_assumptions = [
            *r.assumptions,
            "salinity_disabled_by_default",
            "surface_depletion_untracked_assumed_zero",
        ]
        water["etc_mm"] = r.etc_dual_mm
        water["etc_demand_class"] = _demand_class(r.etc_dual_mm)
        water.update(
            etc_source="dual_kc",
            etc_single_mm=r.etc_single_mm,
            etc_dual_mm=r.etc_dual_mm,
            kcb=r.kcb,
            ke=r.ke,
            dual_assumptions=dual_assumptions,
        )
    except Exception:  # noqa: BLE001 — best-effort: يبقى single عند أيّ تعذّر
        water.setdefault("etc_source", "single_kc")
        water.setdefault("etc_disabled_reason", "dual_inputs_unavailable")


def _ndvi_thresholds_for(crop_id, days_after_planting):
    """عتبات NDVI لمرحلة المحصول من **مظروف بطاقة المحصول** (إن وُجد) — ``None`` إن غير معايَر.

    صدق صريح: **لا عتبات NDVI معايَرة ميدانيّاً في النظام بعد** (لا بطاقة محصول تحمل قسم
    ``ndvi_thresholds``)، فهذا يُرجِع ``None`` دائماً حاليّاً — لا نختلق عتبات. مهيّأ للمستقبل:
    حين تُضاف عتبات معايَرة إلى البطاقة تُقرأ من هنا (threshold_source="crop_card").
    """
    if not crop_id:
        return None
    try:
        from core.crop_cards.loader import load_crop_card

        card = load_crop_card(crop_id)
        env = card.get("ndvi_thresholds") if isinstance(card, dict) else None
        return env or None
    except Exception:  # noqa: BLE001 — fail-safe: تعذّر تحميل البطاقة ⇒ None (لا اختلاق)
        return None


def _apply_ndvi_threshold_gating(state: dict, crop_id, days_after_planting) -> None:
    """C5: بوّابة عتبات NDVI خلف feature flag (default off) — يُعدّل ``remote_sensing`` مكانيّاً.

    يُعلن **صراحةً** سياسة عتبات NDVI بدل الإبهام (الفجوة C5: «NDVI معلوماتيّ لا يحكم
    الصلاحيّة»). OFF (افتراضيّ) أو غياب معايرة ⇒ ``calibration_status="insufficient_field_
    calibration"`` و``thresholds_applied=False`` (NDVI يبقى معلوماتيّاً). ON + بطاقة تحمل عتبات
    معايَرة ⇒ ``threshold_source="crop_card"`` و``thresholds_applied=True``. **لا يغيّر
    validity/execution_mode** ولا يختلق عتبات (صدق).
    """
    rs = state.get("remote_sensing")
    if not isinstance(rs, dict) or not rs.get("available"):
        return  # لا NDVI متاح ⇒ العتبات بلا معنى (نُبقي كتلة «غير متاح» الصادقة كما هي)
    enabled = is_enabled(_APPLY_NDVI_THRESHOLDS_FLAG, os.getenv(_APPLY_NDVI_THRESHOLDS_FLAG))
    thresholds = _ndvi_thresholds_for(crop_id, days_after_planting) if enabled else None
    applied = thresholds is not None
    rs["ndvi_thresholds_enabled"] = enabled
    rs["threshold_source"] = "crop_card" if applied else None
    rs["thresholds_applied"] = applied
    # صدق: العتبات غير المعايَرة (off أو لا بطاقة) ⇒ إعلان السبب صراحةً.
    rs["calibration_status"] = "calibrated" if applied else "insufficient_field_calibration"


def _compose_agronomic(
    field_id: str,
    tenant_id,
    ndvi_mean,
    soil_ec,
    crop_id: str | None = None,
    days_after_planting: int | None = None,
    et0_mm: float | None = None,
) -> dict | None:
    """يستدعي النواة الزراعيّة الغنيّة compose_field_state (دالّة نقيّة بلا شبكة)
    لدمج الحقائق الزراعيّة + التحكيم (Salinity>Vigor) في الحالة القانونيّة.

    Bundle D (D1): يمرّر سياق المحصول (``crop_id``/``days_after_planting``) فتُحسَب Kc،
    وإشارة ``et0`` فيُحقَن ETc الكنسيّ (Kc·ET0) في operational_truths — إضافة صرفة لا تمسّ
    التحكيم. صدق + fail-safe: لا إشارات ⇒ None؛ وأيّ تعذّر استيراد/حساب ⇒ None دون كسر
    recompute (الحالة التشغيليّة تبقى من resolve_field_state).
    """
    try:
        from core.agronomic_state_engine import (
            CropContext,
            SignalInput,
            compose_field_state,
        )

        signals = []
        if ndvi_mean is not None:
            signals.append(SignalInput(source="ndvi", value=float(ndvi_mean)))
        if soil_ec is not None:
            signals.append(SignalInput(source="soil_ec", value=float(soil_ec)))
        if not signals:
            return None
        # ET0 يُمرَّر عبر CropContext (مع المحصول/العمر) فتُحسَب Kc ويُحقَن ETc = Kc·ET0.
        crop_context = None
        if crop_id is not None and days_after_planting is not None:
            crop_context = CropContext(
                crop_id=crop_id,
                days_after_planting=days_after_planting,
                et0_mm=float(et0_mm) if et0_mm is not None else None,
            )
        cs = compose_field_state(
            field_id,
            signals,
            crop_context=crop_context,
            tenant_id=str(tenant_id) if tenant_id else None,
        )
        return {
            "operational_truths": dict(cs.operational_truths),
            "confidence": cs.confidence,
            "confidence_reason": cs.confidence_reason,
            "contradictions": list(cs.contradictions),
            "provenance": list(cs.provenance),
        }
    except Exception:  # noqa: BLE001 — توحيد best-effort، لا يكسر الحالة التشغيليّة
        # هذا المسار يُفعّل تصعيد السلامة (Salinity>Vigor) — الفشل الصامت يعطّل
        # التحكيم. نُسجّل الأثر (مع إبقاء fail-safe) ليُكشَف تشخيصيّاً (مراجعة Copilot).
        logger.warning("compose_field_state تعذّر للحقل %s — تخطّي التحكيم", field_id, exc_info=True)
        return None


async def recompute_field_state(conn, field_id: str) -> dict:
    """يعيد حساب الحالة القانونيّة للحقل ويحفظها في إسقاط field_state (UPSERT).

    يُرجِع {"state": <dict>, "changed": <bool>} حيث changed = تبدّلت الصلاحيّة أو
    نمط التنفيذ عن المحفوظ سابقاً (أو لا صفّ سابق). يُستدعى ضمن tenant_connection.
    صدق: غياب tenant_id للحقل (غير موجود) ⇒ لا حفظ، تُعاد الحالة المحسوبة فقط.
    """
    fresh = await gather_field_freshness(conn, field_id)
    inputs = build_state_inputs(
        last_image_date=fresh["last_image_date"],
        latest_soil_sampled_on=fresh["latest_soil_sampled_on"],
        weather_age_hours=fresh["weather_age_hours"],
        today=date.today(),
    )
    state = resolve_field_state(field_id, **inputs).to_dict()
    state["inputs"] = inputs  # شفافيّة التدقيق: المصادر التي دخلت القرار
    # Stage D: قيمة NDVI الحقيقيّة (من Sentinel عبر raster، مزوّدون مجّانيّون) —
    # معلوماتيّة لا تُغيّر صلاحيّة القرار (تغيير عتبات أغرونوميّة يحتاج تحقّقاً
    # ميدانيّاً). صدق: لا قيمة محسوبة ⇒ available=false لا رقم مُلفَّق.
    _ndvi = fresh.get("ndvi_mean")
    state["remote_sensing"] = {
        "available": _ndvi is not None,
        "ndvi_mean": _ndvi,
        "ndvi_date": fresh["ndvi_date"].isoformat() if fresh.get("ndvi_date") else None,
        "source": "sentinel-2 (raster-service)" if _ndvi is not None else None,
    }

    tenant_id = await conn.fetchval("SELECT tenant_id FROM fields WHERE field_id = $1", field_id)
    if tenant_id is None:
        # الحقل غير موجود ضمن المستأجِر — لا نحفظ إسقاطاً يتيماً (الحالة تُعاد فقط).
        return {"state": state, "changed": False}

    # Bundle D (D1): مصدر ET0 الكنسيّ + سياق المحصول (Kc/العمر) لحقن ETc في الحالة القانونيّة.
    # **إضافيّ best-effort:** أيّ نقص (محصول/تاريخ زراعة/طقس) ⇒ القيمة None (الحقل يغيب، لا اختلاق)
    # ولا يكسر التحكيم القائم (الملوحة/الصلاحيّة تبقى تُحسَب كما كانت).
    crop_id = None
    days_after_planting = None
    et0_mm = None
    weather_payload = None  # حمولة الطقس الخام (تُعاد للنهج المزدوج لبناء WeatherDay)
    field_lat = None
    try:
        from core.season_phenology import resolve_crop_id

        fmeta = await conn.fetchrow(
            "SELECT crop, planting_date, lat FROM fields WHERE field_id = $1", field_id
        )
        if fmeta is not None:
            crop_id = resolve_crop_id(fmeta["crop"])
            field_lat = fmeta["lat"]
            planting = fmeta["planting_date"]
            if planting is not None:
                dap = (date.today() - planting).days
                days_after_planting = dap if dap >= 0 else None
            wrow = await conn.fetchrow(
                "SELECT c.data_json FROM weather_automation_cache c "
                "JOIN weather_automation_locations l ON l.location_key = c.location_key "
                "WHERE l.field_id = $1 ORDER BY c.fetched_at DESC LIMIT 1",
                field_id,
            )
            if wrow is not None:
                weather_payload = wrow["data_json"]
                et0_mm = _et0_from_weather_payload(
                    weather_payload, field_lat, None, date.today().timetuple().tm_yday
                )
    except Exception:  # noqa: BLE001 — توحيد المياه best-effort، لا يكسر الحالة التشغيليّة
        logger.warning("تعذّر اشتقاق ET0/سياق المحصول للحقل %s — يُتخطّى ETc", field_id, exc_info=True)

    # C5: بوّابة عتبات NDVI (إغلاق خلف feature flag، default off): NDVI يبقى **معلوماتيّاً
    # لا يحكم الصلاحيّة** ما لم تُفعَّل العتبات، والكتلة تُعلن **صراحةً** سبب التعطيل
    # (insufficient_field_calibration) بدل الإبهام — لا عتبات مُلفَّقة (صدق).
    _apply_ndvi_threshold_gating(state, crop_id, days_after_planting)

    # Stage E (توحيد النواة): ادمج الحقائق الزراعيّة الغنيّة (compose_field_state)
    # في الحالة القانونيّة — فيصبح الإسقاط مصدر الحقيقة الموحّد (حقائق + جاهزيّة).
    # التحكيم يَحكُم فعليّاً: ملوحة تربة حرجة تُصعّد نمط التنفيذ للمراجعة البشريّة
    # رغم خُضرة NDVI (Salinity>Vigor) — تصعيد سلامة لا تخفيض، ولا يغيّر أرقاماً
    # زراعيّة (يطبّق منطق النواة الموجود فقط).
    agronomic = _compose_agronomic(
        field_id,
        tenant_id,
        fresh.get("ndvi_mean"),
        fresh.get("soil_ec"),
        crop_id=crop_id,
        days_after_planting=days_after_planting,
        et0_mm=et0_mm,
    )
    if agronomic is not None:
        state["agronomic"] = agronomic
        # Bundle D (D3): كتلة المياه الكنسيّة المقروءة من مكان واحد (لا حساب، لا تغيير قرار) —
        # يقرؤها المستهلكون بدل تعدّد مصادر ET0/ETc. غياب القيم ⇒ None (لا تُسقَط، لا اختلاق).
        water = canonical_water(agronomic["operational_truths"])
        if water is not None:
            state["water"] = water
            # ETc-dual canonical (إغلاق خلف feature flag، default off): العلم off ⇒ single كما
            # هو؛ on + مدخلات ⇒ etc من النهج المزدوج بنفس ET0 الكنسيّ؛ on + نقص ⇒ single + سبب.
            _apply_canonical_etc_dual(
                water,
                crop_id,
                days_after_planting,
                et0_mm,
                weather_payload,
                field_lat,
                fresh.get("ndvi_mean"),
            )
        if (
            agronomic["operational_truths"].get("salinity_class") == "critical"
            and state["execution_mode"] == "auto"
        ):
            state["execution_mode"] = "human_review"
            if state["validity"] == "valid":
                state["validity"] = "degraded"
            state.setdefault("reasons_ar", []).append(
                "ملوحة تربة حرجة (تحكيم النواة الزراعيّة: الملوحة تَحكُم رغم خُضرة "
                "NDVI) — تتطلّب مراجعة بشريّة."
            )

    # Bundle B: ثقة الحدود الكنسيّة — اقرأ جودة الحدّ المخزَّنة (يهدّفها مسار
    # boundaries عبر score_boundary) من **مصدر واحد** وأسقِطها ككتلة boundary.
    # best-effort: غياب صفّ/ثقة ⇒ لا كتلة (صدق، لا اختلاق) ولا تصعيد.
    try:
        brow = await conn.fetchrow(
            "SELECT confidence_score, source_type, model_version, review_status "
            "FROM field_boundaries WHERE field_id = $1",
            field_id,
        )
        boundary = canonical_boundary(dict(brow) if brow is not None else None)
        if boundary is not None:
            state["boundary"] = boundary
            # تصعيد ثقة الحدّ — حدّ منخفض الثقة (< العتبة) يُصعّد نمط التنفيذ
            # للمراجعة البشريّة (نظير تصعيد الملوحة الحرجة): تصعيد سلامة لا تخفيض —
            # لا يلمس إلّا حالة auto/valid ولا يغيّر أرقاماً. الدافع: خطأ الترسيم
            # يتسرّب بصمت إلى المساحة/الريّ/الإنتاجيّة ما لم يُكشَف للمراجعة.
            if boundary["review_recommended"] and state["execution_mode"] == "auto":
                state["execution_mode"] = "human_review"
                if state["validity"] == "valid":
                    state["validity"] = "degraded"
                state.setdefault("reasons_ar", []).append(
                    f"ثقة حدّ الحقل منخفضة ({boundary['boundary_confidence']:.2f} < "
                    f"{CONFIDENCE_REVIEW_THRESHOLD:.2f}) — قد تتسرّب أخطاء الترسيم إلى "
                    "المساحة/الريّ/الإنتاجيّة، تتطلّب مراجعة بشريّة."
                )
    except Exception:  # noqa: BLE001 — قراءة الحدّ best-effort، لا تكسر الحالة التشغيليّة
        logger.warning("تعذّر قراءة ثقة حدّ الحقل %s — تُتخطّى كتلة boundary", field_id, exc_info=True)

    # Bundle D (D2): الإجهاد المائيّ الكنسيّ. اقرأ أحدث استنزاف (Dr) + الثقة من دفتر
    # المياه (water_ledger) واشتقّ TAW، فأسقِط كتلة water_stress بمستويات
    # NORMAL/WATCH/CRITICAL + تأكيد طيفيّ (NDMI+MSI) + أهليّة التصعيد (D2b). التصعيد
    # ESCALATE→human_review خلف feature flag (default off، قرار المستخدم). best-effort:
    # غياب Dr موثوق ⇒ لا كتلة (صدق، لا قرار على غياب).
    try:
        lrow = await conn.fetchrow(
            "SELECT depletion_mm, soil_moisture_pct, confidence "
            "FROM water_ledger WHERE field_id = $1 ORDER BY ledger_date DESC LIMIT 1",
            field_id,
        )
        if lrow is not None and lrow["depletion_mm"] is not None:
            from .soil_water import soil_water_params

            # TAW من النسيج (افتراضيّ احتياطيّ) × عمق جذور افتراضيّ موسوم — موسومة
            # calibrated=False صدقاً (معايرة يمنيّة فجوة موثّقة، لا اختلاق دقّة).
            sw = soil_water_params(texture=None)
            stress = canonical_water_stress(
                {
                    "depletion_mm": lrow["depletion_mm"],
                    "taw_mm": sw["taw_mm"],
                    "raw_fraction": sw["raw_fraction"],
                    "depletion_confidence": lrow["confidence"],
                    "soil_moisture_pct": lrow["soil_moisture_pct"],
                    # D2b: تأكيد طيفيّ (NDMI+MSI) من imagery_automation_fields (v99).
                    "ndmi": fresh.get("ndmi_mean"),
                    "msi": fresh.get("msi_mean"),
                }
            )
            if stress is not None:
                state["water_stress"] = stress
                # D2b: التصعيد خلف العلم (default off). المسند الكامل (الأهليّة) مُعلَن
                # دائماً؛ human_review لا يقع إلّا عند تفعيل العلم — صدق: نُعلن سبب
                # التعطيل. تصعيد سلامة لا تخفيض: لا يلمس إلّا auto/valid.
                flag_on = is_enabled(
                    _WATER_STRESS_ESCALATION_FLAG, os.getenv(_WATER_STRESS_ESCALATION_FLAG)
                )
                eligible = stress.get("escalation_eligible") is True
                stress["escalation_triggered"] = bool(eligible and flag_on)
                stress["disabled_reason"] = (
                    "feature_flag_off" if (eligible and not flag_on) else None
                )
                if stress["escalation_triggered"] and state["execution_mode"] == "auto":
                    state["execution_mode"] = "human_review"
                    if state["validity"] == "valid":
                        state["validity"] = "degraded"
                    state.setdefault("reasons_ar", []).append(
                        f"إجهاد مائيّ حرج مؤكَّد طيفيّاً (AWF={stress['water_stress_awf']:.2f}≤0.2، "
                        "NDMI+MSI) — يتطلّب مراجعة بشريّة."
                    )
    except Exception:  # noqa: BLE001 — قراءة الإجهاد best-effort، لا تكسر الحالة التشغيليّة
        logger.warning(
            "تعذّر قراءة الإجهاد المائيّ للحقل %s — تُتخطّى كتلة water_stress", field_id, exc_info=True
        )

    prev = await conn.fetchrow(
        "SELECT validity, execution_mode FROM field_state WHERE field_id = $1",
        field_id,
    )
    changed = (
        prev is None
        or prev["validity"] != state["validity"]
        or prev["execution_mode"] != state["execution_mode"]
    )

    await conn.execute(
        """
        INSERT INTO field_state
            (field_id, tenant_id, validity, execution_mode, confidence_level,
             ndvi_age_days, soil_age_days, weather_age_hours,
             reasons_ar, conflicts, freshness_warnings, inputs, agronomic, computed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, NOW())
        ON CONFLICT (field_id) DO UPDATE SET
            validity = EXCLUDED.validity,
            execution_mode = EXCLUDED.execution_mode,
            confidence_level = EXCLUDED.confidence_level,
            ndvi_age_days = EXCLUDED.ndvi_age_days,
            soil_age_days = EXCLUDED.soil_age_days,
            weather_age_hours = EXCLUDED.weather_age_hours,
            reasons_ar = EXCLUDED.reasons_ar,
            conflicts = EXCLUDED.conflicts,
            freshness_warnings = EXCLUDED.freshness_warnings,
            inputs = EXCLUDED.inputs,
            agronomic = EXCLUDED.agronomic,
            computed_at = NOW()
        """,
        field_id,
        tenant_id,
        state["validity"],
        state["execution_mode"],
        state.get("confidence_level"),
        inputs.get("ndvi_age_days"),
        inputs.get("soil_age_days"),
        inputs.get("weather_age_hours"),
        json.dumps(state.get("reasons_ar", [])),
        json.dumps(state.get("conflicts", [])),
        json.dumps(state.get("freshness_warnings", [])),
        json.dumps(inputs),
        json.dumps(state.get("agronomic")),  # الحقائق الزراعيّة (NULL إن لا إشارات)
    )
    return {"state": state, "changed": changed}
