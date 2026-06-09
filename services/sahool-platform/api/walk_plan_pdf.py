"""
api/walk_plan_pdf.py — تصدير خطة المشي كـPDF عربي (RTL)

خارطة الطريق: المرحلة ١، البند ٩.

ينتج PDF منسّق لخطة المشي ليطبعه المزارع ويأخذه للحقل. RTL + جدول خطوات.
يتبع نفس نمط reports.py (lazy import + fallback لو reportlab غائب).

⚠ ملاحظة RTL: التشكيل العربي الكامل يحتاج arabic_reshaper + python-bidi
(قد لا يكونان مُثبَّتَين). لو غابا، النصّ العربي قد يظهر غير متّصل الحروف في
بعض العارضات — لكنّ المحتوى صحيح. نوفّر دالّة تشكيل اختياريّة.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict


def _shape_arabic(text: str) -> str:
    """يشكّل النصّ العربي للعرض الصحيح (لو المكتبات متاحة)؛ وإلّا يُعيده كما هو."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        # fallback: المحتوى صحيح لكن قد لا تتّصل الحروف في بعض العارضات
        return text


def walk_plan_to_pdf_bytes(plan: Dict[str, Any]) -> bytes:
    """ينتج PDF لخطة مشي. يأخذ dict من WalkPlan.to_dict().

    يحتاج reportlab مُثبَّت (يرفع RuntimeError لو غائب).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        )
        from reportlab.lib import colors
    except ImportError:
        raise RuntimeError(
            "reportlab غير مُثبَّت. ثبّته بـ: pip install reportlab"
        )

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "WPTitle", parent=styles["Title"], alignment=TA_RIGHT, fontSize=18,
    )
    rtl_style = ParagraphStyle(
        "WPRtl", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=11,
    )
    note_style = ParagraphStyle(
        "WPNote", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=10,
        textColor=colors.HexColor("#555555"),
    )

    el = []
    el.append(Paragraph(_shape_arabic("خطة التطبيق الميداني (خطة المشي)"), title_style))
    el.append(Spacer(1, 0.3 * cm))

    # رأس: الحقل + المحصول + الإجماليّات
    method_ar = {
        "broadcast_terrace": "نثر على المصاطب",
        "backpack_spray": "رشّ ظهري",
        "per_tree": "لكلّ شجرة",
    }.get(plan.get("method", ""), plan.get("method", ""))

    header = [
        [_shape_arabic(str(plan.get("crop", "-"))), _shape_arabic("المحصول")],
        [_shape_arabic(method_ar), _shape_arabic("الطريقة")],
        [_shape_arabic(str(plan.get("product_name_ar", "-"))), _shape_arabic("المنتج")],
        [f"{plan.get('total_product_kg', 0)} كغ", _shape_arabic("إجمالي المنتج")],
        [f"{plan.get('total_estimated_hours', 0)} ساعة", _shape_arabic("الوقت المُقدَّر")],
    ]
    htbl = Table(header, colWidths=[8 * cm, 5 * cm])
    htbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#f0f0f0")),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(htbl)
    el.append(Spacer(1, 0.5 * cm))

    # جدول الخطوات
    el.append(Paragraph(_shape_arabic("الخطوات بالترتيب:"), rtl_style))
    el.append(Spacer(1, 0.2 * cm))

    rows = [[
        _shape_arabic("التعليمات"),
        _shape_arabic("الوقت (د)"),
        _shape_arabic("المساحة"),
        _shape_arabic("المنطقة"),
        _shape_arabic("#"),
    ]]
    for s in plan.get("steps", []):
        rows.append([
            _shape_arabic(s.get("instruction_ar", "")),
            f"{s.get('estimated_minutes', 0):.0f}",
            f"{s.get('area_ha', 0)} هـ",
            _shape_arabic(s.get("zone_class", "")),
            str(s.get("order", "")),
        ])

    stbl = Table(rows, colWidths=[7 * cm, 1.8 * cm, 2 * cm, 2 * cm, 1 * cm])
    stbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e7d32")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
    ]))
    el.append(stbl)
    el.append(Spacer(1, 0.5 * cm))

    # ملاحظات
    if plan.get("notes_ar"):
        el.append(Paragraph(_shape_arabic(plan["notes_ar"]), note_style))

    doc.build(el)
    return buf.getvalue()
