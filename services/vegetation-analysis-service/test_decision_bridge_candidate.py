"""RS-8 decision bridge sends a reviewable, replayable candidate (no network).

The bridge used to record the referral with stage ``pending_approval``, which decision-service
stores but can never review (only ``candidate`` rows are reviewable). It now records a
``candidate`` carrying a deterministic ``candidate_lineage_id``, so decision-service derives the
same decision_id on a retry and replays it instead of minting a duplicate.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import decision_bridge
import pytest
from decision_bridge import DecisionBridge, candidate_lineage_id
from diagnosis_engine import build_diagnosis

pytestmark = pytest.mark.unit

TENANT = "88ddb9f8-cf89-4398-a404-fe88ec4d4bb6"


def _diagnosis():
    record = {
        "anomaly_ref": "urn:sahool:anomaly:anm_bridge",
        "tenant_id": TENANT,
        "field_id": "fld_bridge",
        "season_id": "season_2026",
        "status": "confirmed",
        "payload": {
            "signal_type": "ndmi_decline",
            "confidence": "0.78",
            "verification_evidence_refs": ["urn:sahool:evidence:evd_1"],
            "verification_evidence": [
                {
                    "evidence_ref": "urn:sahool:evidence:evd_1",
                    "tenant_id": TENANT,
                    "source_system": "task-service",
                    "evidence_type": "ground_verification",
                    "relation_type": "corroborating",
                    "captured_at": "2026-07-15T00:00:00Z",
                    "content_hash": "a" * 64,
                    "verification_state": "verified",
                }
            ],
            "disposition_reason_codes": ["soil_dry"],
        },
    }
    return build_diagnosis(anomaly_record=record, tenant_id=UUID(TENANT))


class _Response:
    def __init__(self, body: dict) -> None:
        self.status_code = 200
        self._body = body

    def json(self) -> dict:
        return self._body


def _fake_client(posts: list):
    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            posts.append((url, json))
            if url.endswith("/v1/evidence/vegetation-snapshots"):
                return _Response({"snapshot_id": "veg_1"})
            return _Response({"decision_id": "dec_1", "stage": json["stage"]})

    return _Client


def _refer(monkeypatch, diagnosis) -> dict:
    posts: list = []
    monkeypatch.setattr(decision_bridge.httpx, "AsyncClient", _fake_client(posts))
    asyncio.run(
        DecisionBridge(base_url="http://decision.test").refer(
            diagnosis=diagnosis,
            authorization="Bearer t",
            field_state_ref="urn:sahool:field-state:fs_1",
        )
    )
    return next(body for url, body in posts if url.endswith("/v1/decisions/record"))


def test_referral_is_recorded_as_a_reviewable_candidate(monkeypatch):
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    body = _refer(monkeypatch, _diagnosis())
    assert body["stage"] == "candidate"
    value = body["decision_value"]
    assert value["status"] == "pending_approval" and value["approval_required"] is True
    assert value["candidate_lineage_id"].startswith("rs8_")


def test_a_retry_of_the_same_diagnosis_carries_the_same_lineage(monkeypatch):
    monkeypatch.delenv("DECISION_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("SAHOOL_ENV", raising=False)
    diagnosis = _diagnosis()
    first = _refer(monkeypatch, diagnosis)
    retry = _refer(monkeypatch, diagnosis)
    assert first["decision_value"] == retry["decision_value"]
    assert "decision_id" not in first, "decision-service derives it from tenant + lineage"


def test_lineage_is_deterministic_and_content_bound():
    a = candidate_lineage_id("urn:sahool:diagnosis:d1", "f" * 64)
    assert a == candidate_lineage_id("urn:sahool:diagnosis:d1", "f" * 64)
    assert a != candidate_lineage_id("urn:sahool:diagnosis:d1", "e" * 64)
    assert a != candidate_lineage_id("urn:sahool:diagnosis:d2", "f" * 64)
