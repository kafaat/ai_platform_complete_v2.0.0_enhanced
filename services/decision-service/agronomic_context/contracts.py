"""AC-1 canonical contracts: AgronomicContextSnapshot / FieldHistoricalContextSnapshot /
FeatureManifest. These are the ONLY shapes the composer accepts; arbitrary agronomic dicts are
rejected at the boundary. Domain groups are structured jsonb validated here; identity, lineage
and point-in-time fields are first-class."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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
    observed_at: datetime
    available_at: datetime
    quality_status: str = "verified"
    formula_version: str | None = None
    spatial_scope: str | None = None
    temporal_scope: str | None = None


class HistoricalContextIn(BaseModel):
    history_from: datetime
    history_to: datetime
    manifest_version: str = "ac-1"
    history: dict[str, Any] = Field(default_factory=dict)


class ContextComposeIn(BaseModel):
    field_id: str
    season_id: str | None = None
    as_of_time: datetime
    decision_cutoff_time: datetime
    schema_version: str = "ac-1"
    composer_version: str = "ac-1"
    context: dict[str, Any] = Field(default_factory=dict)
    historical: HistoricalContextIn
    features: list[FeatureEntryIn] = Field(default_factory=list)
    idempotency_key: str
