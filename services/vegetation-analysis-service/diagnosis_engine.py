"""RS-8 deterministic diagnosis hypothesis builder.

This module deliberately produces hypotheses, never prescriptions or approved actions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from shared.contracts.remote_sensing import (
    DiagnosisHypothesisV1,
    EvidenceBundleV1,
    EvidenceRefV1,
)
from shared.contracts.remote_sensing.enums import (
    DiagnosisAssessmentStatus,
    EvidenceVerificationState,
    VerificationRequirement,
)


def _condition(signal_type: str, verification_codes: list[str]) -> tuple[str, tuple[str, ...], str]:
    s = signal_type.lower()
    codes = " ".join(verification_codes).lower()
    if "moisture" in s or "ndmi" in s or "msi" in s or "dry" in codes:
        return "water_stress", ("salinity", "root_damage"), "rule_fusion_v1"
    if "ndre" in s or "chlorophyll" in s:
        return (
            "nutrient_deficiency",
            ("normal_phenology_variation", "root_damage"),
            "rule_fusion_v1",
        )
    if "emerg" in s or "canopy" in s:
        return "poor_emergence", ("soil_compaction", "water_stress"), "rule_fusion_v1"
    if "temperature" in s or "lst" in s or "heat" in codes:
        return "heat_stress", ("water_stress", "normal_phenology_variation"), "rule_fusion_v1"
    return (
        "vegetation_stress_unspecified",
        ("water_stress", "nutrient_deficiency"),
        "rule_fusion_v1",
    )


def build_diagnosis(*, anomaly_record: dict[str, Any], tenant_id: UUID) -> DiagnosisHypothesisV1:
    if anomaly_record["status"] != "confirmed":
        raise ValueError("diagnosis_requires_confirmed_anomaly")
    p = anomaly_record["payload"]
    refs = tuple(p.get("verification_evidence_refs") or ())
    now = datetime.now(UTC)
    evidence = tuple(
        EvidenceRefV1.model_validate_json(json.dumps(e)) for e in p.get("verification_evidence", [])
    )
    if not evidence or {e.evidence_ref for e in evidence} != set(refs):
        raise ValueError("diagnosis_requires_original_evidence_metadata")
    if any(
        e.tenant_id != tenant_id
        or e.verification_state != EvidenceVerificationState.VERIFIED
        or e.captured_at > now
        for e in evidence
    ):
        raise ValueError("diagnosis_evidence_scope_or_state_invalid")
    suspected, alternatives, method = _condition(
        str(p.get("signal_type", "")), list(p.get("disposition_reason_codes") or ())
    )
    confidence = Decimal(str(p.get("confidence", "0")))
    if not confidence.is_finite() or not Decimal(0) <= confidence <= Decimal(1):
        raise ValueError("invalid_input_quality_score")
    diagnosis_key = hashlib.sha256(
        f"{anomaly_record['anomaly_ref']}|{suspected}|diagnosis-v1".encode()
    ).hexdigest()[:24]
    return DiagnosisHypothesisV1(
        diagnosis_ref=f"urn:sahool:diagnosis:dgn_{diagnosis_key}",
        tenant_id=tenant_id,
        field_id=anomaly_record["field_id"],
        season_id=anomaly_record["season_id"],
        primary_anomaly_ref=anomaly_record["anomaly_ref"],
        suspected_condition=suspected,
        alternative_conditions=alternatives,
        evidence_bundle=EvidenceBundleV1(evidence=evidence),
        confidence=confidence,
        confidence_method=f"{method}:input_quality_not_diagnostic_probability",
        ground_verification_requirement=VerificationRequirement.NOT_REQUIRED,
        assessment_status=DiagnosisAssessmentStatus.PENDING,
        diagnosis_model_ref="urn:sahool:model:diagnosis_rules_v1",
        proposed_at=now,
    )
