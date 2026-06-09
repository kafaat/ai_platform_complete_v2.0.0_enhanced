"""
services/sahool-platform/api/reports.py — Custom Reports (PDF / CSV)

المرجع: FieldView Quick Start Guide:
    "Custom Reports — Build a PDF or CSV file on one field or your
     entire operation in a minute."

ميزات:
   ١. Field report (single field, season summary)
   ٢. Operation report (multi-field summary)
   ٣. CSV export (للـExcel + للجهات الحكوميّة)
   ٤. PDF export (بـreportlab، RTL + خطّ عربي)

تكييف لليمن:
   - تقارير بالعربيّة مع تواريخ هجريّة (اختياري)
   - متوافق مع تقارير وزارة الزراعة (CSV columns standard)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from io import BytesIO
import csv
import io
import logging

logger = logging.getLogger(__name__)


# ─── Report data structures ─────────────────────────────────────

@dataclass
class FieldReport:
    field_id: str
    field_name_ar: str
    farm_id: str
    tenant_id: str
    area_ha: float
    crop: str
    season_label: str
    planting_date: Optional[str]
    harvest_date: Optional[str]
    lifecycle_stage: str

    # Operations summary
    irrigation_events: int = 0
    total_water_m3: float = 0.0
    fertilizer_events: int = 0
    total_nitrogen_kg: float = 0.0
    total_phosphorus_kg: float = 0.0
    total_potassium_kg: float = 0.0
    pest_treatments: int = 0
    pesticide_kg: float = 0.0

    # Remote sensing
    avg_ndvi: Optional[float] = None
    max_ndvi: Optional[float] = None
    min_ndvi: Optional[float] = None

    # Yield
    estimated_yield_kg_ha: Optional[float] = None
    estimated_yield_total_kg: Optional[float] = None
    actual_yield_kg_ha: Optional[float] = None      # بعد الحصاد فقط
    actual_yield_total_kg: Optional[float] = None

    # Soil
    soil_samples_count: int = 0
    last_soil_ph: Optional[float] = None
    last_soil_ec: Optional[float] = None

    # Anomalies / warnings
    anomalies: List[str] = field(default_factory=list)


@dataclass
class OperationReport:
    """تقرير المزرعة كاملة (multi-field)."""
    tenant_id: str
    operation_name_ar: str
    fields: List[FieldReport]
    period_start: str
    period_end: str
    generated_at: str

    @property
    def total_area_ha(self) -> float:
        return sum(f.area_ha for f in self.fields)

    @property
    def total_yield_kg(self) -> float:
        return sum((f.actual_yield_total_kg or f.estimated_yield_total_kg or 0)
                   for f in self.fields)


# ─── CSV exporter ───────────────────────────────────────────────

CSV_HEADER_AR = [
    "field_id", "اسم_الحقل", "المساحة_هكتار", "المحصول", "الموسم",
    "تاريخ_البذر", "تاريخ_الحصاد", "المرحلة",
    "أحداث_الري", "إجمالي_الماء_م3",
    "أحداث_التسميد", "نيتروجين_كغ", "فوسفور_كغ", "بوتاسيوم_كغ",
    "علاجات_الآفات", "مبيد_كغ",
    "NDVI_متوسط", "NDVI_أعلى", "NDVI_أدنى",
    "إنتاج_متوقّع_كغ_ه", "إنتاج_فعلي_كغ_ه",
    "عيّنات_تربة", "pH", "EC",
    "تنبيهات",
]

CSV_HEADER_EN = [
    "field_id", "field_name", "area_ha", "crop", "season",
    "planting_date", "harvest_date", "stage",
    "irrigation_events", "total_water_m3",
    "fertilizer_events", "nitrogen_kg", "phosphorus_kg", "potassium_kg",
    "pest_treatments", "pesticide_kg",
    "ndvi_avg", "ndvi_max", "ndvi_min",
    "yield_estimated_kg_ha", "yield_actual_kg_ha",
    "soil_samples", "soil_ph", "soil_ec",
    "anomalies",
]


def operation_to_csv(report: OperationReport, lang: str = "ar") -> str:
    """يحوّل التقرير إلى CSV string."""
    out = io.StringIO()
    # BOM للـExcel Arabic
    out.write("\ufeff")

    writer = csv.writer(out)
    header = CSV_HEADER_AR if lang == "ar" else CSV_HEADER_EN
    writer.writerow(header)

    for f in report.fields:
        writer.writerow([
            f.field_id,
            f.field_name_ar,
            f"{f.area_ha:.2f}",
            f.crop,
            f.season_label,
            f.planting_date or "",
            f.harvest_date or "",
            f.lifecycle_stage,
            f.irrigation_events,
            f"{f.total_water_m3:.1f}",
            f.fertilizer_events,
            f"{f.total_nitrogen_kg:.1f}",
            f"{f.total_phosphorus_kg:.1f}",
            f"{f.total_potassium_kg:.1f}",
            f.pest_treatments,
            f"{f.pesticide_kg:.2f}",
            f"{f.avg_ndvi:.3f}" if f.avg_ndvi is not None else "",
            f"{f.max_ndvi:.3f}" if f.max_ndvi is not None else "",
            f"{f.min_ndvi:.3f}" if f.min_ndvi is not None else "",
            f"{f.estimated_yield_kg_ha:.0f}" if f.estimated_yield_kg_ha else "",
            f"{f.actual_yield_kg_ha:.0f}" if f.actual_yield_kg_ha else "",
            f.soil_samples_count,
            f"{f.last_soil_ph:.1f}" if f.last_soil_ph is not None else "",
            f"{f.last_soil_ec:.2f}" if f.last_soil_ec is not None else "",
            "; ".join(f.anomalies),
        ])

    # Summary row
    writer.writerow([])
    writer.writerow([
        "─ المُجمَل ─" if lang == "ar" else "─ TOTAL ─",
        f"{len(report.fields)} حقول",
        f"{report.total_area_ha:.2f}",
        "", "", "", "", "",
        sum(f.irrigation_events for f in report.fields),
        f"{sum(f.total_water_m3 for f in report.fields):.1f}",
        sum(f.fertilizer_events for f in report.fields),
        f"{sum(f.total_nitrogen_kg for f in report.fields):.1f}",
        f"{sum(f.total_phosphorus_kg for f in report.fields):.1f}",
        f"{sum(f.total_potassium_kg for f in report.fields):.1f}",
        sum(f.pest_treatments for f in report.fields),
        f"{sum(f.pesticide_kg for f in report.fields):.2f}",
        "", "", "",
        f"{report.total_yield_kg:.0f}", "",
        "", "", "", "",
    ])

    return out.getvalue()


# ─── PDF exporter (lazy import — reportlab اختياري) ─────────────

def field_to_pdf_bytes(field_report: FieldReport) -> bytes:
    """ينتج PDF بسيط لحقل واحد. يحتاج reportlab مُثبَّت."""
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
        leftMargin=2 * cm, rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    rtl_style = ParagraphStyle(
        "RTL", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=11,
    )
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"], alignment=TA_RIGHT, fontSize=18,
    )

    elements = []
    elements.append(Paragraph(f"تقرير حقل: {field_report.field_name_ar}", title_style))
    elements.append(Spacer(1, 0.5 * cm))

    # Table data
    data = [
        ["القيمة", "البند"],
        [field_report.field_id[:8], "الـID"],
        [f"{field_report.area_ha} هـ", "المساحة"],
        [field_report.crop, "المحصول"],
        [field_report.season_label, "الموسم"],
        [field_report.planting_date or "-", "تاريخ البذر"],
        [field_report.harvest_date or "-", "تاريخ الحصاد"],
        [field_report.lifecycle_stage, "المرحلة"],
        ["─", "─"],
        [str(field_report.irrigation_events), "أحداث الري"],
        [f"{field_report.total_water_m3:.1f} م³", "إجمالي الماء"],
        [str(field_report.fertilizer_events), "أحداث التسميد"],
        [f"{field_report.total_nitrogen_kg:.1f} كغ", "النيتروجين"],
        ["─", "─"],
        [f"{field_report.avg_ndvi:.3f}" if field_report.avg_ndvi else "-", "NDVI متوسط"],
        [
            f"{field_report.estimated_yield_kg_ha:.0f} كغ/هـ" if field_report.estimated_yield_kg_ha else "-",
            "الإنتاج المتوقّع",
        ],
    ]

    table = Table(data, colWidths=[8 * cm, 8 * cm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3EB050")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 1 * cm))

    if field_report.anomalies:
        elements.append(Paragraph("⚠ تنبيهات:", rtl_style))
        for a in field_report.anomalies:
            elements.append(Paragraph(f"  · {a}", rtl_style))

    elements.append(Spacer(1, 0.5 * cm))
    elements.append(Paragraph(
        f"تمّ التوليد: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        rtl_style,
    ))
    elements.append(Paragraph("تطبيق سهول — منصّة الزراعة الذكيّة لليمن", rtl_style))

    doc.build(elements)
    return buf.getvalue()
