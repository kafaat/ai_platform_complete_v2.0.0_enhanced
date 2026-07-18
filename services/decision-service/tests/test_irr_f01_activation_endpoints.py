"""IRR-F01 Phase 1 P1-b — activation gate HTTP surface + enforcement wiring, on real Postgres.

Certifies the operator lifecycle (begin→complete→enabled, revoke, reset) over the API, that the
ingest endpoint enforces the gate when IRR_F01_RESERVATION_ENFORCE_ACTIVATION is on, that the
probe endpoint is closed to a normal caller, and the pure build_sha (deploy metadata) + read cache.
"""

from __future__ import annotations

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


def _client(monkeypatch, env_id: str, *, enforce: bool = False):
    monkeypatch.setenv("DECISION_SERVICE_SOR_ENABLED", "true")
    monkeypatch.setenv("ACTIVATION_ENVIRONMENT_ID", env_id)
    monkeypatch.setenv("ACTIVATION_PROBE_SIGNING_KEY", "probe-key")
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "deadbeef")
    monkeypatch.setenv("IRR_F01_RESERVATION_ENFORCE_ACTIVATION", "1" if enforce else "")
    monkeypatch.delenv("DECISION_SERVICE_AUTH_TOKEN", raising=False)
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


def _evidence(env_id: str, *, complete: bool = True) -> list[dict]:
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    items = [
        {
            "producer": "ci",
            "check_name": "ci_live_certification",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "ci",
            "environment_id": env_id,
        },
        {
            "producer": "decision-service",
            "check_name": "consumer_heartbeat",
            "observed_at": future,
            "valid_until": future,
            "result": "pass",
            "provenance": "inbox",
            "environment_id": env_id,
        },
    ]
    return items if complete else items[:1]


def test_operator_lifecycle_over_api(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    h = {"X-Requested-By": "operator"}
    began = c.post("/v1/activation/irr_f01_reservation/begin", headers=h)
    assert began.status_code == 200 and began.json()["status"] == "evaluating"
    gen = began.json()["generation"]
    done = c.post(
        "/v1/activation/irr_f01_reservation/complete",
        headers=h,
        json={"expected_generation": gen, "evidence": _evidence(env_id), "ttl_seconds": 3600},
    )
    assert done.status_code == 200 and done.json()["status"] == "enabled"
    cur = c.get("/v1/activation/irr_f01_reservation")
    assert cur.status_code == 200 and cur.json()["effective_enabled"] is True
    rv = c.post("/v1/activation/irr_f01_reservation/revoke", headers=h, json={"reason": "incident"})
    assert rv.status_code == 200 and rv.json()["status"] == "revoked"
    assert (
        c.post("/v1/activation/irr_f01_reservation/reset", headers=h).json()["status"] == "disabled"
    )


def test_ingest_enforces_activation_when_flag_on(monkeypatch):
    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id, enforce=True)
    hdr = {"X-Tenant-Id": "00000000-0000-0000-0000-0000000000e1"}
    body = {
        "source_event_id": "e-" + uuid4().hex,
        "event_type": "irrigation.reservation.dispatch_requested",
    }
    # gate disabled ⇒ ingest refused 403
    refused = c.post("/v1/reservation-dispatch-intents", headers=hdr, json=body)
    assert refused.status_code == 403 and "not activated" in refused.json()["detail"]
    # enable the gate, then ingest is accepted
    oh = {"X-Requested-By": "operator"}
    gen = c.post("/v1/activation/irr_f01_reservation/begin", headers=oh).json()["generation"]
    c.post(
        "/v1/activation/irr_f01_reservation/complete",
        headers=oh,
        json={"expected_generation": gen, "evidence": _evidence(env_id), "ttl_seconds": 3600},
    )
    ok = c.post("/v1/reservation-dispatch-intents", headers=hdr, json=body)
    assert ok.status_code == 200 and ok.json()["accepted"] is True


def test_probe_endpoint_closed_to_normal_caller(monkeypatch):
    import activation_gate as gate

    env_id = "env-" + uuid4().hex[:10]
    c = _client(monkeypatch, env_id)
    # no role/signature ⇒ 403
    assert c.get("/v1/activation/irr_f01_reservation/probe").status_code == 403
    sig = gate.probe_signature(env_id, secret="probe-key")
    denied = c.get(
        "/v1/activation/irr_f01_reservation/probe",
        headers={"X-Activation-Role": "user", "X-Activation-Probe-Signature": sig},
    )
    assert denied.status_code == 403
    ok = c.get(
        "/v1/activation/irr_f01_reservation/probe",
        headers={"X-Activation-Role": gate.PROBE_ROLE, "X-Activation-Probe-Signature": sig},
    )
    assert ok.status_code == 200


def test_build_sha_binds_deploy_metadata(monkeypatch):
    import activation_gate as gate

    ev = _evidence("env-x")
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "aaaa")
    a = gate.build_sha(ev)
    monkeypatch.setenv("DEPLOY_BUILD_SHA", "bbbb")
    b = gate.build_sha(ev)
    assert a != b  # a different deployed build changes the fingerprint
    assert gate.build_sha(ev) == b  # deterministic for a fixed build + evidence
