"""Typed adapters turning external soil evidence into canonical SoilObservation records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared.contracts.soil import SoilObservation, SoilObservationQuality, SoilObservationSource

UNITS = {
    "ph": "pH",
    "ec": "dS/m",
    "organic_matter": "%",
    "nitrogen": "mg/kg",
    "phosphorus": "mg/kg",
    "potassium": "mg/kg",
    "cec": "cmol/kg",
    "calcium_carbonate": "%",
    "clay": "%",
    "sand": "%",
    "silt": "%",
    "texture": None,
    # SOIL-MOISTURE-UNIT-IDENTITY-01: `%` العارية **غيرُ مُعلَنة** — لا تقول أهي رطوبةٌ
    # حجميّة (VWC) أم نسبةُ ماءٍ متاح. المُنتِجُ الذي يعرف ما يُخرِجه حسّاسُه يمرّر
    # `units={"soil_moisture": "vwc_pct"}` (أو `available_pct`)، ولا يُخمَّن عنه هنا.
    "soil_moisture": "%",
    "soil_temperature": "degC",
}

#: الوحداتُ التي يقبلها المستهلكُ (`sahool-platform/api/soil_telemetry.py`) مُعلَنةً.
DECLARED_SOIL_MOISTURE_UNITS = frozenset({"vwc_pct", "available_pct", "m3/m3"})


def _require_soil_moisture_measurement(value: Any) -> None:
    """رطوبةُ التربة قياسٌ عدديّ محدود — لا `true`/`false` ولا NaN/inf.

    العقدُ العامّ يسمح بـ`bool` لخصائصَ أخرى عمداً؛ هذا التحقّقُ خاصٌّ بالرطوبة لأنّ
    `float(True) == 1.0` كان يصير قراءةً ثمّ بذرةَ نضوبٍ في التوأم (مراجعة `a7d64adf`).
    """
    if isinstance(value, bool):
        raise ValueError("soil_moisture_value_boolean_not_a_measurement")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("soil_moisture_value_not_numeric") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("soil_moisture_value_not_finite")


def observations_from_properties(
    *,
    tenant_id: str,
    field_id: str,
    source_type: SoilObservationSource,
    source_id: str,
    properties: dict[str, Any],
    observed_at: datetime | None = None,
    depth_from_cm: float = 0,
    depth_to_cm: float = 30,
    approved: bool = False,
    procedure_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    supersedes_observation_ids: dict[str, str] | None = None,
    supersession_reason: str | None = None,
    units: dict[str, str] | None = None,
) -> list[SoilObservation]:
    """يحوّل خصائصَ شاهدٍ إلى سجلّات قانونيّة. ``units`` وحدةٌ **يُعلنها المصدر** لخاصّيّة
    بعينها فتغلب الافتراضيّ في ``UNITS``؛ ما لم يُعلَن يبقى على افتراضيّه (ولـ`soil_moisture`
    الافتراضيُّ `%` أي غيرُ مُعلَن — انظر التعليق على ``UNITS``)."""
    observed_at = observed_at or datetime.now(UTC)
    units = units or {}
    quality = (
        SoilObservationQuality.ACCEPTED
        if approved
        or source_type not in {SoilObservationSource.LABORATORY, SoilObservationSource.SENSOR}
        else SoilObservationQuality.UNCALIBRATED
    )
    confidence_default = {
        SoilObservationSource.LABORATORY: 0.98 if approved else 0.55,
        SoilObservationSource.FIELD: 0.85,
        SoilObservationSource.SENSOR: 0.9 if approved else 0.6,
        SoilObservationSource.ANALOG_FIELDS: 0.6,
        SoilObservationSource.SOILGRIDS: 0.45,
        SoilObservationSource.SMARTPHONE: 0.4,
        SoilObservationSource.REMOTE_SENSING: 0.45,
        SoilObservationSource.MODEL: 0.5,
    }[source_type]
    out: list[SoilObservation] = []
    for prop, value in properties.items():
        if value is None:
            continue
        if prop == "soil_moisture":
            _require_soil_moisture_measurement(value)
        canonical = {
            "ec_dsm": "ec",
            "organic_matter_pct": "organic_matter",
            "nitrogen_mg_kg": "nitrogen",
            "phosphorus_mg_kg": "phosphorus",
            "potassium_mg_kg": "potassium",
            "cec_cmol_kg": "cec",
            "calcium_carbonate_pct": "calcium_carbonate",
        }.get(prop, prop)
        out.append(
            SoilObservation(
                tenant_id=tenant_id,
                field_id=field_id,
                property=canonical,
                value=value,
                unit=units.get(canonical, units.get(prop, UNITS.get(canonical))),
                depth_from_cm=depth_from_cm,
                depth_to_cm=depth_to_cm,
                observed_at=observed_at,
                source_type=source_type,
                source_id=source_id,
                procedure_id=procedure_id,
                quality_status=quality,
                confidence=confidence_default,
                idempotency_key=f"{source_type.value}:{source_id}:{canonical}:{depth_from_cm}:{depth_to_cm}",
                provenance={**(provenance or {}), "adapter_version": "soil-evidence-adapters.v1"},
                supersedes_observation_id=(supersedes_observation_ids or {}).get(canonical),
                supersession_reason=supersession_reason,
            )
        )
    return out
