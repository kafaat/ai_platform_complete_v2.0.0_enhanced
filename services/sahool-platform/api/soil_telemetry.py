"""منطق نقيّ لاختيار/تشكيل أحدث قراءة رطوبة تربة من الشواهد القانونيّة.

القراءات تأتي من ``soil_observations`` (v155) عبر ``field_context._latest_soil_moisture``:
كلّ صفّ يحمل ``value`` و``unit`` و``recorded_at`` (و``device_id``).

**هويّةُ الوحدة — `SOIL-MOISTURE-UNIT-IDENTITY-01`.** كانت هذه الوثيقةُ تقول «٪ من
السعة المتاحة» بينما لا يفرض ذلك أحد: الكاتبُ القانونيّ يخزّن ``"%"`` عاريةً
(`soil-service/evidence_adapters.py:23`)، والحسّاساتُ السعويّة تُخرِج **رطوبةً حجميّة**
(VWC) لا نسبةَ ماءٍ متاح. ونسبةُ VWC ونسبةُ الماء المتاح رقمان مختلفان فيزيائيّاً
(25٪ VWC في تربة طينيّة قربَ الذبول، وفي رمليّة فوق الإشباع). فالقراءةُ تحمل الآن
``unit_kind`` مُصنَّفاً من الوحدة **كما أعلنها المصدر**: ``vwc_pct`` · ``available_pct`` ·
``undeclared`` — والأخيرُ ليس خطأً بل حقيقةٌ تُعلَن لمستهلكٍ يقرّر ماذا يفعل بها.

هذا المنطق نقيّ (لا قاعدة/لا شبكة) ليُختبَر offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# نطاق رطوبة تربة معقول (٪). قراءات خارجه تُعدّ خاطئة (حسّاس معطوب/وحدة مغلوطة)
# وتُتجاهَل لئلّا تُسمّم قرار الريّ — نختار أحدث قراءة *صالحة* فقط.
SOIL_MOISTURE_MIN_PCT = 0.0
SOIL_MOISTURE_MAX_PCT = 100.0

UNIT_VWC_PCT = "vwc_pct"
UNIT_AVAILABLE_PCT = "available_pct"
UNIT_UNDECLARED = "undeclared"

#: ما يُعلنه المصدرُ ⇐ نوعُ الوحدة. ``%``/``pct`` وحدَها **لا تقول أيَّ نسبة** فتبقى
#: غيرَ مُعلَنة. ``m3/m3`` نسبةٌ 0–1 تُحوَّل إلى ٪ عند القراءة.
_UNIT_ALIASES: dict[str, str] = {
    "vwc": UNIT_VWC_PCT,
    "vwc_pct": UNIT_VWC_PCT,
    "vwc%": UNIT_VWC_PCT,
    "volumetric_pct": UNIT_VWC_PCT,
    "m3/m3": UNIT_VWC_PCT,
    "m³/m³": UNIT_VWC_PCT,
    "available_pct": UNIT_AVAILABLE_PCT,
    "available_water_pct": UNIT_AVAILABLE_PCT,
    "paw_pct": UNIT_AVAILABLE_PCT,
    "taw_pct": UNIT_AVAILABLE_PCT,
    "rwc_pct": UNIT_AVAILABLE_PCT,
}
_FRACTIONAL_UNITS = frozenset({"m3/m3", "m³/m³"})


def classify_soil_moisture_unit(raw: Any) -> str:
    """يُصنّف الوحدةَ المُعلَنة؛ ``%`` العارية أو الغياب ⇒ ``undeclared`` (لا تخمين)."""
    if raw is None:
        return UNIT_UNDECLARED
    key = str(raw).strip().lower()
    return _UNIT_ALIASES.get(key, UNIT_UNDECLARED)


def _unit_is_fractional(raw: Any) -> bool:
    return raw is not None and str(raw).strip().lower() in _FRACTIONAL_UNITS


@dataclass(frozen=True)
class SoilMoistureReading:
    """قراءة رطوبة تربة مُشكّلة: القيمة (٪) + زمن القياس + الجهاز + **نوعُ الوحدة**."""

    value_pct: float
    recorded_at: datetime
    device_id: str | None = None
    unit: str | None = None
    unit_kind: str = UNIT_UNDECLARED
    #: هويّةُ المشاهدة وجودتُها — كانت تُفقَد في الإسقاط فتتساوى `accepted` و`suspect`
    #: و`uncalibrated` عند بذرة التوأم (مراجعة `b9c5aceb`، QUALITY-PROJECTION-LOSS).
    observation_id: str | None = None
    quality_status: str | None = None
    calibration_id: str | None = None
    confidence: float | None = None
    depth_from_cm: float | None = None
    depth_to_cm: float | None = None

    @property
    def unit_declared(self) -> bool:
        return self.unit_kind != UNIT_UNDECLARED

    def as_dict(self) -> dict[str, Any]:
        """تشكيل JSON لطبقة الـAPI (recorded_at بصيغة ISO)."""
        return {
            "soil_moisture_pct": self.value_pct,
            "recorded_at": self.recorded_at.isoformat(),
            "device_id": self.device_id,
            "unit": self.unit,
            "unit_kind": self.unit_kind,
            "unit_declared": self.unit_declared,
            "observation_id": self.observation_id,
            "quality_status": self.quality_status,
            "calibration_id": self.calibration_id,
            "confidence": self.confidence,
            "depth_from_cm": self.depth_from_cm,
            "depth_to_cm": self.depth_to_cm,
        }


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _valid_pct(value: Any, *, fractional: bool = False) -> float | None:
    """يحوّل القيمة إلى ٪ صالحة ضمن النطاق، أو None إن تعذّر/خرج عن النطاق.

    **`true`/`false` ليستا قياسَ رطوبة.** `float(True) == 1.0` فكانت قيمةٌ منطقيّة تصير
    1٪ (أو 100٪ تحت `m3/m3`) ثمّ **بذرةَ نضوبٍ** في التوأم — مُعاد إنتاجُه في مراجعة
    `a7d64adf`. تُرفَض قبل التحويل؛ و`0.0`/`1.0` العدديّتان تبقيان مقبولتين بوحدتهما.
    """
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    if fractional:
        v *= 100.0
    if v < SOIL_MOISTURE_MIN_PCT or v > SOIL_MOISTURE_MAX_PCT:
        return None
    return v


def pick_latest_soil_moisture(rows: list[dict[str, Any]]) -> SoilMoistureReading | None:
    """يلتقط أحدث قراءة رطوبة تربة *صالحة* من دفعة صفوف.

    كلّ صفّ قاموس يحمل value و recorded_at (و device_id/unit اختياريّاً). تُتجاهَل
    الصفوف بلا recorded_at أو بقيمة خارج النطاق المعقول. يُعاد أحدثها بـrecorded_at
    (لا نعتمد ترتيب الإدخال — نرتّب صراحةً)، أو None إن لم تتبقَّ قراءة صالحة.
    نوعُ الوحدة يُصنَّف من ``unit`` كما أعلنه المصدر ولا يُخمَّن.
    """
    best: SoilMoistureReading | None = None
    for row in rows:
        recorded_at = row.get("recorded_at")
        if not isinstance(recorded_at, datetime):
            continue
        unit = row.get("unit")
        pct = _valid_pct(row.get("value"), fractional=_unit_is_fractional(unit))
        if pct is None:
            continue
        if best is None or recorded_at > best.recorded_at:
            best = SoilMoistureReading(
                value_pct=pct,
                recorded_at=recorded_at,
                device_id=row.get("device_id"),
                unit=unit,
                unit_kind=classify_soil_moisture_unit(unit),
                observation_id=_opt_str(row.get("observation_id")),
                quality_status=_opt_str(row.get("quality_status")),
                calibration_id=_opt_str(row.get("calibration_id")),
                confidence=_opt_float(row.get("confidence")),
                depth_from_cm=_opt_float(row.get("depth_from_cm")),
                depth_to_cm=_opt_float(row.get("depth_to_cm")),
            )
    return best


def irrigation_soil_input(
    reading: SoilMoistureReading | None, *, now: datetime | None = None
) -> dict[str, Any]:
    """G9 — ما يدخل توصية الريّ من قراءة التربة: **الوحدةُ والعمرُ يُمرَّران لا يُسقَطان**.

    كان المسارُ يمرّر ``value_pct`` عارياً فتُقرأ ``25٪ VWC`` «ماءً متاحاً ٢٥٪» (حرجة ⇒
    ريٌّ عاجل) وقراءةُ أسبوعٍ مضى قراءةَ اليوم. الآن: ``usable_pct`` يُعطى للمُقرِّر
    **فقط** حين تكون القراءةُ طازجةً (سقفُ ``soil_moisture_sensor.max_reading_age_s``
    عبر ``water_twin_seed.sensor_freshness`` نفسها) ووحدتُها قابلةً للمقارنة بعتبات الماء
    المتاح؛ والحجميّةُ بلا θFC/θWP تُعلَن غيرَ قابلة للمقارنة (لا تُحوَّل تخميناً).
    والقراءةُ الخام تبقى معروضةً بوحدتها وعمرها.
    """
    from datetime import UTC

    from api.device_registry import get_device_type
    from api.water_twin_seed import _FRESHNESS_LIMITATION, sensor_freshness

    if reading is None:
        return {
            "usable_pct": None,
            "soil_moisture_pct": None,
            "soil_moisture_at": None,
            "soil_moisture_unit": None,
            "soil_moisture_unit_kind": None,
            "soil_moisture_age_s": None,
            "soil_moisture_freshness": None,
            "soil_moisture_used": False,
            "soil_moisture_limitations": [],
        }
    observed = reading.recorded_at
    if observed.tzinfo is None:  # timestamptz يصل واعياً؛ الساذجُ يُعامَل UTC صراحةً
        observed = observed.replace(tzinfo=UTC)
    age_s = ((now or datetime.now(UTC)) - observed).total_seconds()
    max_age_s = (get_device_type("soil_moisture_sensor") or {}).get("max_reading_age_s")
    freshness = sensor_freshness(age_s, max_age_s)
    limitations = [_FRESHNESS_LIMITATION[freshness]] if freshness != "fresh" else []
    if reading.unit_kind == UNIT_VWC_PCT:
        limitations.append("soil_moisture_vwc_not_comparable_to_available_water")
    elif reading.unit_kind == UNIT_UNDECLARED:
        limitations.append("soil_moisture_sensor_unit_undeclared")
    used = freshness == "fresh" and reading.unit_kind != UNIT_VWC_PCT
    return {
        # الطازجُ وحدَه يبلغ المُقرِّر؛ والحجميّةُ تبلغه ليُعلِنها هو غيرَ مُستعمَلة.
        "usable_pct": reading.value_pct if freshness == "fresh" else None,
        "soil_moisture_pct": reading.value_pct,
        "soil_moisture_at": reading.recorded_at.isoformat(),
        "soil_moisture_unit": reading.unit,
        "soil_moisture_unit_kind": reading.unit_kind,
        "soil_moisture_age_s": round(age_s, 1),
        "soil_moisture_freshness": freshness,
        "soil_moisture_used": used,
        "soil_moisture_limitations": limitations,
    }
