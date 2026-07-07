"""bulletin_render.py — رِندرِر شكل النشرة الإقليميّة (تصنيفيّ) PNG @300dpi — matplotlib Agg.

يرسم شريطاً تصنيفيّاً لكلّ محافظة/مديريّة ملوّناً بحالة NDVI (لا خريطة جغرافيّة — لا حدود).
استيراد matplotlib كسول. **صدق:** الـcaption يُعلن صراحةً «شكل تصنيفيّ لا خريطة»، والمكتوم
يظهر «مكتوم». بلا صفوف ⇒ ``ValueError`` (لا صورة فارغة مُضلِّلة).
"""

from __future__ import annotations

from typing import Any

from bulletin_figure import _CONDITION_AR, CONDITION_COLORS


def render_bulletin_figure_png(
    rows: list[dict[str, Any]],
    *,
    title: str,
    caption: str | None = None,
    dpi: int = 300,
) -> bytes:
    """يرسم شكل النشرة التصنيفيّ من ``rows`` (``bulletin_to_rows``) ويُعيد بايتات PNG."""
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("rows must be a non-empty list (bulletin_to_rows output)")

    import matplotlib  # noqa: PLC0415

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from matplotlib.patches import Patch  # noqa: PLC0415

    n = len(rows)
    fig, ax = plt.subplots(figsize=(9, max(3.0, 0.34 * n + 1.5)))
    labels: list[str] = []
    for i, r in enumerate(reversed(rows)):  # أعلى الشكل = أوّل صفّ
        y = i
        indent = 0.06 if r.get("level") == "district" else 0.0
        ax.barh(y, 1.0 - indent, left=indent, height=0.72, color=r.get("color", "#cccccc"))
        prefix = "— " if r.get("level") == "district" else ""
        name = r.get("district") if r.get("level") == "district" else r.get("governorate")
        labels.append(f"{prefix}{name}")
        ax.text(indent + 0.02, y, str(r.get("label", "")), va="center", fontsize=8, color="#222")

    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_title(title, fontsize=14, fontweight="bold")

    present = {r.get("condition") for r in rows}
    handles = [
        Patch(facecolor=CONDITION_COLORS[c], label=_CONDITION_AR.get(c, c))
        for c in ("exceptional", "favourable", "watch", "poor", "unknown", "suppressed")
        if c in present
    ]
    if handles:
        ax.legend(handles=handles, loc="lower right", fontsize=8, framealpha=0.9)

    foot = caption or ""
    foot = (
        foot + "  ·  " if foot else ""
    ) + "شكل تصنيفيّ (حالة NDVI) — ليس خريطة جغرافيّة (لا حدود إداريّة)"
    fig.text(0.02, 0.01, foot, fontsize=7, va="bottom")

    import io  # noqa: PLC0415

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=int(dpi), bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
