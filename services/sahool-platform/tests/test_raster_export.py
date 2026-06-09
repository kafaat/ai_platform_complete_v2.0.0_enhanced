"""Tests for raster_export (grid → PNG imageOverlay).
Categorical colormap, None → transparent (visual honesty), error on bad input."""

import io

from core.spatial.raster_export import export_summary, grid_to_png
from PIL import Image


class TestPngGeneration:
    def test_basic_grid_produces_valid_png(self):
        grid = [[0.5, 0.6], [0.7, 0.4]]
        r = grid_to_png(grid=grid, indicator="ndvi", south=16.0, west=44.0, north=16.1, east=44.1)
        assert r.png_bytes
        # PNG signature
        assert r.png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        assert r.width_px == 2
        assert r.height_px == 2

    def test_bounds_preserved(self):
        r = grid_to_png(
            grid=[[0.5]], indicator="ndvi", south=16.0, west=44.0, north=16.1, east=44.1
        )
        assert r.bounds == {"south": 16.0, "west": 44.0, "north": 16.1, "east": 44.1}


class TestHonestNullHandling:
    """المبدأ الجوهري: قيمة None → بكسل شفّاف، لا اختراع لون.
    'نعلن الجهل بصرياً' — نسخة بصرية من 'صفر أرقام وهمية'."""

    def test_none_value_becomes_transparent_pixel(self):
        # CRITICAL: قيمة None لا تُلوَّن بأسود (الخطأ الشائع)
        grid = [[None, 0.5], [0.6, None]]
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        img = Image.open(io.BytesIO(r.png_bytes))
        # البكسل (0,0) كان None
        assert img.getpixel((0, 0))[3] == 0, "alpha=0 مطلوب للقيمة المجهولة"
        # البكسل (1,0) معروف
        assert img.getpixel((1, 0))[3] > 0, "البكسل المعروف يجب أن يكون مرئياً"

    def test_transparent_count_accurate(self):
        grid = [[None, 0.5, None], [0.6, None, 0.7]]
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        assert r.transparent_pixels == 3
        assert r.total_pixels == 6

    def test_out_of_range_value_also_transparent(self):
        # القيم خارج النطاق المعرّف (مثلاً NDVI=5.0) → شفّاف (لا تخمين)
        grid = [[5.0]]  # خارج [0,1] لـNDVI
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        img = Image.open(io.BytesIO(r.png_bytes))
        assert img.getpixel((0, 0))[3] == 0


class TestCategoricalColormap:
    """التصنيف فئوي (يطابق map_layer.classify_value)، لا rainbow وهمي."""

    def test_low_ndvi_brown(self):
        grid = [[0.1]]  # نطاق "low" → بنّي
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        img = Image.open(io.BytesIO(r.png_bytes))
        rgba = img.getpixel((0, 0))
        # البنّي: R مرتفع، G و B منخفضان
        assert rgba[0] > rgba[1] and rgba[0] > rgba[2]

    def test_high_ndvi_dark_green(self):
        grid = [[0.85]]  # نطاق "high" → أخضر داكن
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        img = Image.open(io.BytesIO(r.png_bytes))
        rgba = img.getpixel((0, 0))
        # الأخضر يهيمن
        assert rgba[1] > rgba[0] and rgba[1] > rgba[2]


class TestErrorHandling:
    def test_empty_grid_raises(self):
        # CRITICAL: لا نتعامل مع غياب البيانات صامتاً
        try:
            grid_to_png(grid=[], indicator="ndvi", south=0, west=0, north=1, east=1)
            raise AssertionError("كان يجب رفع ValueError")
        except ValueError as e:
            assert "فارغ" in str(e)

    def test_unknown_indicator_raises(self):
        try:
            grid_to_png(grid=[[0.5]], indicator="alien_index", south=0, west=0, north=1, east=1)
            raise AssertionError("كان يجب رفع ValueError")
        except ValueError as e:
            assert "غير مدعوم" in str(e)


class TestExportSummary:
    def test_full_coverage_summary(self):
        grid = [[0.5, 0.6], [0.7, 0.4]]
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        s = export_summary(r)
        assert s["coverage_pct"] == 100.0
        assert "كاملة" in s["note_ar"]

    def test_partial_coverage_reported_honestly(self):
        # 50% بكسل مجهول → يُعلن صراحةً
        grid = [[None, 0.5], [0.6, None]]
        r = grid_to_png(grid=grid, indicator="ndvi", south=0, west=0, north=1, east=1)
        s = export_summary(r)
        assert s["coverage_pct"] == 50.0
        assert "غير معروف" in s["note_ar"]
