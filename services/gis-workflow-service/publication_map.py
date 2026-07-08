"""publication_map.py — رِندرِر خريطة نشر PNG @300dpi (matplotlib Agg) فوق تخطيط نقيّ.

يستهلك تخطيط ``map_layout.build_map_layout`` + مصفوفة قيم ثنائيّة الأبعاد ويُخرِج **بايتات
PNG** بعناصر خرائطيّة: عنوان · شمال (N) · scale bar · legend · caption (المصدر/التاريخ/
الإسقاط/الدقّة/الجودة). matplotlib يُستورَد **بكسل داخل الدالّة** فلا يتطلّب استيراد الوحدة
مكتبةً رسوميّة (يبقى ``map_layout`` نقيّاً قابلاً للاختبار وحده).

**صدق:** بلا بيانات صالحة ⇒ ``ValueError`` (لا صورة فارغة مُضلِّلة). الـcaption يعكس المتوفّر
فقط (الحقول الناقصة «غير متاح» — من التخطيط). لا ادّعاء دقّة/مصدر لم يُمرَّر.
"""

from __future__ import annotations

import io
from typing import Any


def render_publication_png(
    values: Any,
    layout: dict[str, Any],
    *,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    dpi: int = 300,
) -> bytes:
    """يرسم خريطة نشر من ``values`` (2D) + ``layout`` ويُعيد بايتات PNG @``dpi``.

    ``layout`` من ``map_layout.build_map_layout``. ``vmin/vmax`` يثبّتان مدى الألوان
    (لمقارنة عبر الزمن). يرفع ``ValueError`` إن كانت البيانات فارغة/غير ثنائيّة الأبعاد.
    """
    import numpy as np  # noqa: PLC0415 — استيراد كسول: يبقى map_layout نقيّاً.

    arr = np.asarray(values, dtype="float64")
    if arr.ndim != 2 or arr.size == 0:
        raise ValueError("values must be a non-empty 2D array")

    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")  # بلا شاشة — خادميّ.
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from matplotlib.patches import Patch  # noqa: PLC0415

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.imshow(arr, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
    ax.set_xticks([])
    ax.set_yticks([])

    title = layout.get("title")
    if isinstance(title, str) and title:
        ax.set_title(title, fontsize=14, fontweight="bold")

    # سهم الشمال (أعلى-يمين): رمز N فوق سهم لأعلى.
    ax.annotate(
        "N",
        xy=(0.96, 0.90),
        xytext=(0.96, 0.80),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        arrowprops={"facecolor": "black", "width": 2, "headwidth": 8},
    )

    # scale bar (أسفل-يسار): خطّ بطول نسبيّ + تسمية «مستديرة».
    sb = layout.get("scale_bar")
    if isinstance(sb, dict) and sb.get("label"):
        ax.plot([0.05, 0.30], [0.05, 0.05], transform=ax.transAxes, color="black", lw=3)
        ax.text(0.175, 0.07, str(sb["label"]), transform=ax.transAxes, ha="center", fontsize=9)

    # legend من عناصر التخطيط (لون/تسمية).
    entries = (layout.get("legend") or {}).get("entries") or []
    handles = [Patch(facecolor=e["color"], label=e["label"]) for e in entries if e.get("color")]
    if handles:
        ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.85)

    # caption (أسفل الشكل): أسطر البيانات الوصفيّة (الناقص «غير متاح»).
    caption = layout.get("caption") or []
    if caption:
        fig.text(0.02, 0.01, "  ·  ".join(str(c) for c in caption), fontsize=7, va="bottom")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=int(dpi), bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
