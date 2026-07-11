"""api/crop_twin.py — الحالة الرقميّة الموحّدة للمحصول (Crop Digital Twin State)

يجمع لبنات «مركز المحاصيل» في لقطة حالة واحدة متّسقة لحقل/محصول في لحظة:
  • الفينولوجيا: تراكم GDD ⇒ تقدّم الموسم ⇒ المرحلة (api.season_simulation).
  • ماء منطقة الجذور: استنزاف Dr عبر السلسلة (api.root_zone_balance، FAO-56 eq.85).
  • امتصاص العناصر حتى الآن: منحنى الامتصاص عند التقدّم الحاليّ (api.nutrient_4r).

نقيّ حتميّ (لا I/O). ليس نموذجاً جديداً — طبقة **تركيب** تقرأ الوحدات القائمة
وتوحّد حالتها في read-model واحد، فيصير الأساس للمتحكّمات التنبّؤيّة (MPC) لاحقاً.

صدق: يحمل كلّ أوسمة عدم المعايرة من الوحدات المصدر (المعاملات تقديريّة تحتاج
معايرة يمنيّة) ولا يضيف يقيناً غير مدعوم؛ المحصول غير المُعرّف يُوسَم صراحةً.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.crop_intelligence import CropIntelligenceInput, build_crop_intelligence_state

from api.nutrient_4r import nutrient_uptake
from api.root_zone_balance import DayInput, root_zone_balance
from api.season_simulation import (
    _STAGE_FRACTIONS,
    _params_for,
    normalize_crop,
)


@dataclass
class TwinDay:
    """رصد يوم واحد يغذّي التوأم: حرارة (للـGDD) + ET₀/Kc/مطر/ريّ (لميزان الماء)."""

    t_min_c: float
    t_max_c: float
    et0_mm: float
    kc: float
    rain_mm: float = 0.0
    irrigation_mm: float = 0.0
    runoff_mm: float = 0.0


def _stage_from_progress(progress: float) -> str:
    """المرحلة من تقدّم الموسم [0,1] عبر حدود أطوال المراحل (_STAGE_FRACTIONS)."""
    acc = 0.0
    last_name = _STAGE_FRACTIONS[-1][0]
    for name, length in _STAGE_FRACTIONS:
        acc += length
        if progress <= acc:
            return name
    return last_name


def crop_twin_state(
    crop: str | None,
    days: list[TwinDay],
    taw_mm: float,
    raw_fraction: float,
    target_uptake_kg_ha: float = 0.0,
    initial_depletion_mm: float = 0.0,
    auto_irrigate: bool = False,
    field_id: str | None = None,
    season_id: str | None = None,
    spectral_state: dict | None = None,
    source_ids: list[str] | None = None,
    root_policy: dict | None = None,
    stress_history: list[dict] | None = None,
    stress_memory_as_of: str | None = None,
    stress_memory_policy: dict | None = None,
    prior_stress_memory: dict | None = None,
    crop_water_policy: dict | None = None,
    weather_state: dict | None = None,
    gdd_daily_override: list[float | None] | None = None,
    gdd_product: dict | None = None,
) -> dict:
    """يبني الحالة الرقميّة الموحّدة للمحصول من سلسلة أيّام — نقيّ حتميّ.

    يركّب فينولوجيا (GDD⇒تقدّم⇒مرحلة) + ماء منطقة الجذور (Dr عبر السلسلة) + امتصاص
    العناصر حتى الآن (عند التقدّم). لا تلفيق: المعاملات النموذجيّة تقديريّة موسومة،
    والمحصول غير المُعرّف يستعمل معاملات عامّة موسومة.
    """
    crop_key, known = normalize_crop(crop)
    params = _params_for(crop_key)

    # ١) الفينولوجيا: استهلاك منتج GDD القانونيّ من weather-service كما هو.
    # Crop Intelligence لا يجمع daily_gdd ولا يعيد حساب العتبات؛ accumulated_gdd والنَّسَب
    # ونسخة الصيغة تأتي من مالك المنتج. ``gdd_daily_override`` يبقى توافقاً داخلياً قديماً
    # فقط للمستدعين غير المهاجرين، ولا يُستخدم عندما يتوفر المنتج القانونيّ.
    canonical_gdd = dict(gdd_product or {})
    if canonical_gdd:
        raw_gdd = canonical_gdd.get("accumulated_gdd")
        gdd_cum = float(raw_gdd) if isinstance(raw_gdd, (int, float)) else 0.0
        thresholds = canonical_gdd.get("thresholds_used") or {}
        phenology_method = thresholds.get("method") or "canonical_weather_gdd"
        phenology_formula_version = canonical_gdd.get("calculation_version")
        gdd_evidence_ids = list(canonical_gdd.get("contributing_state_ids") or [])
        if canonical_gdd.get("gdd_lineage_id"):
            gdd_evidence_ids.append(str(canonical_gdd["gdd_lineage_id"]))
        gdd_limitations = list(canonical_gdd.get("limitations") or [])
        if canonical_gdd.get("series_quality_status") in {"degraded", "insufficient"}:
            gdd_limitations.append(
                f"canonical_gdd_series_{canonical_gdd.get('series_quality_status')}"
            )
    else:
        # Backward-compatible bridge only; callers should migrate to ``gdd_product``.
        gdd_cum = sum(
            float(value) for value in (gdd_daily_override or [])[: len(days)] if value is not None
        )
        phenology_method = "weather_gdd_daily_override_compat"
        phenology_formula_version = "compat/daily-gdd-override"
        gdd_evidence_ids = []
        gdd_limitations = ["canonical_gdd_product_missing"]
    gdd_mat = params.gdd_to_maturity
    progress = min(1.0, gdd_cum / gdd_mat) if gdd_mat > 0 else 0.0
    past_maturity = gdd_mat > 0 and gdd_cum >= gdd_mat
    stage = _stage_from_progress(progress)

    # ٢) ماء منطقة الجذور عبر السلسلة (نفس فيزياء root_zone_balance).
    rz_days = [
        DayInput(
            et0_mm=d.et0_mm,
            kc=d.kc,
            rain_mm=d.rain_mm,
            irrigation_mm=d.irrigation_mm,
            runoff_mm=d.runoff_mm,
        )
        for d in days
    ]
    rz = root_zone_balance(
        rz_days,
        taw_mm=taw_mm,
        raw_fraction=raw_fraction,
        initial_depletion_mm=initial_depletion_mm,
        auto_irrigate=auto_irrigate,
    )
    depletion_pct = (rz.final_depletion_mm / taw_mm * 100.0) if taw_mm > 0 else 0.0
    needs_irrigation = rz.final_depletion_mm >= rz.raw_mm

    # ٣) امتصاص العناصر حتى الآن عند التقدّم الحاليّ.
    nut = nutrient_uptake(crop_key or crop, progress, target_uptake_kg_ha)

    warnings_ar: list[str] = []
    if not known:
        warnings_ar.append("محصول غير مُعرّف — معاملات نموذج عامّة (موسومة)")
    if past_maturity:
        warnings_ar.append("تجاوز GDD النضج المتوقّع — قد يكون الموسم منتهياً")
    warnings_ar.extend(nut["warnings_ar"])

    crop_intelligence = build_crop_intelligence_state(
        CropIntelligenceInput(
            crop=crop_key or crop,
            gdd_cumulative=gdd_cum,
            gdd_to_maturity=gdd_mat,
            phenology_method=phenology_method,
            phenology_formula_version=phenology_formula_version,
            water_state={
                "status": "available",
                "taw_mm": round(rz.taw_mm, 2),
                "raw_mm": round(rz.raw_mm, 2),
                "depletion_mm": round(rz.final_depletion_mm, 2),
                "needs_irrigation": needs_irrigation,
            },
            nutrient_state={
                "status": "estimated",
                "target_uptake_kg_ha": nut["target_uptake_kg_ha"],
                "stage": nut["matched_stage"],
                "cumulative_fraction_to_date": nut["cumulative_fraction_to_date"],
                "uptake_to_date_kg_ha": nut["uptake_to_date_kg_ha"],
            },
            spectral_state=spectral_state,
            field_id=field_id,
            season_id=season_id,
            source_ids=list(dict.fromkeys([*(source_ids or []), *gdd_evidence_ids])),
            root_policy=root_policy,
            stress_history=stress_history,
            stress_memory_as_of=stress_memory_as_of,
            stress_memory_policy=stress_memory_policy,
            prior_stress_memory=prior_stress_memory,
            crop_water_policy=crop_water_policy,
            weather_state=weather_state,
            limitations=list(dict.fromkeys(gdd_limitations)),
        )
    )

    return {
        "crop": crop_key or (crop or None),
        "crop_known": known,
        "phenology": {
            "gdd_cumulative": round(gdd_cum, 1),
            "gdd_to_maturity": gdd_mat,
            "progress": round(progress, 4),
            "stage": stage,
            "past_maturity": past_maturity,
        },
        "water": {
            "taw_mm": round(rz.taw_mm, 2),
            "raw_mm": round(rz.raw_mm, 2),
            "depletion_mm": round(rz.final_depletion_mm, 2),
            "depletion_pct": round(depletion_pct, 1),
            "needs_irrigation": needs_irrigation,
            "recommended_irrigation_mm": round(
                rz.final_depletion_mm if needs_irrigation else 0.0, 2
            ),
            "total_recommended_irrigation_mm": round(rz.total_recommended_irrigation_mm, 2),
            "trigger_days": rz.trigger_days,
        },
        "nutrient": {
            "target_uptake_kg_ha": nut["target_uptake_kg_ha"],
            "stage": nut["matched_stage"],
            "cumulative_fraction_to_date": nut["cumulative_fraction_to_date"],
            "uptake_to_date_kg_ha": nut["uptake_to_date_kg_ha"],
        },
        "crop_intelligence": crop_intelligence,
        "calibrated": False,
        "warnings_ar": warnings_ar,
    }
