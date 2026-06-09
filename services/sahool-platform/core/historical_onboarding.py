"""
core/historical_onboarding.py — إطار استيعاب البيانات التاريخيّة
=================================================================

السياق:
  المستخدم يملك بيانات لـعدّة مزارعين، عدّة مواسم، عدّة سنوات.
  هذه نقطة التحوّل: ما كان مُؤجَّلاً يصير ممكنناً.

المبدأ التصميمي:
  ✓ لا نفترض schema — نكتشفه من البيانات
  ✓ نُحقّق الجودة قبل ingestion
  ✓ نُولّد تقريراً يخبر المهندس بما يستحقّ البناء
  ✓ ندعم الـformats الشائعة (CSV, Excel، JSON)
  ✓ نحترم source_of_truth (lab > manual > sensor > satellite)

ما هذا الملفّ ليس:
  ✗ ليس loader واحدًا fixed-schema
  ✗ ليس ETL ثقيل (Spark, Airflow) — pure Python
  ✗ ليس parser لـPDF/handwriting (out of scope)

ما هذا الملفّ هو:
  ✓ Schema discovery — يكتشف ما في البيانات
  ✓ Type inference — يستنبط أنواع الأعمدة
  ✓ Quality report — يكشف missing/outliers/inconsistencies
  ✓ Mapping suggestion — يقترح ربط الأعمدة بـcanonical_schemas

سير العمل المتوقَّع:
  ١. المستخدم يرفع ملفّاً
  ٢. discover_schema() يستخرج بنية الملفّ
  ٣. infer_field_types() يحلّل كل عمود
  ٤. quality_report() يكشف المشاكل
  ٥. suggest_mapping() يربط الأعمدة بـcanonical
  ٦. المهندس يراجع ويُصحّح
  ٧. validated_load() يستورد فقط بعد الموافقة
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    """نوع عمود مُستنبَط."""

    INTEGER = "integer"
    FLOAT = "float"
    DATE = "date"
    DATETIME = "datetime"
    STRING = "string"
    BOOLEAN = "boolean"
    IDENTIFIER = "identifier"  # ID-like (UUIDs، أرقام تسلسليّة)
    GEOSPATIAL = "geospatial"  # lat/lon/coordinates
    EMPTY = "empty"  # كل القيم فارغة
    MIXED = "mixed"  # أنواع مختلفة → يحتاج مراجعة


class CanonicalCategory(str, Enum):
    """فئة موحَّدة من canonical_schemas — حيث نربط."""

    # ─── identification ─────
    FARMER_ID = "farmer_id"
    FARM_ID = "farm_id"
    FIELD_ID = "field_id"
    SEASON_ID = "season_id"
    # ─── temporal ─────
    SOWING_DATE = "sowing_date"
    HARVEST_DATE = "harvest_date"
    OBSERVATION_DATE = "observation_date"
    # ─── agronomic ─────
    CROP = "crop"
    AREA_HA = "area_ha"
    YIELD_KG_HA = "yield_kg_ha"
    YIELD_TOTAL_KG = "yield_total_kg"
    VARIETY = "variety"
    # ─── inputs ─────
    SEED_KG_HA = "seed_kg_ha"
    FERTILIZER_KG_HA = "fertilizer_kg_ha"
    IRRIGATION_MM = "irrigation_mm"
    # ─── soil/water (lab/sensor) ─────
    SOIL_PH = "soil_ph"
    SOIL_EC = "soil_ec"
    SOIL_OM_PCT = "soil_om_pct"
    SOIL_N_PPM = "soil_n_ppm"
    # ─── spatial ─────
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    # ─── economic ─────
    PRICE_PER_KG = "price_per_kg"
    COST_TOTAL = "cost_total"
    # ─── unknown ─────
    UNKNOWN = "unknown"


@dataclass
class ColumnProfile:
    """ملف تعريف عمود واحد."""

    column_name: str
    raw_type: FieldType
    sample_values: list[Any]
    distinct_count: int
    null_count: int
    null_pct: float
    # للأعمدة الرقميّة
    min_val: float | None = None
    max_val: float | None = None
    mean_val: float | None = None
    # للنطاق المتوقَّع (لاكتشاف outliers)
    looks_plausible: bool = True
    plausibility_notes: list[str] = field(default_factory=list)
    # الـmapping المقترَح
    suggested_mapping: CanonicalCategory | None = None
    mapping_confidence: float = 0.0  # ٠-١


@dataclass
class QualityIssue:
    """مشكلة جودة مُكتشَفة."""

    severity: str  # 'error' | 'warning' | 'info'
    column: str | None
    row_indices: list[int]  # أوّل ٢٠ row فقط
    message_ar: str
    suggested_action_ar: str


@dataclass
class OnboardingReport:
    """التقرير الكامل عن ملفّ مرفوع."""

    file_name: str
    row_count: int
    column_count: int
    detected_format: str  # 'csv' | 'xlsx' | 'json'
    encoding: str  # 'utf-8' | 'utf-8-sig' | 'cp1256' ...
    columns: list[ColumnProfile]
    issues: list[QualityIssue]
    mapping_coverage_pct: float  # ٪ الأعمدة المربوطة بـcanonical
    readiness: str  # 'ready' | 'needs_review' | 'blocked'


# ─── Pattern dictionaries (للـsuggested mapping) ─────────────────

# عناوين الأعمدة الشائعة (عربيّة + إنجليزيّة)
# الترتيب: confidence score — كل match يضع confidence
COLUMN_NAME_PATTERNS: dict[CanonicalCategory, list[tuple[str, float]]] = {
    CanonicalCategory.FARMER_ID: [
        (r"^farmer.?id$", 0.95),
        (r"^مزارع.?رقم", 0.9),
        (r"^id.?farmer", 0.85),
    ],
    CanonicalCategory.FIELD_ID: [
        (r"^field.?id$", 0.95),
        (r"^plot.?id$", 0.85),
        (r"^حقل.?رقم", 0.9),
        (r"^رقم.?الحقل", 0.9),
    ],
    CanonicalCategory.SEASON_ID: [
        (r"season", 0.85),
        (r"موسم", 0.9),
    ],
    CanonicalCategory.SOWING_DATE: [
        (r"sowing", 0.95),
        (r"planting", 0.9),
        (r"البذار|الزراعة|زراعة", 0.9),
    ],
    CanonicalCategory.HARVEST_DATE: [
        (r"harvest", 0.95),
        (r"حصاد", 0.9),
    ],
    CanonicalCategory.CROP: [
        (r"^crop$", 0.95),
        (r"محصول", 0.9),
    ],
    CanonicalCategory.AREA_HA: [
        (r"area.?ha", 0.95),
        (r"المساحة|مساحة", 0.85),
        (r"^area$", 0.7),
        (r"هكتار", 0.85),
    ],
    CanonicalCategory.YIELD_KG_HA: [
        (r"yield.?kg.?ha", 0.95),
        (r"yield.?per.?ha", 0.9),
        (r"إنتاج.?هكتار|إنتاجية", 0.85),
    ],
    CanonicalCategory.YIELD_TOTAL_KG: [
        (r"yield.?total|total.?yield|total.?harvest", 0.9),
        (r"إنتاج.?كلي|الإنتاج.?الكلي|الحصاد.?الكلي", 0.85),
    ],
    CanonicalCategory.VARIETY: [
        (r"variety|cultivar", 0.95),
        (r"صنف|نوع.?البذرة", 0.85),
    ],
    CanonicalCategory.SEED_KG_HA: [
        (r"seed.?kg.?ha|seed.?rate", 0.9),
        (r"بذر.?هكتار|كميّة.?البذر", 0.85),
    ],
    CanonicalCategory.FERTILIZER_KG_HA: [
        (r"fertilizer.?kg|n.?rate|n.?applied", 0.85),
        (r"سماد|تسميد|نيتروجين|يوريا", 0.8),
    ],
    CanonicalCategory.IRRIGATION_MM: [
        (r"irrigation.?mm|water.?applied", 0.9),
        (r"ري.?ملم|كمية.?الري|مياه.?الري", 0.85),
    ],
    CanonicalCategory.SOIL_PH: [
        (r"^ph$|soil.?ph", 0.95),
        (r"درجة.?الحموضة", 0.9),
    ],
    CanonicalCategory.SOIL_EC: [
        (r"^ec$|electrical.?conductivity|salinity", 0.95),
        (r"ملوحة|توصيل", 0.9),
    ],
    CanonicalCategory.SOIL_OM_PCT: [
        (r"organic.?matter|^om$", 0.9),
        (r"المادة.?العضوية", 0.9),
    ],
    CanonicalCategory.LATITUDE: [
        (r"^lat(itude)?$", 0.95),
        (r"خط.?العرض", 0.9),
    ],
    CanonicalCategory.LONGITUDE: [
        (r"^lon(g(itude)?)?$|^lng$", 0.95),
        (r"خط.?الطول", 0.9),
    ],
    CanonicalCategory.PRICE_PER_KG: [
        (r"price.?kg|price.?per.?kg|unit.?price", 0.9),
        (r"سعر.?كيلو|سعر.?الوحدة", 0.85),
    ],
}

# نطاقات مُتوقَّعة للأعمدة الرقميّة (لاكتشاف outliers)
EXPECTED_RANGES: dict[CanonicalCategory, tuple[float, float]] = {
    CanonicalCategory.AREA_HA: (0.001, 10_000),  # 1 m² إلى 10K ha
    CanonicalCategory.YIELD_KG_HA: (0, 30_000),  # القمح أعلى ~12000
    CanonicalCategory.YIELD_TOTAL_KG: (0, 1e8),
    CanonicalCategory.SEED_KG_HA: (1, 500),
    CanonicalCategory.FERTILIZER_KG_HA: (0, 1000),
    CanonicalCategory.IRRIGATION_MM: (0, 3000),
    CanonicalCategory.SOIL_PH: (3.5, 10.0),  # فيزيائياً ممكن
    CanonicalCategory.SOIL_EC: (0, 30),  # dS/m
    CanonicalCategory.SOIL_OM_PCT: (0, 30),
    CanonicalCategory.LATITUDE: (-90, 90),
    CanonicalCategory.LONGITUDE: (-180, 180),
}


# ─── Type inference ───────────────────────────────────────────────

_DATE_PATTERNS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%Y%m%d",
]


def _try_parse_date(s: str) -> date | None:
    for fmt in _DATE_PATTERNS:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _try_parse_number(s: str) -> float | None:
    if not isinstance(s, str):
        return None
    # دعم الأرقام العربيّة
    arabic = "٠١٢٣٤٥٦٧٨٩"
    english = "0123456789"
    trans = str.maketrans(arabic, english)
    s = s.strip().translate(trans).replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def infer_column_type(values: list[Any]) -> FieldType:
    """يستنبط نوع عمود من قيمه."""
    non_null = [v for v in values if v is not None and str(v).strip() != ""]
    if not non_null:
        return FieldType.EMPTY

    # محاولة boolean
    bool_strings = {"true", "false", "yes", "no", "نعم", "لا", "1", "0"}
    if all(str(v).strip().lower() in bool_strings for v in non_null):
        unique = set(str(v).strip().lower() for v in non_null)
        if len(unique) <= 2 and not unique.issubset({"0", "1"}):
            return FieldType.BOOLEAN

    # محاولة date
    date_count = sum(1 for v in non_null if _try_parse_date(str(v)) is not None)
    if date_count / len(non_null) > 0.8:
        return FieldType.DATE

    # محاولة number
    number_count = sum(1 for v in non_null if _try_parse_number(str(v)) is not None)
    if number_count / len(non_null) > 0.8:
        # int أم float؟
        int_count = sum(
            1 for v in non_null if (n := _try_parse_number(str(v))) is not None and n == int(n)
        )
        if int_count / len(non_null) > 0.95:
            return FieldType.INTEGER
        return FieldType.FLOAT

    # ID-like: متفاوت تماماً (distinct count قريب من total)
    if len(set(non_null)) / len(non_null) > 0.95 and len(non_null) > 5:
        return FieldType.IDENTIFIER

    return FieldType.STRING


# ─── Mapping suggestion ───────────────────────────────────────────


def suggest_mapping_for_column(
    column_name: str,
    column_type: FieldType,
) -> tuple[CanonicalCategory | None, float]:
    """يقترح canonical category لعمود.

    Returns:
        (CanonicalCategory أو None، confidence ٠-١)
    """
    name_lower = column_name.strip().lower()

    best_cat: CanonicalCategory | None = None
    best_conf = 0.0

    for category, patterns in COLUMN_NAME_PATTERNS.items():
        for pattern, conf in patterns:
            if re.search(pattern, name_lower):
                if conf > best_conf:
                    best_cat = category
                    best_conf = conf
                    break  # لكل category، نأخذ أوّل match

    # تخفيض الـconfidence إذا الـtype لا يطابق التوقّع
    if best_cat:
        expected_numeric = best_cat in EXPECTED_RANGES
        is_numeric = column_type in (FieldType.INTEGER, FieldType.FLOAT)
        if expected_numeric and not is_numeric:
            best_conf *= 0.5
        elif best_cat in (
            CanonicalCategory.SOWING_DATE,
            CanonicalCategory.HARVEST_DATE,
            CanonicalCategory.OBSERVATION_DATE,
        ):
            if column_type != FieldType.DATE:
                best_conf *= 0.5

    return best_cat, best_conf


# ─── Quality checks ───────────────────────────────────────────────


def check_plausibility(
    profile: ColumnProfile,
    category: CanonicalCategory | None,
) -> list[str]:
    """يفحص قيم العمود مقابل النطاق المتوقَّع."""
    notes = []
    if category is None or category not in EXPECTED_RANGES:
        return notes

    expected_min, expected_max = EXPECTED_RANGES[category]

    if profile.min_val is not None and profile.min_val < expected_min:
        notes.append(f"قيم أدنى من المتوقَّع: min={profile.min_val}, متوقَّع >={expected_min}")
    if profile.max_val is not None and profile.max_val > expected_max:
        notes.append(f"قيم أعلى من المتوقَّع: max={profile.max_val}, متوقَّع <={expected_max}")
    return notes


# ─── Main API ─────────────────────────────────────────────────────


def profile_column(
    column_name: str,
    values: list[Any],
) -> ColumnProfile:
    """يبني ملفّ تعريف كامل لعمود."""
    inferred_type = infer_column_type(values)
    null_count = sum(1 for v in values if v is None or (isinstance(v, str) and v.strip() == ""))
    distinct = len(set(str(v) for v in values if v is not None and str(v).strip() != ""))
    sample = [v for v in values if v is not None and str(v).strip() != ""][:10]

    profile = ColumnProfile(
        column_name=column_name,
        raw_type=inferred_type,
        sample_values=sample,
        distinct_count=distinct,
        null_count=null_count,
        null_pct=(null_count / len(values) * 100) if values else 0,
    )

    # إحصاءات للأرقام
    if inferred_type in (FieldType.INTEGER, FieldType.FLOAT):
        nums = []
        for v in values:
            n = _try_parse_number(str(v))
            if n is not None:
                nums.append(n)
        if nums:
            profile.min_val = min(nums)
            profile.max_val = max(nums)
            profile.mean_val = sum(nums) / len(nums)

    # الـmapping
    category, conf = suggest_mapping_for_column(column_name, inferred_type)
    profile.suggested_mapping = category
    profile.mapping_confidence = conf

    # الـplausibility
    notes = check_plausibility(profile, category)
    if notes:
        profile.looks_plausible = False
        profile.plausibility_notes = notes

    return profile


def build_report(
    file_name: str,
    columns_data: dict[str, list[Any]],
    detected_format: str = "csv",
    encoding: str = "utf-8",
) -> OnboardingReport:
    """يبني تقرير onboarding كامل من dict {column_name: [values]}."""
    if not columns_data:
        raise ValueError("columns_data فارغة")

    row_count = max(len(v) for v in columns_data.values())
    profiles = [profile_column(name, values) for name, values in columns_data.items()]

    issues: list[QualityIssue] = []

    # ١. أعمدة بـnull عالية (>50٪)
    for p in profiles:
        if p.null_pct > 50:
            issues.append(
                QualityIssue(
                    severity="warning",
                    column=p.column_name,
                    row_indices=[],
                    message_ar=f"العمود {p.column_name}: {p.null_pct:.0f}٪ فارغ",
                    suggested_action_ar="هل العمود اختياري؟ هل البيانات ناقصة؟",
                )
            )

    # ٢. أعمدة EMPTY كلّياً
    for p in profiles:
        if p.raw_type == FieldType.EMPTY:
            issues.append(
                QualityIssue(
                    severity="error",
                    column=p.column_name,
                    row_indices=[],
                    message_ar=f"العمود {p.column_name}: كل القيم فارغة",
                    suggested_action_ar="احذف العمود أو املأ القيم",
                )
            )

    # ٣. أعمدة بقيم غير معقولة
    for p in profiles:
        if not p.looks_plausible:
            for note in p.plausibility_notes:
                issues.append(
                    QualityIssue(
                        severity="warning",
                        column=p.column_name,
                        row_indices=[],
                        message_ar=f"العمود {p.column_name}: {note}",
                        suggested_action_ar="راجع الـunit (هل الأرقام بالـكيلو/طن؟)",
                    )
                )

    # ٤. أعمدة MIXED type
    for p in profiles:
        if p.raw_type == FieldType.MIXED:
            issues.append(
                QualityIssue(
                    severity="error",
                    column=p.column_name,
                    row_indices=[],
                    message_ar=f"العمود {p.column_name}: أنواع قيم مختلطة",
                    suggested_action_ar="وحّد نوع البيانات في كل صفّ",
                )
            )

    # ٥. الـcoverage
    mapped = [
        p
        for p in profiles
        if p.suggested_mapping and p.suggested_mapping != CanonicalCategory.UNKNOWN
    ]
    coverage = (len(mapped) / len(profiles) * 100) if profiles else 0

    # ٦. الـreadiness
    has_errors = any(i.severity == "error" for i in issues)
    if has_errors:
        readiness = "blocked"
    elif coverage < 50:
        readiness = "needs_review"
    elif any(i.severity == "warning" for i in issues):
        readiness = "needs_review"
    else:
        readiness = "ready"

    return OnboardingReport(
        file_name=file_name,
        row_count=row_count,
        column_count=len(profiles),
        detected_format=detected_format,
        encoding=encoding,
        columns=profiles,
        issues=issues,
        mapping_coverage_pct=coverage,
        readiness=readiness,
    )


# ─── CSV ingestion helper ─────────────────────────────────────────


def ingest_csv_string(
    csv_content: str,
    file_name: str = "uploaded.csv",
    delimiter: str = ",",
) -> OnboardingReport:
    """يستوعب محتوى CSV نصّياً.

    لا يستخدم pandas — يكفي csv standard library.
    """
    import csv
    import io

    reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        raise ValueError("CSV فارغ")

    # نحوّل لـcolumn-oriented
    columns_data: dict[str, list[Any]] = {}
    for col in reader.fieldnames or []:
        columns_data[col] = [row.get(col) for row in rows]

    return build_report(file_name, columns_data, "csv")


# ─── Helpers للعرض ────────────────────────────────────────────────


def format_report_ar(report: OnboardingReport) -> str:
    """تقرير عربي مفهوم للمهندس."""
    lines = []
    lines.append(f"تقرير استيعاب: {report.file_name}")
    lines.append(f"  الصفوف: {report.row_count}")
    lines.append(f"  الأعمدة: {report.column_count}")
    lines.append(f"  الصيغة: {report.detected_format} ({report.encoding})")
    lines.append(f"  تغطية الـmapping: {report.mapping_coverage_pct:.0f}٪")
    lines.append(f"  الحالة: {report.readiness}")
    lines.append("")
    lines.append("الأعمدة المُكتشَفة:")
    for p in report.columns:
        mapped = p.suggested_mapping.value if p.suggested_mapping else "غير محدَّد"
        lines.append(
            f"  • {p.column_name} ({p.raw_type.value}, "
            f"null={p.null_pct:.0f}٪) → {mapped} "
            f"({p.mapping_confidence * 100:.0f}٪)"
        )
    if report.issues:
        lines.append("")
        lines.append(f"المشاكل ({len(report.issues)}):")
        for issue in report.issues:
            icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "•")
            lines.append(f"  {icon} {issue.message_ar}")
            lines.append(f"     → {issue.suggested_action_ar}")
    return "\n".join(lines)
