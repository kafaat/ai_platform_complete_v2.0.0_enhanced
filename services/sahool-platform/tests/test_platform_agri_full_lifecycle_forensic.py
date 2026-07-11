from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.engines.fao56 import WeatherDay, kc_for_age
from core.farm_closed_loop import (
    OperationEvent,
    ResourceUse,
    build_economic_state,
    build_inventory_projection,
    operation_event_to_ledger_payload,
)
from core.farm_costing import (
    ActualCostLine,
    SeasonBudgetLine,
    compute_profitability,
    compute_variances,
    generate_cost_recommendations,
    project_to_erp_lines,
)
from core.farm_operations_ledger import (
    EnergyRecord,
    EnergySource,
    EquipmentRecord,
    ExecutionMode,
    InputRecord,
    InputType,
    LaborRecord,
    LedgerCostLine,
    OperationLedgerRecord,
    OperationType,
    WaterRecord,
    ai_feature_row,
    summarize_operational_records,
)
from core.field_lifecycle import FieldQualityState, SoilTestChoice, resolve_state
from core.season_comparison import SeasonMetrics, compare_seasons
from core.season_phenology import crop_kc_profile, current_stage, season_timeline, stage_kc
from core.sensor_intake import ingest_batch
from core.soil_recommendations import soil_to_recommendations
from core.yield_interval_service import field_yield_interval


@dataclass(frozen=True)
class RasterAsset:
    field_id: str
    indicator: str
    acquisition_date: date
    tile_url: str
    mean: float
    available: bool = True


def _select_asset(
    assets: list[RasterAsset], field_id: str, indicator: str, acquisition_date: date
) -> RasterAsset:
    """محاكاة اختيار الطبقة: لا رجوع صامت إلى latest إذا اختار المستخدم تاريخاً محدداً."""
    matches = [
        a
        for a in assets
        if a.field_id == field_id
        and a.indicator == indicator
        and a.acquisition_date == acquisition_date
        and a.available
    ]
    if not matches:
        raise LookupError("selected_imagery_date_or_indicator_unavailable")
    return matches[0]


def test_full_platform_agri_lifecycle_forensic_trace_from_field_to_harvest_and_comparison():
    """محاكاة جنائية لموسم زراعي كامل عبر SAHOOL دون I/O خارجي.

    التغطية المقصودة: إنشاء الحقل → بطاقة الصنف/مراحل النمو → صور ومؤشرات → حساسات
    → فحوصات تربة/مياه → تخطيط موازنة الموسم → عمليات ومهام وسجلات يومية → محركات
    ري/تسميد/تكلفة → توصيات → ربحية/تنبؤ محصول → مقارنة موسم سابق.
    """
    tenant = "tenant-aljawf"
    farm = "farm-alhazm"
    field = "field-pivot-barley-01"
    season = "barley-2026"
    crop_id = "barley"
    area_ha = 42.0
    sowing_date = date(2026, 10, 15)

    # 1) إنشاء الحقل ومصدر الحقيقة الهندسي.
    field_record = {
        "tenant_id": tenant,
        "farm_id": farm,
        "field_id": field,
        "name": "محور الشعير 01",
        "geometry_source": "drawn_geodesic_pivot",
        "irrigation_type": "pivot",
        "pivot": {"center": [44.2145, 15.3712], "radius_m": 365.7},
        "area_ha": area_ha,
        "boundary_confidence": 0.93,
    }
    assert field_record["geometry_source"] == "drawn_geodesic_pivot"
    assert field_record["boundary_confidence"] >= 0.9

    # 2) فحوصات التربة والمياه ترفع حالة الحقل إلى READY.
    state, allowed = resolve_state(SoilTestChoice.PROVIDED, {"S3", "S4", "I3"})
    assert state is FieldQualityState.READY
    assert {"irrigation", "fertility", "salinity_mgmt"}.issubset(set(allowed))
    soil_water_profile = {
        "soil_ph": 7.8,
        "soil_ece_ds_m": 3.2,
        "water_ec_ds_m": 1.4,
        "texture_ar": "طميي",
        "source": "lab",
    }
    soil_guidance = soil_to_recommendations(
        soil_water_profile["texture_ar"], soil_water_profile["soil_ph"]
    )
    assert soil_guidance["fertilizer"]["requires_lab"] is False
    assert soil_guidance["irrigation"] is not None

    # 3) بطاقة المحصول والصنف: مراحل نمو + Kc حسب العمر.
    timeline = season_timeline(crop_id, sowing_date, today=date(2027, 1, 10))
    assert len(timeline) == 4
    assert any(step["status"] == "current" and step["stage"] == "mid" for step in timeline)
    assert current_stage(crop_id, 70)["stage"] == "mid"
    assert stage_kc(crop_id, 70) == 1.15
    crop_profile = crop_kc_profile(crop_id)
    assert crop_profile is not None

    # 4) الأقمار الصناعية والمؤشرات: التاريخ والمؤشر يحددان URL والطبقة بدقة.
    assets = [
        RasterAsset(
            field, "ndvi", date(2026, 11, 1), "/tiles/field/ndvi/2026-11-01/{z}/{x}/{y}.png", 0.42
        ),
        RasterAsset(
            field, "ndvi", date(2027, 1, 5), "/tiles/field/ndvi/2027-01-05/{z}/{x}/{y}.png", 0.71
        ),
        RasterAsset(
            field, "ndmi", date(2027, 1, 5), "/tiles/field/ndmi/2027-01-05/{z}/{x}/{y}.png", 0.28
        ),
        RasterAsset(
            field, "msi", date(2027, 1, 5), "/tiles/field/msi/2027-01-05/{z}/{x}/{y}.png", 0.82
        ),
    ]
    ndvi_mid = _select_asset(assets, field, "ndvi", date(2027, 1, 5))
    msi_mid = _select_asset(assets, field, "msi", date(2027, 1, 5))
    assert ndvi_mid.tile_url != msi_mid.tile_url
    assert "ndvi" in ndvi_mid.tile_url and "msi" in msi_mid.tile_url

    # 5) الحساسات والطقس تدخل كقرائن، لا كبديل للمعمل.
    sensor_batch = ingest_batch(
        [
            {
                "tenant_id": tenant,
                "field_id": field,
                "sensor_type": "soil_moisture",
                "value": 24.0,
                "unit": "%",
                "device_id": "soil-01",
            },
            {
                "tenant_id": tenant,
                "field_id": field,
                "sensor_type": "soil_ec",
                "value": 2.6,
                "unit": "dS/m",
                "device_id": "soil-ec-01",
            },
            {
                "tenant_id": tenant,
                "field_id": field,
                "sensor_type": "air_humidity",
                "value": 54.0,
                "unit": "%",
                "device_id": "met-01",
            },
        ]
    )
    assert sensor_batch["accepted_count"] == 3
    assert sensor_batch["rejected_count"] == 0

    weather_days = {
        10: WeatherDay(30, 15, 50, 2.2, 19.0, 15.37, 1100, 295),
        35: WeatherDay(31, 16, 48, 2.5, 20.0, 15.37, 1100, 320),
        70: WeatherDay(34, 18, 42, 3.1, 22.0, 15.37, 1100, 10),
        105: WeatherDay(33, 17, 45, 2.8, 21.0, 15.37, 1100, 45),
    }
    # WS-C.1b Zero-Legacy: compute_irrigation (نواة ملكيّة-صفر ميّتة إنتاجيّاً) حُذفت؛ ET0
    # يُنفَّذ في المحرّك ويُحقَن (هنا ثابت مرجعيّ للاختبار). نُبقي تحقّق «الاحتياج الريّي
    # يرتفع منتصف الموسم» عبر البدائيّات الباقية: kc_for_age × ET0 محقون (1مم=10م³/هـ).
    _ET0_MM = 6.0

    def _stage_m3_ha(das: int) -> float:
        kc, _ = kc_for_age(crop_profile, das)
        return round(_ET0_MM * kc * 10.0, 1)

    irrigation_m3_by_stage = {das: _stage_m3_ha(das) for das in weather_days}
    assert kc_for_age(crop_profile, 70)[0] >= kc_for_age(crop_profile, 10)[0]
    assert irrigation_m3_by_stage[70] > irrigation_m3_by_stage[10]

    # 6) تخطيط الموسم: موازنة حسب المراحل والمدخلات المتوقعة.
    budget = [
        SeasonBudgetLine(
            "b-prep", season, "land_preparation", stage="preparation", planned_cost=840000
        ),
        SeasonBudgetLine(
            "b-seed",
            season,
            "seed",
            stage="planting",
            planned_quantity=6300,
            unit="kg",
            planned_unit_cost=520,
        ),
        SeasonBudgetLine(
            "b-fert-dev",
            season,
            "fertilizer",
            stage="development",
            planned_quantity=5200,
            unit="kg",
            planned_unit_cost=390,
        ),
        SeasonBudgetLine(
            "b-fert-mid",
            season,
            "fertilizer",
            stage="mid",
            planned_quantity=3000,
            unit="kg",
            planned_unit_cost=390,
        ),
        SeasonBudgetLine(
            "b-water",
            season,
            "water",
            stage="mid",
            planned_quantity=265000,
            unit="m3",
            planned_unit_cost=18,
        ),
        SeasonBudgetLine(
            "b-energy",
            season,
            "energy",
            stage="mid",
            planned_quantity=19500,
            unit="kWh",
            planned_unit_cost=42,
        ),
        SeasonBudgetLine("b-pest", season, "pesticide", stage="mid", planned_cost=650000),
        SeasonBudgetLine("b-harvest", season, "harvest", stage="harvest", planned_cost=1850000),
        SeasonBudgetLine(
            "b-transport", season, "transport", stage="transport", planned_cost=720000
        ),
        SeasonBudgetLine("b-storage", season, "storage", stage="storage", planned_cost=240000),
        SeasonBudgetLine(
            "b-admin", season, "administration", stage="whole_season", planned_cost=500000
        ),
    ]

    # 7) التنفيذ اليومي/المهام: تجهيز، حراثة، بذار، نمو، ري، تسميد، وقاية، حصاد، نقل، تخزين.
    operations = [
        OperationLedgerRecord(
            "op-prep",
            tenant,
            date(2026, 10, 1),
            OperationType.LAND_PREPARATION,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.RENTED_EQUIPMENT,
            contractor_id="contractor-tillage",
            cost_lines=(LedgerCostLine("land_preparation", 900000),),
        ),
        OperationLedgerRecord(
            "op-plant",
            tenant,
            date(2026, 10, 15),
            OperationType.PLANTING,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("seed", 3276000), LedgerCostLine("labor", 260000)),
        ),
        OperationLedgerRecord(
            "op-fert-dev",
            tenant,
            date(2026, 11, 10),
            OperationType.FERTILIZATION,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("fertilizer", 2100000),),
        ),
        OperationLedgerRecord(
            "op-irrig-mid",
            tenant,
            date(2027, 1, 10),
            OperationType.IRRIGATION,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(
                LedgerCostLine("water", 5400000),
                LedgerCostLine("energy", 1020000),
            ),
        ),
        OperationLedgerRecord(
            "op-pest",
            tenant,
            date(2027, 1, 18),
            OperationType.PEST_CONTROL,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.CONTRACTOR,
            cost_lines=(LedgerCostLine("pesticide", 880000),),
        ),
        OperationLedgerRecord(
            "op-harvest",
            tenant,
            date(2027, 3, 28),
            OperationType.HARVEST,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.CONTRACTOR,
            cost_lines=(LedgerCostLine("harvest", 1980000),),
        ),
        OperationLedgerRecord(
            "op-transport",
            tenant,
            date(2027, 3, 30),
            OperationType.TRANSPORT,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.MIXED,
            cost_lines=(LedgerCostLine("transport", 810000), LedgerCostLine("storage", 260000)),
        ),
        OperationLedgerRecord(
            "op-admin",
            tenant,
            date(2027, 4, 3),
            OperationType.OTHER,
            season,
            farm,
            field,
            execution_mode=ExecutionMode.SELF,
            cost_lines=(LedgerCostLine("administration", 560000),),
        ),
    ]
    water = [
        WaterRecord(
            "op-irrig-mid",
            field,
            "well-03",
            "pivot-01",
            hours_operated=292,
            water_volume_m3=300000,
            measurement_method="meter",
        )
    ]
    energy = [
        EnergyRecord(
            "op-irrig-mid",
            EnergySource.SOLAR,
            kwh=24200,
            hours_operated=292,
            well_id="well-03",
            pivot_id="pivot-01",
        )
    ]
    equipment = [
        EquipmentRecord("op-prep", "tractor-rented", hours_worked=34),
        EquipmentRecord("op-irrig-mid", "pivot-01", hours_worked=292),
        EquipmentRecord("op-harvest", "harvester-contractor", hours_worked=26),
    ]
    labor = [
        LaborRecord("op-plant", "crew-planting", workers_count=6, hours=52, wage_amount=260000),
        LaborRecord("op-transport", "crew-storage", workers_count=4, hours=32, wage_amount=160000),
    ]
    inputs = [
        InputRecord(
            "op-plant", InputType.SEED, "seed-barley-certified", 6300, "kg", estimated_cost=3276000
        ),
        InputRecord(
            "op-fert-dev", InputType.FERTILIZER, "urea", 5400, "kg", estimated_cost=2100000
        ),
        InputRecord(
            "op-pest",
            InputType.PESTICIDE,
            "fungicide-preventive",
            72,
            "liter",
            estimated_cost=880000,
        ),
    ]
    summary = summarize_operational_records(
        operations, water=water, energy=energy, equipment=equipment, labor=labor, inputs=inputs
    )
    assert summary.record_count == 8
    assert summary.water_volume_m3 == 300000
    assert summary.energy_kwh == 24200
    assert summary.equipment_hours == 352
    assert summary.input_quantities["seed:kg"] == 6300

    # 8) الانحرافات والتوصيات: الموازنة مقابل التنفيذ الفعلي.
    actuals = [
        ActualCostLine(
            op.record_id + ":" + line.category,
            season,
            line.category,
            stage={
                "land_preparation": "preparation",
                "seed": "planting",
                "labor": "planting",
                "fertilizer": "development",
                "water": "mid",
                "energy": "mid",
                "pesticide": "mid",
                "harvest": "harvest",
                "transport": "transport",
                "storage": "storage",
                "administration": "whole_season",
            }.get(line.category, "whole_season"),
            actual_cost=line.amount,
        )
        for op in operations
        for line in op.cost_lines
    ]
    variances = compute_variances(budget, actuals)
    variance_by = {(v.stage, v.category): v for v in variances}
    assert variance_by[("mid", "water")].severity in {"watch", "critical"}
    assert (
        variance_by[("mid", "pesticide")].actual_cost
        > variance_by[("mid", "pesticide")].planned_cost
    )
    recs = generate_cost_recommendations(variances)
    assert any(r.code == "cost_variance_mid_water" for r in recs)
    assert all(r.provenance["requires_human_review"] for r in recs)

    # 9) إسقاطات رقابية: مخزون وERP وautowrite preview لا تكتب فعلياً.
    inv = build_inventory_projection(
        [
            ResourceUse("seed", 6300, "kg", 3276000, "seed-barley-certified"),
            ResourceUse("fertilizer", 5400, "kg", 2100000, "urea"),
        ],
        sync_enabled=False,
    )
    assert all(
        line.posting_mode == "projection_only" and line.disabled_reason == "feature_flag_off"
        for line in inv
    )
    erp = project_to_erp_lines(actuals, cost_center="farm-alhazm", project=season, currency="YER")
    assert {line.category for line in erp} >= {"water", "seed", "fertilizer", "harvest"}
    payload = operation_event_to_ledger_payload(
        OperationEvent(
            "evt-irrigation-finished",
            tenant,
            date(2027, 1, 10),
            "irrigation",
            season,
            farm,
            field,
            cost_category="water",
            cost_amount=5400000,
            water_m3=300000,
            energy_kwh=24200,
            inputs=(ResourceUse("fertilizer", 100, "kg", 39000, "urea"),),
        )
    )
    assert payload["autowrite_eligible"] is True
    assert payload["provenance"] == {"source": "operation_event", "persisted": False}

    # 10) ربحية، حالة اقتصادية، ميزات تعلم، وتنبؤ إنتاج نزيه.
    revenue = 21_700_000
    yield_tons = 154.0
    profit = compute_profitability(
        season,
        revenue=revenue,
        cost_lines=actuals,
        yield_quantity=yield_tons,
        unit="ton",
        currency="YER",
    )
    assert profit.gross_margin > 0
    economic_state = build_economic_state(
        season, summary, area_ha=area_ha, profitability=profit, variances=variances
    )
    assert economic_state.provenance["canonical_state_write"] is False
    assert economic_state.water_m3_per_ha == summary.water_volume_m3 / area_ha
    features = ai_feature_row(summary, area_ha=area_ha)
    assert features["provenance"]["prediction"] is False
    yint = field_yield_interval(
        point_estimate=3.7,
        residuals=[0.18, -0.22, 0.11, -0.14, 0.2, -0.25, 0.16, -0.19, 0.23, -0.17, 0.12],
        coverage=0.9,
    )
    assert yint["calibrated"] is True
    assert yint["interval"][0] < yint["point_estimate"] < yint["interval"][1]

    # 11) مقارنة مواسم لنفس المحصول.
    comparison = compare_seasons(
        SeasonMetrics(
            season,
            crop_id,
            kc_mid=1.15,
            yield_t_ha=yield_tons / area_ha,
            water_used_m3=summary.water_volume_m3,
            ndvi_peak=ndvi_mid.mean,
            et0_total_mm=520,
            water_use_efficiency=yield_tons / summary.water_volume_m3,
        ),
        SeasonMetrics(
            "barley-2025",
            crop_id,
            kc_mid=1.12,
            yield_t_ha=3.2,
            water_used_m3=330000,
            ndvi_peak=0.66,
            et0_total_mm=535,
            water_use_efficiency=138 / 330000,
        ),
    )
    assert comparison["crop_id"] == crop_id
    assert "yield_t_ha" in comparison["metrics"]
    assert comparison["metrics"]["yield_t_ha"]["better"] is True

    # 12) أثر المحركات والقرار النهائي: السلسلة مكتملة ومحكومة بالمصدر.
    trace = {
        "field_created": field_record["field_id"],
        "lab_state": state.value,
        "crop_card": crop_id,
        "current_growth_stage": current_stage(crop_id, 70)["name_ar"],
        "selected_satellite_layers": [ndvi_mid.tile_url, msi_mid.tile_url],
        "sensor_observations": sensor_batch["accepted_count"],
        "irrigation_recommendation_m3_ha_mid": irrigation_m3_by_stage[70],
        "season_budget_lines": len(budget),
        "operation_records": summary.record_count,
        "variance_items": len(variances),
        "recommendations": [r.code for r in recs],
        "yield_interval_status": yint["status_ar"],
        "comparison_verdict": comparison["verdict_ar"],
        "erp_projection_mode": "projection_only",
        "inventory_projection_mode": "projection_only",
    }
    assert trace["lab_state"] == "ready"
    assert trace["irrigation_recommendation_m3_ha_mid"] > 0
    assert trace["operation_records"] == 8
    assert trace["yield_interval_status"] == "معايَر"
    assert trace["erp_projection_mode"] == "projection_only"
