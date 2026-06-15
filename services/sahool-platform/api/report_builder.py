"""بانِي التقارير (Report Builder) — سجلّ حقول التقرير + مُدقّق مواصفة نقيّ.

المشكلة المسدودة: اليوم تُرمَّز التقارير كأكواد مضمّنة (انظر api/reports.py: FieldReport
بحقوله الثابتة، وendpoints التقارير في main.py التي تُجمّع أعمدة محدّدة سلفاً). كلّ
تقرير جديد أو عمود جديد يعني تعديل كود في طبقات متعدّدة. هذا الملف يحوّل **وصف الحقول
المتاحة** إلى بيانات (metadata) لا كود: كلّ حقل تقرير يُعلَن مرّة واحدة هنا (المعرّف،
الأسماء، الكيان المصدر، النوع، الوحدة، الوصف)، فإضافة حقل = سطر بيانات واحد.

`build_report_spec(selection)` دالّة **نقيّة** (لا قاعدة، لا شبكة): تأخذ اختيار المستخدم
(الحقول المطلوبة + المرشِّحات الاختياريّة)، تتحقّق منه مقابل السجلّ، وتُعيد **المواصفة
المُتحقَّق منها فقط** + الحقول المُحلّلة (resolved_fields) + تحذيرات (warnings).

نطاق هذا الإصدار (PR): يُسلّم **السجلّ + مُدقّق المواصفة** فقط. تجميع البيانات الفعليّ
(قراءة الصفوف من القاعدة وملء القيم) و**التصيير** (CSV/PDF عبر api/reports.py) **متابعة
لاحقة** — هنا نُنتج المواصفة المُتحقَّق منها لا التقرير المُجمَّع.

أمانة البيانات: الحقول والكيانات مأخوذة حرفيّاً من api/reports.py (FieldReport) ومن
endpoints التقارير في main.py (farm-summary/field-summary/season-summary) — لا نخترع
أعمدة لا مصدر لها في النموذج القائم.
"""

from __future__ import annotations

from dataclasses import dataclass

# الكيانات المصدر المسموح بها — تطابق نطاقات التقارير القائمة في main.py/reports.py.
# field: حقل زراعيّ واحد، season: موسم محصول، operation: تجميع متعدّد الحقول (مزرعة).
ALLOWED_ENTITIES: tuple[str, ...] = ("field", "season", "operation")

# أنواع القيم المسموح بها لحقل التقرير (للتصيير/التجميع لاحقاً).
ALLOWED_DTYPES: tuple[str, ...] = ("string", "number", "integer", "date", "list")


@dataclass(frozen=True)
class ReportField:
    """حقل تقرير مُعلَن كبيانات — وحدة كتالوج واحدة (declare-a-field).

    - `id`: معرّف ثابت قابل للبرمجة (مثل "area_ha").
    - `name_ar`: اسم معروض بالعربيّة.
    - `entity`: الكيان المصدر ضمن ALLOWED_ENTITIES.
    - `dtype`: نوع القيمة ضمن ALLOWED_DTYPES (للتجميع/التصيير لاحقاً).
    - `unit`: الوحدة (مثل "ha", "kg", "m3"؛ فارغة للنصوص/التواريخ).
    - `description_ar`: وصف موجز + تأريض المصدر في النموذج القائم.
    """

    id: str
    name_ar: str
    entity: str
    dtype: str
    unit: str = ""
    description_ar: str = ""

    def as_dict(self) -> dict:
        """تشكيل JSON لطبقة الـAPI."""
        return {
            "id": self.id,
            "name_ar": self.name_ar,
            "entity": self.entity,
            "dtype": self.dtype,
            "unit": self.unit,
            "description_ar": self.description_ar,
        }


# ── السجلّ المركزيّ: مصدر واحد لحقول التقرير المتاحة ─────────────────
# كلّ مدخل مؤرَّض على api/reports.py (FieldReport) وendpoints التقارير في main.py.
_REGISTRY: dict[str, ReportField] = {
    # ── الهويّة والوصف (field) — FieldReport.field_id/field_name_ar/crop/area_ha ──
    "field_id": ReportField(
        id="field_id",
        name_ar="معرّف الحقل",
        entity="field",
        dtype="string",
        description_ar="المعرّف الفريد للحقل — مؤرَّض على FieldReport.field_id.",
    ),
    "field_name": ReportField(
        id="field_name",
        name_ar="اسم الحقل",
        entity="field",
        dtype="string",
        description_ar="اسم الحقل المعروض — مؤرَّض على FieldReport.field_name_ar.",
    ),
    "crop": ReportField(
        id="crop",
        name_ar="المحصول",
        entity="field",
        dtype="string",
        description_ar="نوع المحصول المزروع — مؤرَّض على FieldReport.crop.",
    ),
    "area_ha": ReportField(
        id="area_ha",
        name_ar="المساحة",
        entity="field",
        dtype="number",
        unit="ha",
        description_ar="مساحة الحقل بالهكتار — مؤرَّض على FieldReport.area_ha.",
    ),
    # ── الموسم (season) — FieldReport.season_label/planting_date/harvest_date ──
    "season_label": ReportField(
        id="season_label",
        name_ar="الموسم",
        entity="season",
        dtype="string",
        description_ar="وسم الموسم النشط — مؤرَّض على FieldReport.season_label.",
    ),
    "planting_date": ReportField(
        id="planting_date",
        name_ar="تاريخ البذر",
        entity="season",
        dtype="date",
        description_ar="تاريخ زراعة المحصول — مؤرَّض على FieldReport.planting_date.",
    ),
    "harvest_date": ReportField(
        id="harvest_date",
        name_ar="تاريخ الحصاد",
        entity="season",
        dtype="date",
        description_ar="تاريخ الحصاد — مؤرَّض على FieldReport.harvest_date.",
    ),
    # ── ملخّص العمليّات (field) — FieldReport.irrigation_events/total_water_m3/... ──
    "irrigation_events": ReportField(
        id="irrigation_events",
        name_ar="أحداث الريّ",
        entity="field",
        dtype="integer",
        unit="count",
        description_ar="عدد أحداث الريّ — مؤرَّض على FieldReport.irrigation_events.",
    ),
    "total_water_m3": ReportField(
        id="total_water_m3",
        name_ar="إجماليّ الماء",
        entity="field",
        dtype="number",
        unit="m3",
        description_ar="إجماليّ ماء الريّ بالمتر المكعّب — مؤرَّض على FieldReport.total_water_m3.",
    ),
    "fertilizer_events": ReportField(
        id="fertilizer_events",
        name_ar="أحداث التسميد",
        entity="field",
        dtype="integer",
        unit="count",
        description_ar="عدد أحداث التسميد — مؤرَّض على FieldReport.fertilizer_events.",
    ),
    "pest_treatments": ReportField(
        id="pest_treatments",
        name_ar="علاجات الآفات",
        entity="field",
        dtype="integer",
        unit="count",
        description_ar="عدد علاجات الآفات — مؤرَّض على FieldReport.pest_treatments.",
    ),
    # ── الاستشعار عن بُعد (field) — FieldReport.avg_ndvi/max_ndvi/min_ndvi ──
    "avg_ndvi": ReportField(
        id="avg_ndvi",
        name_ar="متوسّط NDVI",
        entity="field",
        dtype="number",
        unit="dimensionless",
        description_ar="متوسّط مؤشّر NDVI الموسميّ — مؤرَّض على FieldReport.avg_ndvi.",
    ),
    # ── الإنتاج (field) — FieldReport.estimated_yield_*/actual_yield_* ──
    "estimated_yield_total_kg": ReportField(
        id="estimated_yield_total_kg",
        name_ar="الإنتاج المتوقّع",
        entity="field",
        dtype="number",
        unit="kg",
        description_ar="الإنتاج المتوقّع الكلّيّ — مؤرَّض على FieldReport.estimated_yield_total_kg.",
    ),
    "actual_yield_total_kg": ReportField(
        id="actual_yield_total_kg",
        name_ar="الإنتاج الفعليّ",
        entity="field",
        dtype="number",
        unit="kg",
        description_ar="الإنتاج الفعليّ بعد الحصاد — مؤرَّض على FieldReport.actual_yield_total_kg.",
    ),
    # ── التربة (field) — FieldReport.last_soil_ph/last_soil_ec ──
    "last_soil_ph": ReportField(
        id="last_soil_ph",
        name_ar="حموضة التربة (pH)",
        entity="field",
        dtype="number",
        unit="pH",
        description_ar="آخر قراءة حموضة تربة — مؤرَّض على FieldReport.last_soil_ph.",
    ),
    # ── الشذوذات (field) — FieldReport.anomalies (قائمة نصّيّة) ──
    "anomalies": ReportField(
        id="anomalies",
        name_ar="التنبيهات/الشذوذات",
        entity="field",
        dtype="list",
        description_ar="قائمة الشذوذات/التحذيرات المرصودة — مؤرَّض على FieldReport.anomalies.",
    ),
}


def list_report_fields() -> list[dict]:
    """كلّ حقول التقرير المُعلَنة كقوائم dict (لطبقة الـAPI)، بترتيب الإدراج."""
    return [rf.as_dict() for rf in _REGISTRY.values()]


def get_report_field(id: str) -> dict | None:
    """حقل التقرير بمعرّفه كـdict، أو None إن لم يكن مُعلَناً."""
    rf = _REGISTRY.get(id)
    return rf.as_dict() if rf is not None else None


def known_field_ids() -> list[str]:
    """معرّفات حقول التقرير المُعلَنة، بترتيب الإدراج."""
    return list(_REGISTRY.keys())


def build_report_spec(selection: dict | None) -> dict:
    """يبني **مواصفة تقرير مُتحقَّق منها** من اختيار المستخدم — دالّة نقيّة (لا قاعدة/شبكة).

    المدخل `selection` (dict) يدعم:
      • `fields`: قائمة معرّفات حقول مطلوبة (إلزاميّة عمليّاً — تُرفَض لو فارغة).
      • `entity`: كيان مصدر اختياريّ لتقييد الحقول عليه (ضمن ALLOWED_ENTITIES).
      • `filters`: dict مرشِّحات اختياريّ يُمرَّر كما هو (لا يُفسَّر هنا — متابعة).

    المخرَج: مواصفة مُتحقَّق منها فقط — **لا بيانات مُجمَّعة** (التجميع/التصيير متابعة):
      • `fields`: المعرّفات المعروفة المطلوبة (بترتيب الطلب، دون تكرار).
      • `resolved_fields`: الـmetadata الكامل لكلّ حقل معروف (من السجلّ).
      • `entity`: الكيان المُقيِّد إن مُرّر وكان صالحاً.
      • `filters`: المرشِّحات كما وردت (مُمرَّرة دون تفسير).
      • `warnings`: تحذيرات لا تكسر البناء (حقول مجهولة، كيان غير صالح، خارج التقييد...).

    التحقّق يرفع ValueError عند مدخل غير صالح بنيويّاً (ليس dict، أو لا حقول معروفة).
    """
    if selection is None or not isinstance(selection, dict):
        raise ValueError("اختيار التقرير يجب أن يكون كائناً (dict) يحوي 'fields'.")

    warnings: list[str] = []

    # الكيان المُقيِّد (اختياريّ) — تحذير لا رفض لو غير صالح.
    entity = selection.get("entity")
    if entity is not None and entity not in ALLOWED_ENTITIES:
        warnings.append(f"كيان غير معروف '{entity}' — تجاهَلَ التقييد بالكيان.")
        entity = None

    raw_fields = selection.get("fields") or []
    if not isinstance(raw_fields, list):
        raise ValueError("'fields' يجب أن يكون قائمة معرّفات حقول.")

    resolved: list[dict] = []
    field_ids: list[str] = []
    seen: set[str] = set()
    for fid in raw_fields:
        if fid in seen:
            warnings.append(f"حقل مكرّر '{fid}' — أُدرِج مرّة واحدة.")
            continue
        meta = _REGISTRY.get(fid)
        if meta is None:
            warnings.append(f"حقل مجهول '{fid}' — استُبعِد من المواصفة.")
            continue
        # لو قُيّد الكيان: تحذير على الحقول خارجه (لا رفض — تبقى في المواصفة).
        if entity is not None and meta.entity != entity:
            warnings.append(f"الحقل '{fid}' من كيان '{meta.entity}' خارج الكيان المُقيَّد '{entity}'.")
        seen.add(fid)
        field_ids.append(fid)
        resolved.append(meta.as_dict())

    if not field_ids:
        raise ValueError("لا حقول معروفة في الاختيار — لا يمكن بناء مواصفة فارغة.")

    spec: dict = {
        "fields": field_ids,
        "resolved_fields": resolved,
        "warnings": warnings,
    }
    if entity is not None:
        spec["entity"] = entity
    filters = selection.get("filters")
    if filters is not None:
        # المرشِّحات تُمرَّر دون تفسير — تفسيرها/تطبيقها متابعة لاحقة (تجميع البيانات).
        spec["filters"] = filters
    return spec
