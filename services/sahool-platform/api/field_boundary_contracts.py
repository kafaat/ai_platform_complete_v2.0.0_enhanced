"""api/field_boundary_contracts.py — عقود الواجهة لمراحل الـML في pipeline الحدود.

هذا الملفّ يُعرّف **عقود واجهة (interface contracts)** لمراحل ML الثلاث في إطار
استخلاص حدود الحقل (multi_temporal_composite, crop_mask, delineation). الغرض:
جعل ربط نموذج **حقيقيّ** لاحقاً مجرّد تنفيذ للعقد، دون لمس بقيّة الـpipeline.

مبدأ الصدق المطلق:
  • هذه العقود تصف **الأشكال (shapes) فقط** — لا تُنتج أيّ بكسلات/أقنعة/مضلّعات،
    ولا تحتوي أيّ نموذج، ولا تُلفّق أيّ أرقام.
  • لا استيراد لقواعد بيانات/شبكة/تعلّم آليّ، ولا shapely/numpy/rasterio —
    مكتبة قياسيّة + typing فقط (وحدة نقيّة).
  • معرّفات نطاقات Sentinel-2 المستخدمة هي **المعرّفات القياسيّة من ESA**
    (وليست مُختلقة)، موثّقة بصدق أدناه.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# نطاقات Sentinel-2 — المعرّفات القياسيّة من وكالة الفضاء الأوروبيّة (ESA).
# هذه أسماء النطاقات الحقيقيّة (ليست مُختلقة) ذات الصلة بترسيم المحاصيل:
#   B02 = أزرق (Blue)       B03 = أخضر (Green)     B04 = أحمر (Red)
#   B08 = الأشعّة تحت الحمراء القريبة (NIR)
#   B11 = الأشعّة تحت الحمراء قصيرة الموجة 1 (SWIR1)
#   B12 = الأشعّة تحت الحمراء قصيرة الموجة 2 (SWIR2)
# ---------------------------------------------------------------------------
SENTINEL2_BANDS: tuple[str, ...] = ("B02", "B03", "B04", "B08", "B11", "B12")


@dataclass(frozen=True)
class AreaOfInterest:
    """منطقة الاهتمام (AOI) — وصف هندسيّ فقط، لا بكسلات.

    bbox بترتيب (minx, miny, maxx, maxy). الافتراض EPSG:4326 (طول/عرض بالدرجات).
    geometry_wkt اختياريّ لوصف هندسة أدقّ من المستطيل المحيط.
    """

    bbox: tuple[float, float, float, float]
    crs: str = "EPSG:4326"
    geometry_wkt: str | None = None

    def validate(self) -> list[str]:
        """يُعيد قائمة مخالفات بالعربيّة (لا يرفع استثناءً أبداً)."""
        violations: list[str] = []
        if not isinstance(self.bbox, (tuple, list)) or len(self.bbox) != 4:
            violations.append("bbox يجب أن يكون رباعيّاً (minx, miny, maxx, maxy).")
            return violations
        minx, miny, maxx, maxy = self.bbox
        if not (minx < maxx):
            violations.append("يجب أن يكون minx أصغر من maxx.")
        if not (miny < maxy):
            violations.append("يجب أن يكون miny أصغر من maxy.")
        if self.crs == "EPSG:4326":
            if not (-180.0 <= minx <= 180.0 and -180.0 <= maxx <= 180.0):
                violations.append("خط الطول خارج المدى المعقول [-180, 180] لـ EPSG:4326.")
            if not (-90.0 <= miny <= 90.0 and -90.0 <= maxy <= 90.0):
                violations.append("خط العرض خارج المدى المعقول [-90, 90] لـ EPSG:4326.")
        return violations


@dataclass(frozen=True)
class TimeWindow:
    """نافذة زمنيّة بتاريخَي بداية/نهاية بصيغة ISO (YYYY-MM-DD)."""

    start: str
    end: str

    def validate(self) -> list[str]:
        """يتحقّق من قابليّة التحليل ISO ومن start <= end (لا يرفع استثناءً)."""
        violations: list[str] = []
        parsed: dict[str, date] = {}
        for label, value in (("start", self.start), ("end", self.end)):
            try:
                parsed[label] = date.fromisoformat(value)
            except (ValueError, TypeError):
                violations.append(f"التاريخ '{label}' غير قابل للتحليل بصيغة ISO: {value!r}.")
        if "start" in parsed and "end" in parsed and parsed["start"] > parsed["end"]:
            violations.append("يجب أن يكون تاريخ البداية قبل أو يساوي تاريخ النهاية.")
        return violations


@dataclass(frozen=True)
class CompositeRef:
    """واصف مُركّب راستر متعدّد الأزمنة — يصف **أين/ما هو** المُركّب لا بكسلاته.

    لا يحمل أيّ مصفوفة بكسلات؛ مجرّد بيانات وصفيّة (band_names, الأبعاد, CRS,
    والمصدر) تتيح لمرحلة لاحقة جلب البكسلات الحقيقيّة عند توفّر المزوّد.
    """

    band_names: tuple[str, ...]
    time_window: TimeWindow
    width: int
    height: int
    crs: str
    source_uri: str | None = None


@runtime_checkable
class RasterSource(Protocol):
    """عقد مزوّد الراستر الحقيقيّ (مثل Sentinel-2 عبر STAC/SentinelHub/GEE).

    أيّ مزوّد حقيقيّ يجب أن يُحقّق هذا التوقيع. **لا يُشحن أيّ تنفيذ ملموس هنا** —
    هذه واجهة فقط؛ لا تجلب الوحدة أيّ بيانات ولا تتّصل بأيّ خدمة.
    """

    def fetch_composite(
        self,
        aoi: AreaOfInterest,
        window: TimeWindow,
        bands: Sequence[str],
    ) -> CompositeRef:
        """يُعيد واصف مُركّب (CompositeRef) للمنطقة/النافذة/النطاقات — لا بكسلات هنا."""
        ...


@dataclass(frozen=True)
class MLStageContract:
    """عقد مدخلات/مخرجات لمرحلة ML واحدة (أشكال فقط).

    output_key_types: تخطيط فضفاض من مفتاح المخرَج إلى نوع python المتوقّع
    (مثل polygons → list, model_version → str, composite → CompositeRef).
    """

    stage_id: str
    required_input_keys: tuple[str, ...]
    required_output_keys: tuple[str, ...]
    output_key_types: dict[str, type] = field(default_factory=dict)


# سجلّ عقود مراحل ML الثلاث — متطابق مع مفاتيح ctx في الإطار الفعليّ.
ML_STAGE_CONTRACTS: dict[str, MLStageContract] = {
    "multi_temporal_composite": MLStageContract(
        stage_id="multi_temporal_composite",
        required_input_keys=("aoi", "time_window", "raster_source"),
        required_output_keys=("composite",),
        output_key_types={"composite": CompositeRef},
    ),
    "crop_mask": MLStageContract(
        stage_id="crop_mask",
        required_input_keys=("composite",),
        required_output_keys=("crop_mask", "model_version"),
        output_key_types={"crop_mask": object, "model_version": str},
    ),
    "delineation": MLStageContract(
        stage_id="delineation",
        required_input_keys=("crop_mask",),
        required_output_keys=("polygons",),
        output_key_types={"polygons": list},
    ),
}

# ترتيب مراحل ML كما في BOUNDARY_PIPELINE (للاستبطان بترتيب ثابت).
_ML_STAGE_ORDER: tuple[str, ...] = (
    "multi_temporal_composite",
    "crop_mask",
    "delineation",
)


def validate_ml_stage_input(stage_id: str, ctx: dict) -> list[str]:
    """يتحقّق من توفّر مفاتيح المدخلات المطلوبة في ctx (لا يرفع استثناءً)."""
    contract = ML_STAGE_CONTRACTS.get(stage_id)
    if contract is None:
        return [f"مرحلة ML غير معروفة: {stage_id}"]
    violations: list[str] = []
    for key in contract.required_input_keys:
        if key not in ctx:
            violations.append(f"مفتاح مدخل مطلوب مفقود: {key}")
    return violations


def validate_ml_stage_output(stage_id: str, updates: dict) -> list[str]:
    """يتحقّق من مفاتيح المخرجات المطلوبة وأنواعها (لا يرفع استثناءً)."""
    contract = ML_STAGE_CONTRACTS.get(stage_id)
    if contract is None:
        return [f"مرحلة ML غير معروفة: {stage_id}"]
    violations: list[str] = []
    for key in contract.required_output_keys:
        if key not in updates:
            violations.append(f"مفتاح مخرَج مطلوب مفقود: {key}")
            continue
        expected = contract.output_key_types.get(key)
        if expected is not None and not isinstance(updates[key], expected):
            violations.append(f"نوع المخرَج '{key}' غير صحيح: المتوقّع {expected.__name__}.")
    return violations


def describe_contracts() -> list[dict]:
    """استبطان عقود مراحل ML الثلاث بترتيب BOUNDARY_PIPELINE."""
    out: list[dict] = []
    for stage_id in _ML_STAGE_ORDER:
        contract = ML_STAGE_CONTRACTS[stage_id]
        out.append(
            {
                "stage_id": contract.stage_id,
                "required_input_keys": list(contract.required_input_keys),
                "required_output_keys": list(contract.required_output_keys),
                "output_types": {
                    key: typ.__name__ for key, typ in contract.output_key_types.items()
                },
            }
        )
    return out
