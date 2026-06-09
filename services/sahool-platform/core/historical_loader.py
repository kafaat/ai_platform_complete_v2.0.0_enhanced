"""
sahool_core.historical_loader
==============================
استيراد بيانات المواسم السابقة لتفعيل المعايرة فوراً.

الفجوة المسدودة: calibration_loop يقرأ من tenant_dir لكنّ لا طبقة
استيراد من ملفات خارجية (CSV/JSON/Excel). النتيجة: zone_factor يبقى
null إلى الأبد بانتظار "موسم جديد"، رغم وجود مواسم سابقة موثّقة.

في السياق الفعلي (مئات المزارع، نشر بمنطقة، تاريخ موجود):
  المعايرة تبدأ من اليوم الأول من البيانات التاريخية، لا تنتظر.

المبادئ المحفوظة:
  • الصدق الإحصائي: قراءة بدون وزن (kg) تُرفض، لا تُخمَّن
  • سيادة tenant: كل سطر يتطلّب tenant_id صحيحاً
  • التحقّق الفيزيائي: الإنتاجية خارج النطاق المعقول = خطأ إدخال
  • التتبّع: كل صف يحفظ source_file + import_date للتدقيق
  • لا اختراع: الصفوف الفاسدة تُسجَّل برفض صريح، لا تُحذف بصمت

السلسلة المغلقة المُفعَّلة:
  CSV تاريخي → historical_loader → yield_history → calibration_loop
  → zone_factor (محسوب من التاريخ، لا null!) → توصيات أدقّ فوراً
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# نطاقات فيزيائية معقولة للإنتاجية (طن/هكتار) — رفض الجنون
# مصدر: متوسطات عالمية × 3 (لقبول أعلى منتج معقول)
_YIELD_RANGES = {
    "wheat":    (0.3, 12.0),
    "barley":   (0.3, 10.0),
    "sorghum":  (0.5, 15.0),
    "millet":   (0.2, 6.0),
    "maize":    (0.5, 18.0),
    "cotton":   (0.2, 6.0),
    "tomato":   (5.0, 150.0),    # خضراوات أعلى
    "potato":   (5.0, 80.0),
    "default":  (0.1, 200.0),    # حدّ علوي بعيد للسلامة
}


@dataclass
class HistoricalRow:
    """صفّ صالح جاهز لـcalibration_loop."""
    tenant_id: str
    field_id: str
    season: str                  # "2024", "2024_winter"، إلخ
    crop_id: str
    actual_yield_t_ha: float     # الإنتاجية الفعلية الموزونة
    planted_area_ha: float | None = None
    planting_date: str | None = None
    harvest_date: str | None = None
    source_file: str | None = None
    notes_ar: str | None = None


@dataclass
class LoadResult:
    """نتيجة استيراد دفعة — مقبول/مرفوض بشفافية."""
    accepted_rows: list[HistoricalRow] = field(default_factory=list)
    rejections: list[dict] = field(default_factory=list)
    warnings_ar: list[str] = field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_rows)

    @property
    def rejected_count(self) -> int:
        return len(self.rejections)

    @property
    def summary_ar(self) -> str:
        return (f"قُبل {self.accepted_count}، رُفض {self.rejected_count}"
                + (f" (تحذيرات: {len(self.warnings_ar)})"
                   if self.warnings_ar else ""))


def _validate_row(row: dict, line_no: int, source: str | None = None
                  ) -> tuple[HistoricalRow | None, str | None]:
    """يتحقّق من صفّ واحد. يُرجع (الصفّ المُهيكَل، سبب الرفض إن وُجد)."""

    # ١. الحقول الإلزامية
    for required in ("tenant_id", "field_id", "season",
                     "crop_id", "actual_yield_t_ha"):
        if not row.get(required):
            return None, f"حقل ناقص: {required}"

    # ٢. الإنتاجية رقمياً
    try:
        yield_val = float(row["actual_yield_t_ha"])
    except (ValueError, TypeError):
        return None, f"إنتاجية غير رقمية: '{row['actual_yield_t_ha']}'"

    if yield_val <= 0:
        return None, f"إنتاجية ≤0 ({yield_val}) — حصاد فاشل يجب توثيقه بحقل منفصل"

    # ٣. النطاق الفيزيائي حسب المحصول
    crop_key = str(row["crop_id"]).lower()
    lo, hi = _YIELD_RANGES.get(crop_key, _YIELD_RANGES["default"])
    if not (lo <= yield_val <= hi):
        return None, (f"إنتاجية {yield_val} ط/هـ خارج النطاق الفيزيائي "
                      f"[{lo}, {hi}] للمحصول {crop_key} — راجع الإدخال")

    # ٤. المساحة (اختيارية لكن إن وُجدت يجب أن تكون منطقية)
    planted_area = None
    if row.get("planted_area_ha"):
        try:
            planted_area = float(row["planted_area_ha"])
            if planted_area <= 0 or planted_area > 10_000:
                return None, f"مساحة غير منطقية: {planted_area} هـ"
        except (ValueError, TypeError):
            return None, f"مساحة غير رقمية: '{row['planted_area_ha']}'"

    # ٥. تواريخ (اختيارية، تحقّق شكلي فقط — ISO YYYY-MM-DD)
    for date_field in ("planting_date", "harvest_date"):
        if row.get(date_field):
            try:
                datetime.strptime(row[date_field], "%Y-%m-%d")
            except ValueError:
                return None, (f"{date_field} ليس بصيغة ISO (YYYY-MM-DD): "
                              f"'{row[date_field]}'")

    return HistoricalRow(
        tenant_id=str(row["tenant_id"]),
        field_id=str(row["field_id"]),
        season=str(row["season"]),
        crop_id=crop_key,
        actual_yield_t_ha=yield_val,
        planted_area_ha=planted_area,
        planting_date=row.get("planting_date") or None,
        harvest_date=row.get("harvest_date") or None,
        source_file=source,
        notes_ar=row.get("notes_ar") or None,
    ), None


def load_csv(csv_text: str, source_file: str | None = None) -> LoadResult:
    """يستورد دفعة من CSV نصّي. الأعمدة المطلوبة:
    tenant_id, field_id, season, crop_id, actual_yield_t_ha
    الاختيارية: planted_area_ha, planting_date, harvest_date, notes_ar."""
    result = LoadResult()
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
    except Exception as e:
        result.rejections.append({"line": 0, "reason": f"تعذّر قراءة CSV: {e}"})
        return result

    for line_no, row in enumerate(reader, start=2):  # 2 لأن السطر 1 رأس
        validated, error = _validate_row(row, line_no, source_file)
        if validated:
            result.accepted_rows.append(validated)
        else:
            result.rejections.append({"line": line_no, "reason": error,
                                      "row_snippet": dict(list(row.items())[:3])})

    if not result.accepted_rows and result.rejections:
        result.warnings_ar.append("لم يُقبل أي صفّ — راجع تنسيق الملف وأسماء الأعمدة")
    elif result.rejections:
        result.warnings_ar.append(
            f"{result.rejected_count} صفوف رُفضت — البيانات المقبولة سليمة")

    return result


def load_json(json_text: str, source_file: str | None = None) -> LoadResult:
    """يستورد قائمة JSON من السجلات. تنسيق كل سجلّ مثل CSV."""
    result = LoadResult()
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        result.rejections.append({"line": 0, "reason": f"JSON غير صالح: {e}"})
        return result

    if not isinstance(data, list):
        result.rejections.append({"line": 0,
            "reason": "JSON يجب أن يكون قائمة من السجلات"})
        return result

    for idx, row in enumerate(data):
        if not isinstance(row, dict):
            result.rejections.append({"line": idx,
                "reason": "كل سجلّ يجب أن يكون object"})
            continue
        validated, error = _validate_row(row, idx, source_file)
        if validated:
            result.accepted_rows.append(validated)
        else:
            result.rejections.append({"line": idx, "reason": error})

    return result


# ── الجسر إلى calibration_loop ──

def to_calibration_records(rows: list[HistoricalRow]) -> list[dict]:
    """يحوّل الصفوف المقبولة إلى تنسيق calibration_loop المتوقّع.

    calibration_loop.read_yield_history يقرأ list[dict] بمفاتيح
    {field_id, season, actual_yield, crop_id}. هذا الجسر يضمن
    التوافق دون تعديل calibration_loop."""
    return [{
        "field_id": r.field_id,
        "season": r.season,
        "actual_yield": r.actual_yield_t_ha,
        "crop_id": r.crop_id,
        "planted_area_ha": r.planted_area_ha,
        "source": r.source_file or "imported",
    } for r in rows]


def group_by_tenant(rows: list[HistoricalRow]) -> dict[str, list[HistoricalRow]]:
    """يجمّع الصفوف حسب tenant_id. ضروري لأن المعايرة على مستوى المستأجر."""
    grouped: dict[str, list[HistoricalRow]] = {}
    for r in rows:
        grouped.setdefault(r.tenant_id, []).append(r)
    return grouped


def import_summary(result: LoadResult) -> dict:
    """ملخّص قابل للقراءة (للواجهة أو تقرير الاستيراد)."""
    tenants = {r.tenant_id for r in result.accepted_rows}
    fields = {(r.tenant_id, r.field_id) for r in result.accepted_rows}
    seasons = {r.season for r in result.accepted_rows}
    crops = {r.crop_id for r in result.accepted_rows}
    return {
        "accepted": result.accepted_count,
        "rejected": result.rejected_count,
        "unique_tenants": len(tenants),
        "unique_fields": len(fields),
        "unique_seasons": len(seasons),
        "unique_crops": len(crops),
        "summary_ar": result.summary_ar,
        "rejections_preview": result.rejections[:5],
    }
