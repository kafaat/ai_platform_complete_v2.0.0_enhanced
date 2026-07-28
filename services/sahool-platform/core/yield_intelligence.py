"""Canonical yield intelligence product built from validated map records and optional TrueUp."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_yield_state.v1"


@dataclass(frozen=True)
class CanonicalYieldState:
    schema_version: str
    field_id: str
    season_id: str
    source_sha256: str
    record_count: int
    raw_mean_kg_ha: float | None
    calibrated_mean_kg_ha: float | None
    calibration_factor: float | None
    min_kg_ha: float | None
    max_kg_ha: float | None
    quality_status: str
    limitations: list[str]
    state_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_canonical_yield_state(
    *,
    field_id: str,
    season_id: str,
    source_sha256: str,
    records: list[dict[str, Any]],
    calibration_factor: float | None = None,
) -> CanonicalYieldState:
    if not field_id or not season_id or not source_sha256:
        raise ValueError("field_id, season_id and source_sha256 are required")
    values: list[float] = []
    rejected = 0
    for row in records:
        value = row.get("yield_kg_ha")
        try:
            f = float(value)
        except (TypeError, ValueError):
            rejected += 1
            continue
        if not math.isfinite(f) or f < 0:
            rejected += 1
            continue
        values.append(f)
    limitations: list[str] = []
    if rejected:
        limitations.append(f"rejected_invalid_records:{rejected}")
    if not values:
        limitations.append("no_valid_yield_records")
    if calibration_factor is not None and not 0.7 <= float(calibration_factor) <= 1.3:
        raise ValueError("calibration_factor must be within accepted TrueUp range 0.7..1.3")
    raw = round(sum(values) / len(values), 3) if values else None
    calibrated = (
        round(raw * float(calibration_factor), 3)
        if raw is not None and calibration_factor is not None
        else None
    )
    if calibration_factor is None:
        limitations.append("trueup_not_applied")
    quality = (
        "verified"
        if values and calibration_factor is not None and not rejected
        else "accepted_with_warning"
        if values
        else "missing"
    )
    body = dict(
        schema_version=SCHEMA_VERSION,
        field_id=field_id,
        season_id=season_id,
        source_sha256=source_sha256,
        record_count=len(values),
        raw_mean_kg_ha=raw,
        calibrated_mean_kg_ha=calibrated,
        calibration_factor=calibration_factor,
        min_kg_ha=round(min(values), 3) if values else None,
        max_kg_ha=round(max(values), 3) if values else None,
        quality_status=quality,
        limitations=limitations,
    )
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CanonicalYieldState(**body, state_digest=digest)
