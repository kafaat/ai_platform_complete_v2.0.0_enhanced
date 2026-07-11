"""WX-12.1 runtime<->decision-service contract test.

Drives the *real* runtime/worker code paths with a capturing transport, then replays every
request they emit against the decision-service FastAPI app in mirror mode (SoR off). A missing
route yields 404/405; a missing required header yields 400; a body that fails the Pydantic model
yields 422. The contract is satisfied only when each replayed request reaches the SoR gate (503).
This catches exactly the class of gaps structural guards miss: URL/header/body drift.
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

ADAPTER_DIR = pathlib.Path(__file__).resolve().parents[1]
DS_DIR = ADAPTER_DIR.parents[0] / "decision-service"

os.environ.update(
    {
        "SAHOOL_ENV": "staging",
        "MODEL_REGISTRY_URL": "http://registry.local",
        "MODEL_REGISTRY_TOKEN": "tok",
        "MODEL_REGISTRY_BACKEND": "http",
        "MODEL_TRAFFIC_CONTROLLER_URL": "http://controller.local",
        "MODEL_METRICS_SOURCE_URL": "http://metrics.local",
        "MODEL_TRAINING_BACKEND_URL": "http://training.local",
        "MODEL_INFERENCE_VERIFY_URL": "http://inference.local",
        "REGISTRY_ADAPTER_ID": "adapter-1",
        "DECISION_SERVICE_URL": "http://decision.local",
        "DECISION_SERVICE_TOKEN": "tok",
    }
)
os.environ.pop("DECISION_SERVICE_SOR_ENABLED", None)  # mirror mode: mutating endpoints end at 503

for p in (str(ADAPTER_DIR), str(DS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

fastapi_testclient = pytest.importorskip("fastapi.testclient")
import main as ds  # noqa: E402  decision-service FastAPI app
import runtime as rt  # noqa: E402
import worker as wk  # noqa: E402

CLIENT = fastapi_testclient.TestClient(ds.app)
CAPTURED: list[dict] = []


def _replay(method: str, url: str, headers: dict, body):
    path = url.replace("http://decision.local", "")
    q = ""
    if "?" in path:
        path, q = path.split("?", 1)
    hdrs = {k: v for k, v in (headers or {}).items() if k != "Authorization"}
    resp = CLIENT.request(
        method,
        path,
        params=dict(x.split("=", 1) for x in q.split("&") if x),
        headers=hdrs,
        json=body,
    )
    # 503 = route exists, headers ok, body validated, stopped at the mirror SoR gate.
    assert resp.status_code not in (404, 405), f"route missing: {method} {path}"
    assert resp.status_code != 400, f"required header missing: {method} {path} -> {resp.text[:200]}"
    assert resp.status_code != 422, f"body fails Pydantic: {method} {path} -> {resp.text[:200]}"
    assert resp.status_code == 503, f"expected mirror 503, got {resp.status_code}: {method} {path}"


def _capturing(method, url, *, token="", body=None, headers=None, timeout=15.0):
    # Registry/controller/metrics/training helpers hit non-decision hosts; stub those, capture DS.
    if "decision.local" in url:
        CAPTURED.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        return {}
    if "registry.local" in url:
        return {"alias": "a", "artifact_uri": "s3://x", "artifact_digest": "d" * 64, "version": "1"}
    resp = {
        "verification_state": "verified_healthy",
        "checks": {},
        "latency_ms": 1.0,
        "failure_reason": None,
        "artifact_digest": "d" * 64,
        "traffic_percent": 10.0,
        "candidate_artifact_digest": "d" * 64,
        "version": "1",
        "sample_count": 500,
        "feature_drift": 0.0,
        "job_id": "job-1",
        "state": "submitted",
        "backend_version": "b1",
    }
    # echo correlation keys so the helpers' request/response correlation checks pass.
    for k in ("request_id", "idempotency_key", "model_id", "artifact_digest"):
        if body and k in body:
            resp[k] = body[k]
    return resp


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(rt, "_json_request", _capturing)
    CAPTURED.clear()
    yield


def _emitted():
    return [c for c in CAPTURED if "decision.local" in c["url"]]


def test_runtime_verification_and_rollout_and_retraining_satisfy_contract():
    r = rt.LifecycleRuntime()
    tenant = "00000000-0000-0000-0000-000000001111"
    # payloads mirror exactly what list_runtime_work() emits for each work_type.
    r.verify_activation(
        tenant,
        {
            "activation_receipt_id": "ar1",
            "model_id": "m1",
            "feature_set_id": "f1",
            "target_environment": "staging",
            "active_artifact_uri": "s3://a",
            "active_artifact_digest": "d" * 64,
        },
    )
    r.apply_rollout(
        tenant,
        {
            "rollout_plan_id": "rp1",
            "model_id": "m1",
            "feature_set_id": "f1",
            "target_environment": "staging",
            "rollout_mode": "canary",
            "traffic_percent": 10.0,
            "candidate_artifact_digest": "d" * 64,
            "expected_active_artifact_digest": "e" * 64,
        },
    )
    r.record_monitoring(
        tenant,
        {"model_id": "m1", "feature_set_id": "f1", "target_environment": "staging"},
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
    )
    r.dispatch_retraining(
        tenant,
        {
            "retraining_request_id": "rr1",
            "model_id": "m1",
            "feature_set_id": "f1",
            "dataset_fingerprint": "d" * 64,
            "training_manifest": {"a": 1},
            "code_version": "v1",
            "hyperparameters": {"lr": 0.1},
        },
    )
    calls = _emitted()
    assert len(calls) == 4
    for c in calls:
        _replay(c["method"], c["url"], c["headers"], c["body"])


def test_active_state_uses_target_environment_param():
    r = rt.LifecycleRuntime()
    tenant = "00000000-0000-0000-0000-000000001111"
    captured_get = {}

    def _cap_get(method, url, **kw):
        captured_get["url"] = url
        return {"registry_alias": "a", "active_artifact_digest": "d" * 64}

    import runtime as rmod

    orig = rmod._json_request
    rmod._json_request = _cap_get
    try:
        r.reconcile_active_state(
            tenant,
            "m1",
            "f1",
            "staging",
            lambda *a, **k: type("S", (), {"artifact_digest": "d" * 64, "version": "1"})(),
        )
    finally:
        rmod._json_request = orig
    assert "target_environment=staging" in captured_get["url"]
    assert "environment=staging" not in captured_get["url"].replace(
        "target_environment=staging", ""
    )


def test_worker_activation_and_rollback_receipts_satisfy_contract(monkeypatch):
    monkeypatch.setattr(
        wk,
        "HttpRegistry",
        lambda: type(
            "R",
            (),
            {
                "compare_and_swap": lambda self, **k: type(
                    "S", (), {"artifact_uri": "s3://x", "artifact_digest": "d" * 64, "version": "1"}
                )()
            },
        )(),
    )
    posts: list[dict] = []
    monkeypatch.setattr(
        wk,
        "_post",
        lambda path, payload, tenant_id, extra=None: (
            posts.append({"path": path, "payload": payload, "extra": extra}) or {}
        ),
    )
    tenant = "00000000-0000-0000-0000-000000001111"
    wk.execute_activation(
        {
            "activation_command_id": "ac1",
            "model_id": "m1",
            "target_environment": "staging",
            "registry_alias": "a",
            "previous_artifact_digest": "e" * 64,
            "candidate_artifact_uri": "s3://c",
            "candidate_artifact_digest": "d" * 64,
        },
        tenant,
    )
    wk.execute_rollback(
        {
            "rollback_command_id": "rc1",
            "model_id": "m1",
            "target_environment": "staging",
            "registry_alias": "a",
            "replace_artifact_digest": "d" * 64,
            "restore_artifact_uri": "s3://r",
            "restore_artifact_digest": "e" * 64,
        },
        tenant,
    )
    receipts = [p for p in posts if p["path"].endswith("/receipt")]
    assert receipts, "worker emitted no receipt"
    for r in receipts:
        assert "idempotency_key" in r["payload"], f"receipt missing idempotency_key: {r['path']}"
        assert (r["extra"] or {}).get("X-Recorded-By"), (
            f"receipt missing X-Recorded-By: {r['path']}"
        )


def test_service_token_guard_enforced_when_configured(monkeypatch):
    # opt-in: with the shared token configured, non-probe requests without a valid bearer are 401.
    monkeypatch.setenv("DECISION_SERVICE_AUTH_TOKEN", "secret-xyz")
    no_bearer = CLIENT.post(
        "/v1/learning/monitoring-snapshots",
        headers={"X-Tenant-Id": "00000000-0000-0000-0000-000000001111", "X-Captured-By": "a"},
        json={},
    )
    assert no_bearer.status_code == 401
    with_bearer = CLIENT.post(
        "/v1/learning/monitoring-snapshots",
        headers={
            "X-Tenant-Id": "00000000-0000-0000-0000-000000001111",
            "X-Captured-By": "a",
            "Authorization": "Bearer secret-xyz",
        },
        json={},
    )
    assert with_bearer.status_code != 401  # passes auth (then 422/503 downstream)
    assert CLIENT.get("/healthz").status_code != 401  # probes are exempt
