"""Canonical yield intelligence product built from validated map records and optional TrueUp."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_yield_state.v1"


STATUS_EVALUATED = "evaluated"
STATUS_NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class YieldScope:
    """Whether a set of queried records can carry a canonical state at all.

    A canonical yield state is identified by (field, season, source_sha256), so it is
    meaningful over exactly one ingestion of one season. The danger otherwise is not a
    wrong number but a *plausible* one: averaging the first page of a large harvest
    produces a figure that looks exactly like the field's yield.
    """

    evaluable: bool
    limitations: list[str]
    ingestion_id: str | None = None
    season_id: str | None = None


def assess_yield_scope(*, rows: list[dict[str, Any]], truncated: bool) -> YieldScope:
    """Pure scope check — no I/O. Names every reason a scope cannot be summarised."""
    if truncated:
        return YieldScope(False, ["record_page_truncated"])
    if not rows:
        return YieldScope(False, ["no_records_in_scope"])
    ingestions = {row.get("ingestion_id") for row in rows}
    seasons = {row.get("season_id") for row in rows}
    limitations: list[str] = []
    if len(ingestions) > 1:
        limitations.append("multiple_ingestions_in_scope")
    if len(seasons) > 1:
        limitations.append("multiple_seasons_in_scope")
    if limitations:
        return YieldScope(False, limitations)
    season_id = next(iter(seasons))
    if not season_id:
        return YieldScope(False, ["season_id_missing_on_records"])
    return YieldScope(True, [], ingestion_id=next(iter(ingestions)), season_id=season_id)


def summarize_yield_scope(
    *,
    field_id: str,
    rows: list[dict[str, Any]],
    scope: YieldScope,
    source_sha256: str | None,
) -> dict[str, Any]:
    """Build the canonical state for a sound scope, or report why there is none.

    ``source_sha256`` is required rather than defaulted: a placeholder digest would bind
    the state to provenance that does not exist.
    """
    if not scope.evaluable:
        return {
            "status": STATUS_NOT_EVALUATED,
            "state": None,
            "limitations": list(scope.limitations),
        }
    if not source_sha256:
        return {
            "status": STATUS_NOT_EVALUATED,
            "state": None,
            "limitations": ["source_sha256_unavailable"],
        }
    state = build_canonical_yield_state(
        field_id=field_id,
        season_id=scope.season_id or "",
        source_sha256=source_sha256,
        records=rows,
        # TrueUp calibration has no stored owner yet; the state records
        # `trueup_not_applied` rather than assuming a factor of 1.0.
        calibration_factor=None,
    )
    return {"status": STATUS_EVALUATED, "state": state.to_dict(), "limitations": []}


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
