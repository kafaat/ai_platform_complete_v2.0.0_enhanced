"""Decision-specific minimum evidence policy for canonical soil profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .profile import SoilProfileSnapshot, validate_soil_profile_snapshot

LOW_RISK_USES = {
    "baseline_profile",
    "sampling_plan",
    "preliminary_crop_suitability",
    "field_investigation",
    "conservative_irrigation_guidance",
}
MEDIUM_RISK_USES = {
    "irrigation_schedule",
    "crop_selection",
    "salinity_management_guidance",
}
HIGH_RISK_USES = {
    "fertilizer_rate",
    "gypsum_rate",
    "leaching_requirement",
    "subsurface_drainage_design",
    "high_risk_reclamation",
    "automatic_irrigation_execution",
}

_LEVEL_RANK = {
    "baseline_only": 0,
    "modelled": 1,
    "analog_guided": 2,
    "field_observed": 3,
    "lab_verified": 4,
    "operational_verified": 5,
}


@dataclass(frozen=True)
class SoilUseDecision:
    allowed: bool
    code: str
    reasons: tuple[str, ...]
    required_rank: int
    actual_rank: int


def validate_soil_use(profile: SoilProfileSnapshot | dict[str, Any], use: str) -> SoilUseDecision:
    snapshot, issues = validate_soil_profile_snapshot(
        profile.model_dump(mode="json") if isinstance(profile, SoilProfileSnapshot) else profile
    )
    if snapshot is None:
        return SoilUseDecision(False, "canonical_soil_profile_required", tuple(issues), 99, -1)
    use = (use or "").strip().lower()
    actual = _LEVEL_RANK.get(snapshot.evidence_level.value, -1)
    if use in HIGH_RISK_USES:
        required = 4
    elif use in MEDIUM_RISK_USES:
        required = 3
    else:
        required = 0
    reasons: list[str] = []
    if not snapshot.quality_gate.passed:
        reasons.append("soil_profile_quality_gate_failed")
    if use in set(snapshot.blocked_use):
        reasons.append("soil_use_explicitly_blocked")
    if snapshot.allowed_use and use not in set(snapshot.allowed_use) and use not in LOW_RISK_USES:
        reasons.append("soil_use_not_declared_allowed")
    if actual < required:
        reasons.append("soil_evidence_level_insufficient")
    if use in HIGH_RISK_USES and not snapshot.quality_gate.executable:
        reasons.append("soil_profile_not_executable")
    return SoilUseDecision(
        not reasons,
        "soil_use_allowed" if not reasons else "soil_use_blocked",
        tuple(reasons),
        required,
        actual,
    )
