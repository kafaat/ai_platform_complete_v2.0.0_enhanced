"""
services/sahool-platform/api/report_builder.py — بنّاء التقارير (Report Builder)

المشكلة: التقارير حاليّاً ثابتة (أقسام مُبرمَجة في واجهة ReportsPage، ونقاط
نهاية مُجمَّدة: /reports/farm-summary و /field/{id}/summary و /season/{id}/summary
و operation_report CSV). لا يستطيع المستخدِم اختيار ما يريد في تقريره.

الحلّ (هذا الملفّ): بنّاء تقارير قائم على البيانات الوصفيّة (metadata-driven):
   ١. كتالوج «حقول التقرير» (ReportField) — كلّ بند مأخوذ من *مفتاح حقيقيّ*
      تُنتجه نقاط النهاية القائمة فعلاً (لا اختراع لما لا تقدر المنصّة عليه).
   ٢. بنّاء مواصفة (build_report_spec): يأخذ اختياراً تصريحيّاً من المستخدِم
      {المدى الزمنيّ، الحقول، الصيغة} ويُعيد مواصفة تقرير مُتحقَّقاً منها
      (ReportSpec) + بيانات الحقول المحلولة + تحذيرات.

نمط البنّاء (builder pattern): المستخدِم يصف ماذا يريد تصريحيّاً، والبنّاء
يتحقّق من الاختيار مقابل الكتالوج (مصدر الحقيقة الوحيد عمّا تقدر المنصّة على
إنتاجه) ويُخرج مواصفة نظيفة. نقيّ تماماً: لا قاعدة بيانات ولا شبكة، ولا يرمي
استثناءً على اختيار سيّئ — يتحمّل برِفق ويُسجّل تحذيرات.

صدق المصدر: هذا الملفّ ينتج *مواصفة* التقرير فقط. تجميع البيانات الفعليّ
وتصييرها (CSV/JSON/PDF) يُوصَل لاحقاً بنقاط /reports القائمة والمُصدِّرات في
api/reports.py (operation_to_csv / field_to_pdf_bytes) — متابعة موثَّقة، ليست
مُنفَّذة هنا.

كلّ حقل في الكتالوج موثَّق بمصدره (نقطة النهاية ومفتاح الحمولة):
   - farm   → GET /api/v1/reports/farm-summary
   - field  → GET /api/v1/reports/field/{field_id}/summary
   - season → GET /api/v1/reports/season/{season_id}/summary
   - cost/activity → FieldReport (operation_report CSV عبر operation_to_csv)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# ─── الصيغ المسموحة للتقرير ──────────────────────────────────────
# مدعومة فعلاً عبر المُصدِّرات القائمة: CSV (operation_to_csv)،
# PDF (field_to_pdf_bytes عبر reportlab)، JSON (حمولات /reports الخام).
ALLOWED_FORMATS: tuple[str, ...] = ("csv", "json", "pdf")

_DEFAULT_FORMAT = "csv"


# ─── بنية حقل التقرير ────────────────────────────────────────────


@dataclass(frozen=True)
class ReportField:
    """بند واحد في كتالوج التقارير — مأخوذ من مفتاح حمولة حقيقيّ.

    id:           معرّف ثابت يستخدمه المستخدِم في الاختيار.
    name_ar:      الاسم المعروض بالعربيّة.
    category:     الفئة ("farm"|"field"|"season"|"cost"|"activity").
    data_key:     مفتاح القيمة في حمولات /reports القائمة (مصدر الحقيقة).
    value_type:   نوع العرض ("number"|"text"|"chart"|"table").
    description_ar: وصف اختياريّ للبند.
    """

    id: str
    name_ar: str
    category: str
    data_key: str
    value_type: str
    description_ar: str = ""


# ─── الكتالوج — مُغذّى من مفاتيح حقيقيّة فقط ─────────────────────
# لا نخترع حقولاً لا تقدر المنصّة على إنتاجها. كلّ data_key أدناه يُطابق
# مفتاحاً تُعيده نقطة نهاية تقرير قائمة (أُشير إلى مصدره في التعليق).
_CATALOG_FIELDS: tuple[ReportField, ...] = (
    # ── farm: GET /api/v1/reports/farm-summary ──
    ReportField(
        id="farm_farms_count",
        name_ar="عدد المزارع",
        category="farm",
        data_key="farms_count",
        value_type="number",
        description_ar="إجماليّ مزارع المستأجِر",
    ),
    ReportField(
        id="farm_fields_count",
        name_ar="عدد الحقول",
        category="farm",
        data_key="fields_count",
        value_type="number",
        description_ar="إجماليّ الحقول",
    ),
    ReportField(
        id="farm_total_area_ha",
        name_ar="إجماليّ المساحة (هكتار)",
        category="farm",
        data_key="total_area_ha",
        value_type="number",
    ),
    ReportField(
        id="farm_active_seasons_count",
        name_ar="المواسم النشطة",
        category="farm",
        data_key="active_seasons_count",
        value_type="number",
    ),
    ReportField(
        id="farm_activities_total",
        name_ar="إجماليّ العمليّات",
        category="farm",
        data_key="activities_total",
        value_type="number",
    ),
    ReportField(
        id="farm_activities_by_status",
        name_ar="العمليّات حسب الحالة",
        category="farm",
        data_key="activities_by_status",
        value_type="chart",
    ),
    ReportField(
        id="farm_open_alerts_count",
        name_ar="التنبيهات المفتوحة",
        category="farm",
        data_key="open_alerts_count",
        value_type="number",
    ),
    ReportField(
        id="farm_area_by_crop",
        name_ar="المساحة حسب المحصول",
        category="farm",
        data_key="area_by_crop",
        value_type="chart",
    ),
    # ── field: GET /api/v1/reports/field/{field_id}/summary ──
    ReportField(
        id="field_name",
        name_ar="اسم الحقل",
        category="field",
        data_key="name",
        value_type="text",
    ),
    ReportField(
        id="field_area_ha",
        name_ar="مساحة الحقل (هكتار)",
        category="field",
        data_key="area_ha",
        value_type="number",
    ),
    ReportField(
        id="field_crop",
        name_ar="المحصول",
        category="field",
        data_key="crop",
        value_type="text",
    ),
    ReportField(
        id="field_soil_type",
        name_ar="نوع التربة",
        category="field",
        data_key="soil_type",
        value_type="text",
    ),
    ReportField(
        id="field_current_season",
        name_ar="الموسم النشط",
        category="field",
        data_key="current_season",
        value_type="table",
    ),
    ReportField(
        id="field_activities_by_type",
        name_ar="عمليّات الحقل حسب النوع",
        category="field",
        data_key="activities_by_type",
        value_type="chart",
    ),
    ReportField(
        id="field_recent_alerts",
        name_ar="آخر تنبيهات الحقل",
        category="field",
        data_key="recent_alerts",
        value_type="table",
    ),
    # ── season: GET /api/v1/reports/season/{season_id}/summary ──
    ReportField(
        id="season_crops",
        name_ar="محاصيل الموسم",
        category="season",
        data_key="crops",
        value_type="text",
    ),
    ReportField(
        id="season_cultivar",
        name_ar="الصنف",
        category="season",
        data_key="cultivar",
        value_type="text",
    ),
    ReportField(
        id="season_irrigation_type",
        name_ar="نوع الريّ",
        category="season",
        data_key="irrigation_type",
        value_type="text",
    ),
    ReportField(
        id="season_sowing_date",
        name_ar="تاريخ البذر",
        category="season",
        data_key="sowing_date",
        value_type="text",
    ),
    ReportField(
        id="season_season_end",
        name_ar="نهاية الموسم",
        category="season",
        data_key="season_end",
        value_type="text",
    ),
    ReportField(
        id="season_stage_count",
        name_ar="عدد المراحل",
        category="season",
        data_key="stage_count",
        value_type="number",
    ),
    ReportField(
        id="season_activities_count",
        name_ar="عدد عمليّات الموسم",
        category="season",
        data_key="activities_count",
        value_type="number",
    ),
    # ── cost/activity: FieldReport (operation_report CSV) ──
    ReportField(
        id="op_irrigation_events",
        name_ar="أحداث الريّ",
        category="activity",
        data_key="irrigation_events",
        value_type="number",
    ),
    ReportField(
        id="op_total_water_m3",
        name_ar="إجماليّ الماء (م³)",
        category="activity",
        data_key="total_water_m3",
        value_type="number",
    ),
    ReportField(
        id="op_fertilizer_events",
        name_ar="أحداث التسميد",
        category="activity",
        data_key="fertilizer_events",
        value_type="number",
    ),
    ReportField(
        id="op_total_nitrogen_kg",
        name_ar="النيتروجين (كغ)",
        category="cost",
        data_key="total_nitrogen_kg",
        value_type="number",
    ),
    ReportField(
        id="op_avg_ndvi",
        name_ar="متوسّط NDVI",
        category="field",
        data_key="avg_ndvi",
        value_type="number",
    ),
    ReportField(
        id="op_estimated_yield_kg_ha",
        name_ar="الإنتاج المتوقّع (كغ/هـ)",
        category="cost",
        data_key="estimated_yield_kg_ha",
        value_type="number",
    ),
)

# الكتالوج كقاموس مفهرس بالـid (مصدر الحقيقة عمّا تنتجه المنصّة).
_CATALOG: dict[str, ReportField] = {f.id: f for f in _CATALOG_FIELDS}


# ─── واجهات الكتالوج ─────────────────────────────────────────────


def list_report_fields() -> list[ReportField]:
    """يُعيد كلّ حقول الكتالوج (قائمة جديدة كي لا يُعدَّل الكتالوج)."""
    return list(_CATALOG.values())


def get_report_field(field_id: str) -> ReportField | None:
    """يُعيد حقل الكتالوج بالـid، أو None إن لم يوجد."""
    return _CATALOG.get(field_id)


def fields_for_category(category: str) -> list[ReportField]:
    """يُرشّح حقول الكتالوج بالفئة المُعطاة."""
    return [f for f in _CATALOG.values() if f.category == category]


# ─── مواصفة التقرير ──────────────────────────────────────────────


@dataclass(frozen=True)
class ReportSpec:
    """مواصفة تقرير مُتحقَّق منها — ناتج build_report_spec.

    title_ar:   عنوان التقرير بالعربيّة.
    date_from:  بداية المدى (نصّ ISO أو None).
    date_to:    نهاية المدى (نصّ ISO أو None).
    field_ids:  معرّفات حقول الكتالوج المختارة (مُصفّاة على الموجود فقط).
    format:     صيغة الإخراج (ضمن ALLOWED_FORMATS).
    """

    title_ar: str
    date_from: str | None
    date_to: str | None
    field_ids: tuple[str, ...]
    format: str


_DEFAULT_TITLE = "تقرير مخصّص"


def _coerce_str_or_none(value: object) -> str | None:
    """يُحوّل القيمة إلى نصّ غير فارغ أو None (بِرفق، لا يرمي)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_report_spec(selection: dict) -> dict:
    """يبني مواصفة تقرير من اختيار تصريحيّ — نقيّ، لا يرمي على اختيار سيّئ.

    المُدخَل (كلّه اختياريّ عدا المنطق الافتراضيّ):
        {
          "title": str?,           # العنوان (افتراضيّ: «تقرير مخصّص»)
          "date_from": str?,       # بداية المدى (ISO)
          "date_to": str?,         # نهاية المدى (ISO)
          "field_ids": [str, ...], # معرّفات حقول الكتالوج
          "format": str?,          # csv|json|pdf (افتراضيّ: csv)
        }

    السلوك:
        - يُبقي فقط field_ids الموجودة في الكتالوج؛ المجهولة تذهب إلى warnings
          (لا يرمي استثناءً).
        - صيغة غائبة/غير صالحة ⇒ csv + تحذير.
        - اختيار فارغ/غير قاموس/مُشوَّش ⇒ لا يرمي (يُعيد مواصفة افتراضيّة).

    المُخرَج:
        {
          "spec": <ReportSpec كقاموس>,
          "resolved_fields": [بيانات حقل الكتالوج الوصفيّة, ...],
          "warnings": [str, ...],
        }

    صدق: هذه *مواصفة* فقط؛ التجميع/التصيير يُوصَل لاحقاً بنقاط /reports
    والمُصدِّرات في api/reports.py — متابعة موثَّقة.
    """
    warnings: list[str] = []

    # حماية: اختيار غير قاموس ⇒ نُعامله كاختيار فارغ مع تحذير.
    if not isinstance(selection, dict):
        warnings.append("الاختيار ليس قاموساً — استُخدمت مواصفة افتراضيّة")
        selection = {}

    # العنوان.
    title_ar = _coerce_str_or_none(selection.get("title")) or _DEFAULT_TITLE

    # المدى الزمنيّ (يُمرَّر كما هو نصّاً؛ التحقّق العميق من التواريخ متابعة).
    date_from = _coerce_str_or_none(selection.get("date_from"))
    date_to = _coerce_str_or_none(selection.get("date_to"))

    # حقول التقرير: نُبقي الموجود في الكتالوج فقط، والمجهول → تحذير.
    raw_field_ids = selection.get("field_ids", [])
    if not isinstance(raw_field_ids, (list, tuple)):
        warnings.append("field_ids ليست قائمة — تجوهلت")
        raw_field_ids = []

    valid_ids: list[str] = []
    resolved_fields: list[dict] = []
    seen: set[str] = set()
    for fid in raw_field_ids:
        key = str(fid)
        cat_field = _CATALOG.get(key)
        if cat_field is None:
            warnings.append(f"حقل مجهول تُجوهِل: {key}")
            continue
        if key in seen:
            continue  # تكرار: نُبقي أوّل ظهور فقط
        seen.add(key)
        valid_ids.append(key)
        resolved_fields.append(asdict(cat_field))

    # الصيغة: غائبة/غير صالحة ⇒ csv + تحذير.
    raw_format = selection.get("format")
    fmt = str(raw_format).strip().lower() if raw_format is not None else ""
    if fmt not in ALLOWED_FORMATS:
        if raw_format is not None:
            warnings.append(
                f"صيغة غير مدعومة ({raw_format!r}) — استُخدمت الافتراضيّة {_DEFAULT_FORMAT}"
            )
        fmt = _DEFAULT_FORMAT

    spec = ReportSpec(
        title_ar=title_ar,
        date_from=date_from,
        date_to=date_to,
        field_ids=tuple(valid_ids),
        format=fmt,
    )

    return {
        "spec": asdict(spec),
        "resolved_fields": resolved_fields,
        "warnings": warnings,
    }
