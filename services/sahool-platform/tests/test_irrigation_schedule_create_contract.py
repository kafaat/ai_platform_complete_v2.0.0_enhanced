"""POST /api/v1/irrigation/schedules: ربط الحقل من الصمّام + Idempotency-Key.

UI-M1: نموذج الموبايل لا يرسل field_id والخادم كان يُدرج req.field_id كما هو، فجدولٌ
على صمّام الحقل A يُحفظ بلا حقل ولا يظهر في ``GET ?field_id=A``. الآن يُشتقّ الحقل من
الصمّام، ويُرفض تعارض الحقل المُرسَل مع حقل الصمّام، ويُتحقَّق أنّ الحقل يخصّ المستأجِر.

UI-M2: الموبايل يُعيد POST نفسه بمفتاح Idempotency-Key بعد ضياع الردّ، والنقطة كانت
تتجاهله: إعادةٌ بلا صمّام تُنشئ جدولاً ثانياً، وإعادةٌ على صمّام تصطدم بالجدول الأوّل
فتردّ 409 تعارضاً كاذباً رغم نجاح الحفظ. الإعادة الصادقة تُعيد الآن النتيجة الأولى،
والمفتاح نفسه بحمولة مختلفة ⇒ 409.
"""

from contextlib import asynccontextmanager
from datetime import time

import pytest
from api.main import get_current_user
from api.routers import irrigation as mod
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_KEY = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
_TENANT = "00000000-0000-0000-0000-000000000001"


def _user():
    return UserSchema(
        user_id="u1",
        tenant_id=_TENANT,
        role=UserRole.MANAGER,
        name_ar="مدير",
    )


def _harness(monkeypatch, *, valves=None, fields=("field-a", "field-b")):
    """قاعدة وهميّة: صمّامات المستأجِر {valve_id: field_id} + حقوله + جداول مُدرَجة."""
    valves = {"vlv_a": "field-a"} if valves is None else valves
    inserted: list[dict] = []
    events: list[tuple] = []
    commands: dict = {}

    class FakeConn:
        async def fetch(self, query, *vals):
            assert "FROM irrigation_schedules" in query
            return [
                {
                    "schedule_id": s["schedule_id"],
                    "start_time": s["start_time"],
                    "duration_min": s["duration_min"],
                    "days_of_week": s["days_of_week"],
                }
                for s in inserted
                if s["valve_id"] == vals[0] and s["enabled"]
            ]

        async def fetchrow(self, query, *vals):
            assert "FROM irrigation_valves" in query
            if vals[0] not in valves:
                return None
            return {"valve_id": vals[0], "field_id": valves[vals[0]]}

        async def fetchval(self, query, *vals):
            assert "FROM fields" in query
            return 1 if vals[0] in fields else None

        async def execute(self, query, *vals):
            assert "INSERT INTO irrigation_schedules" in query
            inserted.append(
                {
                    "schedule_id": vals[0],
                    "field_id": vals[2],
                    "valve_id": vals[3],
                    "start_time": vals[5],
                    "duration_min": vals[6],
                    "days_of_week": vals[7],
                    "enabled": vals[9],
                }
            )

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield FakeConn()

    async def emit(conn, user, event_type, aggregate_type, aggregate_id, payload, **kw):
        events.append((event_type, payload))

    class FakeCommandStore:
        def __init__(self, pool, conn=None):
            pass

        async def insert(self, cmd):
            if cmd.command_id in commands:
                return False
            commands[cmd.command_id] = cmd
            return True

        async def get(self, command_id):
            return commands.get(command_id)

        async def mark_succeeded(self, command_id, result):
            from api.command_store import CommandStatus

            commands[command_id].status = CommandStatus.SUCCEEDED
            commands[command_id].result = result

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", emit)
    monkeypatch.setattr(mod, "CommandStore", FakeCommandStore)
    monkeypatch.setattr(mod, "get_pool", lambda: None)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), inserted, events


_BODY = {"name": "ريّ الفجر", "start_time": "06:30", "duration_min": 30, "enabled": True}


# ── UI-M1: ربط الحقل ─────────────────────────────────────────────────


def test_schedule_on_a_field_valve_inherits_the_valve_field(monkeypatch):
    c, inserted, events = _harness(monkeypatch)
    resp = c.post("/api/v1/irrigation/schedules", json={**_BODY, "valve_id": "vlv_a"})
    assert resp.status_code == 201, resp.text
    assert inserted[0]["field_id"] == "field-a"
    assert events[0][1] == {"field_id": "field-a", "valve_id": "vlv_a"}


def test_field_that_contradicts_the_valve_field_is_rejected(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    resp = c.post(
        "/api/v1/irrigation/schedules",
        json={**_BODY, "valve_id": "vlv_a", "field_id": "field-b"},
    )
    assert resp.status_code == 422
    assert inserted == []


def test_matching_field_and_valve_are_accepted(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    resp = c.post(
        "/api/v1/irrigation/schedules",
        json={**_BODY, "valve_id": "vlv_a", "field_id": "field-a"},
    )
    assert resp.status_code == 201
    assert inserted[0]["field_id"] == "field-a"


def test_unknown_valve_is_404_not_an_unlinked_schedule(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    resp = c.post("/api/v1/irrigation/schedules", json={**_BODY, "valve_id": "vlv_missing"})
    assert resp.status_code == 404
    assert inserted == []


def test_field_outside_the_tenant_is_404(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    resp = c.post("/api/v1/irrigation/schedules", json={**_BODY, "field_id": "field-foreign"})
    assert resp.status_code == 404
    assert inserted == []


def test_unattached_valve_keeps_the_requested_field(monkeypatch):
    c, inserted, _ = _harness(monkeypatch, valves={"vlv_free": None})
    resp = c.post(
        "/api/v1/irrigation/schedules",
        json={**_BODY, "valve_id": "vlv_free", "field_id": "field-b"},
    )
    assert resp.status_code == 201
    assert inserted[0]["field_id"] == "field-b"


# ── UI-M2: Idempotency-Key ───────────────────────────────────────────


def test_replay_without_valve_does_not_create_a_second_schedule(monkeypatch):
    c, inserted, events = _harness(monkeypatch)
    h = {"Idempotency-Key": _KEY}
    first = c.post("/api/v1/irrigation/schedules", json=_BODY, headers=h)
    again = c.post("/api/v1/irrigation/schedules", json=_BODY, headers=h)
    assert first.status_code == 201 and again.status_code == 201
    assert again.json() == first.json()
    assert len(inserted) == 1
    assert len(events) == 1


def test_replay_on_a_valve_returns_the_first_result_not_a_false_conflict(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    h = {"Idempotency-Key": _KEY}
    body = {**_BODY, "valve_id": "vlv_a"}
    first = c.post("/api/v1/irrigation/schedules", json=body, headers=h)
    again = c.post("/api/v1/irrigation/schedules", json=body, headers=h)
    assert first.status_code == 201
    assert again.status_code == 201, again.text
    assert again.json()["schedule_id"] == first.json()["schedule_id"]
    assert len(inserted) == 1


def test_same_key_with_a_changed_payload_is_409(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    h = {"Idempotency-Key": _KEY}
    c.post("/api/v1/irrigation/schedules", json=_BODY, headers=h)
    resp = c.post("/api/v1/irrigation/schedules", json={**_BODY, "duration_min": 45}, headers=h)
    assert resp.status_code == 409
    assert len(inserted) == 1


def test_without_a_key_each_post_creates_a_schedule(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    c.post("/api/v1/irrigation/schedules", json=_BODY)
    c.post("/api/v1/irrigation/schedules", json=_BODY)
    assert len(inserted) == 2


def test_overlap_guard_still_rejects_a_genuinely_new_conflicting_schedule(monkeypatch):
    c, inserted, _ = _harness(monkeypatch)
    body = {**_BODY, "valve_id": "vlv_a"}
    assert c.post("/api/v1/irrigation/schedules", json=body).status_code == 201
    resp = c.post(
        "/api/v1/irrigation/schedules",
        json=body,
        headers={"Idempotency-Key": "7a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"},
    )
    assert resp.status_code == 409
    assert len(inserted) == 1
    assert inserted[0]["start_time"] == time(6, 30)
