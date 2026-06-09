"""
sahool_core.spatial.bivariate_raster
=====================================
دمج مؤشّرين على نفس الخريطة بكسلياً — لا متوسّط، لا اختراع.

الفجوة المسدودة: raster_export يصدّر مؤشّراً واحداً. لكن:
  NDVI منخفض + NDMI جيّد = نبات ضعيف رغم وجود ماء (آفة؟ تربة؟)
  NDVI منخفض + NDMI منخفض = إجهاد جفاف
  NDVI جيّد + NDMI منخفض = نبات يستهلك بسرعة (يحتاج ريّاً قريباً)
  NDVI جيّد + NDMI جيّد = صحّة كاملة

هذه التركيبات الأربع تشخيصية، لا يكشفها مؤشّر منفرد.

التمييز الفنّي عن "overlay stacking" البصري:
  ✗ تكديس طبقتين شفّافتين: ألوان تختلط رياضياً بطريقة لا تعكس الواقع
    (لون "ناتج" لا يقابل تركيبة مفهومة)
  ✓ تصنيف ثنائي مشترك (bivariate classification): كل تركيبة لها لون
    محدّد سلفاً ومعنى تشخيصي. هذا هو معيار رسم خرائط الزراعة الدقيقة.

المبادئ المحفوظة:
  • لا متوسّط، لا تطبيع وهمي
  • أيّ من المؤشّرين None → بكسل شفّاف (الجهل بصرياً)
  • التصنيف فئوي (4×4 = 16 فئة بألوان مختارة بدقّة)
  • متّسق مع raster_export (نفس فئات NDVI الأربع)
"""
from __future__ import annotations

import io
from dataclasses import dataclass


# عتبات كلّ مؤشّر — متطابقة مع raster_export._BAND_COLORS
_NDVI_BANDS = [(0.0, 0.2, "low"), (0.2, 0.4, "med"),
               (0.4, 0.7, "good"), (0.7, 1.0, "high")]
_NDMI_BANDS = [(-1.0, 0.0, "dry"), (0.0, 0.2, "med"),
               (0.2, 0.4, "good"), (0.4, 1.0, "wet")]


# مصفوفة الألوان الثنائية 4×4 — مختارة لتعكس التركيبة التشخيصية
# المحور: NDVI (الصفوف، نمو) × NDMI (الأعمدة، ماء)
# الفكرة: تركيبة الإجهاد (low+dry) حمراء، الصحّة (high+good/wet) خضراء
_BIVARIATE_PALETTE = {
    # NDVI low (نباتي ضعيف)
    ("low",  "dry"):  (165,  42,  42, 200),    # أحمر داكن — إجهاد جفاف
    ("low",  "med"):  (210, 105,  30, 200),    # بنّي محروق — جفاف خفيف
    ("low",  "good"): (218, 165,  32, 200),    # ذهبي — نبات سيّء رغم الماء (آفة/تربة؟)
    ("low",  "wet"):  (138,  43, 226, 200),    # بنفسجي — غمر/مرض (تشخيص نادر)

    # NDVI med (متوسّط)
    ("med",  "dry"):  (205, 133,  63, 200),    # بنّي فاتح
    ("med",  "med"):  (222, 184, 135, 200),    # رمل
    ("med",  "good"): (189, 183, 107, 200),    # كاكي
    ("med",  "wet"):  (143, 188, 143, 200),    # أخضر فاتح — يميل للماء

    # NDVI good (جيّد)
    ("good", "dry"):  (240, 230, 140, 200),    # خاكي فاتح — يحتاج ريّاً قريباً
    ("good", "med"):  (152, 251, 152, 200),    # أخضر شاحب
    ("good", "good"): (144, 238, 144, 200),    # أخضر فاتح
    ("good", "wet"):  ( 60, 179, 113, 200),    # أخضر بحري

    # NDVI high (كثيف)
    ("high", "dry"):  (255, 215,   0, 200),    # ذهبي — مخالف للتوقّع (تحقّق)
    ("high", "med"):  ( 50, 205,  50, 200),    # أخضر ليموني
    ("high", "good"): ( 34, 139,  34, 200),    # أخضر داكن
    ("high", "wet"):  (  0, 100,   0, 200),    # أخضر غاية — صحّة كاملة
}


# التشخيص النصّي لكل تركيبة (للنقر على البكسل في الواجهة)
_DIAGNOSTIC_AR = {
    ("low",  "dry"):  "إجهاد جفاف شديد — أولوية ريّ",
    ("low",  "med"):  "نباتي ضعيف + ماء محدود — افحص الجذور",
    ("low",  "good"): "نباتي ضعيف رغم الماء — آفة/مرض/ملوحة محتملة",
    ("low",  "wet"):  "نباتي ضعيف + ماء زائد — غمر أو مرض جذور",
    ("med",  "dry"):  "نموّ متوسّط مع نقص ماء",
    ("med",  "med"):  "وضع متوسّط — راقب",
    ("med",  "good"): "نموّ متوسّط مع ماء كافٍ",
    ("med",  "wet"):  "نموّ متوسّط مع ماء وفير",
    ("good", "dry"):  "نموّ جيّد لكن الماء ينضب — اروِ قريباً",
    ("good", "med"):  "نموّ جيّد مع ماء متوسّط",
    ("good", "good"): "صحّة جيّدة",
    ("good", "wet"):  "نموّ جيّد مع رطوبة عالية",
    ("high", "dry"):  "نمو كثيف مع نقص ماء — تحقّق ميدانياً",
    ("high", "med"):  "نمو كثيف مع ماء متوسّط",
    ("high", "good"): "صحّة قويّة",
    ("high", "wet"):  "صحّة كاملة",
}


def _classify(value: float | None, bands: list) -> str | None:
    """يُرجع اسم الفئة أو None للقيمة غير المعروفة."""
    if value is None:
        return None
    for lo, hi, name in bands:
        if lo <= value <= hi:
            return name
    return None   # خارج النطاق المتوقّع — كأنه مجهول


@dataclass
class BivariateExport:
    png_bytes: bytes
    width_px: int
    height_px: int
    bounds: dict
    indicator_x: str
    indicator_y: str
    transparent_pixels: int
    total_pixels: int
    class_counts: dict        # {("low","dry"): n_pixels, ...}


def combine_grids_to_png(
    *,
    grid_ndvi: list[list[float | None]],
    grid_ndmi: list[list[float | None]],
    south: float,
    west: float,
    north: float,
    east: float,
) -> BivariateExport:
    """يدمج grid NDVI + grid NDMI بكسلياً → PNG bivariate.

    شرط أساسي: الشبكتان بنفس الأبعاد (نفس البكسلة).
    إن اختلفتا → ValueError صريح (لا إعادة عيّنة وهمية)."""
    # PIL استيراد كسول
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow مطلوب — pip install pillow") from e

    if not grid_ndvi or not grid_ndmi:
        raise ValueError("شبكة فارغة — لا بيانات للدمج")

    h, w = len(grid_ndvi), len(grid_ndvi[0])
    if len(grid_ndmi) != h or len(grid_ndmi[0]) != w:
        raise ValueError(
            f"أبعاد الشبكتين متختلفة: NDVI={h}×{w} مقابل "
            f"NDMI={len(grid_ndmi)}×{len(grid_ndmi[0])} — إعادة العيّنة "
            "خارج نطاق هذه الوحدة (تجنّب الاختراع)")

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pixels = img.load()

    transparent = 0
    counts: dict = {}

    for row in range(h):
        for col in range(w):
            v_ndvi = grid_ndvi[row][col] if col < len(grid_ndvi[row]) else None
            v_ndmi = grid_ndmi[row][col] if col < len(grid_ndmi[row]) else None

            cls_ndvi = _classify(v_ndvi, _NDVI_BANDS)
            cls_ndmi = _classify(v_ndmi, _NDMI_BANDS)

            # أيّ منهما مجهول → بكسل شفّاف
            if cls_ndvi is None or cls_ndmi is None:
                pixels[col, row] = (0, 0, 0, 0)
                transparent += 1
                continue

            key = (cls_ndvi, cls_ndmi)
            color = _BIVARIATE_PALETTE.get(key, (0, 0, 0, 0))
            pixels[col, row] = color
            counts[key] = counts.get(key, 0) + 1

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)

    return BivariateExport(
        png_bytes=buf.getvalue(),
        width_px=w, height_px=h,
        bounds={"south": south, "west": west, "north": north, "east": east},
        indicator_x="ndvi", indicator_y="ndmi",
        transparent_pixels=transparent,
        total_pixels=w * h,
        class_counts=counts,
    )


def bivariate_legend() -> list[dict]:
    """وسيلة إيضاح للوحة الثنائية — جاهزة للعرض في الواجهة."""
    legend = []
    for (ndvi_cls, ndmi_cls), rgba in _BIVARIATE_PALETTE.items():
        legend.append({
            "ndvi_class": ndvi_cls,
            "ndmi_class": ndmi_cls,
            "color_rgba": rgba,
            "diagnostic_ar": _DIAGNOSTIC_AR[(ndvi_cls, ndmi_cls)],
        })
    return legend


def diagnose_pixel(value_ndvi: float | None, value_ndmi: float | None) -> dict:
    """تشخيص بكسل واحد — للنقر التفاعلي على الخريطة."""
    cls_ndvi = _classify(value_ndvi, _NDVI_BANDS)
    cls_ndmi = _classify(value_ndmi, _NDMI_BANDS)
    if cls_ndvi is None or cls_ndmi is None:
        return {
            "ndvi": value_ndvi, "ndmi": value_ndmi,
            "class": None,
            "diagnostic_ar": "بيانات ناقصة — لا تشخيص ممكن",
        }
    return {
        "ndvi": value_ndvi, "ndmi": value_ndmi,
        "ndvi_class": cls_ndvi, "ndmi_class": cls_ndmi,
        "color_rgba": _BIVARIATE_PALETTE[(cls_ndvi, cls_ndmi)],
        "diagnostic_ar": _DIAGNOSTIC_AR[(cls_ndvi, cls_ndmi)],
    }
