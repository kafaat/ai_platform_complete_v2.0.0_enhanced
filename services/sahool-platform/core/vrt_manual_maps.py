"""
sahool_core.vrt_manual_maps
=============================
Variable Rate Treatment — Manual Execution Maps.

النقطة "العبقرية" التي حدّدتها مراجعتان مستقلّتان: VRT بدون ISOBUS
ليس workaround، بل ميزة تنافسية للسياق اليمني.

النموذج الذهني:
  ┌────────────────────────────────────┬────────────────────────────┐
  │ المنصّة الغربية                   │ سهول                       │
  ├────────────────────────────────────┼────────────────────────────┤
  │ ISOXML                             │ خرائط بشرية قابلة للتنفيذ  │
  │ Task Controller                    │ عامل ميداني                │
  │ Auto application                   │ Manual zoned application   │
  │ $50K machinery                     │ مزارع + أكياس ملوّنة       │
  └────────────────────────────────────┴────────────────────────────┘

الفجوة المسدودة: لدينا zone_detection + raster_export، لكن لا أحد
يبني "خطّة تنفيذ" منهما. هذه الوحدة:
  1. تأخذ zones من zone_detection
  2. تربط كل zone بـtreatment محدّد (rate, product, color)
  3. تنتج خطّة تنفيذ قابلة للطباعة
  4. تشمل تعليمات بشرية بالعربية للعامل الميداني

المبادئ المحفوظة:
  • Safety first: PHI gate يُحرس قبل أيّ توصية مبيد
  • Color coding بصري: 5 ألوان قياسية (أحمر/برتقالي/أصفر/أخضر/أزرق)
  • صفر اختراع: zone بلا بيانات → "لا توصية" صراحة (لا تخمين)
  • قابل للطباعة: PNG/PDF (لا تطبيق mobile مطلوب)
  • Reversible: يمكن تعديل/إلغاء قبل التنفيذ

ما لم يُبنَ هنا (مُؤجَّل بمبرّر):
  • PDF generation الفعلي (يستحقّ مكتبة dedicated)
  • Mobile companion app
  • GPS-guided execution (يحتاج جهاز ميداني)
  → كلّها wrappers خفيفة فوق هذه البنية
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TreatmentColor(str, Enum):
    """ترميز لوني قياسي — حسّ بشري بصري سريع."""

    RED = "#D32F2F"  # تركيز عالي / منطقة حرجة
    ORANGE = "#F57C00"  # تركيز متوسّط-عالي
    YELLOW = "#FBC02D"  # تركيز متوسّط
    GREEN = "#388E3C"  # تركيز منخفض / سليم
    BLUE = "#1976D2"  # لا تطبيق (skip zone)
    GRAY = "#757575"  # بيانات غير كافية


class TreatmentType(str, Enum):
    NITROGEN = "nitrogen"  # تسميد نيتروجيني
    PHOSPHORUS = "phosphorus"
    POTASSIUM = "potassium"
    IRRIGATION = "irrigation"
    PESTICIDE = "pesticide"  # SAFETY CRITICAL
    HERBICIDE = "herbicide"  # SAFETY CRITICAL
    SOIL_AMENDMENT = "soil_amendment"


@dataclass
class ZoneTreatment:
    """توصية لمنطقة واحدة داخل حقل."""

    zone_id: str
    treatment_type: TreatmentType
    rate_per_ha: float | None
    rate_unit: str  # "kg/ha" / "L/ha" / "mm"
    product_name_ar: str | None = None
    color: TreatmentColor = TreatmentColor.GRAY
    area_ha: float | None = None
    expected_amount: float | None = None  # rate × area
    expected_unit: str | None = None
    worker_instructions_ar: str = ""
    safety_notes_ar: list[str] = field(default_factory=list)


@dataclass
class ManualExecutionMap:
    """خريطة تنفيذ قابلة للطباعة — البديل البشري لـISOXML."""

    field_id: str
    field_name_ar: str
    map_id: str  # للتتبّع: "vrt_2026_05_31_001"
    treatment_type: TreatmentType
    total_area_ha: float
    zones: list[ZoneTreatment]
    total_product_needed: float
    total_product_unit: str
    legend_ar: dict  # color → meaning
    execution_steps_ar: list[str]  # تعليمات مرتّبة للعامل
    safety_warnings_ar: list[str]  # PHI، حماية شخصية، إلخ
    created_at: str = ""


# ─── ترميز لوني للجرعات ──────────────────────────────────────────


def _rate_to_color(rate: float | None, rate_range: tuple[float, float]) -> TreatmentColor:
    """يحوّل جرعة إلى لون حسب موقعها في النطاق.

    rate_range: (min_typical, max_typical) للمحصول/المنطقة.
    رتب 5 (red→blue) + gray للبيانات الناقصة."""
    if rate is None:
        return TreatmentColor.GRAY
    min_r, max_r = rate_range
    if max_r <= min_r:
        return TreatmentColor.GRAY
    if rate <= 0:
        return TreatmentColor.BLUE  # skip
    normalized = (rate - min_r) / (max_r - min_r)
    if normalized <= 0.2:
        return TreatmentColor.GREEN
    elif normalized <= 0.4:
        return TreatmentColor.YELLOW
    elif normalized <= 0.7:
        return TreatmentColor.ORANGE
    else:
        return TreatmentColor.RED


def build_zone_treatment(
    zone_id: str,
    treatment_type: TreatmentType,
    rate_per_ha: float | None,
    rate_unit: str,
    area_ha: float,
    *,
    product_name_ar: str | None = None,
    rate_range_for_color: tuple[float, float] | None = None,
    phi_status: str | None = None,  # "safe" / "blocked" / None
    days_to_safe: int | None = None,
) -> ZoneTreatment:
    """يبني توصية منطقة واحدة. يفرض السلامة قبل المبيدات."""
    safety: list[str] = []
    instructions = ""

    # SAFETY GATE: المبيدات/مبيدات الأعشاب تخضع لـPHI
    if treatment_type in (TreatmentType.PESTICIDE, TreatmentType.HERBICIDE):
        if phi_status == "blocked":
            # لا توصية حتى لو طُلبت
            rate_per_ha = None
            safety.append(f"⛔ بوّابة PHI: لا رشّ — يجب الانتظار {days_to_safe or '؟'} يوماً")
            instructions = "لا تنفّذ — في فترة الأمان قبل الحصاد. راجع المهندس الزراعي."
        elif phi_status != "safe":
            rate_per_ha = None
            safety.append("⚠️ حالة PHI غير محدّدة — تحقّق قبل الرشّ")
            instructions = "لا تنفّذ بدون موافقة المهندس على PHI"
        else:
            safety.append("✓ PHI آمن")
            safety.append("ارتدِ معدّات الحماية (قفّازات، كمّامة)")

    # اللون
    color = TreatmentColor.GRAY
    if rate_per_ha is not None and rate_range_for_color:
        color = _rate_to_color(rate_per_ha, rate_range_for_color)

    # الكمّيّة المتوقّعة
    expected = rate_per_ha * area_ha if rate_per_ha is not None else None
    expected_unit = rate_unit.replace("/ha", "") if rate_unit else None

    # تعليمات عربية للعامل
    if not instructions:
        if rate_per_ha is None:
            instructions = "لا توصية — بيانات غير كافية"
        elif rate_per_ha <= 0:
            instructions = "تخطّى هذه المنطقة (لا حاجة)"
        else:
            product_text = f" من {product_name_ar}" if product_name_ar else ""
            instructions = (
                f"طبّق {rate_per_ha}{rate_unit}{product_text} "
                f"على {area_ha} هكتار "
                f"(الإجمالي: {expected:.1f}{expected_unit or ''})"
            )

    return ZoneTreatment(
        zone_id=zone_id,
        treatment_type=treatment_type,
        rate_per_ha=rate_per_ha,
        rate_unit=rate_unit,
        product_name_ar=product_name_ar,
        color=color,
        area_ha=area_ha,
        expected_amount=expected,
        expected_unit=expected_unit,
        worker_instructions_ar=instructions,
        safety_notes_ar=safety,
    )


def build_execution_map(
    field_id: str,
    field_name_ar: str,
    treatment_type: TreatmentType,
    zone_treatments: list[ZoneTreatment],
    *,
    map_id_suffix: str = "",
) -> ManualExecutionMap:
    """يجمع zone_treatments في خريطة تنفيذ كاملة قابلة للطباعة."""
    from datetime import datetime

    # الإجماليات (تخطّي None بصراحة)
    total_area = sum(z.area_ha for z in zone_treatments if z.area_ha)
    total_product = sum(z.expected_amount for z in zone_treatments if z.expected_amount is not None)
    common_unit = next((z.expected_unit for z in zone_treatments if z.expected_unit), "")

    # Legend
    legend = {
        TreatmentColor.RED.value: "تركيز عالي — أكبر اهتمام",
        TreatmentColor.ORANGE.value: "تركيز متوسّط-عالي",
        TreatmentColor.YELLOW.value: "تركيز متوسّط",
        TreatmentColor.GREEN.value: "تركيز منخفض",
        TreatmentColor.BLUE.value: "تخطّى (لا حاجة)",
        TreatmentColor.GRAY.value: "بيانات غير كافية",
    }

    # خطوات التنفيذ المرتّبة (أحمر→برتقالي→أصفر→أخضر)
    color_order = {
        TreatmentColor.RED: 0,
        TreatmentColor.ORANGE: 1,
        TreatmentColor.YELLOW: 2,
        TreatmentColor.GREEN: 3,
        TreatmentColor.BLUE: 4,
        TreatmentColor.GRAY: 5,
    }
    ordered_zones = sorted(zone_treatments, key=lambda z: color_order[z.color])
    steps = [
        f"{i + 1}. منطقة {z.zone_id} ({z.color.value}): {z.worker_instructions_ar}"
        for i, z in enumerate(ordered_zones)
    ]

    # تحذيرات السلامة المُجمّعة
    warnings: list[str] = []
    for z in zone_treatments:
        warnings.extend(z.safety_notes_ar)
    # uniqueness
    warnings = list(dict.fromkeys(warnings))

    if treatment_type in (TreatmentType.PESTICIDE, TreatmentType.HERBICIDE):
        warnings.append("⚠️ ابعد الأطفال والحيوانات أثناء الرشّ")
        warnings.append("⚠️ تحقّق من سرعة الرياح (<15 km/h)")

    map_id = f"vrt_{datetime.now().strftime('%Y%m%d')}_{map_id_suffix or field_id}"

    return ManualExecutionMap(
        field_id=field_id,
        field_name_ar=field_name_ar,
        map_id=map_id,
        treatment_type=treatment_type,
        total_area_ha=round(total_area, 2),
        zones=zone_treatments,
        total_product_needed=round(total_product, 2),
        total_product_unit=common_unit,
        legend_ar=legend,
        execution_steps_ar=steps,
        safety_warnings_ar=warnings,
        created_at=datetime.now().isoformat(),
    )


def map_summary_for_print(emap: ManualExecutionMap) -> str:
    """نصّ مرتّب للطباعة — للعامل/المهندس في الحقل."""
    lines = [
        f"خريطة تنفيذ — {emap.field_name_ar}",
        f"رقم: {emap.map_id}",
        f"نوع: {emap.treatment_type.value}",
        f"المساحة الكلّية: {emap.total_area_ha} هكتار",
        f"الكمّيّة الإجمالية: {emap.total_product_needed} {emap.total_product_unit}",
        "",
        "خطوات التنفيذ (بالترتيب):",
    ]
    lines.extend(emap.execution_steps_ar)

    if emap.safety_warnings_ar:
        lines.extend(["", "⚠️ تحذيرات السلامة:"])
        lines.extend(f"  • {w}" for w in emap.safety_warnings_ar)

    lines.extend(["", "ملاحظة: هذه خريطة بشرية. لا حاجة لمعدّات ISOBUS."])
    return "\n".join(lines)
