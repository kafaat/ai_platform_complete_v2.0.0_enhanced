"""Ownership-safe RS-8 bridge to the existing decision-service."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from shared.contracts.remote_sensing import DiagnosisDecisionReferralV1, DiagnosisHypothesisV1
from shared.contracts.remote_sensing.decision_referral_v1 import (
    FieldContextRefV1,
    SuggestedActionClassV1,
    ValidityContextV1,
)


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
            "Authorization": authorization,
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
            "quality_gate": {"status": "verified", "source": "ground_verification"},
            "feature_manifest": {
                "contract": "DiagnosisHypothesisV1",
                "version": diagnosis.schema_version,
            },
            "payload": body,
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
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
                "stage": "pending_approval",
                "decision_value": {
                    "diagnosis_ref": diagnosis.diagnosis_ref,
                    "suspected_condition": diagnosis.suspected_condition,
                    "confidence": float(diagnosis.confidence),
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
                urgency="high" if diagnosis.confidence >= Decimal("0.8") else "medium",
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
