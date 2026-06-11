"""منطق نقيّ لاختيار/تشكيل أحدث قراءة رطوبة تربة من telemetry الأجهزة.

القراءات تأتي من device_telemetry (v24): كلّ صفّ يحمل sensor_type + value +
recorded_at. الأجهزة من نوع soil_moisture المرتبطة بحقل (iot_devices.field_id)
تُنتج قراءات رطوبة التربة بالنسبة المئويّة (٪ من السعة المتاحة).

هذا المنطق نقيّ (لا قاعدة/لا شبكة) ليُختبَر offline: يلتقط أحدث قراءة صالحة من
دفعة صفوف ويشكّلها لاستهلاك محرّك التنبيهات / توصية الريّ وطبقة الـAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# نطاق رطوبة تربة معقول (٪). قراءات خارجه تُعدّ خاطئة (حسّاس معطوب/وحدة مغلوطة)
# وتُتجاهَل لئلّا تُسمّم قرار الريّ — نختار أحدث قراءة *صالحة* فقط.
SOIL_MOISTURE_MIN_PCT = 0.0
SOIL_MOISTURE_MAX_PCT = 100.0


@dataclass(frozen=True)
class SoilMoistureReading:
    """قراءة رطوبة تربة مُشكّلة: القيمة (٪) + زمن القياس + الجهاز المصدر."""

    value_pct: float
    recorded_at: datetime
    device_id: str | None = None
    unit: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """تشكيل JSON لطبقة الـAPI (recorded_at بصيغة ISO)."""
        return {
            "soil_moisture_pct": self.value_pct,
            "recorded_at": self.recorded_at.isoformat(),
            "device_id": self.device_id,
            "unit": self.unit,
        }


def _valid_pct(value: Any) -> float | None:
    """يحوّل القيمة إلى ٪ صالحة ضمن النطاق، أو None إن تعذّر/خرج عن النطاق."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v < SOIL_MOISTURE_MIN_PCT or v > SOIL_MOISTURE_MAX_PCT:
        return None
    return v


def pick_latest_soil_moisture(rows: list[dict[str, Any]]) -> SoilMoistureReading | None:
    """يلتقط أحدث قراءة رطوبة تربة *صالحة* من دفعة صفوف telemetry.

    كلّ صفّ قاموس يحمل value و recorded_at (و device_id/unit اختياريّاً). تُتجاهَل
    الصفوف بلا recorded_at أو بقيمة خارج النطاق المعقول. يُعاد أحدثها بـrecorded_at
    (لا نعتمد ترتيب الإدخال — نرتّب صراحةً)، أو None إن لم تتبقَّ قراءة صالحة.
    """
    best: SoilMoistureReading | None = None
    for row in rows:
        recorded_at = row.get("recorded_at")
        if not isinstance(recorded_at, datetime):
            continue
        pct = _valid_pct(row.get("value"))
        if pct is None:
            continue
        if best is None or recorded_at > best.recorded_at:
            best = SoilMoistureReading(
                value_pct=pct,
                recorded_at=recorded_at,
                device_id=row.get("device_id"),
                unit=row.get("unit"),
            )
    return best
