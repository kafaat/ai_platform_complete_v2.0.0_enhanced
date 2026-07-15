from __future__ import annotations

from datetime import datetime

import pytest
from anomaly_requests import VerificationCompletion
from anomaly_store import AnomalyNotFound, AnomalyStore
from pydantic import ValidationError


def _payload(ref: str, tenant: str) -> dict:
    return {
        "anomaly_ref": ref,
        "tenant_id": tenant,
        "field_id": "fld_final",
        "season_id": "sea_final",
        "status": "detected",
    }


def test_anomaly_store_tenant_scope_is_enforced_in_storage(tmp_path):
    store = AnomalyStore(str(tmp_path / "anomalies.db"))
    ref = "urn:sahool:anomaly:anm_final"
    store.upsert_detected(_payload(ref, "tenant-a"))

    with pytest.raises(AnomalyNotFound):
        store.get(ref, tenant_id="tenant-b")

    with pytest.raises(AnomalyNotFound):
        store.transition(
            ref,
            "triaged",
            expected_version=1,
            tenant_id="tenant-b",
        )

    record = store.get(ref, tenant_id="tenant-a")
    assert record["status"] == "detected"
    assert record["aggregate_version"] == 1


def test_verification_completion_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        VerificationCompletion(
            expected_version=1,
            task_ref="urn:sahool:task:task_1",
            verification_result="confirmed",
            completed_at=datetime(2026, 7, 15, 12, 0, 0),
        )
