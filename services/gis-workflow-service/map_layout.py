"""map_layout.py — تخطيط خريطة نشر (scale bar / north arrow / legend / caption) — منطق صرف.

الشريحة A من «Sahool GIS Workflow Engine»: يبني **تخطيط** خريطة ورقيّة قابلة للنشر من
البيانات الوصفيّة، **بلا matplotlib** (الرسم الفعليّ في ``publication_map.py``). فصل التخطيط
(نقيّ، قابل للاختبار حتميّاً) عن الرسم (I/O ثقيل) يتيح تحقّقاً صادقاً بلا اعتماد رسوميّ.

**صدق حاسم:** الـcaption يُركَّب من الحقول المتوفّرة فقط؛ أيّ حقل ناقص ⇒ «غير متاح» صراحةً
(لا اختلاق مصدر/تاريخ/دقّة). scale bar = رقم «مستدير» (1/2/5×10ⁿ) لا كسر تعسّفيّ.
"""

from __future__ import annotations

import math
from typing import Any

# ترتيب حقول الـcaption (المفتاح → التسمية العربيّة). القيمة الناقصة تُعرَض «غير متاح».
_CAPTION_FIELDS: tuple[tuple[str, str], ...] = (
    ("area_name", "المنطقة"),
    ("index", "المؤشّر"),
    ("source", "المصدر"),
    ("acquisition_date", "تاريخ الالتقاط"),
    ("crs", "الإسقاط"),
    ("resolution_m", "الدقّة"),
    ("quality_score", "درجة الجودة"),
)
_MISSING_AR = "غير متاح"


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def format_distance_ar(meters: Any) -> str:
    """مسافة بصيغة عربيّة مقروءة: ``≥1000`` ⇒ «كم» وإلّا «م». غير رقميّ ⇒ «غير متاح»."""
    m = _num(meters)
    if m is None or m < 0:
        return _MISSING_AR
    if m >= 1000:
        km = m / 1000.0
        txt = f"{km:.1f}".rstrip("0").rstrip(".")
        return f"{txt} كم"
    txt = f"{m:.0f}"
    return f"{txt} م"


def nice_scale_bar_m(map_width_m: Any, *, fraction: float = 0.25) -> dict[str, Any] | None:
    """طول scale bar «مستدير» (1/2/5×10ⁿ) قريب من ``fraction`` من عرض الخريطة.

    يُرجِع ``{length_m, label}`` أو None إن كان العرض غير صالح (لا نُلفِّق مقياساً).
    """
    w = _num(map_width_m)
    if w is None or w <= 0:
        return None
    target = w * float(fraction)
    if target <= 0:
        return None
    exp = math.floor(math.log10(target))
    base = 10.0**exp
    # أكبر قيمة من {1,2,5}×base لا تتجاوز الهدف (رقم مستدير مألوف للخرائط).
    length = base
    for mult in (5.0, 2.0, 1.0):
        if mult * base <= target:
            length = mult * base
            break
    return {"length_m": length, "label": format_distance_ar(length)}


def class_break_labels(breaks: Any) -> list[str]:
    """تسميات فئات من عتبات صاعدة: n عتبة ⇒ n+1 تسمية («< a» / «a–b» / «> z»).

    عتبات غير رقميّة/غير صاعدة ⇒ قائمة فارغة (لا فئات مُختلَقة).
    """
    if not isinstance(breaks, (list, tuple)) or not breaks:
        return []
    vals = [_num(b) for b in breaks]
    if any(v is None for v in vals):
        return []
    if any(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
        return []  # يجب أن تكون صاعدة تماماً

    def _fmt(x: float) -> str:
        return f"{x:g}"

    labels = [f"< {_fmt(vals[0])}"]
    labels += [f"{_fmt(vals[i])}–{_fmt(vals[i + 1])}" for i in range(len(vals) - 1)]
    labels.append(f"> {_fmt(vals[-1])}")
    return labels


def legend_entries(classes: Any) -> list[dict[str, str]]:
    """عناصر مفتاح صالحة من ``[{label, color}]``: يُسقِط الشاذّ (بلا لون/تسمية)."""
    out: list[dict[str, str]] = []
    for c in classes if isinstance(classes, (list, tuple)) else []:
        if not isinstance(c, dict):
            continue
        label, color = c.get("label"), c.get("color")
        if isinstance(label, str) and label and isinstance(color, str) and color:
            out.append({"label": label, "color": color})
    return out


def caption_lines(meta: Any) -> list[str]:
    """أسطر الـcaption بالترتيب الثابت؛ كلّ حقل ناقص ⇒ «غير متاح» (صدق، لا تلفيق).

    ``resolution_m`` يُعرَض «Nم»؛ ``quality_score`` (0..1) يُعرَض نسبةً مئويّة.
    """
    m = meta if isinstance(meta, dict) else {}
    lines: list[str] = []
    for key, label_ar in _CAPTION_FIELDS:
        raw = m.get(key)
        if key == "resolution_m":
            n = _num(raw)
            value = f"{n:g} م" if n is not None and n > 0 else _MISSING_AR
        elif key == "quality_score":
            n = _num(raw)
            value = f"{round(n * 100)}%" if n is not None else _MISSING_AR
        else:
            value = str(raw) if isinstance(raw, str) and raw.strip() else _MISSING_AR
        lines.append(f"{label_ar}: {value}")
    return lines


def build_map_layout(spec: Any) -> dict[str, Any]:
    """يجمع تخطيط الخريطة من ``spec`` (title/map_width_m/classes/meta) — نقيّ حتميّ.

    ``spec``: ``{title?, map_width_m?, classes?, meta?}``. North arrow ثابت (رمز «N»
    أعلى-يمين). scale bar/legend/caption صادقة عند نقص المدخلات.
    """
    s = spec if isinstance(spec, dict) else {}
    title = s.get("title") if isinstance(s.get("title"), str) and s.get("title") else None
    return {
        "title": title,
        "scale_bar": nice_scale_bar_m(s.get("map_width_m")),
        "north_arrow": {"symbol": "N", "position": "top_right"},
        "legend": {"entries": legend_entries(s.get("classes"))},
        "caption": caption_lines(s.get("meta")),
    }
