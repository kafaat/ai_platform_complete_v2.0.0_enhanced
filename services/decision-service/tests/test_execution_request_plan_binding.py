"""Execution requests are bound to the approved plan, and stale work does not fire.

P0 review of the actuation chain (main 8216ef41d):

* ``create_execution_request`` checked only ids and states, then stored the caller's
  ``target_type``/``target_id``/``operation_type``/``command_payload`` — an approved plan for one
  operation, target and quantity could authorize any other.
* ``authorize_dispatch`` and ``claim_execution_request`` ignored the plan's ``planned_end``, and a
  queued request could be claimed at any age (a kill-switch released hours later fired it).

The tests drive the persistence functions against an in-memory fake connection (no Postgres) and
assert both the refusal reason and that nothing was written.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

import persistence  # noqa: E402

pytestmark = pytest.mark.unit

TENANT = "00000000-0000-0000-0000-000000001214"
NOW = datetime.now(UTC)


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _plan(**overrides):
    plan = {
        "dispatch_authorization_id": "auth_1",
        "execution_plan_id": "plan_1",
        "decision_id": "dec_1",
        "status": "authorized",
        "plan_state": "planned",
        "review_state": "approved",
        "plan_operation_type": "irrigation",
        "target_zone_ids": [],
        "required_resources": [{"target_id": "valve-7"}],
        "constraints": {"max_irrigation_mm": 12.0},
        "planned_start": NOW - timedelta(minutes=5),
        "planned_end": NOW + timedelta(hours=2),
    }
    plan.update(overrides)
    return plan


def _request(**overrides):
    request = SimpleNamespace(
        execution_plan_id="plan_1",
        decision_id="dec_1",
        target_type="equipment",
        target_id="valve-7",
        operation_type="irrigation",
        command_payload={
            "device_id": "valve-7",
            "command": "irrigate",
            "payload": {"field_id": "f1", "amount_mm": 10.0, "duration_sec": 600},
        },
        idempotency_key="idem_1",
    )
    for key, value in overrides.items():
        setattr(request, key, value)
    return request


class _CreateConn:
    def __init__(self, plan):
        self.plan = plan
        self.inserted: tuple | None = None
        self.outbox: list[tuple] = []

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        if "decision_outbox_events" in sql:
            self.outbox.append(args)

    async def fetchrow(self, sql, *args):
        if "FROM decision_execution_requests WHERE tenant_id=$1::uuid AND idempotency_key" in sql:
            return None
        if "FROM decision_dispatch_authorizations a" in sql:
            return self.plan
        if "INSERT INTO decision_execution_requests" in sql:
            self.inserted = args
            return {
                "execution_request_id": args[0],
                "dispatch_authorization_id": args[2],
                "execution_plan_id": args[3],
                "decision_id": args[4],
                "target_type": args[5],
                "target_id": args[6],
                "operation_type": args[7],
                "status": "queued",
                "requested_by": args[11],
                "requested_at": NOW,
            }
        raise AssertionError(f"unexpected query: {sql}")

    async def close(self):
        return None


def _create(monkeypatch, plan, request) -> tuple[dict, _CreateConn]:
    conn = _CreateConn(plan)

    async def fake_connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", fake_connect)
    result = asyncio.run(
        persistence.create_execution_request(
            tenant_id=TENANT,
            dispatch_authorization_id="auth_1",
            requested_by="operator",
            payload=request,
        )
    )
    return result, conn


def test_request_covered_by_the_plan_is_queued(monkeypatch):
    result, conn = _create(monkeypatch, _plan(), _request())
    assert result["status"] == "ok" and result["execution_state"] == "queued"
    assert conn.inserted is not None and len(conn.outbox) == 1


@pytest.mark.parametrize(
    ("plan", "request_overrides", "reason"),
    [
        (_plan(), {"operation_type": "fertigation"}, "operation_type_mismatch"),
        (
            _plan(),
            {
                "target_id": "valve-9",
                "command_payload": {"device_id": "valve-9", "command": "open", "payload": {}},
            },
            "target_mismatch",
        ),
        (
            _plan(),
            {"command_payload": {"device_id": "valve-9", "command": "close", "payload": {}}},
            "command_target_mismatch",
        ),
        (
            _plan(required_resources=[], target_zone_ids=[]),
            {},
            "plan_target_unbound",
        ),
        (
            _plan(required_resources=[], target_zone_ids=["z1"]),
            {},
            "target_zone_mismatch",
        ),
        (
            _plan(),
            {
                "command_payload": {
                    "device_id": "valve-7",
                    "command": "irrigate",
                    "payload": {"field_id": "f1", "amount_mm": 30.0, "duration_sec": 600},
                }
            },
            "quantity_exceeds_plan",
        ),
        (
            _plan(constraints={"max_duration_minutes": 5}),
            {},
            "duration_exceeds_plan",
        ),
        (
            _plan(constraints={}, planned_end=NOW + timedelta(minutes=2)),
            {},
            "duration_exceeds_plan_window",
        ),
        (
            _plan(),
            {
                "command_payload": {
                    "device_id": "valve-7",
                    "command": "irrigate",
                    "payload": {"field_id": "f1", "amount_mm": "lots", "duration_sec": 600},
                }
            },
            "invalid_command_quantity",
        ),
        (_plan(planned_end=NOW - timedelta(seconds=1)), {}, "plan_expired"),
    ],
)
def test_request_outside_the_plan_is_refused_and_not_written(
    monkeypatch, plan, request_overrides, reason
):
    result, conn = _create(monkeypatch, plan, _request(**request_overrides))
    assert result == {"status": "conflict", "reason": reason}
    assert conn.inserted is None and conn.outbox == []


def test_a_permitted_value_in_one_layer_does_not_mask_another(monkeypatch):
    """The adapter reads the nested payload; an allowed top-level zone must not hide it."""
    plan = _plan(target_zone_ids=["f1"])
    request = _request(
        command_payload={
            "device_id": "valve-7",
            "command": "irrigate",
            "field_id": "f1",
            "payload": {"field_id": "f2", "amount_mm": 5.0, "duration_sec": 60},
        }
    )
    result, conn = _create(monkeypatch, plan, request)
    assert result == {"status": "conflict", "reason": "target_zone_mismatch"}
    assert conn.inserted is None


def test_task_request_on_a_plan_without_targets_is_still_allowed(monkeypatch):
    """Human tasks carry no device; the equipment-only target rule must not break them."""
    plan = _plan(required_resources=[], constraints={}, planned_end=None)
    request = _request(
        target_type="task", target_id="task-provider", command_payload={"minutes": 20}
    )
    result, _ = _create(monkeypatch, plan, request)
    assert result["status"] == "ok"


# ── authorize_dispatch: an expired plan cannot be authorized ──────────────────────────────


class _AuthorizeConn:
    def __init__(self, planned_end):
        self.source = {
            "execution_plan_id": "plan_1",
            "decision_id": "dec_1",
            "review_id": "rev_1",
            "candidate_lineage_id": "lin_1",
            "plan_state": "planned",
            "planned_end": planned_end,
            "review_state": "approved",
            "new_state": "approved",
        }
        self.inserted = False

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        return None

    async def fetchrow(self, sql, *args):
        if "FROM decision_dispatch_authorizations" in sql and "idempotency_key=$2" in sql:
            return None
        if "FROM decision_execution_plans p" in sql:
            return self.source
        if "INSERT INTO decision_dispatch_authorizations" in sql:
            self.inserted = True
            return None
        raise AssertionError(f"unexpected query: {sql}")

    async def close(self):
        return None


def test_authorize_dispatch_refuses_an_expired_plan(monkeypatch):
    conn = _AuthorizeConn(NOW - timedelta(minutes=1))

    async def fake_connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", fake_connect)
    result = asyncio.run(
        persistence.authorize_dispatch(
            tenant_id=TENANT,
            execution_plan_id="plan_1",
            decision_id="dec_1",
            review_id="rev_1",
            candidate_lineage_id="lin_1",
            idempotency_key="idem_a",
            authorized_by="operator",
            payload=SimpleNamespace(
                expected_plan_state="planned",
                policy_version="p1",
                weather_snapshot_id="w1",
                resource_snapshot_id="r1",
                authorization_reason="ok",
            ),
        )
    )
    assert result == {"status": "conflict", "reason": "plan_expired"}
    assert conn.inserted is False


# ── claim_execution_request: stale queued work does not fire on release ───────────────────


class _ClaimConn:
    def __init__(self, *, requested_at, planned_end, plan_exists=True):
        self.request = {
            "execution_request_id": "exec_1",
            "execution_plan_id": "plan_1",
            "status": "queued",
            "target_type": "equipment",
            "requested_at": requested_at,
        }
        self.plan = {"planned_end": planned_end} if plan_exists else None
        self.claimed = False
        self.updated = False

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        if "UPDATE decision_execution_requests" in sql:
            self.updated = True

    async def fetchrow(self, sql, *args):
        if "FROM decision_execution_delivery_attempts" in sql:
            return None
        if "FROM decision_execution_requests" in sql:
            return self.request
        if "FROM decision_execution_plans" in sql:
            return self.plan
        if "INSERT INTO decision_execution_delivery_attempts" in sql:
            self.claimed = True
            return {
                "delivery_attempt_id": args[0],
                "execution_request_id": args[2],
                "adapter_id": args[3],
                "adapter_kind": args[4],
                "claimed_at": NOW,
            }
        raise AssertionError(f"unexpected query: {sql}")

    async def close(self):
        return None


def _claim(monkeypatch, conn) -> dict:
    async def fake_connect():
        return conn

    monkeypatch.setattr(persistence, "_connect", fake_connect)
    return asyncio.run(
        persistence.claim_execution_request(
            tenant_id=TENANT,
            execution_request_id="exec_1",
            adapter_id="actuator-service",
            adapter_kind="equipment",
            delivery_token="tok",
        )
    )


def test_fresh_request_on_a_live_plan_is_claimed(monkeypatch):
    conn = _ClaimConn(requested_at=NOW - timedelta(minutes=1), planned_end=NOW + timedelta(hours=1))
    result = _claim(monkeypatch, conn)
    assert result["status"] == "ok" and conn.claimed and conn.updated


def test_request_older_than_the_max_age_is_not_claimed(monkeypatch):
    monkeypatch.setenv("DECISION_EXECUTION_REQUEST_MAX_AGE_S", "600")
    conn = _ClaimConn(requested_at=NOW - timedelta(minutes=11), planned_end=None)
    result = _claim(monkeypatch, conn)
    assert result == {"status": "conflict", "reason": "execution_request_expired"}
    assert not conn.claimed and not conn.updated


def test_default_max_age_is_one_hour(monkeypatch):
    monkeypatch.delenv("DECISION_EXECUTION_REQUEST_MAX_AGE_S", raising=False)
    conn = _ClaimConn(requested_at=NOW - timedelta(hours=1, minutes=1), planned_end=None)
    assert _claim(monkeypatch, conn)["reason"] == "execution_request_expired"


@pytest.mark.parametrize("bad", ["", "abc", "0", "-5", "nan", "inf"])
def test_unusable_max_age_falls_back_to_the_default(monkeypatch, bad):
    monkeypatch.setenv("DECISION_EXECUTION_REQUEST_MAX_AGE_S", bad)
    assert (
        persistence._execution_request_max_age_s()
        == persistence.EXECUTION_REQUEST_MAX_AGE_DEFAULT_S
    )


def test_request_on_an_expired_plan_is_not_claimed(monkeypatch):
    conn = _ClaimConn(
        requested_at=NOW - timedelta(minutes=1), planned_end=NOW - timedelta(seconds=1)
    )
    assert _claim(monkeypatch, conn) == {"status": "conflict", "reason": "plan_expired"}
    assert not conn.claimed and not conn.updated


def test_request_whose_plan_is_missing_is_not_claimed(monkeypatch):
    conn = _ClaimConn(requested_at=NOW, planned_end=None, plan_exists=False)
    assert _claim(monkeypatch, conn) == {"status": "conflict", "reason": "execution_plan_not_found"}
    assert not conn.claimed


def test_unreadable_plan_end_fails_closed():
    assert persistence._plan_expired("not-a-time", NOW) is True
    assert persistence._plan_expired(None, NOW) is False
