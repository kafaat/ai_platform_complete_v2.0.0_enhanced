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

import ast
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
        payload={},
        request_digest=digest,
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


# ── T6: كلّ نقطة idempotent تقارن البصمة (لا ناتج الأوّل لجسمٍ آخر) ──────────


def _valve_state(monkeypatch):
    """أمر حالة الصمّام بقاعدة وهميّة تُسجِّل كلّ تحديثٍ فعليّ (نظير نمط ``_irrigation``)."""
    from api.routers import irrigation as mod

    updates: list[str] = []
    store = _Store()

    class Conn:
        async def fetchrow(self, query, *vals):
            assert "UPDATE irrigation_valves" in query
            updates.append(vals[0])
            return {"valve_id": vals[1], "field_id": "field-a"}

    @asynccontextmanager
    async def fake_tenant_connection(user):
        yield Conn()

    async def noop(*a, **kw):
        return True

    monkeypatch.setattr(mod, "tenant_connection", fake_tenant_connection)
    monkeypatch.setattr(mod, "_emit_domain_event", noop)
    monkeypatch.setattr(mod, "_record_run_ledger", noop)
    monkeypatch.setattr(mod, "CommandStore", store)
    monkeypatch.setattr(mod, "get_pool", lambda: None)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app), updates


def test_valve_command_v2_with_v1_key_is_409_not_v1_result(monkeypatch):
    """T6 (مقيس في التدقيق): «إغلاق» بمفتاح «فتح» أعاد ناتج الفتح بـ200 ولم يُنفَّذ."""
    c, updates = _valve_state(monkeypatch)
    h = {"Idempotency-Key": _KEY}
    path = "/api/v1/irrigation/valves/vlv_a/state"
    first = c.post(path, json={"status": "open"}, headers=h)
    assert first.status_code == 200, first.text
    again = c.post(path, json={"status": "open"}, headers=h)
    assert again.status_code == 200 and again.json() == first.json()  # إعادة صادقة
    other = c.post(path, json={"status": "closed"}, headers=h)
    assert other.status_code == 409, other.text
    assert other.json()["detail"]["reason"] == "payload_mismatch"
    assert "open" not in other.text
    # المسار جزءٌ من البصمة: المفتاح نفسه على صمّامٍ آخر ليس إعادةً لأمر الأوّل.
    elsewhere = c.post("/api/v1/irrigation/valves/vlv_b/state", json={"status": "open"}, headers=h)
    assert elsewhere.status_code == 409, elsewhere.text
    assert updates == ["open"]


def test_every_idempotent_call_site_passes_a_request_digest():
    """حارس T6: لا موضع استدعاء بلا ``request_digest=`` (الغياب كان إعادةً عمياء)."""
    import ast
    from pathlib import Path

    api_root = Path(__file__).resolve().parents[1] / "api"
    sites, missing = 0, []
    for path in sorted(api_root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "_idempotent":
                continue
            sites += 1
            if not any(k.arg == "request_digest" for k in node.keywords):
                missing.append(f"{path.relative_to(api_root)}:{node.lineno}")
    assert sites >= 20, sites  # الحارس يرى المواضع فعلاً (لا نجاح فارغ)
    assert missing == [], missing


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
            if "pg_advisory_xact_lock" in query:
                assert "fields.geometry:" in query and vals == (_TENANT,)
                return "SELECT 1"
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


# ── مراجعة PR #1324: بصمة PATCH تُميّز «لم يُرسَل» عن «أُرسِل null» ─────────────
# ``_build_field_update`` يكتب الأعمدة الموجودة في ``model_fields_set`` فقط، فـ``{"name":"x"}``
# يُبقي ``soil_ph`` و``{"name":"x","soil_ph":null}`` يمسحه. ``model_dump()`` يُخرج الاثنين
# متطابقَين (الغائب None افتراضاً)، فكانت البصمة واحدة ⇒ إعادة المفتاح لجسمٍ يمسح العمود
# تُعيد ناتج الأوّل (200) ولا تمسح شيئاً، بدل 409 ``payload_mismatch``.

_FIELD_PATCH_OMITTED = {"name": "x"}
_FIELD_PATCH_CLEARED = {"name": "x", "soil_ph": None}


def _patch_digest(body, field_id="fld_1"):
    from api.field_models import FieldUpdateRequest
    from api.main import model_digest

    return model_digest(FieldUpdateRequest.model_validate(body), field_id)


def test_field_patch_bodies_with_different_effects_have_different_digests():
    from api.field_models import FieldUpdateRequest, _build_field_update

    omitted = FieldUpdateRequest.model_validate(_FIELD_PATCH_OMITTED)
    cleared = FieldUpdateRequest.model_validate(_FIELD_PATCH_CLEARED)
    # المقدّمة: الجسمان يكتبان أعمدةً مختلفة فعلاً.
    assert _build_field_update(omitted) == ("name = $1", ["x"])
    assert _build_field_update(cleared) == ("name = $1, soil_ph = $2", ["x", None])
    assert omitted.model_dump(mode="json") == cleared.model_dump(mode="json")
    assert _patch_digest(_FIELD_PATCH_OMITTED) != _patch_digest(_FIELD_PATCH_CLEARED)
    # ومسح عمودٍ آخر ليس مسح soil_ph.
    assert _patch_digest(_FIELD_PATCH_CLEARED) != _patch_digest({"name": "x", "crop": None})
    # ومعامل المسار يبقى في البصمة.
    assert _patch_digest(_FIELD_PATCH_CLEARED) != _patch_digest(_FIELD_PATCH_CLEARED, "fld_2")


@pytest.mark.parametrize(
    ("first", "second"),
    [(_FIELD_PATCH_OMITTED, _FIELD_PATCH_CLEARED), (_FIELD_PATCH_CLEARED, _FIELD_PATCH_OMITTED)],
    ids=["omitted-then-cleared", "cleared-then-omitted"],
)
async def test_field_patch_key_reuse_with_explicit_null_is_409_not_a_replay(first, second):
    store = _Store()
    ran: list[int] = []

    async def work():
        ran.append(1)
        return {"field_id": "fld_1"}

    result = await _call(store, work, command_type="field.update", digest=_patch_digest(first))
    replay = await _call(store, _never(), command_type="field.update", digest=_patch_digest(first))
    assert replay == result and ran == [1]  # الجسم نفسه ⇒ إعادة صادقة
    with pytest.raises(HTTPException) as exc:
        await _call(store, _never(), command_type="field.update", digest=_patch_digest(second))
    assert exc.value.status_code == 409
    assert exc.value.detail["reason"] == "payload_mismatch"
    assert ran == [1]


def test_presence_digest_keeps_stored_digests_of_unambiguous_bodies():
    """توافق البصمات المخزَّنة: جسمٌ بلا قيمةٍ افتراضيّة صريحة يبقى ببصمته السابقة."""
    from api.field_models import FieldUpdateRequest
    from api.idempotency import request_digest
    from api.routers.irrigation import ValveStateRequest

    body = {"name": "x", "soil_ph": 6.5, "geometry": _POLY}
    legacy = request_digest(
        {
            "scope": "fld_1",
            "request": FieldUpdateRequest.model_validate(body).model_dump(mode="json"),
        }
    )
    assert _patch_digest(body) == legacy
    # نموذجٌ بلا دلالة جزئيّة: البصمة لا تتغيّر حتّى مع قيمةٍ صريحة.
    from api.main import model_digest

    valve = ValveStateRequest.model_validate({"status": "open"})
    assert model_digest(valve, "vlv_a") == request_digest(
        {"scope": "vlv_a", "request": valve.model_dump(mode="json")}
    )


def _model_class_of(func, arg_name, module):
    for a in [*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs]:
        if a.arg == arg_name and isinstance(a.annotation, ast.Name):
            return getattr(module, a.annotation.id, None)
    return None


def _reads_presence(func, arg_name) -> bool:
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "model_fields_set"
            and isinstance(node.value, ast.Name)
            and node.value.id == arg_name
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "model_dump"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == arg_name
            and any(
                k.arg == "exclude_unset" and getattr(k.value, "value", False) is True
                for k in node.keywords
            )
        ):
            return True
    return False


def test_every_idempotent_handler_with_partial_semantics_digests_field_presence():
    """حارس: معالِجٌ يبصم ``req`` ويقرأ ``req.model_fields_set``/``exclude_unset`` ⇒ نموذجه
    يُعلن ``IDEMPOTENCY_DIGEST_PRESENCE`` (وإلّا عاد خلط «لم يُرسَل» بـ«أُرسِل null»)."""
    import importlib
    from pathlib import Path

    routers_root = Path(__file__).resolve().parents[1] / "api" / "routers"
    seen, missing = [], []
    for path in sorted(routers_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = None
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for call in ast.walk(func):
                if not (isinstance(call, ast.Call) and call.args):
                    continue
                name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
                if name != "model_digest" or not isinstance(call.args[0], ast.Name):
                    continue
                arg = call.args[0].id
                if not _reads_presence(func, arg):
                    continue
                module = module or importlib.import_module(f"api.routers.{path.stem}")
                cls = _model_class_of(func, arg, module)
                site = f"{path.name}:{func.name}"
                seen.append(site)
                if cls is None or not getattr(cls, "IDEMPOTENCY_DIGEST_PRESENCE", False):
                    missing.append(site)
    assert "fields.py:update_field" in seen, seen  # الحارس يرى PATCH الحقل فعلاً
    assert missing == [], missing
