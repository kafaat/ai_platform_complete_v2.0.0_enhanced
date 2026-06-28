import os

from api.phase12_marketplace_ecosystem import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# phase9-12 routers مؤمَّنة بتوكن خدمة على مستوى الراوتر؛ نضبط السرّ ونمرّر الترويسة.
os.environ.setdefault("SAHOOL_AGENT_TOKEN", "test-agent-token")


def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, headers={"X-Agent-Token": os.environ["SAHOOL_AGENT_TOKEN"]})


def manifest():
    return {
        "name": "irrigation_optimizer",
        "version": "1.0.0",
        "author": "sahool",
        "permissions": ["field.read", "weather.read", "recommendations.write"],
        "hooks": ["recommendation.before", "recommendation.after"],
        "entrypoint": "plugin.main:handler",
    }


def test_phase12_validate_and_cycle_endpoints():
    c = client()
    res = c.post("/v1/ecosystem/plugins/validate", json={"manifest": manifest()})
    assert res.status_code == 200
    assert res.json()["valid"] is True

    cycle = c.post("/v1/ecosystem/cycle", json={"manifest": manifest()})
    assert cycle.status_code == 200
    data = cycle.json()
    assert data["cycle_id"].startswith("ecosystem_")
    assert data["installation"]["installed"] is True


def test_phase12_webhook_and_usage_endpoints():
    c = client()
    webhook = c.post(
        "/v1/ecosystem/webhooks",
        json={
            "tenant_id": "tenant-1",
            "url": "https://example.com/hook",
            "events": ["field.updated"],
            "secret_ref": "secret/ref",
        },
    )
    assert webhook.status_code == 200

    delivery = c.post(
        "/v1/ecosystem/webhooks/delivery-plan",
        json={
            "subscription": webhook.json()["webhook"],
            "event_type": "field.updated",
            "payload": {"field_id": "f1"},
            "secret": "secret",
        },
    )
    assert delivery.status_code == 200
    assert delivery.json()["status"] == "pending"

    usage = c.post(
        "/v1/ecosystem/usage",
        json={
            "tenant_id": "tenant-1",
            "app_id": "app-1",
            "meter": "api_calls_day",
            "quantity": 1,
            "idempotency_key": "idem-1",
        },
    )
    assert usage.status_code == 200
    assert usage.json()["recorded"] is True


def test_phase12_connector_sdk_graphql_portal_endpoints():
    c = client()
    connector = c.post(
        "/v1/ecosystem/connectors/descriptor",
        json={"name": "ERPNext", "connector_type": "erp", "capabilities": ["farm.sync"]},
    )
    assert connector.status_code == 200
    assert connector.json()["connector"]["connector_type"] == "erp"
    assert c.get("/v1/ecosystem/sdk/manifest").json()["languages"]
    assert "Field" in c.get("/v1/ecosystem/graphql/schema").json()["types"]
    assert c.get("/v1/ecosystem/developer-portal/index").json()["status"] == "ready_for_static_site"


def approved_app_payload():
    c = client()
    reg = c.post(
        "/v1/ecosystem/marketplace/apps", json={"manifest": manifest(), "category": "agronomy"}
    )
    assert reg.status_code == 200
    app = reg.json()["app"]
    inst = c.post(
        "/v1/ecosystem/marketplace/installations",
        json={
            "app": app,
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "installed_by": "user-1",
        },
    )
    assert inst.status_code == 200
    return c, app, inst.json()["installation"]


def test_phase12_plugin_runtime_plan_and_output_validation_endpoints():
    c, app, installation = approved_app_payload()
    plan_res = c.post(
        "/v1/ecosystem/plugins/runtime/plan",
        json={
            "app": app,
            "installation": installation,
            "action": "recommendation.propose",
            "payload": {"field_id": "f1"},
            "usage_totals": {},
            "idempotency_key": "idem-api-1",
        },
    )
    assert plan_res.status_code == 200
    plan = plan_res.json()["plan"]
    assert plan["decision"] == "allow"

    validation = c.post(
        "/v1/ecosystem/plugins/runtime/validate-output",
        json={"plan": plan, "output": {"effects": [{"kind": "recommendation_proposal"}]}},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    envelope = c.post(
        "/v1/ecosystem/plugins/runtime/event-envelope",
        json={
            "plan": plan,
            "event_type": "plugin.recommendation.proposed",
            "payload": {"token": "redacted", "ok": True},
        },
    )
    assert envelope.status_code == 200
    assert "token" not in envelope.json()["envelope"]["payload"]


def test_phase12_plugin_runtime_report_endpoint():
    c, app, installation = approved_app_payload()
    report = c.post(
        "/v1/ecosystem/plugins/runtime/report",
        json={
            "app": app,
            "installation": installation,
            "actions": ["field.context.read", "recommendation.propose"],
        },
    )
    assert report.status_code == 200
    assert report.json()["summary"]["actions_checked"] == 2
