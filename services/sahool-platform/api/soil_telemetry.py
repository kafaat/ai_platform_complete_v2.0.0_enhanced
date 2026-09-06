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
        }


def _valid_pct(value: Any, *, fractional: bool = False) -> float | None:
    """يحوّل القيمة إلى ٪ صالحة ضمن النطاق، أو None إن تعذّر/خرج عن النطاق."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
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
            )
    return best
