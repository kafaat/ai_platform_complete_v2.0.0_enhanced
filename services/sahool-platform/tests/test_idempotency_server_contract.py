"""عقد الخادم لـIdempotency-Key (D4) وربط حقل جدول الريّ (D5) — مستوى الوحدة.

D4: المفتاح مربوطٌ بالمستأجر **ونوع العمليّة**؛ البصمة من تمثيلٍ موحَّد للحمولة المؤثّرة
(ترتيب مفاتيح JSON وصيغة الوقت لا يصنعان تعارضاً)؛ 409 يحمل ``detail.reason`` ثابتاً
(``payload_mismatch`` / ``in_progress`` / ``retention_expired``) ونصّاً لا يدفع إلى إنشاءٍ
بمفتاحٍ جديد (OD-2)؛ وإنشاء الحقل والموسم يقارنان البصمة كما يقارنها جدول الريّ.

D5: صمّام مستأجرٍ آخر (حتى تحت دورٍ يتجاوز RLS) يُردّ 404 نفسه لصمّامٍ غائب؛ ولا صمّام
ولا حقل ⇒ 201 «جدول غير مرتبط بحقل» (OD-1: الحقل لا يُفرَض).

الأدلّة الحيّة على PostgreSQL (التزامن، الارتداد، مدّة الاحتفاظ، R14/R15) في
``tests_v9/test_d4d5_idempotency_irrigation_live_pg.py``.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from api.main import get_current_user
from core.canonical_schemas import UserRole, UserSchema
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_KEY = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"
_TENANT = "00000000-0000-0000-0000-000000000001"
_OTHER = "00000000-0000-0000-0000-000000000002"
_OD2_TEXT = (
    "هذه العملية أُرسلت سابقاً بنفس المعرّف. استعِد نتيجة المحاولة السابقة أولاً، ولا تُنشئ سجلاً جديداً."
)


def _user():
    return UserSchema(user_id="u1", tenant_id=_TENANT, role=UserRole.MANAGER, name_ar="مدير")


class _Store:
    """نظير CommandStore في الذاكرة (مشترك بين الطلبات كجدول commands)."""

    def __init__(self):
        self.rows: dict = {}

    def __call__(self, pool, conn=None):  # يُحقَن مكان الصنف: CommandStore(get_pool(), conn=…)
        return self

    async def insert(self, cmd) -> bool:
        if cmd.command_id in self.rows:
            return False
        self.rows[cmd.command_id] = cmd
        return True

    async def get(self, command_id):
        return self.rows.get(command_id)

    async def mark_succeeded(self, command_id, result):
        from api.command_store import CommandStatus

        self.rows[command_id].status = CommandStatus.SUCCEEDED
        self.rows[command_id].result = result


def _stored(store, *, command_type, tenant=_TENANT, payload=None, result=None, age=None):
    from api.command_store import Command, CommandStatus

    row = Command.new(command_type, "u1", tenant, payload or {}, command_id=_KEY)
    row.status = CommandStatus.SUCCEEDED
    row.result = result if result is not None else {"id": "first"}
    if age is not None:
        row.created_at = datetime.now(UTC) - age
    store.rows[_KEY] = row
    return row


async def _call(store, work, *, command_type="field.create", tenant=_TENANT, digest="d" * 64):
    from api.main import _idempotent

    return await _idempotent(
        store,
        _KEY,
        work,
        command_type=command_type,
        actor_id="u1",
        tenant_id=tenant,
        payload={"request_digest": digest},
    )


def _never():
    async def work():
        raise AssertionError("نُفِّذ العمل لمفتاحٍ مستعمَل")

    return work


# ── D4: _idempotent ─────────────────────────────────────────────────────


async def test_payload_mismatch_carries_a_stable_reason_and_the_od2_message():
    store = _Store()
    _stored(store, command_type="field.create", payload={"request_digest": "a" * 64})
    with pytest.raises(HTTPException) as e:
        await _call(store, _never(), digest="b" * 64)
    assert e.value.status_code == 409
    assert e.value.detail["reason"] == "payload_mismatch"
    assert e.value.detail["message_ar"] == _OD2_TEXT
    assert "مفتاحاً جديداً" not in str(e.value.detail)  # OD-2: لا دفع إلى مفتاحٍ جديد


async def test_in_progress_carries_its_own_reason():
    from api.command_store import CommandStatus

    store = _Store()
    row = _stored(store, command_type="field.create", payload={"request_digest": "d" * 64})
    row.status = CommandStatus.PROCESSING
    with pytest.raises(HTTPException) as e:
        await _call(store, _never())
    assert e.value.status_code == 409
    assert e.value.detail["reason"] == "in_progress"
    assert "قيد المعالجة" in e.value.detail["message_ar"]


async def test_a_key_is_bound_to_its_operation_type():
    """مفتاح «إنشاء حقل» بالبصمة نفسها لا يُعيد ناتجه لـ«إنشاء موسم» ولا ينفّذ العمل."""
    store = _Store()
    _stored(
        store,
        command_type="field.create",
        payload={"request_digest": "d" * 64},
        result={"field_id": "fld_secret"},
    )
    with pytest.raises(HTTPException) as e:
        await _call(store, _never(), command_type="season.create")
    assert e.value.status_code == 409
    assert e.value.detail["reason"] == "payload_mismatch"
    assert "fld_secret" not in str(e.value.detail)


async def test_a_foreign_tenant_reads_exactly_like_a_payload_mismatch():
    store = _Store()
    _stored(store, command_type="field.create", payload={"request_digest": "d" * 64})
    with pytest.raises(HTTPException) as foreign:
        await _call(store, _never(), tenant=_OTHER)
    with pytest.raises(HTTPException) as mismatch:
        await _call(store, _never(), digest="e" * 64)
    assert foreign.value.detail == mismatch.value.detail


async def test_replay_inside_the_retention_window_returns_the_stored_result():
    store = _Store()
    _stored(
        store,
        command_type="field.create",
        payload={"request_digest": "d" * 64},
        result={"field_id": "fld_1"},
        age=timedelta(days=29),
    )
    assert await _call(store, _never()) == {"field_id": "fld_1"}


async def test_replay_after_the_retention_window_reconciles_and_never_reexecutes(monkeypatch):
    """R13 (الخادم): بعد المدّة لا ناتج قديم ولا تنفيذ ثانٍ — 409 retention_expired."""
    monkeypatch.delenv("SAHOOL_IDEMPOTENCY_RETENTION_DAYS", raising=False)
    store = _Store()
    _stored(
        store,
        command_type="field.create",
        payload={"request_digest": "d" * 64},
        result={"field_id": "fld_1"},
        age=timedelta(days=31),
    )
    with pytest.raises(HTTPException) as e:
        await _call(store, _never())
    assert e.value.status_code == 409
    assert e.value.detail["reason"] == "retention_expired"
    assert e.value.detail["retention_days"] == 30
    assert "fld_1" not in str(e.value.detail)
    # المدّة قابلة للضبط وموثّقة في العقد نفسه.
    monkeypatch.setenv("SAHOOL_IDEMPOTENCY_RETENTION_DAYS", "45")
    assert await _call(store, _never()) == {"field_id": "fld_1"}


def test_request_digest_ignores_json_key_order():
    from api.idempotency import request_digest

    a = {"name": "x", "geometry": {"type": "Polygon", "coordinates": [[[1, 2]]]}}
    b = {"geometry": {"coordinates": [[[1, 2]]], "type": "Polygon"}, "name": "x"}
    assert request_digest(a) == request_digest(b)
    assert request_digest(a) != request_digest({**a, "name": "y"})


# ── D4 + D5: جدول الريّ ─────────────────────────────────────────────────


def _irrigation(monkeypatch, *, valves=None, fields=None):
    """قاعدة وهميّة تحترم شرط المستأجر إن مرّره الاستعلام، وإلّا تتصرّف كدورٍ يتجاوز RLS."""
    from api.routers import irrigation as mod

    valves = {"vlv_a": ("field-a", _TENANT)} if valves is None else valves
    fields = {"field-a": _TENANT, "field-b": _TENANT} if fields is None else fields
    inserted: list[dict] = []
    store = _Store()

    def _visible(owner, query, vals):
        return "tenant_id" not in query or str(vals[1]) == owner

    class Conn:
        async def fetch(self, query, *vals):
            return []

        async def fetchrow(self, query, *vals):
            assert "FROM irrigation_valves" in query
            hit = valves.get(vals[0])
            if hit is None or not _visible(hit[1], query, vals):
                return None
            return {"valve_id": vals[0], "field_id": hit[0]}

        async def fetchval(self, query, *vals):
            assert "FROM fields" in query
            owner = fields.get(vals[0])
            return 1 if owner is not None and _visible(owner, query, vals) else None

        async def execute(self, query, *vals):
            assert "INSERT INTO irrigation_schedules" in query
            inserted.append({"schedule_id": vals[0], "field_id": vals[2], "valve_id": vals[3]})

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield Conn()

    async def emit(*a, **kw):
        return True

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", emit)
    monkeypatch.setattr(mod, "CommandStore", store)
    monkeypatch.setattr(mod, "get_pool", lambda: None)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), inserted, store


_SCHED = "/api/v1/irrigation/schedules"
_BODY = {"name": "ريّ الفجر", "start_time": "06:30", "duration_min": 30, "enabled": True}


def test_irrigation_replay_with_reordered_keys_and_seconds_is_the_same_operation(monkeypatch):
    """«06:30» و«06:30:00» بترتيب مفاتيح آخر = الحمولة المؤثّرة نفسها ⇒ الناتج الأوّل لا 409."""
    c, inserted, _ = _irrigation(monkeypatch)
    h = {"Idempotency-Key": _KEY, "Content-Type": "application/json"}
    first = c.post(_SCHED, json=_BODY, headers=h)
    again = c.post(
        _SCHED,
        content='{"enabled": true, "duration_min": 30, "start_time": "06:30:00", "name": "ريّ الفجر"}'.encode(),
        headers=h,
    )
    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json() == first.json()
    assert len(inserted) == 1


def test_irrigation_changed_payload_is_409_payload_mismatch(monkeypatch):
    c, inserted, _ = _irrigation(monkeypatch)
    h = {"Idempotency-Key": _KEY}
    c.post(_SCHED, json=_BODY, headers=h)
    resp = c.post(_SCHED, json={**_BODY, "duration_min": 45}, headers=h)
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason"] == "payload_mismatch"
    assert resp.json()["detail"]["message_ar"] == _OD2_TEXT
    assert len(inserted) == 1


def test_foreign_tenant_valve_is_the_same_404_as_a_missing_valve(monkeypatch):
    """R14: تحت دورٍ يتجاوز RLS كان صمّام مستأجرٍ آخر يُقبَل ويُشتقّ منه حقله."""
    c, inserted, _ = _irrigation(
        monkeypatch,
        valves={"vlv_foreign": ("field-x", _OTHER)},
        fields={"field-x": _OTHER},
    )
    foreign = c.post(_SCHED, json={**_BODY, "valve_id": "vlv_foreign"})
    missing = c.post(_SCHED, json={**_BODY, "valve_id": "vlv_none"})
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert "field-x" not in foreign.text
    assert inserted == []


def test_foreign_tenant_field_is_the_same_404_as_a_missing_field(monkeypatch):
    c, inserted, _ = _irrigation(monkeypatch, fields={"field-x": _OTHER})
    foreign = c.post(_SCHED, json={**_BODY, "field_id": "field-x"})
    missing = c.post(_SCHED, json={**_BODY, "field_id": "field-none"})
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()
    assert inserted == []


def test_neither_valve_nor_field_is_created_unlinked(monkeypatch):
    """OD-1: الحقل اختياريّ — بلا صمّام ولا حقل ⇒ 201 وجدول غير مرتبط بحقل."""
    c, inserted, _ = _irrigation(monkeypatch)
    resp = c.post(_SCHED, json=_BODY, headers={"Idempotency-Key": _KEY})
    assert resp.status_code == 201, resp.text
    assert inserted == [
        {"schedule_id": resp.json()["schedule_id"], "field_id": None, "valve_id": None}
    ]


# ── D4: إنشاء الحقل والموسم يقارنان البصمة ──────────────────────────────

_POLY = {
    "type": "Polygon",
    "coordinates": [
        [[45.550, 15.050], [45.552, 15.050], [45.552, 15.052], [45.550, 15.052], [45.550, 15.050]]
    ],
}


def _fields_router(monkeypatch):
    from api.routers import fields as mod

    store = _Store()
    created: list[dict] = []

    class Conn:
        async def fetchrow(self, query, *vals):
            return None  # لا اسم مكرّر

        async def fetch(self, query, *vals):
            return []  # لا تداخل ولا موسم نشط سابق

        async def fetchval(self, query, *vals):
            return 1  # الحقل يخصّ المستأجر

        async def execute(self, query, *vals):
            assert "INSERT INTO seasons" in query
            created.append({"season_id": vals[0], "crops": vals[3]})

        def transaction(self):
            @asynccontextmanager
            async def tx():
                yield None

            return tx()

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield Conn()

    async def insert_field(conn, user, *, field_id, name, geometry, area_ha, lat, lon, **kw):
        created.append({"field_id": field_id, "name": name})
        return {
            "field_id": field_id,
            "farm_id": "",
            "name_ar": name,
            "crop": "",
            "area_ha": area_ha,
            "quality_grade": "PENDING_LAB",
            "health_summary_ar": "—",
            "geometry": geometry,
        }

    async def emit(*a, **kw):
        return True

    async def recompute(conn, field_id):
        return {"changed": False}

    import api.field_state_projection as projection

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "CommandStore", store)
    monkeypatch.setattr(mod, "get_pool", lambda: None)
    monkeypatch.setattr(mod, "_insert_field_within_tx", insert_field)
    monkeypatch.setattr(mod, "_emit_domain_event", emit)
    monkeypatch.setattr(mod, "_kick_imagery_processing", lambda **kw: None)
    monkeypatch.setattr(projection, "recompute_field_state", recompute)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), created


def test_field_create_same_key_with_another_field_is_409_not_the_first_field(monkeypatch):
    c, created = _fields_router(monkeypatch)
    body = {"name": "حقل الوادي", "geometry": _POLY, "country": "اليمن", "region": "البيضاء"}
    h = {"Idempotency-Key": _KEY}
    first = c.post("/api/v1/fields", json=body, headers=h)
    assert first.status_code == 201, first.text
    again = c.post("/api/v1/fields", json=body, headers=h)
    assert again.status_code == 201 and again.json()["field_id"] == first.json()["field_id"]
    other = c.post("/api/v1/fields", json={**body, "name": "حقل آخر"}, headers=h)
    assert other.status_code == 409, other.text
    assert other.json()["detail"]["reason"] == "payload_mismatch"
    assert len(created) == 1


def test_season_create_same_key_with_another_season_is_409(monkeypatch):
    c, created = _fields_router(monkeypatch)
    path = "/api/v1/fields/fld_1/seasons"
    h = {"Idempotency-Key": _KEY}
    first = c.post(path, json={"crops": ["قمح"]}, headers=h)
    assert first.status_code == 201, first.text
    again = c.post(path, json={"crops": ["قمح"]}, headers=h)
    assert again.status_code == 201 and again.json()["season_id"] == first.json()["season_id"]
    other = c.post(path, json={"crops": ["شعير"]}, headers=h)
    assert other.status_code == 409, other.text
    assert other.json()["detail"]["reason"] == "payload_mismatch"
    # الموسم نفسه على حقلٍ آخر بالمفتاح نفسه: الحقل جزء من الحمولة المؤثّرة.
    elsewhere = c.post("/api/v1/fields/fld_2/seasons", json={"crops": ["قمح"]}, headers=h)
    assert elsewhere.status_code == 409
    assert len(created) == 1
