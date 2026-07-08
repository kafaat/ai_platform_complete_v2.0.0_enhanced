from __future__ import annotations

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
HEADERS = {"X-Tenant-Id": "tenant-1"}


def test_contract_names_owned_loop_tables():
    data = client.get("/contract").json()
    assert data["service"] == "decision-service"
    assert "decision_record" in data["owned_tables"]
    assert "online_learning_updates" in data["owned_tables"]
    assert data["platform_role"].startswith("BFF")


def test_decision_outcome_and_learning_endpoints_exist():
    dec = client.post(
        "/v1/decisions/record",
        headers=HEADERS,
        json={"decision_type": "irrigation", "decision_value": {"action": "irrigate"}},
    )
    assert dec.status_code == 200
    did = dec.json()["decision_id"]
    out = client.post(
        "/v1/outcomes/record",
        headers=HEADERS,
        json={"decision_id": did, "planned": {}, "actual": {}, "metrics": {}, "success": True},
    )
    assert out.status_code == 200
    learn = client.post("/v1/learning/updates", headers=HEADERS, json={"model_id": "m1"})
    assert learn.status_code == 200
    assert learn.json()["traceability_status"] == "rejected_untraceable"


def test_learning_update_traceable_when_source_present():
    res = client.post(
        "/v1/learning/updates",
        headers=HEADERS,
        json={"model_id": "m1", "source_type": "outcome_record", "source_id": "out_1"},
    )
    assert res.status_code == 200
    assert res.json()["traceability_status"] == "traceable"


def test_dispatch_decision_persistence_endpoint():
    """P4.5: the platform dispatch/execute write route now delegates here."""
    res = client.post(
        "/v1/dispatch/decisions",
        headers=HEADERS,
        json={"recommendation_id": "rec-1", "action_type": "irrigate", "state": "queued"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["persisted"] is True
    assert body["tenant_id"] == "tenant-1"
    assert body["recommendation_id"] == "rec-1"
    assert body["state"] == "queued"
    assert body["decision_id"].startswith("disp_")


def test_recommendation_outcome_persistence_endpoint():
    """P4.5: the platform recommendations/outcomes write route now delegates here."""
    res = client.post(
        "/v1/recommendation-outcomes",
        headers=HEADERS,
        json={"recommendation_id": "rec-9", "outcome": "actual_recorded"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["persisted"] is True
    assert body["recommendation_id"] == "rec-9"
    assert body["outcome"] == "actual_recorded"


def test_write_endpoints_require_tenant_header():
    """Tenant scoping moved with persistence: writes without X-Tenant-Id are rejected."""
    for path, payload in [
        ("/v1/decisions/record", {"decision_type": "irrigation"}),
        ("/v1/dispatch/decisions", {"recommendation_id": "r", "action_type": "irrigate"}),
        ("/v1/outcomes/record", {"decision_id": "d"}),
        ("/v1/recommendation-outcomes", {"recommendation_id": "r"}),
        ("/v1/learning/updates", {"model_id": "m"}),
    ]:
        res = client.post(path, json=payload)
        assert res.status_code == 401, path


def test_p4_6_read_side_decision_list_endpoint():
    """P4.6: the platform decision-records read route now delegates here."""
    res = client.get("/v1/decisions", headers=HEADERS, params={"field_id": "fld-1", "limit": 25})
    assert res.status_code == 200
    body = res.json()
    assert body["tenant_id"] == "tenant-1"
    assert body["field_id"] == "fld-1"
    assert body["limit"] == 25
    assert body["decisions"] == []
    assert body["count"] == 0


def test_p4_6_read_side_field_lineage_endpoint():
    """P4.6: the platform field-lineage read route now delegates here."""
    res = client.get("/v1/fields/fld-9/lineage", headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["field_id"] == "fld-9"
    assert body["decisions"] == []
    assert body["orphan_outcomes"] == []
    assert body["count"] == 0


def test_p4_6_read_side_reconciled_outcomes_endpoint():
    """P4.6: reconciled-outcome semantics (learning dashboard) belong to the owner service."""
    res = client.get(
        "/v1/outcomes/reconciled", headers=HEADERS, params={"field_id": "fld-1", "season_id": "s1"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["tenant_id"] == "tenant-1"
    recon = body["outcome_reconciliation"]
    assert recon["enabled"] is True
    assert recon["success_rate"] is None
    assert recon["by_source"] == {}


def test_read_endpoints_require_tenant_header():
    """Read scoping is tenant-bound too: reads without X-Tenant-Id are rejected."""
    for path in ("/v1/decisions", "/v1/fields/fld-1/lineage", "/v1/outcomes/reconciled"):
        res = client.get(path)
        assert res.status_code == 401, path
