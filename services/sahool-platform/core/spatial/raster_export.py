"""
sahool_core.spatial.raster_export
==================================
تصدير المؤشّرات كطبقات بكسلية (PNG image overlay) فوق الخريطة.

الفجوة المسدودة: detect_zones_of_interest يُنتج grid (raster خام)،
copernicus يجلب raster، لكن لا تحويل بكسلي للعرض. هذا يكمل سلسلة
الاستشعار: قياس فضائي → grid → PNG ملوّن → imageOverlay في الواجهة.

التمييز الفنّي:
  • Tiled (WMTS): مناسب لمساحات قارّيّة (NASA GIBS) — over-engineering لحقل.
  • ImageOverlay: PNG واحد على حدود الحقل — كافٍ لـ≤142 هـ (مزرعة).

اخترنا ImageOverlay. الواجهة تستخدم Leaflet:
    L.imageOverlay(pngBlob, [[south, west], [north, east]]).addTo(map);

المبادئ المحفوظة:
  • التصنيف فئوي (يطابق map_layer.classify_value)، لا rainbow وهمي
  • قيمة None في الـgrid → بكسل شفّاف (alpha=0)، لا أسود وهمي
    "نعلن الجهل بصرياً" — نسخة بصرية من مبدأ "صفر أرقام وهمية"
  • محايد العارض: PNG bytes قياسي، أي مكتبة خرائط تقرأه
  • Pillow (PIL) فقط — لا rasterio/GDAL ثقيلة
"""

from __future__ import annotations

import io
from dataclasses import dataclass

# تصنيف الألوان (مزامن مع map_layer._INDICATOR_BANDS)
# كلّ نطاق: (lo, hi, R, G, B) — RGB صريحة لتجنّب تحويل hex
_BAND_COLORS = {
    "ndvi": [
        (0.0, 0.2, 139, 69, 19),  # بنّي — أرض عارية
        (0.2, 0.4, 218, 165, 32),  # ذهبي — متوسّط
        (0.4, 0.7, 144, 238, 144),  # أخضر فاتح — جيّد
        (0.7, 1.0, 34, 139, 34),  # أخضر داكن — كثيف
    ],
    "ndmi": [
        (-1.0, 0.0, 210, 105, 30),
        (0.0, 0.2, 244, 164, 96),
        (0.2, 0.4, 135, 206, 235),
        (0.4, 1.0, 70, 130, 180),
    ],
    "salinity_si": [
        (0.0, 0.10, 144, 238, 144),  # منخفض
        (0.10, 0.30, 255, 215, 0),  # متوسّط — تحذير
        (0.30, 1.0, 220, 20, 60),  # مرتفع — تنبيه (لكن سقف قرينة فقط)
    ],
}


@dataclass
class RasterExport:
    png_bytes: bytes
    width_px: int
    height_px: int
    bounds: dict  # {"south", "west", "north", "east"}
    indicator: str
    transparent_pixels: int  # عدد البكسل غير المعروف (للصدق الإحصائي)
    total_pixels: int


def _pixel_for_value(value: float | None, bands: list) -> tuple[int, int, int, int]:
    """يُرجع RGBA لقيمة واحدة. None → شفّاف (alpha=0)، لا اختراع."""
    if value is None:
        return (0, 0, 0, 0)  # شفّاف تماماً
    for lo, hi, r, g, b in bands:
        if lo <= value <= hi:
            return (r, g, b, 200)  # شبه شفّاف ليبقى أساس الخريطة مرئياً
    # خارج النطاق المتوقّع → شفّاف (لا نخمّن خارج التصنيف)
    return (0, 0, 0, 0)


def grid_to_png(
    *,
    grid: list[list[float | None]],
    indicator: str,
    south: float,
    west: float,
    north: float,
    east: float,
) -> RasterExport:
    """يحوّل grid قيم المؤشّر إلى PNG ملوّن.

    grid: 2D — grid[row][col]، الصف 0 = شمال، العمود 0 = غرب.
    indicator: ndvi / ndmi / salinity_si — يحدّد الـcolormap.
    bounds: حدود الحقل (lat/lon) — يضعها الواجهة في imageOverlay.

    يُرجع PNG bytes + إحصاء بسيط (كم بكسل شفّاف/مجهول)."""
    # PIL استيراد كسول (في حال لم يُحتج)
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow (PIL) مطلوب لتصدير raster: pip install pillow") from e

    if not grid or not grid[0]:
        raise ValueError("grid فارغ — لا بيانات للتصدير")

    bands = _BAND_COLORS.get(indicator)
    if not bands:
        raise ValueError(f"المؤشّر '{indicator}' غير مدعوم في الـcolormap")

    height = len(grid)
    width = len(grid[0])
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))  # شفّاف افتراضاً
    pixels = img.load()

    transparent_count = 0
    for row in range(height):
        for col in range(width):
            val = grid[row][col] if col < len(grid[row]) else None
            rgba = _pixel_for_value(val, bands)
            pixels[col, row] = rgba
            if rgba[3] == 0:
                transparent_count += 1

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)

    return RasterExport(
        png_bytes=buf.getvalue(),
        width_px=width,
        height_px=height,
        bounds={"south": south, "west": west, "north": north, "east": east},
        indicator=indicator,
        transparent_pixels=transparent_count,
        total_pixels=width * height,
    )


def export_summary(export: RasterExport) -> dict:
    """ملخّص قابل للقراءة (لتسجيل الصدق الإحصائي بصرياً)."""
    coverage_pct = (
        round(100 * (1 - export.transparent_pixels / export.total_pixels), 1)
        if export.total_pixels
        else 0.0
    )
    return {
        "indicator": export.indicator,
        "resolution": f"{export.width_px}×{export.height_px} بكسل",
        "bounds": export.bounds,
        "coverage_pct": coverage_pct,
        "png_size_kb": round(len(export.png_bytes) / 1024, 1),
        "note_ar": (
            f"تغطية {coverage_pct}% — {export.transparent_pixels} بكسل غير معروف (شفّاف)"
            if export.transparent_pixels
            else f"تغطية كاملة ({export.total_pixels} بكسل)"
        ),
    }
