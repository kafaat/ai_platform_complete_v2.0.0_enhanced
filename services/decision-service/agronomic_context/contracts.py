"""AC-1 canonical contracts: AgronomicContextSnapshot / FieldHistoricalContextSnapshot /
FeatureManifest. These are the ONLY shapes the composer accepts; arbitrary agronomic dicts are
rejected at the boundary. Domain groups are structured jsonb validated here; identity, lineage
and point-in-time fields are first-class.

Boundary hardening:

* every point-in-time field is ``AwareDatetime``: a naive timestamp compared with an aware one
  raised ``TypeError`` in ``point_in_time.validate_composition`` (HTTP 500), the same class as
  DECISION-PLAN-MIXED-TIMEZONE-500-01. It is now a 422 through the ordinary pydantic path;
* a non-finite float (NaN, Infinity, -Infinity), at any depth of a feature ``value`` or of
  ``context``/``history``, is a typed ``non_finite_number`` violation of
  ``point_in_time.validate_composition`` (422 through the route's violation envelope):
  ``model_dump(mode="json")`` rewrote it to ``null``, so the feature-manifest hash covered a value
  never supplied, and in ``context``/``history`` it reached jsonb, which refuses NaN. It is not a
  pydantic error on purpose: FastAPI's default 422 body echoes the offending input, and NaN cannot
  be encoded as JSON, so a pydantic rejection surfaced as a 500;
* a feature that declares a ``unit`` is numeric, so its value must be a real ``int``/``float``;
  ``True``/``False`` (a Python ``int`` subclass) and strings are refused there. A feature without
  a unit keeps carrying categorical values (``crop_id``, ``cultivar_id``, flags, structures).
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, ValidationInfo, field_validator

# domain groups the snapshot must carry (plan §4.1). Each group is a dict of named values; the
# composer requires the group keys to exist — empty groups are allowed only with a typed reason
# recorded by the caller (e.g. rainfed field with no irrigation system).
CONTEXT_GROUPS = (
    "crop",
    "soil",
    "irrigation",
    "weather",
    "climate",
    "terrain",
    "operations",
)

QUALITY_STATES = {"verified", "accepted_with_warning", "stale", "missing", "rejected"}


class FeatureEntryIn(BaseModel):
    name: str
    value: Any
    unit: str | None = None
    source_service: str
    source_snapshot_id: str | None = None
    observed_at: AwareDatetime
    available_at: AwareDatetime
    quality_status: str = "verified"
    formula_version: str | None = None
    spatial_scope: str | None = None
    temporal_scope: str | None = None

    @field_validator("unit")
    @classmethod
    def _unit_implies_number(cls, unit: str | None, info: ValidationInfo) -> str | None:
        # ``value`` is declared before ``unit`` so it is already validated (and present) here.
        if unit is not None and "value" in info.data:
            value = info.data["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    f"a feature with unit {unit!r} must carry a number, not {type(value).__name__}"
                )
        return unit


class HistoricalContextIn(BaseModel):
    history_from: AwareDatetime
    history_to: AwareDatetime
    manifest_version: str = "ac-1"
    history: dict[str, Any] = Field(default_factory=dict)


class ContextComposeIn(BaseModel):
    field_id: str
    season_id: str | None = None
    as_of_time: AwareDatetime
    decision_cutoff_time: AwareDatetime
    schema_version: str = "ac-1"
    composer_version: str = "ac-1"
    context: dict[str, Any] = Field(default_factory=dict)
    historical: HistoricalContextIn
    features: list[FeatureEntryIn] = Field(default_factory=list)
    idempotency_key: str
