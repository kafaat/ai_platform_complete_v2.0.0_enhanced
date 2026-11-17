"""W4-05: the WX-12 model-lifecycle loop is stopped server-side by default.

Owner decision 2026-11-16: until a real owner exists for the four external backends (traffic
controller, inference verifier, metrics source, training backend), the decision-service must not
accept WX-12 work it cannot carry out. HTTP boundary through ``TestClient`` with persistence
mocked, no Postgres: the refusal comes after header/body/SoR validation and before any write,
with no Retry-After, and /readyz reports the capability without changing its verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

TOKEN = "w4-05-token"
TENANT = "00000000-0000-0000-0000-000000004055"
DIGEST = "a" * 64

# (method, path, writer patched on main, body, actor header)
ENDPOINTS = [
    (
        "/v1/learning/activation-receipts/actrcp_1/verification",
        "create_post_activation_verification",
        {
            "verification_state": "verified_healthy",
            "artifact_digest": DIGEST,
            "idempotency_key": "k",
        },
        "X-Verified-By",
    ),
    (
        "/v1/learning/activation-receipts/actrcp_1/rollout-plan",
        "create_rollout_plan",
        {"mode": "canary", "traffic_percent": 10, "idempotency_key": "k"},
        "X-Requested-By",
    ),
    (
        "/v1/learning/monitoring-snapshots",
        "record_monitoring_snapshot",
        {
            "model_id": "m1",
            "target_environment": "staging",
            "window_start": "2026-11-01T00:00:00+00:00",
            "window_end": "2026-11-02T00:00:00+00:00",
            "sample_count": 10,
            "drift_state": "stable",
            "idempotency_key": "k",
        },
        "X-Captured-By",
    ),
    (
        "/v1/learning/retraining-requests",
        "create_retraining_request",
        {
            "model_id": "m1",
            "target_environment": "staging",
            "dataset_fingerprint": DIGEST,
            "training_manifest": {"a": 1},
            "code_version": "v1",
            "idempotency_key": "k",
        },
        "X-Requested-By",
    ),
    (
        "/v1/learning/rollout-plans/rollout_1/receipt",
        "record_rollout_receipt",
        {"receipt_state": "applied", "controller_id": "c1", "idempotency_key": "k"},
        "X-Recorded-By",
    ),
    (
        "/v1/learning/retraining-requests/retrain_1/dispatch-receipt",
        "record_retraining_dispatch_receipt",
        {
            "dispatch_state": "dispatched",
            "dispatcher_id": "d1",
            "job_id": "j1",
            "idempotency_key": "k",
        },
        "X-Recorded-By",
    ),
    (
        "/v1/learning/runtime-schedules",
        "create_runtime_schedule",
        {
            "kind": "monitoring_window",
            "model_id": "m1",
            "target_environment": "staging",
            "period_seconds": 300,
            "idempotency_key": "k",
        },
        "X-Requested-By",
    ),
    (
        "/v1/learning/reconcile-evidence",
        "record_reconcile_evidence",
        {
            "model_id": "m1",
            "target_environment": "staging",
            "expected_artifact_digest": DIGEST,
            "observed_artifact_digest": DIGEST,
            "drift_detected": False,
            "idempotency_key": "k",
        },
        "X-Recorded-By",
    ),
]
IDS = [e[1] for e in ENDPOINTS]


@pytest.fixture
def client(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main, "sor_enabled", lambda: True)
    monkeypatch.delenv("DECISION_MODEL_LIFECYCLE_ENABLED", raising=False)
    return main, TestClient(main.app, raise_server_exceptions=False)


def _headers(actor_header: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "X-Tenant-ID": TENANT, actor_header: "ops"}


def test_the_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("DECISION_MODEL_LIFECYCLE_ENABLED", raising=False)
    assert persistence.model_lifecycle_enabled() is False
    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", value)
        assert persistence.model_lifecycle_enabled() is True
    monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", "0")
    assert persistence.model_lifecycle_enabled() is False


@pytest.mark.parametrize(("path", "writer", "body", "actor"), ENDPOINTS, ids=IDS)
def test_off_refuses_with_a_named_state_and_writes_nothing(
    client, monkeypatch, path, writer, body, actor
):
    main, test_client = client
    spy = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(main, writer, spy)
    response = test_client.post(path, json=body, headers=_headers(actor))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "model_lifecycle_disabled"
    assert "retry-after" not in {k.lower() for k in response.headers}
    spy.assert_not_called()


@pytest.mark.parametrize(("path", "writer", "body", "actor"), ENDPOINTS, ids=IDS)
def test_off_still_validates_first(client, monkeypatch, path, writer, body, actor):
    """The refusal comes after validation: a missing actor is still 400, not the flag's 503."""
    main, test_client = client
    spy = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(main, writer, spy)
    headers = _headers(actor)
    headers.pop(actor)
    response = test_client.post(path, json=body, headers=headers)
    assert response.status_code == 400, response.text
    spy.assert_not_called()


@pytest.mark.parametrize(("path", "writer", "body", "actor"), ENDPOINTS, ids=IDS)
def test_off_does_not_mask_the_sor_gate(client, monkeypatch, path, writer, body, actor):
    main, test_client = client
    monkeypatch.setattr(main, "sor_enabled", lambda: False)
    spy = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(main, writer, spy)
    response = test_client.post(path, json=body, headers=_headers(actor))
    assert response.status_code == 503
    assert response.json()["detail"] == "decision-service is not the system-of-record"
    spy.assert_not_called()


@pytest.mark.parametrize(("path", "writer", "body", "actor"), ENDPOINTS, ids=IDS)
def test_on_reaches_the_writer(client, monkeypatch, path, writer, body, actor):
    main, test_client = client
    monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", "1")
    spy = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(main, writer, spy)
    response = test_client.post(path, json=body, headers=_headers(actor))
    assert response.status_code == 200, response.text
    spy.assert_awaited_once()


def test_the_feed_asks_the_query_for_the_flag_state(client, monkeypatch):
    main, test_client = client
    monkeypatch.setattr(main, "_verify_worker_identity", lambda *a, **k: None)
    monkeypatch.setattr(main, "worker_tenant_authorized", AsyncMock(return_value=True))
    feed = AsyncMock(return_value={"status": "ok", "items": []})
    monkeypatch.setattr(main, "list_runtime_work", feed)
    headers = {"Authorization": f"Bearer {TOKEN}", "X-Tenant-ID": TENANT}
    off = test_client.get("/v1/learning/runtime-work?worker_id=w1", headers=headers)
    monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", "1")
    on = test_client.get("/v1/learning/runtime-work?worker_id=w1", headers=headers)
    assert (off.status_code, on.status_code) == (200, 200), (off.text, on.text)
    flags = [call.kwargs["include_model_lifecycle"] for call in feed.await_args_list]
    assert flags == [False, True]


def test_readyz_reports_the_capability_without_changing_the_verdict(client, monkeypatch):
    main, test_client = client
    monkeypatch.setattr(main, "sor_enabled", lambda: False)
    off = test_client.get("/readyz")
    monkeypatch.setenv("DECISION_MODEL_LIFECYCLE_ENABLED", "1")
    on = test_client.get("/readyz")
    assert off.status_code == on.status_code
    assert off.json()["ready"] == on.json()["ready"]
    cap_off = off.json()["capabilities"]["model_lifecycle"]
    cap_on = on.json()["capabilities"]["model_lifecycle"]
    assert cap_off["enabled"] is False and cap_off["code"] == "model_lifecycle_disabled"
    assert cap_on["enabled"] is True and cap_on["code"] is None


def test_every_wx12_write_endpoint_is_gated():
    """Negative control: a WX-12 write route added without the refusal fails here."""
    import inspect

    import main

    gated = set()
    for route in main.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if "POST" not in methods or not path.startswith("/v1/learning/"):
            continue
        source = inspect.getsource(route.endpoint)
        if "_refuse_while_model_lifecycle_disabled()" in source:
            gated.add(path)
    expected = {path for path, *_ in ENDPOINTS}
    expected = {p.replace("actrcp_1", "{activation_receipt_id}") for p in expected}
    expected = {p.replace("rollout_1", "{rollout_plan_id}") for p in expected}
    expected = {p.replace("retrain_1", "{retraining_request_id}") for p in expected}
    assert gated == expected, sorted(gated ^ expected)
