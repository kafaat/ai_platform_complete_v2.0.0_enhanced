"""Ownership-safe RS-8 bridge to the existing decision-service."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from shared.contracts.remote_sensing import DiagnosisDecisionReferralV1, DiagnosisHypothesisV1
from shared.contracts.remote_sensing.decision_referral_v1 import (
    FieldContextRefV1,
    SuggestedActionClassV1,
    ValidityContextV1,
)
from shared.security.decision_service_auth import decision_service_auth_headers


def candidate_lineage_id(diagnosis_ref: str, snapshot_hash: str) -> str:
    """Deterministic candidate lineage for one diagnosis over one evidence snapshot."""
    return "rs8_" + hashlib.sha256(f"{diagnosis_ref}|{snapshot_hash}".encode()).hexdigest()[:16]


class DecisionBridge:
    def __init__(self, base_url: str | None = None, timeout_s: float = 8.0) -> None:
        self.base_url = (base_url or os.getenv("DECISION_SERVICE_URL", "")).rstrip("/")
        self.timeout_s = timeout_s

    async def refer(
        self,
        *,
        diagnosis: DiagnosisHypothesisV1,
        authorization: str,
        field_state_ref: str,
        soil_context_ref: str | None = None,
        weather_context_ref: str | None = None,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("decision_service_not_configured")
        body = diagnosis.model_dump(mode="json")
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        snapshot_hash = hashlib.sha256(canonical).hexdigest()
        snapshot_idempotency = "idmp_rs8_snapshot_" + snapshot_hash
        decision_idempotency = (
            "idmp_rs8_decision_"
            + hashlib.sha256(f"{diagnosis.diagnosis_ref}|{snapshot_hash}".encode()).hexdigest()
        )
        headers = {
            **decision_service_auth_headers(),
            "X-Tenant-Id": str(diagnosis.tenant_id),
            "Content-Type": "application/json",
            "Idempotency-Key": snapshot_idempotency,
        }
        now = datetime.now(UTC)
        snapshot_payload = {
            "field_id": diagnosis.field_id,
            "season_id": diagnosis.season_id,
            "snapshot_hash": snapshot_hash,
            "acquisition_at": diagnosis.proposed_at.isoformat(),
            "data_available_at": now.isoformat(),
            "quality_gate": snapshot_quality_gate(diagnosis, now=now),
            "feature_manifest": {
                "contract": "DiagnosisHypothesisV1",
                "version": diagnosis.schema_version,
            },
            "payload": body,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
            snap = await client.post(
                f"{self.base_url}/v1/evidence/vegetation-snapshots",
                headers=headers,
                json=snapshot_payload,
            )
            if snap.status_code >= 400:
                raise RuntimeError(f"decision_snapshot_rejected:{snap.status_code}")
            snapshot_id = snap.json()["snapshot_id"]
            decision_payload = {
                "field_id": diagnosis.field_id,
                "season_id": diagnosis.season_id,
                "decision_type": "remote_sensing_diagnosis_referral",
                # "candidate" is the only reviewable stage: the former "pending_approval" stage
                # was stored but could never be reviewed. The review state lives server-side.
                "stage": "candidate",
                "decision_value": {
                    "status": "pending_approval",
                    "approval_required": True,
                    # Deterministic content identity: decision-service derives the decision_id
                    # from tenant + this lineage, so a retry replays instead of duplicating.
                    "candidate_lineage_id": candidate_lineage_id(
                        diagnosis.diagnosis_ref, snapshot_hash
                    ),
                    "diagnosis_ref": diagnosis.diagnosis_ref,
                    "suspected_condition": diagnosis.suspected_condition,
                    "confidence": float(diagnosis.confidence),
                    "confidence_method": diagnosis.confidence_method,
                    "confidence_is_probability": False,
                    "evidence_refs": [e.evidence_ref for e in diagnosis.evidence_bundle.evidence],
                },
                "confidence": float(diagnosis.confidence),
                "vegetation_snapshot_id": snapshot_id,
            }
            decision_headers = {**headers, "Idempotency-Key": decision_idempotency}
            dec = await client.post(
                f"{self.base_url}/v1/decisions/record",
                headers=decision_headers,
                json=decision_payload,
            )
            if dec.status_code >= 400:
                raise RuntimeError(f"decision_referral_rejected:{dec.status_code}")
            result = dec.json()

        referral_key = hashlib.sha256(f"{diagnosis.diagnosis_ref}|decision".encode()).hexdigest()[
            :24
        ]
        referral = DiagnosisDecisionReferralV1(
            referral_ref=f"urn:sahool:decision-referral:dref_{referral_key}",
            tenant_id=diagnosis.tenant_id,
            field_id=diagnosis.field_id,
            season_id=diagnosis.season_id,
            diagnosis_ref=diagnosis.diagnosis_ref,
            field_context=FieldContextRefV1(
                field_state_ref=field_state_ref,
                soil_context_ref=soil_context_ref,
                weather_context_ref=weather_context_ref,
            ),
            evidence_bundle=diagnosis.evidence_bundle,
            suggested_action_class=SuggestedActionClassV1(
                action_type="investigate_and_recommend",
                urgency="medium",  # Input quality is not agronomic urgency.
            ),
            validity_context=ValidityContextV1(
                valid_from=now,
                valid_until=now + timedelta(hours=48),
                weather_window_required=False,
            ),
            referred_at=now,
        )
        return {
            "referral": referral.model_dump(mode="json"),
            "decision_service": result,
            "idempotency": {
                "snapshot": snapshot_idempotency,
                "decision": decision_idempotency,
            },
        }


_GROUND_EVIDENCE_TYPE = "ground_verification"
_SUPPORTING_RELATIONS = frozenset({"primary", "supporting", "corroborating"})


def snapshot_quality_gate(diagnosis: DiagnosisHypothesisV1, *, now: datetime) -> dict[str, Any]:
    """The snapshot's quality gate, derived from the diagnosis evidence (never a fixed label).

    ``verified``/``ground_verification`` is claimed only when the bundle carries ground
    verification evidence of this tenant that is VERIFIED, supports the diagnosis, is not
    expired at ``now``, and is not contradicted by another ground observation. Otherwise the
    snapshot says plainly that it is an unverified remote-sensing hypothesis and repeats the
    diagnosis' own ground-verification requirement. decision-service eligibility does not read
    these two fields, so the honest value does not change acceptance.
    """
    tenant = str(diagnosis.tenant_id)
    ground = [
        e
        for e in diagnosis.evidence_bundle.evidence
        if e.evidence_type == _GROUND_EVIDENCE_TYPE and str(e.tenant_id) == tenant
    ]
    contradicted = any(
        str(e.relation_type) == "contradicting" and str(e.verification_state) != "superseded"
        for e in ground
    )
    usable = [
        e
        for e in ground
        if str(e.relation_type) in _SUPPORTING_RELATIONS
        and str(e.verification_state) == "verified"
        and (e.valid_until is None or e.valid_until > now)
    ]
    requirement = str(diagnosis.ground_verification_requirement)
    if usable and not contradicted:
        return {
            "status": "verified",
            "source": _GROUND_EVIDENCE_TYPE,
            "evidence_refs": sorted(e.evidence_ref for e in usable),
            "ground_verification_requirement": requirement,
        }
    return {
        "status": "contradicted" if contradicted else "unverified",
        "source": "remote_sensing_hypothesis",
        "evidence_refs": [],
        "ground_verification_requirement": requirement,
    }
