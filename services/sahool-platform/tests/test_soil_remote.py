"""Tests for remote-sensing soil texture indicator (BSI) — guides, never governs."""

from core.spatial.pipeline import compute_bsi_from_bands, estimate_soil_texture


class TestSoilRemoteSensing:
    def test_bsi_higher_for_bare_soil(self):
        bare = compute_bsi_from_bands(swir1=0.35, red=0.30, nir=0.25, blue=0.20)
        veg = compute_bsi_from_bands(swir1=0.20, red=0.10, nir=0.45, blue=0.08)
        assert bare > veg  # bare soil has higher BSI

    def test_bsi_zero_denominator_safe(self):
        assert compute_bsi_from_bands(0, 0, 0, 0) == 0.0

    def test_texture_always_low_confidence(self):
        # CRITICAL: remote sensing soil texture is never high-confidence
        for bsi in (0.35, 0.15, -0.05, -0.2):
            r = estimate_soil_texture(bsi, ndvi=0.1)
            assert r["confidence"] == "low"

    def test_no_texture_under_vegetation(self):
        # cannot estimate soil texture through dense canopy
        r = estimate_soil_texture(0.2, ndvi=0.65)
        assert r["texture"] is None
        assert r["confidence"] == "none"

    def test_texture_always_directs_to_field_sample(self):
        # guides, never governs: must always point to lab/field confirmation
        r = estimate_soil_texture(0.35, ndvi=0.1)
        assert "مختبر" in r["note_ar"] or "حقلية" in r["note_ar"]

    def test_sandier_for_higher_bsi(self):
        sandy = estimate_soil_texture(0.35, ndvi=0.1)["texture"]
        clay = estimate_soil_texture(-0.15, ndvi=0.1)["texture"]
        assert "رملي" in sandy
        assert "طيني" in clay or "طين" in clay


class TestSoilZoneClassification:
    def _bbox(self):
        from core.spatial.indicators import GeoBBox

        return GeoBBox(min_lon=44.94, min_lat=16.08, max_lon=44.95, max_lat=16.09)

    def test_detects_distinct_texture_zones(self):
        from core.spatial.indicators import classify_soil_zones

        bsi = [[0.35, 0.35, 0.35, -0.15, -0.15, -0.15]] * 3
        ndvi = [[0.1] * 6 for _ in range(3)]
        zones = classify_soil_zones(bsi, ndvi, self._bbox())
        assert len(zones) == 2
        textures = {z.texture_class for z in zones}
        assert any("رملي" in t for t in textures)
        assert any("طين" in t for t in textures)

    def test_skips_under_vegetation(self):
        from core.spatial.indicators import classify_soil_zones

        bsi = [[0.35] * 6] * 3
        ndvi = [[0.7] * 6 for _ in range(3)]  # dense canopy
        assert classify_soil_zones(bsi, ndvi, self._bbox()) == []

    def test_always_low_confidence_and_directs_sampling(self):
        from core.spatial.indicators import classify_soil_zones

        bsi = [[0.35] * 6] * 3
        ndvi = [[0.1] * 6 for _ in range(3)]
        zones = classify_soil_zones(bsi, ndvi, self._bbox())
        assert all(z.confidence == "low" for z in zones)
        assert all(z.directs_sampling for z in zones)

    def test_homogeneous_field_single_zone(self):
        from core.spatial.indicators import classify_soil_zones

        bsi = [[0.35] * 6] * 3  # all sandy
        ndvi = [[0.1] * 6 for _ in range(3)]
        zones = classify_soil_zones(bsi, ndvi, self._bbox())
        assert len(zones) == 1


class TestSoilDiscriminationIndices:
    def test_clay_ratio_higher_for_clay(self):
        from core.spatial.pipeline import clay_minerals_ratio

        assert clay_minerals_ratio(0.30, 0.25) > 1.0  # clay signal
        assert clay_minerals_ratio(0, 0) == 0.0  # safe

    def test_iron_ratio_detects_iron(self):
        from core.spatial.pipeline import iron_oxide_ratio

        assert iron_oxide_ratio(0.35, 0.20) > 1.3  # iron-rich
        assert iron_oxide_ratio(0.20, 0) == 0.0  # safe

    def test_refine_keeps_low_confidence(self):
        from core.spatial.pipeline import refine_soil_texture

        r = refine_soil_texture(0.32, 0.1, clay_ratio=1.15, iron_ratio=1.4)
        assert r["confidence"] == "low"  # never high from remote sensing
        assert "مخبري" in r["note_ar"]

    def test_refine_flags_clay_contradiction(self):
        from core.spatial.pipeline import refine_soil_texture

        # BSI says sandy, but clay ratio high → should note contradiction
        r = refine_soil_texture(0.32, 0.1, clay_ratio=1.15)
        assert "طمي" in r["note_ar"]

    def test_refine_skips_under_vegetation(self):
        from core.spatial.pipeline import refine_soil_texture

        r = refine_soil_texture(0.3, 0.7, clay_ratio=1.2)  # dense canopy
        assert r["texture"] is None


class TestGrowthStageDetection:
    def test_short_series_no_stage(self):
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.2)])
        assert r["stage"] is None

    def test_emergence_low_ndvi(self):
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.15), (25, 0.18), (40, 0.22)])
        assert r["stage"] == "emergence"

    def test_senescence_declining(self):
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.3), (60, 0.85), (110, 0.45)])
        assert r["stage"] == "senescence"

    def test_stage_clean_series_estimate_confidence(self):
        # clean (non-noisy) series → estimate; never "measured"/"high"
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.2), (50, 0.6), (90, 0.82)])
        assert r["confidence"] in ("estimate", "low")  # never measured/high

    def test_crop_consistency_flags_mismatch(self):
        from core.spatial.pipeline import crop_type_consistency_check

        r = crop_type_consistency_check(0.35, "قمح", (0.7, 0.9))
        assert not r["consistent"]
        r2 = crop_type_consistency_check(0.82, "قمح", (0.7, 0.9))
        assert r2["consistent"]


class TestLAI:
    def test_lai_increases_with_ndvi(self):
        from core.spatial.pipeline import estimate_lai_from_ndvi

        low = estimate_lai_from_ndvi(0.3)["lai"]
        high = estimate_lai_from_ndvi(0.8)["lai"]
        assert high > low

    def test_lai_bare_soil_near_zero(self):
        from core.spatial.pipeline import estimate_lai_from_ndvi

        assert estimate_lai_from_ndvi(0.15)["lai"] == 0.0

    def test_lai_always_estimate(self):
        from core.spatial.pipeline import estimate_lai_from_ndvi

        assert estimate_lai_from_ndvi(0.6)["confidence"] == "estimate"

    def test_lai_invalid_ndvi(self):
        from core.spatial.pipeline import estimate_lai_from_ndvi

        assert estimate_lai_from_ndvi(-0.1)["lai"] is None


class TestPhenologyCloudNoise:
    def test_clean_series_normal_confidence(self):
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.2), (40, 0.5), (70, 0.75)])
        assert r["cloud_noise_detected"] is False
        assert r["confidence"] == "estimate"

    def test_noisy_series_flagged_low_confidence(self):
        # FIX: cloud-induced spikes must be detected and lower confidence
        from core.spatial.pipeline import detect_growth_stage_from_ndvi

        r = detect_growth_stage_from_ndvi([(10, 0.5), (20, 0.1), (30, 0.55), (40, 0.08), (50, 0.6)])
        assert r["cloud_noise_detected"] is True
        assert r["confidence"] == "low"
