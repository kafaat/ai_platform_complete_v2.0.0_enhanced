"""Unit tests for SAHOOL Core Phase 0a."""

import math

import pytest
from core.engines.fao56 import (
    CropKcProfile,
    GrowthStage,
    SoilZone,
    WeatherDay,
    compute_irrigation,
    kc_for_age,
    leaching_requirement,
    penman_monteith_et0,
    salinity_stress_ks,
)
from core.engines.fusion import (
    Confidence,
    IndexReading,
    diagnose_stress,
    ensemble_variance,
    fuse_health,
)
from core.engines.fuzzy import (
    TrapezoidParams,
    ascending_score,
    descending_score,
    trapezoidal_score,
)
from core.engines.market_analyzer import (
    PriceRisk,
    analyse_market,
    classify_price_risk,
    coefficient_of_variation,
)


# ── FAO-56 ───────────────────────────────────────────────────
class TestFAO56:
    def _weather(self):
        return WeatherDay(42, 22, 25, 3.5, 27, 16.15, 1100, 200)

    def _crop(self):
        return CropKcProfile("sorghum", 0.30, 1.05, 0.55, [20, 35, 40, 30], 6.8, 16.0)

    def test_et0_positive_and_reasonable(self):
        et0 = penman_monteith_et0(self._weather())
        # Hot arid summer day -> ET0 typically 8-12 mm
        assert 5.0 < et0 < 15.0

    def test_kc_stages(self):
        crop = self._crop()
        assert kc_for_age(crop, 10)[1] == GrowthStage.INITIAL
        assert kc_for_age(crop, 40)[1] == GrowthStage.DEVELOPMENT
        assert kc_for_age(crop, 80)[1] == GrowthStage.MID_SEASON
        assert kc_for_age(crop, 120)[1] == GrowthStage.LATE_SEASON

    def test_kc_mid_equals_card_value(self):
        crop = self._crop()
        kc, stage = kc_for_age(crop, 70)
        assert stage == GrowthStage.MID_SEASON
        assert kc == 1.05

    def test_salinity_no_stress_below_threshold(self):
        crop = self._crop()
        assert salinity_stress_ks(crop, 5.0) == 1.0

    def test_salinity_stress_above_threshold(self):
        crop = self._crop()
        ks = salinity_stress_ks(crop, 8.8)  # 2 dS/m above 6.8
        assert 0.0 < ks < 1.0
        # 16% per dS/m * 2 = 32% loss -> Ks ~ 0.68
        assert abs(ks - 0.68) < 0.01

    def test_leaching_requirement(self):
        lr = leaching_requirement(water_ec=2.0, crop_threshold_ece=6.8)
        assert 0.0 < lr < 0.5

    def test_sandy_needs_more_frequent_irrigation(self):
        w, crop = self._weather(), self._crop()
        sandy = SoilZone("s", "sandy", 80, 0.5, 1.15, "fast", 60)
        loam = SoilZone("l", "loam", 180, 0.55, 0.95, "medium", 80)
        r_sandy = compute_irrigation(w, crop, sandy, 50, 5.5, 2.0)
        r_loam = compute_irrigation(w, crop, loam, 50, 5.5, 2.0)
        # sandy has lower TAW -> shorter interval
        assert r_sandy.irrigation_interval_days < r_loam.irrigation_interval_days


# ── Fuzzy ────────────────────────────────────────────────────
class TestFuzzy:
    def test_dead_zone_returns_zero(self):
        p = TrapezoidParams(4.0, 5.0, 6.0, 7.0)
        assert trapezoidal_score(3.5, p) == 0.0  # below acceptable
        assert trapezoidal_score(8.0, p) == 0.0  # above acceptable

    def test_optimal_plateau(self):
        p = TrapezoidParams(4.0, 5.0, 6.0, 7.0)
        assert trapezoidal_score(5.5, p) == 1.0

    def test_shoulders_linear(self):
        p = TrapezoidParams(4.0, 6.0, 6.0, 8.0)
        assert trapezoidal_score(5.0, p) == 0.5  # halfway up rising shoulder

    def test_descending_salinity(self):
        assert descending_score(0.5, 1.0, 2.0) == 1.0  # below optimal
        assert descending_score(2.5, 1.0, 2.0) == 0.0  # above acceptable
        assert descending_score(1.5, 1.0, 2.0) == 0.5  # halfway

    def test_ascending_organic_matter(self):
        assert ascending_score(3.0, 1.0, 2.0) == 1.0
        assert ascending_score(0.5, 1.0, 2.0) == 0.0


# ── Fusion ───────────────────────────────────────────────────
class TestFusion:
    def test_correlated_indices_dont_reduce_variance_much(self):
        """Same-family (correlated) fusion barely helps — the honest math."""
        same_family = [
            IndexReading("ndvi", 0.6, 0.1, 0.5, "optical"),
            IndexReading("evi2", 0.6, 0.1, 0.5, "optical"),
        ]
        cross_family = [
            IndexReading("ndvi", 0.6, 0.1, 0.5, "optical"),
            IndexReading("sar_vh", 0.6, 0.1, 0.5, "sar"),
        ]
        var_same = ensemble_variance(same_family)
        var_cross = ensemble_variance(cross_family)
        # cross-family fusion should yield LOWER variance (more independent)
        assert var_cross < var_same

    def test_cloud_shifts_to_sar(self):
        readings = [
            IndexReading("ndvi", 0.6, 0.1, 0.5, "optical"),
            IndexReading("sar_vh", 0.55, 0.12, 0.5, "sar"),
        ]
        res = fuse_health(readings, cloud_cover_pct=40.0)
        assert res.dominant_family == "sar"

    def test_diagnostic_tree_water_stress(self):
        d = diagnose_stress(
            ndmi=0.1, cwsi=0.7, ndre=0.5, ndvi=0.6, salinity_index=0.1, ec_trend="stable"
        )
        assert d["cause"] == "water_stress"
        assert d["confidence"] == Confidence.HIGH

    def test_diagnostic_tree_unknown(self):
        d = diagnose_stress(
            ndmi=0.5, cwsi=0.3, ndre=0.5, ndvi=0.6, salinity_index=0.1, ec_trend="stable"
        )
        assert d["cause"] == "unknown"


# ── Market ───────────────────────────────────────────────────
class TestMarket:
    def test_cv_needs_three_points(self):
        assert coefficient_of_variation([100, 200]) is None
        assert coefficient_of_variation([100, 110, 105]) is not None

    def test_high_volatility_classified(self):
        # widely varying prices -> high CV
        cv = coefficient_of_variation([100, 300, 50, 400, 80])
        assert classify_price_risk(cv) == PriceRisk.HIGH

    def test_no_data_returns_unknown(self):
        sig = analyse_market("x", [])
        assert sig.price_risk == PriceRisk.UNKNOWN
        assert sig.data_quality == "none"


# ── No fabricated numbers guard ──────────────────────────────
class TestNoFakeNumbers:
    def test_core_crop_card_has_no_calibration(self):
        """ARCHITECTURAL INVARIANT: core crop cards must NOT contain
        calibration, yield, or zone_factor — those live in districts/tenant."""
        import os

        import yaml

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "core",
            "crop_cards",
            "sorghum.yaml",
        )
        card = yaml.safe_load(open(path, encoding="utf-8"))
        assert "calibration" not in card, "core card must not have calibration"
        assert "yield_estimate" not in card
        assert "zone_factor" not in card

    def test_core_has_no_farm_data(self):
        """No Al-Jawf/Sakha/well data may leak into core crop cards."""
        import os

        path = os.path.join(os.path.dirname(__file__), "..", "core", "crop_cards")
        for fn in os.listdir(path):
            if not fn.endswith(".yaml"):
                continue
            text = open(os.path.join(path, fn), encoding="utf-8").read().lower()
            for forbidden in ["sakha", "6.17", "142ha", "w1", "w8"]:
                assert forbidden not in text, f"{forbidden} leaked into {fn}"


# ── Provenance (the constitution, enforced) ──────────────────
class TestProvenance:
    def test_golden_rule_weakest_link(self):
        from core.provenance import Confidence, Provenance, Stage, Status

        strong = Provenance("a", 1, "u", Stage.RAW, Status.PHYSICS, "s", "g", 0.05, "v")
        weak = Provenance("b", 2, "u", Stage.RAW, Status.CALIBRATED, "s", "g", 0.30, "v")
        derived = Provenance(
            "c", 2, "u", Stage.DERIVED, Status.PHYSICS, "s", "g", 0.05, "v", inputs=[strong, weak]
        )
        # despite own low error, confidence bounded by weak input (30%)
        assert derived.confidence == Confidence.LOW

    def test_pending_has_no_value(self):
        from core.provenance import pending

        y = pending("yield", "t/ha", "weighed harvest")
        assert y.value is None
        assert "قيد المعايرة" in y.explain_ar()

    def test_error_propagation_multiply(self):
        from core.provenance import Provenance, Stage, Status, propagate_multiply

        a = Provenance("a", 1, "u", Stage.RAW, Status.PHYSICS, "s", "g", 0.08, "v")
        b = Provenance("b", 1, "u", Stage.RAW, Status.PHYSICS, "s", "g", 0.05, "v")
        err = propagate_multiply(a, b)
        # quadrature: sqrt(0.08^2 + 0.05^2) ~ 0.094
        assert abs(err - 0.0943) < 0.001

    def test_confidence_categories(self):
        from core.provenance import Confidence, confidence_from_error

        assert confidence_from_error(0.05) == Confidence.HIGH
        assert confidence_from_error(0.20) == Confidence.MEDIUM
        assert confidence_from_error(0.40) == Confidence.LOW
