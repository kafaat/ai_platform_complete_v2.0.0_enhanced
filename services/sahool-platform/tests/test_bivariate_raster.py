"""Tests for bivariate_raster (NDVI × NDMI dual classification).
Honest pixel combination (no averaging), diagnostic clarity, dimension safety."""

import io

from core.spatial.bivariate_raster import bivariate_legend, combine_grids_to_png, diagnose_pixel
from PIL import Image


class TestDiagnosticCombinations:
    """الجوهر العلمي: كل تركيبة لها تشخيص مختلف لا يكشفه مؤشّر منفرد."""

    def test_low_ndvi_dry_is_drought_stress(self):
        d = diagnose_pixel(value_ndvi=0.1, value_ndmi=-0.2)
        assert d["ndvi_class"] == "low"
        assert d["ndmi_class"] == "dry"
        assert "جفاف" in d["diagnostic_ar"]

    def test_low_ndvi_with_water_reveals_pest_or_disease(self):
        # CRITICAL: التشخيص الذي لا يكشفه NDVI وحده
        # نبات سيّء + ماء جيّد = ليس جفافاً، بل آفة/مرض/ملوحة
        d = diagnose_pixel(value_ndvi=0.15, value_ndmi=0.3)
        assert d["ndvi_class"] == "low"
        assert d["ndmi_class"] == "good"
        # التشخيص يجب أن يذكر آفة/مرض
        diag = d["diagnostic_ar"]
        assert "آفة" in diag or "مرض" in diag or "ملوحة" in diag

    def test_good_ndvi_dry_warns_to_irrigate(self):
        # نموّ جيّد لكن ماء ينضب → ريّ قريب
        d = diagnose_pixel(value_ndvi=0.5, value_ndmi=-0.1)
        assert d["ndvi_class"] == "good"
        assert d["ndmi_class"] == "dry"
        assert "اروِ" in d["diagnostic_ar"] or "نقص ماء" in d["diagnostic_ar"]

    def test_high_ndvi_wet_full_health(self):
        d = diagnose_pixel(value_ndvi=0.85, value_ndmi=0.5)
        assert d["ndvi_class"] == "high"
        assert d["ndmi_class"] == "wet"
        assert "صحّة" in d["diagnostic_ar"]


class TestPixelCombination:
    def test_dual_grids_produce_valid_png(self):
        r = combine_grids_to_png(
            grid_ndvi=[[0.5, 0.6], [0.7, 0.4]],
            grid_ndmi=[[0.3, 0.4], [0.5, 0.2]],
            south=0,
            west=0,
            north=1,
            east=1,
        )
        assert r.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert r.indicator_x == "ndvi"
        assert r.indicator_y == "ndmi"

    def test_any_none_makes_transparent_pixel(self):
        # CRITICAL: إن كان أيّ مؤشّر مجهولاً → شفّاف (لا اختراع)
        r = combine_grids_to_png(
            grid_ndvi=[[0.5, None]], grid_ndmi=[[None, 0.3]], south=0, west=0, north=1, east=1
        )
        img = Image.open(io.BytesIO(r.png_bytes))
        # كلا البكسلين فيهما None → شفّاف
        assert img.getpixel((0, 0))[3] == 0
        assert img.getpixel((1, 0))[3] == 0
        assert r.transparent_pixels == 2

    def test_class_counts_accurate(self):
        r = combine_grids_to_png(
            grid_ndvi=[[0.1, 0.1]],  # كلاهما low
            grid_ndmi=[[-0.2, -0.2]],  # كلاهما dry
            south=0,
            west=0,
            north=1,
            east=1,
        )
        assert r.class_counts.get(("low", "dry")) == 2


class TestDimensionValidation:
    def test_mismatched_dimensions_raises(self):
        # CRITICAL: لا إعادة عيّنة وهمية — الأبعاد المختلفة خطأ صريح
        try:
            combine_grids_to_png(
                grid_ndvi=[[0.5, 0.5]], grid_ndmi=[[0.3]], south=0, west=0, north=1, east=1
            )
            raise AssertionError("كان يجب رفع ValueError")
        except ValueError as e:
            assert "أبعاد" in str(e) or "مختلفة" in str(e)

    def test_empty_grid_raises(self):
        try:
            combine_grids_to_png(grid_ndvi=[], grid_ndmi=[], south=0, west=0, north=1, east=1)
            raise AssertionError
        except ValueError as e:
            assert "فارغة" in str(e)


class TestUnknownValueHandling:
    def test_diagnose_unknown_returns_none_class(self):
        d = diagnose_pixel(value_ndvi=None, value_ndmi=0.3)
        assert d["class"] is None
        assert "بيانات ناقصة" in d["diagnostic_ar"]

    def test_out_of_range_treated_as_unknown(self):
        # NDVI=5 خارج النطاق [0,1] → معامَل كمجهول (لا تخمين)
        d = diagnose_pixel(value_ndvi=5.0, value_ndmi=0.3)
        assert d.get("class") is None


class TestLegend:
    def test_legend_has_all_16_combinations(self):
        legend = bivariate_legend()
        assert len(legend) == 16  # 4 NDVI × 4 NDMI

    def test_legend_has_diagnostic_for_each(self):
        legend = bivariate_legend()
        assert all(item.get("diagnostic_ar") for item in legend)
