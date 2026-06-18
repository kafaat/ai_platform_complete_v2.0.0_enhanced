"""أداة: مستكشف مؤشّرات الغطاء النباتيّ (Vegetation Index Explorer) — نقيّة حتميّة.

تحسب مؤشّراً طيفيّاً مختاراً من قيم انعكاس النطاقات (reflectance ∈ [0,1]) وتُرجِع
القيمة مع تفسير صحّيّ عربيّ مختصر بحسب مجالات القيمة.

**النطاقات والصيغ** (مطابقة لـ`services/raster-service/band_math.py` علميّاً):

    NDVI = (NIR − RED) / (NIR + RED)                      — كثافة الغطاء النباتيّ
    NDRE = (NIR − RedEdge) / (NIR + RedEdge)              — النيتروجين/الكلوروفيل
    EVI  = 2.5·(NIR − RED) / (NIR + 6·RED − 7.5·BLUE + 1) — غطاء محسّن (مناطق كثيفة)
    MSAVI = (2·NIR + 1 − sqrt((2·NIR+1)² − 8·(NIR−RED))) / 2 — تصحيح تربة ذاتيّ

**لماذا تنفيذ داخليّ بدل إعادة استخدام `band_math`؟** وحدة `band_math` تقع في خدمة
أخرى (raster-service) وتتطلّب حقن `numpy` عبر وسيط `_np` للعمل على مصفوفات، وهو ما
لا يلائم أداةً نقيّةً بلا تبعيّات تعمل على أعداد مفردة. لذا أُعيدت الصيغ نفسها هنا
حرفيّاً (نفس المقامات والثوابت) لضمان تطابق النتائج عدديّاً.

ملاحظة علميّة: التفسير الزراعيّ إرشاديّ ويحتاج معايرة ميدانيّة محلّيّة؛ لا قرار
ريّ/تسميد بقيمة قمر صناعيّ وحدها.
"""

from __future__ import annotations

from ..registry import Tool, ToolParam, register

# اسم المؤشّر → النطاقات المطلوبة (بالإضافة إلى nir الإلزاميّ دائماً).
_INDEX_REQUIRED_BANDS = {
    "NDVI": ("red",),
    "NDRE": ("red_edge",),
    "EVI": ("red", "blue"),
    "MSAVI": ("red",),
}

_INDEX_OPTIONS = ("NDVI", "NDRE", "EVI", "MSAVI")


def _interpret(index: str, value: float | None) -> str:
    """تفسير صحّيّ عربيّ مختصر بحسب مجال القيمة (إرشاديّ)."""
    if value is None:
        return "تعذّر الحساب (مقام صفريّ) — تحقّق من قيم النطاقات."
    if index == "EVI":
        # EVI غير محدود بـ[-1,1] لكنه عمليّاً قريب من مجالات مشابهة.
        if value < 0.1:
            return "غطاء نباتيّ ضعيف جدّاً أو تربة عارية."
        if value < 0.3:
            return "غطاء نباتيّ خفيف — نموّ مبكّر أو إجهاد."
        if value < 0.5:
            return "غطاء نباتيّ معتدل وصحّة متوسّطة."
        return "غطاء نباتيّ كثيف وصحّة جيّدة."
    # مؤشّرات نسبيّة في [-1,1] تقريباً (NDVI/NDRE/MSAVI).
    if value < 0.0:
        return "ماء أو سطح غير نباتيّ (قيمة سالبة)."
    if value < 0.2:
        return "تربة عارية أو نبات شديد الإجهاد."
    if value < 0.4:
        return "غطاء نباتيّ متناثر أو إجهاد ملحوظ."
    if value < 0.6:
        return "غطاء نباتيّ معتدل وصحّة متوسّطة."
    return "غطاء نباتيّ كثيف وصحّة جيّدة."


def _div(numerator: float, denominator: float) -> float | None:
    """قسمة آمنة: تُرجِع None عند مقام صفريّ بدل رفع استثناء."""
    if denominator == 0:
        return None
    return numerator / denominator


def compute(inp: dict) -> dict:
    index = inp["index"]
    nir = inp["nir"]
    red = inp.get("red")
    red_edge = inp.get("red_edge")
    blue = inp.get("blue")

    # التحقّق من توفّر النطاقات المطلوبة للمؤشّر المختار (صدق: لا اختراع نطاق).
    needed = _INDEX_REQUIRED_BANDS.get(index)
    if needed is None:
        raise ValueError(f"مؤشّر غير مدعوم: {index} — المتاح {_INDEX_OPTIONS}")
    band_values = {"red": red, "red_edge": red_edge, "blue": blue}
    arabic_names = {"red": "الأحمر", "red_edge": "الحافة الحمراء", "blue": "الأزرق"}
    missing = [b for b in needed if band_values[b] is None]
    if missing:
        labels = "، ".join(arabic_names[b] for b in missing)
        raise ValueError(f"المؤشّر {index} يتطلّب نطاقات إضافيّة مفقودة: {labels}")

    if index == "NDVI":
        value = _div(nir - red, nir + red)
    elif index == "NDRE":
        value = _div(nir - red_edge, nir + red_edge)
    elif index == "EVI":
        value = _div(2.5 * (nir - red), nir + 6.0 * red - 7.5 * blue + 1.0)
    elif index == "MSAVI":
        term = 2.0 * nir + 1.0
        radicand = term * term - 8.0 * (nir - red)
        if radicand < 0:
            radicand = 0.0
        value = (term - radicand**0.5) / 2.0
    else:  # غير قابل للوصول (تحقّقنا أعلاه) — حارس دفاعيّ.
        raise ValueError(f"مؤشّر غير مدعوم: {index}")

    return {
        "index": index,
        "value": None if value is None else round(value, 4),
        "interpretation_ar": _interpret(index, value),
    }


register(
    Tool(
        id="vegetation_index_explorer",
        name_ar="مستكشف مؤشّرات الغطاء النباتيّ",
        category="remote_sensing",
        description_ar=(
            "يحسب مؤشّراً طيفيّاً مختاراً (NDVI/NDRE/EVI/MSAVI) من قيم انعكاس "
            "النطاقات [0,1] مع تفسير صحّيّ مختصر."
        ),
        params=[
            ToolParam(
                "index",
                "select",
                "المؤشّر",
                options=_INDEX_OPTIONS,
                default="NDVI",
            ),
            ToolParam("nir", "number", "الأشعّة تحت الحمراء القريبة (NIR)", min=0, max=1),
            ToolParam(
                "red",
                "number",
                "النطاق الأحمر (RED)",
                required=False,
                min=0,
                max=1,
            ),
            ToolParam(
                "red_edge",
                "number",
                "نطاق الحافة الحمراء (Red Edge) — لـNDRE",
                required=False,
                min=0,
                max=1,
            ),
            ToolParam(
                "blue",
                "number",
                "النطاق الأزرق (BLUE) — لـEVI",
                required=False,
                min=0,
                max=1,
            ),
        ],
        compute=compute,
        result_unit_ar="قيمة المؤشّر (بلا وحدة)",
        tags=("استشعار", "مؤشّر", "غطاء نباتيّ", "NDVI"),
    )
)
