"""Tests for Tier 2 modules:
- multi_season_analytics: trends + rotation
- transfer_learning: cross-district knowledge with tenant isolation
- vrt_manual_maps: Human-Executable Precision Agriculture + PHI safety
"""

from core.multi_season_analytics import (
    TrendDirection,
    analyze_salinity_trend,
    analyze_yield_trend,
    detect_rotation_pattern,
    multi_season_summary,
)
from core.transfer_learning import (
    DistrictProfile,
    TransferConfidence,
    suggest_transfer,
    transfer_summary,
)
from core.vrt_manual_maps import (
    TreatmentColor,
    TreatmentType,
    build_execution_map,
    build_zone_treatment,
    map_summary_for_print,
)

# ─── Multi-Season Analytics ──────────────────────────────────────


class TestYieldTrend:
    def test_improving_trend_detected(self):
        trend = analyze_yield_trend(
            [
                {"season_year": 2023, "yield_t_ha": 3.0},
                {"season_year": 2024, "yield_t_ha": 3.3},
                {"season_year": 2025, "yield_t_ha": 3.6},
            ]
        )
        assert trend.direction == TrendDirection.IMPROVING
        assert trend.change_pct_total == 20.0

    def test_declining_trend_detected(self):
        trend = analyze_yield_trend(
            [
                {"season_year": 2023, "yield_t_ha": 4.0},
                {"season_year": 2024, "yield_t_ha": 3.5},
                {"season_year": 2025, "yield_t_ha": 3.0},
            ]
        )
        assert trend.direction == TrendDirection.DECLINING

    def test_stable_within_5pct(self):
        # ضمن ±5% = مستقرّ، لا "trend"
        trend = analyze_yield_trend(
            [
                {"season_year": 2024, "yield_t_ha": 3.50},
                {"season_year": 2025, "yield_t_ha": 3.55},
            ]
        )
        assert trend.direction == TrendDirection.STABLE

    def test_single_season_insufficient(self):
        # CRITICAL: لا "trend" من نقطة واحدة (صفر اختراع)
        trend = analyze_yield_trend(
            [
                {"season_year": 2025, "yield_t_ha": 3.5},
            ]
        )
        assert trend.direction == TrendDirection.INSUFFICIENT
        assert trend.first_value is None

    def test_empty_input_insufficient(self):
        trend = analyze_yield_trend([])
        assert trend.direction == TrendDirection.INSUFFICIENT

    def test_none_values_filtered(self):
        # CRITICAL: None yields لا تُختلق
        trend = analyze_yield_trend(
            [
                {"season_year": 2023, "yield_t_ha": None},
                {"season_year": 2024, "yield_t_ha": 3.3},
                {"season_year": 2025, "yield_t_ha": None},
            ]
        )
        # فقط 2024 صالح → INSUFFICIENT
        assert trend.direction == TrendDirection.INSUFFICIENT
        assert trend.seasons_analyzed == 1

    def test_confidence_grows_with_seasons(self):
        # 2 موسم = low، 3 = medium، 4+ = high
        t2 = analyze_yield_trend(
            [
                {"season_year": 2024, "yield_t_ha": 3.0},
                {"season_year": 2025, "yield_t_ha": 3.5},
            ]
        )
        t4 = analyze_yield_trend(
            [
                {"season_year": 2022, "yield_t_ha": 3.0},
                {"season_year": 2023, "yield_t_ha": 3.2},
                {"season_year": 2024, "yield_t_ha": 3.4},
                {"season_year": 2025, "yield_t_ha": 3.6},
            ]
        )
        assert t2.confidence == "low"
        assert t4.confidence == "high"


class TestSalinityTrend:
    def test_increasing_salinity_alerts(self):
        # تزايد الملوحة = تدهور (DECLINING في المعنى الزراعي)
        trend = analyze_salinity_trend(
            [
                {"season_year": 2023, "ec_ds_m": 1.0},
                {"season_year": 2024, "ec_ds_m": 1.3},
                {"season_year": 2025, "ec_ds_m": 1.7},
            ]
        )
        assert trend.direction == TrendDirection.DECLINING
        assert "⚠️" in trend.reason_ar or "متزايدة" in trend.reason_ar


class TestRotationPattern:
    def test_monoculture_detected(self):
        # 3 مواسم نفس المحصول → diversity منخفض
        r = detect_rotation_pattern(
            "fld_03",
            [
                {"season_year": 2023, "crop_id": "wheat"},
                {"season_year": 2024, "crop_id": "wheat"},
                {"season_year": 2025, "crop_id": "wheat"},
            ],
        )
        assert r.most_used_crop == "wheat"
        assert r.most_used_pct == 100.0
        assert r.diversity_index < 0.5

    def test_diverse_rotation(self):
        r = detect_rotation_pattern(
            "fld_03",
            [
                {"season_year": 2023, "crop_id": "wheat"},
                {"season_year": 2024, "crop_id": "sorghum"},
                {"season_year": 2025, "crop_id": "barley"},
            ],
        )
        assert r.diversity_index == 1.0  # كل المحاصيل فريدة


# ─── Transfer Learning ───────────────────────────────────────────


class TestTransferLearning:
    def _source(self, **kw):
        defaults = dict(
            district_id="src",
            tenant_id="tnt_001",
            governorate_id="al_bayda",
            crop_seasons_count=4,
            avg_yield_t_ha=3.5,
            typical_salinity_ds_m=1.3,
            dominant_soil_type="clay_loam",
            common_crops=["wheat"],
            avg_zone_factor=0.92,
        )
        defaults.update(kw)
        return DistrictProfile(**defaults)

    def _target(self, **kw):
        defaults = dict(
            district_id="tgt",
            tenant_id="tnt_001",
            governorate_id="al_bayda",
            dominant_soil_type="clay_loam",
            typical_salinity_ds_m=1.4,
            common_crops=[],
        )
        defaults.update(kw)
        return DistrictProfile(**defaults)

    def test_similar_districts_high_confidence(self):
        # مشابهتان جدّاً → HIGH
        sugg = suggest_transfer(self._target(), [self._source()], crop="wheat")
        assert sugg.confidence in (TransferConfidence.HIGH, TransferConfidence.MEDIUM)
        assert sugg.suggested_zone_factor is not None

    def test_cross_tenant_blocked(self):
        # CRITICAL: لا نقل بين tenants أبداً
        other = self._source(tenant_id="tnt_OTHER")
        sugg = suggest_transfer(self._target(), [other], crop="wheat")
        assert sugg.confidence == TransferConfidence.NONE

    def test_no_source_for_crop(self):
        # source ليس لديه هذا المحصول
        src = self._source(common_crops=["sorghum"])  # لا wheat
        sugg = suggest_transfer(self._target(), [src], crop="wheat")
        assert sugg.confidence == TransferConfidence.NONE

    def test_low_similarity_blocked(self):
        # ظروف مختلفة جدّاً → لا نقل
        src = self._source(
            governorate_id="other_gov", dominant_soil_type="sandy", typical_salinity_ds_m=5.0
        )
        sugg = suggest_transfer(self._target(), [src], crop="wheat")
        # قد يكون LOW أو NONE حسب السياق
        assert sugg.confidence in (TransferConfidence.NONE, TransferConfidence.LOW)

    def test_no_invention_when_empty(self):
        # CRITICAL: لا candidates → "none" صراحة
        sugg = suggest_transfer(self._target(), [], crop="wheat")
        assert sugg.confidence == TransferConfidence.NONE
        assert "ابدأ بمعايرة محلّية" in sugg.notes_ar

    def test_transferred_zone_factor_dampened(self):
        # CRITICAL: المنقول يُخفَّف نحو 1.0 حسب الثقة
        # source: zone_factor=0.85
        src = self._source(avg_zone_factor=0.85)
        sugg = suggest_transfer(self._target(), [src], crop="wheat")
        if sugg.suggested_zone_factor is not None:
            # المُقتَرح يجب أن يكون بين 0.85 و 1.0 (لا "نسخ مباشر")
            assert 0.85 <= sugg.suggested_zone_factor <= 1.0


# ─── VRT Manual Maps ─────────────────────────────────────────────


class TestVRTManualMaps:
    def test_simple_zone_treatment(self):
        z = build_zone_treatment(
            "z_1",
            TreatmentType.NITROGEN,
            rate_per_ha=80,
            rate_unit="kg/ha",
            area_ha=2.5,
            product_name_ar="يوريا",
            rate_range_for_color=(40, 100),
        )
        assert z.expected_amount == 200.0
        assert z.color != TreatmentColor.GRAY

    def test_phi_blocked_strips_rate(self):
        # CRITICAL: PHI blocked → لا rate حتى لو طُلب (السلامة لا تُتخطّى)
        z = build_zone_treatment(
            "z_p",
            TreatmentType.PESTICIDE,
            rate_per_ha=1.5,
            rate_unit="L/ha",
            area_ha=2.0,
            phi_status="blocked",
            days_to_safe=7,
        )
        assert z.rate_per_ha is None
        assert any("PHI" in s for s in z.safety_notes_ar)

    def test_phi_undefined_blocks_pesticide(self):
        # CRITICAL: phi_status=None للمبيد → يُحرَس أيضاً
        z = build_zone_treatment(
            "z_p",
            TreatmentType.PESTICIDE,
            rate_per_ha=1.5,
            rate_unit="L/ha",
            area_ha=2.0,
            phi_status=None,
        )
        assert z.rate_per_ha is None

    def test_nitrogen_no_phi_check(self):
        # تسميد ليس safety-critical → rate يبقى
        z = build_zone_treatment(
            "z_n", TreatmentType.NITROGEN, rate_per_ha=60, rate_unit="kg/ha", area_ha=2.0
        )
        assert z.rate_per_ha == 60

    def test_color_coding_progression(self):
        # rate low/mid/high → green/yellow/red
        low = build_zone_treatment(
            "z",
            TreatmentType.NITROGEN,
            rate_per_ha=45,
            rate_unit="kg/ha",
            area_ha=1.0,
            rate_range_for_color=(40, 100),
        )
        high = build_zone_treatment(
            "z",
            TreatmentType.NITROGEN,
            rate_per_ha=95,
            rate_unit="kg/ha",
            area_ha=1.0,
            rate_range_for_color=(40, 100),
        )
        assert low.color == TreatmentColor.GREEN
        assert high.color == TreatmentColor.RED

    def test_missing_data_returns_gray(self):
        # CRITICAL: لا rate_range → gray (لا اختراع لون)
        z = build_zone_treatment(
            "z", TreatmentType.NITROGEN, rate_per_ha=50, rate_unit="kg/ha", area_ha=1.0
        )
        assert z.color == TreatmentColor.GRAY

    def test_full_execution_map(self):
        zones = [
            build_zone_treatment(
                f"z_{i}",
                TreatmentType.NITROGEN,
                rate_per_ha=50 + i * 10,
                rate_unit="kg/ha",
                area_ha=2.0,
                rate_range_for_color=(40, 100),
            )
            for i in range(3)
        ]
        emap = build_execution_map("fld_03", "حقل القمح", TreatmentType.NITROGEN, zones)
        assert emap.total_area_ha == 6.0
        assert emap.total_product_needed > 0
        assert len(emap.execution_steps_ar) == 3
        assert "vrt_" in emap.map_id

    def test_pesticide_map_includes_safety_warnings(self):
        # خريطة مبيدات يجب أن تحوي تحذيرات السلامة
        zones = [
            build_zone_treatment(
                "z",
                TreatmentType.PESTICIDE,
                rate_per_ha=1.0,
                rate_unit="L/ha",
                area_ha=1.0,
                phi_status="safe",
            )
        ]
        emap = build_execution_map("fld", "x", TreatmentType.PESTICIDE, zones)
        # تحذيرات يجب أن تكون موجودة
        assert any("الأطفال" in w or "الرياح" in w for w in emap.safety_warnings_ar)
