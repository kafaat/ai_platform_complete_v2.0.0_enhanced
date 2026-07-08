"""api/field_season_projection.py — الحقيقة التشغيليّة الموحّدة للحقل-الموسم — VNext الموحِّد.

يجمع محرّكات الموسم النقيّة القائمة في **قراءة واحدة** لكلّ ``(field_id, season_id)`` — بدل أن
يستدعي الذكاء/الواجهة/التقارير مصادر متفرّقة، يقرؤون «حقيقة تشغيليّة» واحدة:

  ① حارس التقويم        ``api.season_calendar_guard.evaluate_season_calendar``  (داخل/خارج نافذة)
  ② الفينولوجيا الحراريّة ``core.gdd_phenology.phenology_progress``               (المرحلة + GDD + تباعد)
  ③ Kc الطوريّ           ``core.season_phenology.stage_kc``                       (FAO-56)
  ④ مخاطر المرحلة        ``core.season_stage_risk.stage_weather_risks``           (طقس × مرحلة)
  ⑤ تعارض الاستشعار      ``core.eo_stage_mismatch.detect_eo_stage_mismatch``      (NDVI/NDMI × مرحلة)
  + الماء (عجز 7/14 يوم) + المهام المفتوحة (تُمرَّر من القاعدة).

يقع في ``api/`` لأنّه يعتمد ``api.season_calendar_guard`` (الذي يعتمد بيانات تقويم في api)؛ فاستيراد
core منه سليم (api ← core)، عكسه ممنوع (core لا يستورد api). المرحلة الفعّالة = مرحلة GDD إن انطبقت،
وإلّا مرحلة الأيّام — وتُغذّي ④ و⑤.

**نقيّ (لا شبكة/قاعدة):** يستقبل المُدخَلات الخام ويُخرِج القاموس الموحّد. طبقة القراءة من القاعدة
(تجمع المُدخَلات ثمّ تنادي هذه الدالّة) رقيقة وتُبنى لاحقاً مع بطاقة أدلّة الموسم.

صدق: كلّ مكوّن يحمل ثقته وأدلّته الناقصة؛ الموحِّد يجمعها. المُدخَل الغائب ⇒ الكتلة None/inconclusive
+ يُدرَج في ``evidence_missing`` — لا رقم مُختلَق. ``season_confidence`` سقفها MEDIUM (كلّه تقدير/توقّع).
"""

from __future__ import annotations

from datetime import date

from core.eo_stage_mismatch import detect_eo_stage_mismatch
from core.gdd_phenology import phenology_progress
from core.season_phenology import resolve_crop_id, stage_kc
from core.season_stage_risk import stage_weather_risks

from api.season_calendar_guard import evaluate_season_calendar


def assemble_field_season_state(
    *,
    field_id: str | None = None,
    season_id: str | None = None,
    crop: str | None = None,
    cultivar: str | None = None,
    sowing_date: date | None = None,
    season_end: date | None = None,
    today: date | None = None,
    accumulated_gdd: float | None = None,
    observed_ndvi: float | None = None,
    observed_ndmi: float | None = None,
    valid_pixel_ratio: float | None = None,
    cloud_pct: float | None = None,
    weather_signals: dict | None = None,
    water_deficit_7d_mm: float | None = None,
    water_deficit_14d_mm: float | None = None,
    water_stress_factor: float | None = None,
    open_tasks_count: int | None = None,
) -> dict:
    """يبني الحقيقة التشغيليّة الموحّدة للحقل-الموسم من مُدخَلات خام. نقيّ.

    يُعيد قاموساً واحداً يحمل: الهويّة، المرحلة الفعّالة، أيّام البذار، GDD، حالة التقويم،
    Kc الحاليّ، عجز الماء 7/14 يوم، تعارض الاستشعار، مخاطر المرحلة، المهام المفتوحة،
    ``season_confidence``، و``evidence_used``/``evidence_missing`` المُجمَّعة.
    """
    crop_id = resolve_crop_id(crop)
    ref = today or date.today()
    days_after_sowing = (ref - sowing_date).days if sowing_date is not None else None

    # ① التقويم
    calendar = evaluate_season_calendar(crop, sowing_date, season_end)
    # ② الفينولوجيا الحراريّة (+ الأيّام)
    pheno = phenology_progress(crop_id, days_after_sowing, accumulated_gdd)
    # المرحلة الفعّالة: GDD إن انطبقت وتوفّرت، وإلّا الأيّام.
    effective_stage = pheno.get("gdd_stage") or pheno.get("days_stage")
    stage_source = (
        "gdd" if pheno.get("gdd_stage") else ("days" if pheno.get("days_stage") else None)
    )
    # ③ Kc الطوريّ
    current_kc = stage_kc(crop_id, days_after_sowing)

    # ④ مخاطر المرحلة (تُغذّى بالطقس + الماء)
    risk_signals = dict(weather_signals or {})
    if water_stress_factor is not None:
        risk_signals.setdefault("water_stress_factor", water_stress_factor)
    if water_deficit_7d_mm is not None:
        risk_signals.setdefault("water_deficit_mm", water_deficit_7d_mm)
    stage_risk = stage_weather_risks(effective_stage, crop_id, risk_signals)

    # ⑤ تعارض الاستشعار مع المرحلة
    eo = detect_eo_stage_mismatch(
        effective_stage,
        observed_ndvi,
        observed_ndmi,
        valid_pixel_ratio=valid_pixel_ratio,
        cloud_pct=cloud_pct,
    )

    # ── تجميع الأدلّة (صدق: ما توفّر مقابل ما نقص من الإشارات الجوهريّة) ──
    core_signals = {
        "crop": crop_id is not None,
        "sowing_date": sowing_date is not None,
        "days_after_sowing": days_after_sowing is not None,
        "accumulated_gdd": accumulated_gdd is not None,
        "ndvi": observed_ndvi is not None,
        "weather": bool(weather_signals),
        "water": water_stress_factor is not None
        or water_deficit_7d_mm is not None
        or water_deficit_14d_mm is not None,
        "open_tasks": open_tasks_count is not None,
    }
    evidence_used = [k for k, present in core_signals.items() if present]
    evidence_missing = [k for k, present in core_signals.items() if not present]

    # ── ثقة الموسم: سقف MEDIUM. منخفضة إن جُهِلت المرحلة أو ندرت الإشارات الحيّة. ──
    live = sum(1 for k in ("ndvi", "weather", "water") if core_signals[k])
    season_confidence = "low" if (effective_stage is None or live == 0) else "medium"

    return {
        "schema": "field_season_state.v1",
        "field_id": field_id,
        "season_id": season_id,
        "crop": crop_id,
        "crop_input": crop,
        "cultivar": cultivar,
        # الطور
        "current_stage": effective_stage,
        "current_stage_ar": pheno.get("gdd_stage_ar") or pheno.get("days_stage_ar"),
        "stage_source": stage_source,  # gdd | days | None
        "days_after_sowing": days_after_sowing,
        "accumulated_gdd": accumulated_gdd,
        "gdd_to_maturity": pheno.get("gdd_to_maturity"),
        "gdd_fraction": pheno.get("gdd_fraction"),
        "phenology_divergence": pheno.get("divergence"),
        "current_kc": current_kc,
        # التقويم
        "calendar_status": calendar.get("status"),
        "calendar": calendar,
        # الماء
        "water_deficit_7d_mm": water_deficit_7d_mm,
        "water_deficit_14d_mm": water_deficit_14d_mm,
        "water_stress_factor": water_stress_factor,
        # الاستشعار × المرحلة
        "eo_stage_mismatch": eo,
        # مخاطر المرحلة (طقس × مرحلة)
        "weather_stage_risks": stage_risk,
        # العمليّات
        "open_operations": open_tasks_count,
        # الحوكمة/الصدق
        "season_confidence": season_confidence,
        "requires_review": bool(
            calendar.get("requires_review")
            or stage_risk.get("requires_action")
            or eo.get("status") == "below_expected"
            or (pheno.get("divergence") or {}).get("diverged")
        ),
        "evidence_used": evidence_used,
        "evidence_missing": evidence_missing,
        "disclaimer_ar": (
            "حقيقة تشغيليّة مُجمَّعة من محرّكات تقديريّة (تقويم/GDD/FAO-56/طقس متوقّع/استشعار). "
            "السقف MEDIUM؛ الناقص مُعلَن في evidence_missing — لا رقم مُختلَق."
        ),
    }
