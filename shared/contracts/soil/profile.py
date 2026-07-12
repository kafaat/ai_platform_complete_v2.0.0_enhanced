"""Canonical SoilProfileSnapshot.v1 contract.

The snapshot is the single governed read model for agricultural engines and the
Decision Center. Raw evidence remains owned by its producer; this projection
preserves source class, confidence, lineage, conflicts, and allowed uses.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

SOIL_PROFILE_CONTRACT_VERSION = "soil-profile.v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class SoilProfileStatus(StrEnum):
    BASELINE = "baseline"
    ENHANCED_BASELINE = "enhanced_baseline"
    REGIONAL_GUIDED = "regional_guided"
    FIELD_GUIDED = "field_guided"
    VERIFIED = "verified"
    OPERATIONAL_VERIFIED = "operational_verified"


class SoilEvidenceLevel(StrEnum):
    BASELINE_ONLY = "baseline_only"
    MODELLED = "modelled"
    ANALOG_GUIDED = "analog_guided"
    FIELD_OBSERVED = "field_observed"
    LAB_VERIFIED = "lab_verified"
    OPERATIONAL_VERIFIED = "operational_verified"


class SoilEvidenceClass(StrEnum):
    MEASURED = "measured"
    MODELLED = "modelled"
    PROXY = "proxy"
    ANALOG_ESTIMATE = "analog_estimate"
    DERIVED = "derived"


class SoilPropertyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any = None
    unit: str | None = None
    evidence_class: SoilEvidenceClass
    selected_source: str
    source_id: str | None = None
    observed_at: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    verification_required: bool = False
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class SoilLayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depth_from_cm: float = Field(ge=0)
    depth_to_cm: float = Field(gt=0)
    properties: dict[str, SoilPropertyValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _depth_order(self) -> SoilLayer:
        if self.depth_to_cm <= self.depth_from_cm:
            raise ValueError("soil_layer_depth_invalid")
        return self


class SoilQualityGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    executable: bool = False
    reasons: list[str] = Field(default_factory=list)


class SoilModelInputs(BaseModel):
    """Strict hydraulics supplied to crop/water models when scientifically available."""

    model_config = ConfigDict(extra="forbid")

    field_capacity: float | None = Field(default=None, ge=0, le=1)
    wilting_point: float | None = Field(default=None, ge=0, le=1)
    rootable_depth_cm: float | None = Field(default=None, gt=0)
    bulk_density: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _physical_consistency(self) -> SoilModelInputs:
        if self.field_capacity is not None and self.wilting_point is not None:
            if self.wilting_point >= self.field_capacity:
                raise ValueError("soil_hydraulics_invalid")
        return self


class SoilProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = SOIL_PROFILE_CONTRACT_VERSION
    profile_id: str = Field(min_length=1, max_length=128)
    profile_hash: str
    tenant_id: str | None = None
    field_id: str = Field(min_length=1, max_length=128)
    zone_id: str | None = None
    effective_at: datetime
    data_available_at: datetime
    status: SoilProfileStatus
    evidence_level: SoilEvidenceLevel
    layers: list[SoilLayer] = Field(min_length=1)
    completeness_score: float = Field(ge=0.0, le=1.0)
    quality_gate: SoilQualityGate
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    allowed_use: list[str] = Field(default_factory=list)
    blocked_use: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    selection_policy_version: str = Field(min_length=1)
    model_inputs: SoilModelInputs | None = None

    @model_validator(mode="after")
    def _snapshot_integrity(self) -> SoilProfileSnapshot:
        if self.contract_version != SOIL_PROFILE_CONTRACT_VERSION:
            raise ValueError("soil_profile_contract_version_unsupported")
        if not _HASH_RE.fullmatch(self.profile_hash):
            raise ValueError("soil_profile_hash_invalid")
        if self.data_available_at < self.effective_at:
            raise ValueError("soil_profile_available_before_effective")
        if self.quality_gate.executable and not self.quality_gate.passed:
            raise ValueError("soil_profile_executable_without_passed_gate")
        return self


def canonical_soil_profile_hash(payload: dict[str, Any]) -> str:
    """Hash snapshot content excluding profile_hash itself."""
    canonical = dict(payload)
    canonical.pop("profile_hash", None)
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_soil_profile_snapshot(payload: Any) -> tuple[SoilProfileSnapshot | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["soil_profile_not_object"]
    try:
        return SoilProfileSnapshot.model_validate(payload), []
    except Exception as exc:  # pydantic emits structured errors; boundary returns stable codes.
        errors = getattr(exc, "errors", lambda: [])()
        if errors:
            out: list[str] = []
            for error in errors:
                loc = ".".join(str(x) for x in error.get("loc", ())) or "soil_profile"
                msg = str(error.get("msg", "invalid"))
                out.append(f"{loc}:{msg}")
            return None, out
        return None, [f"soil_profile_invalid:{type(exc).__name__}"]
