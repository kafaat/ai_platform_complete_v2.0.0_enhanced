"""verify_execution_outcome must not record a verified success against a failed receipt.

A ``verified_success`` outcome is stored with ``success=True`` and later feeds learning
attribution and model evaluation, so it is only admissible when the actuator receipt itself
reported ``accepted``. These tests drive the persistence function against an in-memory fake
connection (no Postgres) and check both the refusal and that nothing is written.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001213"
RECEIPT = "rec_1"


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


# What a real actuator receipt must carry before it can back ``verified_success``.
REAL_ACKED = {"actuator_mode": "real", "published": True, "device_ack": True}


class _FakeConn:
    def __init__(
        self,
        *,
        request_status: str,
        receipt_status: str,
        attempt_status: str,
        target_type: str = "equipment",
        receipt_payload: object = REAL_ACKED,
    ):
        self.source = {
            "execution_request_id": "exec_1",
            "execution_plan_id": "plan_1",
            "dispatch_authorization_id": "auth_1",
            "decision_id": "dec_1",
            "status": request_status,
            "receipt_id": RECEIPT,
            "receipt_status": receipt_status,
            "attempt_receipt_id": RECEIPT,
            "attempt_receipt_status": attempt_status,
            "target_type": target_type,
            "receipt_payload": receipt_payload,
        }
        self.inserted: tuple | None = None
        self.outbox: list[tuple] = []

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        if "decision_outbox_events" in sql:
            self.outbox.append(args)

    async def fetchrow(self, sql, *args):
        if "FROM outcome_record WHERE tenant_id=$1::uuid AND idempotency_key" in sql:
            return None
        if "FROM decision_execution_requests r" in sql:
            return self.source
        if "INSERT INTO outcome_record" in sql:
            self.inserted = args
            return {
                "outcome_id": args[0],
                "execution_request_id": args[8],
                "execution_plan_id": args[10],
                "dispatch_authorization_id": args[9],
                "decision_id": args[2],
                "receipt_id": args[11],
                "verification_state": args[12],
                "evidence_snapshot_id": args[13],
                "success": args[5],
                "verified_by": args[6],
                "verified_at": "2026-10-26T00:00:00+00:00",
            }
        raise AssertionError(f"unexpected query: {sql}")

    async def close(self):
        return None


def _payload(state: str) -> SimpleNamespace:
    return SimpleNamespace(
        execution_plan_id="plan_1",
        dispatch_authorization_id="auth_1",
        decision_id="dec_1",
        receipt_id=RECEIPT,
        verification_state=state,
        evidence_snapshot_id="ev_1",
        actual={"completed": True},
        metrics={},
        idempotency_key="idem_1",
    )


def _verify(monkeypatch, conn: _FakeConn, state: str) -> dict:
    async def fake_connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", fake_connect)
    return asyncio.run(
        persistence.verify_execution_outcome(
            tenant_id=TENANT,
            execution_request_id="exec_1",
            verified_by="operator",
            payload=_payload(state),
        )
    )


def test_verified_success_on_failed_receipt_is_refused(monkeypatch):
    conn = _FakeConn(request_status="failed", receipt_status="failed", attempt_status="failed")
    result = _verify(monkeypatch, conn, "verified_success")
    assert result == {"status": "conflict", "reason": "receipt_not_accepted"}
    assert conn.inserted is None
    assert conn.outbox == []


def test_verified_success_refused_when_delivery_attempt_receipt_failed(monkeypatch):
    conn = _FakeConn(request_status="accepted", receipt_status="accepted", attempt_status="failed")
    result = _verify(monkeypatch, conn, "verified_success")
    assert result == {"status": "conflict", "reason": "receipt_not_accepted"}
    assert conn.inserted is None


def test_verified_success_on_accepted_receipt_is_recorded(monkeypatch):
    conn = _FakeConn(
        request_status="accepted", receipt_status="accepted", attempt_status="accepted"
    )
    result = _verify(monkeypatch, conn, "verified_success")
    assert result["status"] == "ok"
    assert result["success"] is True
    assert len(conn.outbox) == 1


def test_verified_failure_on_failed_receipt_is_still_recorded(monkeypatch):
    conn = _FakeConn(request_status="failed", receipt_status="failed", attempt_status="failed")
    result = _verify(monkeypatch, conn, "verified_failure")
    assert result["status"] == "ok"
    assert result["success"] is False


# ── An equipment "accepted" receipt is a broker publish, not ground truth ─────────────────
# The actuator bridge records ``actuator_mode`` and ``published`` and says outright that
# "published != physically executed". verified_success on such a receipt fed learning attribution
# with publishes — and, in simulation mode, with commands that never left the process.


@pytest.mark.parametrize(
    ("receipt_payload", "reason"),
    [
        (
            {"actuator_mode": "simulation", "published": True, "device_ack": True},
            "receipt_simulated",
        ),
        ({"actuator_mode": "real", "simulated": True, "device_ack": True}, "receipt_simulated"),
        ({"actuator_mode": "disabled", "published": False}, "receipt_not_real_actuator"),
        ({"published": True, "device_ack": True}, "receipt_not_real_actuator"),
        ({"actuator_mode": "real", "published": False}, "receipt_not_published"),
        ({"actuator_mode": "real", "published": True}, "receipt_lacks_device_ack"),
        (
            {"actuator_mode": "real", "published": True, "publish_only": True, "device_ack": True},
            "receipt_lacks_device_ack",
        ),
        ({}, "receipt_not_real_actuator"),
        (None, "receipt_lacks_actuator_evidence"),
    ],
)
def test_verified_success_needs_a_real_device_ack_on_equipment(
    monkeypatch, receipt_payload, reason
):
    conn = _FakeConn(
        request_status="accepted",
        receipt_status="accepted",
        attempt_status="accepted",
        receipt_payload=receipt_payload,
    )
    result = _verify(monkeypatch, conn, "verified_success")
    assert result == {"status": "conflict", "reason": reason}
    assert conn.inserted is None and conn.outbox == []


def test_receipt_payload_stored_as_json_text_is_read(monkeypatch):
    """A receipt payload that arrives as JSON text must be parsed, not read as empty."""
    conn = _FakeConn(
        request_status="accepted",
        receipt_status="accepted",
        attempt_status="accepted",
        receipt_payload='{"actuator_mode": "real", "published": true, "device_ack": true}',
    )
    assert _verify(monkeypatch, conn, "verified_success")["status"] == "ok"


def test_verified_failure_on_a_simulated_receipt_is_still_recorded(monkeypatch):
    conn = _FakeConn(
        request_status="accepted",
        receipt_status="accepted",
        attempt_status="accepted",
        receipt_payload={"actuator_mode": "simulation", "published": True},
    )
    result = _verify(monkeypatch, conn, "verified_failure")
    assert result["status"] == "ok" and result["success"] is False


def test_task_receipts_keep_the_existing_contract(monkeypatch):
    """A human/task-provider receipt has no actuator mode; it is not held to the device rule."""
    conn = _FakeConn(
        request_status="accepted",
        receipt_status="accepted",
        attempt_status="accepted",
        target_type="task",
        receipt_payload={"provider_task_id": "t-1"},
    )
    assert _verify(monkeypatch, conn, "verified_success")["status"] == "ok"
