"""Phase 2 P2-b — satellite_cdse activation gate HTTP surface + source-selection enforcement.

Certifies the operator lifecycle (begin→complete→enabled, revoke, reset) over the API, that the
/source enforcement read routes to 'cdse' when the gate is enabled and to the 'element84' fallback
otherwise (a SOURCE SELECTION, never a 403 — the deliberate Category-A variation from irr_f01), and
that the probe endpoint is closed to a normal caller. Runs against real Postgres.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

DB = os.getenv("DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not DB, reason="requires real Postgres")


def _client(monkeypatch, env_id: str):
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env_id)
    monkeypatch.setenv("ACTIVATION_PROBE_SIGNING_KEY", "probe-key")
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "d" * 40)
    monkeypatch.setenv("ACTIVATION_EVIDENCE_SIGNING_KEY", "evidence-key")
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    import main
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _evidence(env_id: str, *, complete: bool = True) -> list[dict]:
    observed = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    items = [
        {
            "producer": "raster-service",
            "check_name": "cdse_credentials_present",
            "observed_at": observed,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/cdse_client",
            "environment_id": env_id,
        },
        {
            "producer": "raster-service",
            "check_name": "cdse_live_probe",
            "observed_at": observed,
            "valid_until": future,
            "result": "pass",
            "provenance": "raster-service/stac_search",
            "environment_id": env_id,
        },
    ]
    return items if complete else items[:1]


def _store_evidence(client, items: list[dict], gate_name: str) -> list[str]:
    from activation_gate_core import canonical_evidence_signature

    refs = []
    for item in items:
        body = {**item, "gate_name": gate_name, "build_sha": "d" * 40, "payload": {}}
        body["signature"] = canonical_evidence_signature("evidence-key", **body)
        response = client.post("/v1/activation/evidence-receipts", json=body)
        assert response.status_code == 201, response.text
        refs.append(response.json()["evidence_id"])
    return refs


def test_operator_lifecycle_over_api(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}
    began = c.post("/v1/activation/satellite_cdse/begin", headers=h)
    assert began.status_code == 200 and began.json()["status"] == "evaluating"
    gen = began.json()["generation"]
    done = c.post(
        "/v1/activation/satellite_cdse/complete",
        headers=h,
        json={
            "expected_generation": gen,
            "evidence_refs": _store_evidence(c, _evidence(env_id), "satellite_cdse"),
            "ttl_seconds": 3600,
        },
    )
    assert done.status_code == 200 and done.json()["status"] == "enabled"
    cur = c.get("/v1/activation/satellite_cdse")
    assert cur.status_code == 200 and cur.json()["effective_enabled"] is True
    rv = c.post("/v1/activation/satellite_cdse/revoke", headers=h, json={"reason": "incident"})
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    assert c.post("/v1/activation/satellite_cdse/reset", headers=h).json()["status"] == "disabled"


def test_source_selection_reflects_gate(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}
    # disabled ⇒ safe element84 fallback, never a refusal
    src = c.get("/v1/activation/satellite_cdse/source")
    assert src.status_code == 200
    assert src.json()["source"] == "element84" and src.json()["fallback"] is True
    # enable the gate ⇒ source flips to cdse
    gen = c.post("/v1/activation/satellite_cdse/begin", headers=h).json()["generation"]
    c.post(
        "/v1/activation/satellite_cdse/complete",
        headers=h,
        json={
            "expected_generation": gen,
            "evidence_refs": _store_evidence(c, _evidence(env_id), "satellite_cdse"),
            "ttl_seconds": 3600,
        },
    )
    enabled = c.get("/v1/activation/satellite_cdse/source")
    assert enabled.status_code == 200
    assert enabled.json()["source"] == "cdse" and enabled.json()["fallback"] is False
    # incomplete evidence path: revoke ⇒ back to fallback
    c.post("/v1/activation/satellite_cdse/revoke", headers=h, json={"reason": "incident"})
    assert c.get("/v1/activation/satellite_cdse/source").json()["source"] == "element84"


def test_probe_endpoint_closed_to_normal_caller(monkeypatch):
    import satellite_cdse_activation_gate as gate

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # no role/signature ⇒ 403
    assert c.get("/v1/activation/satellite_cdse/probe").status_code == 403
    sig = gate.probe_signature(env_id, secret="probe-key")
    denied = c.get(
        "/v1/activation/satellite_cdse/probe",
        headers={"X-Activation-Role": "user", "X-Activation-Probe-Signature": sig},
    )
    assert denied.status_code == 403
    ok = c.get(
        "/v1/activation/satellite_cdse/probe",
        headers={"X-Activation-Role": gate.PROBE_ROLE, "X-Activation-Probe-Signature": sig},
    )
    assert ok.status_code == 200


def test_source_requires_system_of_record(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env_id)
    monkeypatch.delenv("DECISION_SERVICE_SOR_ENABLED", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from fastapi.testclient import TestClient

    c = TestClient(main.app)
    # mirror mode (no SoR) ⇒ 503, never a silent source answer
    assert c.get("/v1/activation/satellite_cdse/source").status_code == 503
