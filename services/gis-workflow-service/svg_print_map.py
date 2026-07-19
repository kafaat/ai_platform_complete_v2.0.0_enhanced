"""svg_print_map.py — مُجمِّع خريطة طباعة متجهة (A6) — وحدة صرفة (لا قاعدة/matplotlib).

يبني SVG متجهاً من مسارات ``ST_AsSVG`` (تُجلَب في raster-service من طبقة A7 + هندسة الحقل) بـ**طبقات
مستقلّة** ``<g id="admin">`` · ``<g id="field">`` · ``<g id="indicator">`` — فيفتحها مصمّم في Illustrator
ويعدّل طبقة دون طلب (ملفّ الطباعة أصل قابل للتحرير لا صورة نهائية). شرط تصميم Map2SVG محفوظ.

**الإسناد القانوني ذاتيّ الاشتقاق (شرط ج):** التذييل ثنائيّ اللغة يُبنى من **سجلّ مرجعيّة A7**
(source/dataset_version/license_title/retrieved_at) لا نصّاً ثابتاً — فإن تبدّلت الرخصة عند إعادة تحميل A7
تبدّل التذييل تلقائيّاً. حدود HDX/OCHA CC-BY تُلزِم إظهار الإسناد.

**كتم الخصوصيّة على المتجه (الشرط الرابع، مانع تصميميّ):** الشكل التصنيفيّ يحجب المجموعات المكتومة نصّاً؛
لكن الخريطة قد تُسرِّبها **بصريّاً** إن لُوّنت مديريّة مكتومة بدرجة NDVI. لذا وحدة ``suppressed`` تُرسَم
هندستها **بلا تعبئة بيانات** — نمط «محجوب» (hatch رماديّ) متميّز عن أيّ فئة NDVI + ``class="suppressed-no-data"``
(للحارس) — الخريطة تقول «هنا حجب» بصدق، لا تتظاهر بالغياب ولا تُسرِّب باللون ما مُنِع بالرقم.
"""

from __future__ import annotations

import html
from typing import Any

_SUPPRESSED_CLASS = "suppressed-no-data"
_SUPPRESSED_FILL = "url(#suppressed)"


def attribution_footer_lines(source: dict[str, Any] | None) -> tuple[str, str]:
    """سطرا التذييل (عربيّ/إنجليزيّ) من سجلّ مرجعيّة A7 — لا نصّ ثابت. غياب المصدر ⇒ إعلان صريح."""
    s = source or {}
    src = str(s.get("source") or "?")
    ver = str(s.get("dataset_version") or "?")
    lic = str(s.get("license_title") or "?")
    retrieved = str(s.get("retrieved_at") or "")
    date = retrieved[:10] if retrieved else "?"
    ar = f"الحدود الإداريّة: {src} — {ver} ({date}) · {lic}"
    en = f"Administrative boundaries: {src} — {ver} · {lic}"
    return ar, en


def _esc(p: Any) -> str:
    return html.escape(str(p), quote=True)


def _defs() -> str:
    """نمط «محجوب» متميّز بصريّاً عن أيّ فئة NDVI (hatch رماديّ)."""
    return (
        '<defs><pattern id="suppressed" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><rect width="6" height="6" fill="#eeeeee"/>'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#9e9e9e" stroke-width="1.4"/></pattern></defs>'
    )


def _boundary_layer(group_id: str, paths: list[str] | None, fill: str, stroke: str) -> str:
    inner = "".join(
        f'<path d="{_esc(p)}" fill="{fill}" stroke="{stroke}" stroke-width="0.5"/>'
        for p in (paths or [])
        if p
    )
    return f'<g id="{group_id}">{inner}</g>'


def _indicator_layer(units: list[dict[str, Any]] | None) -> str:
    """طبقة choropleth: وحدة مكتومة ⇒ نمط «محجوب» بلا قيمة؛ غيرها ⇒ لون قيمتها (لا تسريب بصريّ)."""
    parts = []
    for u in units or []:
        path = u.get("path")
        if not path:
            continue
        if u.get("suppressed"):
            # **لا تعبئة بيانات** — نمط محجوب + class للحارس (كتم الخصوصيّة يمتدّ للمتجه).
            parts.append(
                f'<path d="{_esc(path)}" fill="{_SUPPRESSED_FILL}" class="{_SUPPRESSED_CLASS}" '
                f'stroke="#9e9e9e" stroke-width="0.4"/>'
            )
        else:
            parts.append(
                f'<path d="{_esc(path)}" fill="{_esc(u.get("fill") or "none")}" '
                f'class="ndvi-value" stroke="#33691e" stroke-width="0.3"/>'
            )
    return f'<g id="indicator">{"".join(parts)}</g>'


def assemble_print_map_svg(
    *,
    admin_paths: list[str] | None,
    field_paths: list[str] | None,
    indicator_units: list[dict[str, Any]] | None = None,
    attribution_source: dict[str, Any] | None,
    width: int = 1000,
    height: int = 1200,
    view_box: str = "0 0 1000 1200",
) -> str:
    """يُجمِّع خريطة الطباعة المتجهة: طبقات مستقلّة + تذييل مشتقّ + كتم خصوصيّة على المتجه.

    ``indicator_units``: ``[{"path": svg, "fill": "#..", "suppressed": bool}]`` — المكتومة بلا قيمة.
    """
    ar, en = attribution_footer_lines(attribution_source)
    admin = _boundary_layer("admin", admin_paths, "#f4f7f4", "#33691e")
    field = _boundary_layer("field", field_paths, "none", "#c62828")
    indicator = _indicator_layer(indicator_units)
    footer = (
        f'<g id="attribution">'
        f'<text x="12" y="{height - 26}" font-size="13" fill="#444" direction="rtl">{html.escape(ar)}</text>'
        f'<text x="12" y="{height - 10}" font-size="12" fill="#666">{html.escape(en)}</text>'
        f"</g>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="{view_box}">{_defs()}{admin}{field}{indicator}{footer}</svg>'
    )
