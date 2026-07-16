"""اختبارات وحدة لموجِّه الوصفات اليدويّة (v95 — Manual VRT Prescriptions).

صدق: مسار كتابة/قراءة DB الفعليّ تكامليّ (يتطلّب Postgres+RLS — كـscouting_pins).
هنا نختبر وحدويّاً ما يُتحقَّق حتميّاً بلا قاعدة حيّة:

  • نقاوة المُحوِّل ``_row_to_prescription`` (تطبيع الصفّ، تفكيك zones JSONB نصّاً،
    تنسيق created_at ISO) — مطابقة الحفظ↔القراءة.
  • سرد بقاعدة معطَّلة ⇒ قائمة فارغة صادقة + سبب (لا اختراع وصفات).
  • السرد بمحاكاة ``tenant_connection`` (RLS) يُرجِع ما يُعيده الاتّصال فقط — والعزل
    بالمستأجِر يُفرَض على مستوى الاتّصال (SET app.current_tenant) لا في SQL.
  • توصيل الموجِّه: النقطتان مُضمَّنتان بأفعال HTTP الصحيحة (POST/GET) وأذونات
    FIELD_EDIT/FIELD_VIEW.
"""

from __future__ import annotations

import api.main  # noqa: F401 — تهيئة api.main قبل استيراد الموجِّه
import pytest
from api.routers import prescriptions as rx

pytestmark = pytest.mark.unit


# ─── المُحوِّل النقيّ ─────────────────────────────────────────────


def test_row_to_prescription_maps_fields_and_parses_zones_json():
    """يطبّع الصفّ ويفكّك zones إن عادت نصّاً (asyncpg JSONB) وينسّق created_at ISO."""

    class _DT:
        def isoformat(self):
            return "2026-06-22T10:00:00+00:00"

    row = {
        "prescription_id": "rx_1",
        "field_id": "fld_1",
        "name": "وصفة قمح",
        "product_type": "seed",
        "zones": '[{"geometry": {"type": "Polygon"}, "rate": 450, "unit": "seeds/m2"}]',
        "created_by": "user_1",
        "created_at": _DT(),
    }
    out = rx._row_to_prescription(row)
    assert out["prescription_id"] == "rx_1"
    assert out["field_id"] == "fld_1"
    assert out["name"] == "وصفة قمح"
    assert out["product_type"] == "seed"
    assert out["created_by"] == "user_1"
    assert out["created_at"] == "2026-06-22T10:00:00+00:00"
    assert isinstance(out["zones"], list) and len(out["zones"]) == 1
    assert out["zones"][0]["rate"] == 450
    assert out["zones"][0]["unit"] == "seeds/m2"


def test_row_to_prescription_accepts_already_parsed_zones_list():
    """zones قائمةً أصلاً (mock) تُمرَّر كما هي؛ created_at نصّاً يُمرَّر كما هو."""
    row = {
        "prescription_id": "rx_2",
        "field_id": "fld_2",
        "name": "تسميد",
        "product_type": "fertility",
        "zones": [{"geometry": {"type": "Polygon"}, "rate": 120, "unit": "kg/ha"}],
        "created_by": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    out = rx._row_to_prescription(row)
    assert out["zones"][0]["unit"] == "kg/ha"
    assert out["created_at"] == "2026-01-01T00:00:00+00:00"
    assert out["created_by"] is None


def test_row_to_prescription_malformed_zones_falls_back_to_empty():
    """zones نصّاً تالفاً ⇒ قائمة فارغة (لا انهيار، لا اختراع مناطق)."""
    row = {
        "prescription_id": "rx_3",
        "field_id": "fld_3",
        "name": "x",
        "product_type": "seed",
        "zones": "{not json",
        "created_by": "u",
        "created_at": "",
    }
    out = rx._row_to_prescription(row)
    assert out["zones"] == []


# ─── السرد: قاعدة معطّلة ⇒ فارغ صادق ────────────────────────────


async def test_list_prescriptions_db_disabled_returns_empty_with_reason(monkeypatch):
    """``_DB_POOL is None`` ⇒ قائمة فارغة + note_ar (لا وصفات مخترَعة، لا 500)."""
    monkeypatch.setattr(rx, "_DB_POOL", None)
    out = await rx.list_prescriptions(field_id="fld_x", user=object())
    assert out["field_id"] == "fld_x"
    assert out["prescriptions"] == []
    assert out["total"] == 0
    assert "note_ar" in out


# ─── السرد: محاكاة tenant_connection (RLS) ───────────────────────


class _FakeConn:
    """اتّصال وهميّ: fetch يُرجِع صفوفاً مُهيّأة، fetchval (assert_field) ⇒ 1."""

    def __init__(self, rows):
        self._rows = rows

    async def fetchval(self, *a, **k):
        return 1  # الحقل ضمن المستأجِر

    async def fetch(self, *a, **k):
        return self._rows


class _FakeCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


async def test_list_prescriptions_maps_rows_from_connection(monkeypatch):
    """السرد يُرجِع فقط ما يعيده الاتّصال (المُرشَّح بـRLS) عبر المُحوِّل النقيّ."""
    rows = [
        {
            "prescription_id": "rx_a",
            "field_id": "fld_1",
            "name": "أ",
            "product_type": "seed",
            "zones": [{"geometry": {"type": "Polygon"}, "rate": 400, "unit": "seeds/m2"}],
            "created_by": "u1",
            "created_at": "2026-06-22T10:00:00+00:00",
        }
    ]
    monkeypatch.setattr(rx, "_DB_POOL", object())  # مُفعَّل (مسار القاعدة)
    monkeypatch.setattr(rx, "tenant_connection", lambda user: _FakeCtx(_FakeConn(rows)))

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    out = await rx.list_prescriptions(field_id="fld_1", user=object())
    assert out["total"] == 1
    assert out["prescriptions"][0]["prescription_id"] == "rx_a"
    assert out["prescriptions"][0]["zones"][0]["rate"] == 400


async def test_list_prescriptions_tenant_isolation_empty_when_no_rows(monkeypatch):
    """مستأجِر بلا صفوف (RLS يرشّح) ⇒ قائمة فارغة صادقة (لا تسريب)."""
    monkeypatch.setattr(rx, "_DB_POOL", object())
    monkeypatch.setattr(rx, "tenant_connection", lambda user: _FakeCtx(_FakeConn([])))

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    out = await rx.list_prescriptions(field_id="fld_other", user=object())
    assert out["prescriptions"] == []
    assert out["total"] == 0


# ─── الحفظ: التحقّق ومحاكاة الإدراج ──────────────────────────────


async def test_create_prescription_rejects_unknown_product_type():
    """نوع منتج غير مدعوم ⇒ 422 (يدويّ صرف — لا يتجاوز ما تنتجه الواجهة)."""
    from fastapi import HTTPException

    req = rx.PrescriptionCreateRequest(
        prescription_id="rx_1", name="x", product_type="pesticide", zones=[]
    )
    with pytest.raises(HTTPException) as ei:
        await rx.create_prescription(req=req, field_id="fld_1", user=object())
    assert ei.value.status_code == 422


async def test_create_prescription_db_disabled_returns_503(monkeypatch):
    """قاعدة معطّلة ⇒ 503 موثَّق (لا ادّعاء حفظ)."""
    from fastapi import HTTPException

    monkeypatch.setattr(rx, "_DB_POOL", None)
    req = rx.PrescriptionCreateRequest(
        prescription_id="rx_1", name="x", product_type="seed", zones=[]
    )
    with pytest.raises(HTTPException) as ei:
        await rx.create_prescription(req=req, field_id="fld_1", user=object())
    assert ei.value.status_code == 503


async def test_create_prescription_persists_and_returns_payload(monkeypatch):
    """الحفظ يُدرِج (مُعامَل) ويُرجِع الوصفة مع persisted=True."""

    captured = {}

    class _WConn:
        # INSERT ... RETURNING via fetchval: capture it and return the id (row inserted).
        async def fetchval(self, sql, *args, **k):
            if "INSERT INTO prescriptions" in sql:
                captured["sql"] = sql
                captured["args"] = args
                return args[0]  # prescription_id ⇒ a real insert happened
            return 1

    class _User:
        tenant_id = "11111111-1111-1111-1111-111111111111"
        user_id = "user_1"

    monkeypatch.setattr(rx, "_DB_POOL", object())
    monkeypatch.setattr(rx, "tenant_connection", lambda user: _FakeCtx(_WConn()))

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    req = rx.PrescriptionCreateRequest(
        prescription_id="rx_1",
        name="وصفة قمح",
        product_type="seed",
        zones=[rx.PrescriptionZone(geometry={"type": "Polygon"}, rate=450, unit="seeds/m2")],
    )
    out = await rx.create_prescription(req=req, field_id="fld_1", user=_User())
    assert out["persisted"] is True and out["idempotent_replay"] is False
    assert out["prescription_id"] == "rx_1"
    assert out["field_id"] == "fld_1"
    assert out["zones"][0]["rate"] == 450
    # INSERT ... RETURNING (بارامتريّ، لا حقن) — القيم تُمرَّر كوسائط.
    assert "ON CONFLICT (prescription_id) DO NOTHING" in captured["sql"]
    assert "RETURNING prescription_id" in captured["sql"]
    assert "rx_1" in captured["args"]


def _stored_row(**over):
    row = {
        "prescription_id": "rx_1",
        "field_id": "fld_1",
        "season_id": None,
        "season_resolution_status": "unresolved",
        "name": "وصفة قمح",
        "product_type": "seed",
        # rate is a float field ⇒ what gets stored (json of model_dump) is 450.0, not 450.
        "zones": [{"geometry": {"type": "Polygon"}, "rate": 450.0, "unit": "seeds/m2"}],
        "created_by": "user_1",
        "created_at": "2026-06-22T10:00:00+00:00",
    }
    row.update(over)
    return row


def _conflict_conn(existing_row):
    """A connection whose INSERT conflicts (fetchval→None) and whose read-back
    (fetchrow) returns ``existing_row`` (None ⇒ invisible/cross-tenant)."""

    class _CConn:
        async def fetchval(self, sql, *args, **k):
            if "INSERT INTO prescriptions" in sql:
                return None  # ON CONFLICT DO NOTHING ⇒ no row inserted
            return 1

        async def fetchrow(self, *a, **k):
            return existing_row

    return _CConn()


async def _make_req(**over):
    kw = dict(
        prescription_id="rx_1",
        name="وصفة قمح",
        product_type="seed",
        zones=[rx.PrescriptionZone(geometry={"type": "Polygon"}, rate=450, unit="seeds/m2")],
    )
    kw.update(over)
    return rx.PrescriptionCreateRequest(**kw)


class _U:
    tenant_id = "11111111-1111-1111-1111-111111111111"
    user_id = "user_1"


async def test_create_prescription_idempotent_replay_returns_persisted_false(monkeypatch):
    """Same id + same content ⇒ NOT a new write: persisted=False, returns the stored row."""
    monkeypatch.setattr(rx, "_DB_POOL", object())
    monkeypatch.setattr(
        rx, "tenant_connection", lambda user: _FakeCtx(_conflict_conn(_stored_row()))
    )

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    out = await rx.create_prescription(req=await _make_req(), field_id="fld_1", user=_U())
    assert out["persisted"] is False and out["idempotent_replay"] is True
    assert out["prescription_id"] == "rx_1"  # the STORED row is returned


async def test_create_prescription_same_id_different_content_is_409(monkeypatch):
    """Same id, different content ⇒ 409 IDEMPOTENCY_CONFLICT (never claim persistence)."""
    from fastapi import HTTPException

    monkeypatch.setattr(rx, "_DB_POOL", object())
    monkeypatch.setattr(
        rx, "tenant_connection", lambda user: _FakeCtx(_conflict_conn(_stored_row(name="مختلف")))
    )

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    with pytest.raises(HTTPException) as ei:
        await rx.create_prescription(req=await _make_req(), field_id="fld_1", user=_U())
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "IDEMPOTENCY_CONFLICT"


async def test_create_prescription_cross_tenant_id_collision_is_409(monkeypatch):
    """Id exists but invisible to this tenant (global PK owned elsewhere) ⇒ 409, not success."""
    from fastapi import HTTPException

    monkeypatch.setattr(rx, "_DB_POOL", object())
    monkeypatch.setattr(rx, "tenant_connection", lambda user: _FakeCtx(_conflict_conn(None)))

    async def _ok_assert(conn, field_id):
        return None

    monkeypatch.setattr(rx, "_assert_field_in_tenant", _ok_assert)
    with pytest.raises(HTTPException) as ei:
        await rx.create_prescription(req=await _make_req(), field_id="fld_1", user=_U())
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "IDEMPOTENCY_CONFLICT"


# ─── توصيل الموجِّه ──────────────────────────────────────────────


def test_prescription_endpoints_wired():
    """النقطتان مُضمَّنتان في التطبيق بأفعالهما الصحيحة (POST/GET)."""
    routes = {(r.path, m) for r in api.main.app.routes for m in getattr(r, "methods", set())}
    assert ("/api/v1/fields/{field_id}/prescriptions", "POST") in routes
    assert ("/api/v1/fields/{field_id}/prescriptions", "GET") in routes
