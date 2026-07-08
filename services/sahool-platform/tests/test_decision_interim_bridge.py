"""INTERIM decision bridge behavior (requirement 6 a–e), mocked — no Postgres, no HTTP.

Proves the temporary dual-path contract:
 (a) the platform performs the authoritative DB write (INSERT + outbox emit);
 (b) the decision-service mirror is attempted after the authoritative write;
 (c) a decision-service mirror failure does NOT lose platform data and does NOT fail the
     request (the response is derived solely from the platform write);
 (d) the platform write is fail-closed: if the platform DB write fails, the request 503s
     (covered here) — and the decision-service stub can never claim persistence
     (covered by services/decision-service/tests: test_write_endpoints_never_claim_real_persistence);
 (e) the migration path to a future decision-service SoR is documented (asserted here).
"""

from __future__ import annotations

from pathlib import Path

import api.main  # noqa: F401 — initialise api.main before importing routers
import pytest
from api.routers import decision_record as dr
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-bridge",
    tenant_id="00000000-0000-0000-0000-000000000009",
    role=UserRole.OWNER,
    name_ar="جسر",
)


class _FakeConn:
    def __init__(self, log: list, *, fail: bool = False):
        self.log = log
        self.fail = fail

    async def execute(self, sql, *args):
        if self.fail:
            raise RuntimeError("simulated platform DB failure")
        self.log.append(("execute", sql))

    async def fetchval(self, sql, *args):
        if self.fail:
            raise RuntimeError("simulated platform DB failure")
        self.log.append(("fetchval", sql))
        return None  # no idempotency replay row

    async def fetchrow(self, sql, *args):
        self.log.append(("fetchrow", sql))
        return None

    async def fetch(self, sql, *args):
        self.log.append(("fetch", sql))
        return []


class _FakeTenantConn:
    def __init__(self, log: list, *, fail: bool = False):
        self.log = log
        self.fail = fail

    async def __aenter__(self):
        return _FakeConn(self.log, fail=self.fail)

    async def __aexit__(self, *exc):
        return False


def _wire(
    monkeypatch, log: list, *, mirror_calls: list, mirror_raises: bool, db_fail: bool = False
):
    monkeypatch.setattr(dr, "tenant_connection", lambda user: _FakeTenantConn(log, fail=db_fail))

    async def _fake_emit(*args, **kwargs):
        log.append(("emit", args[2] if len(args) > 2 else None))

    monkeypatch.setattr(dr, "_emit_domain_event", _fake_emit)

    async def _fake_mirror_decision(payload, *, tenant_id=None):
        mirror_calls.append(("decision", payload, tenant_id))
        if mirror_raises:
            raise RuntimeError("decision-service is down")
        return {"accepted": True, "authoritative": False, "persisted": False}

    async def _fake_mirror_outcome(payload, *, tenant_id=None):
        mirror_calls.append(("outcome", payload, tenant_id))
        if mirror_raises:
            raise RuntimeError("decision-service is down")
        return {"accepted": True, "authoritative": False, "persisted": False}

    monkeypatch.setattr(dr, "_mirror_decision_to_service", _fake_mirror_decision)
    monkeypatch.setattr(dr, "_mirror_outcome_to_service", _fake_mirror_outcome)


async def test_decision_record_writes_platform_then_mirrors_when_mirror_ok(monkeypatch):
    log: list = []
    mirror_calls: list = []
    _wire(monkeypatch, log, mirror_calls=mirror_calls, mirror_raises=False)
    req = dr.DecisionRecordRequest(
        decision_type="irrigation_plan", decision_value={"action": "irrigate"}, field_id="fld-1"
    )
    out = await dr.record_decision(req, _USER)
    # (a) authoritative platform write happened (INSERT + outbox emit).
    assert any(k == "execute" and "INSERT INTO decision_record" in s for k, s in log)
    assert any(k == "emit" for k, s in log)
    # (b) the mirror was attempted after the write.
    assert mirror_calls and mirror_calls[0][0] == "decision"
    # response derived from platform write.
    assert out["persisted"] is True
    assert out["authoritative_store"] == "sahool-platform"


async def test_decision_record_survives_mirror_failure_without_data_loss(monkeypatch):
    log: list = []
    mirror_calls: list = []
    _wire(monkeypatch, log, mirror_calls=mirror_calls, mirror_raises=True)
    req = dr.DecisionRecordRequest(
        decision_type="irrigation_plan", decision_value={"action": "irrigate"}, field_id="fld-1"
    )
    # (c) mirror raising must NOT propagate; request still succeeds.
    out = await dr.record_decision(req, _USER)
    assert out["persisted"] is True
    # platform write still committed (not lost) and mirror was attempted.
    assert any(k == "execute" and "INSERT INTO decision_record" in s for k, s in log)
    assert mirror_calls and mirror_calls[0][0] == "decision"


async def test_decision_record_is_fail_closed_when_platform_write_fails(monkeypatch):
    log: list = []
    mirror_calls: list = []
    _wire(monkeypatch, log, mirror_calls=mirror_calls, mirror_raises=False, db_fail=True)
    req = dr.DecisionRecordRequest(decision_type="irrigation_plan", decision_value={"a": 1})
    # (d) platform write failure => 503, and the mirror is never used to fake success.
    with pytest.raises(HTTPException) as exc:
        await dr.record_decision(req, _USER)
    assert exc.value.status_code == 503
    assert not mirror_calls  # mirror not reached; no fake persistence


async def test_outcome_record_writes_platform_then_mirrors(monkeypatch):
    log: list = []
    mirror_calls: list = []
    _wire(monkeypatch, log, mirror_calls=mirror_calls, mirror_raises=True)  # mirror down
    req = dr.OutcomeRecordRequest(decision_id="dec_1", field_id="fld-1")
    out = await dr.record_outcome(req, _USER)  # mirror failure must not fail the request
    assert any(k == "fetchval" and "INSERT INTO outcome_record" in s for k, s in log)
    assert any(k == "emit" for k, s in log)
    assert mirror_calls and mirror_calls[0][0] == "outcome"
    assert out["persisted"] is True
    assert out["authoritative_store"] == "sahool-platform"


def test_migration_path_to_future_sor_is_documented():
    contract = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "architecture"
        / "DECISION_SERVICE_BOUNDARY_CONTRACT.md"
    ).read_text(encoding="utf-8")
    assert "Migration path" in contract
    assert "temporary Source of Record" in contract
    assert "mirror" in contract
