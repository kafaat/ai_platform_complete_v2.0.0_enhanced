"""اختبارات وحدة (unit): دبابيس الاستطلاع الدائمة — منطق القراءة + الإدامة.

تثبت بلا قاعدة حيّة (conn مزيّف + tenant_connection مُرقَّع) أنّ:

  • نقطة القراءة ``GET /api/v1/scouting/pins`` تُرشِّح بـfield_id وتُرتِّب الأحدث
    أوّلاً، وتُحوّل الصفوف إلى dict مطابق لـ ScoutingPin.to_dict (مفتاح pin_id).
  • SQL القراءة بارامتريّ (لا حقن): يحوي ``WHERE field_id = $1`` و``ORDER BY
    created_at DESC`` ويختار من ``scouting_pins``.
  • ``_row_to_pin`` نقيّ: يُنسّق ``created_at`` ISO ويُمرّر كلّ الحقول.
  • القاعدة غير مفعّلة (``_DB_POOL is None``) ⇒ قائمة فارغة صريحة مع سبب
    (لا اختراع مشاهدات).
  • إدامة POST (``_persist_scouting_pin``) best-effort: تعذّر القاعدة ⇒ ``False``
    (لا استثناء يصعد، يبقى المسار offline-first سليماً)؛ ونجاحها يُمرّر SQL
    بارامتريّاً إلى جدول ``scouting_pins`` مع ``ON CONFLICT (pin_id) DO NOTHING``.

نواة بلا خدمات (لا Postgres). تُعلَّم unit.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import uuid

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)

pytest.importorskip("fastapi")


class _FakeUser:
    def __init__(self):
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.role = "manager"


class _FakeConn:
    """conn مزيّف: يلتقط آخر استعلام fetch/execute ويُرجِع صفوفاً مُعدّة."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self.fetch_sql: str | None = None
        self.fetch_args: tuple | None = None
        self.execute_sql: str | None = None
        self.execute_args: tuple | None = None
        self.asserted_field: str | None = None

    async def fetch(self, sql, *args):  # noqa: ANN001
        self.fetch_sql = sql
        self.fetch_args = args
        return self._rows

    async def execute(self, sql, *args):  # noqa: ANN001
        self.execute_sql = sql
        self.execute_args = args
        return "INSERT 0 1"

    async def fetchval(self, sql, *args):  # noqa: ANN001 — يُحاكي _assert_field_in_tenant
        return 1


class _FakeTenantConn:
    """async context manager يُحاكي tenant_connection (يُعيد conn مزيّفاً)."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def scouting_mod():
    # api.main يستورد الموجِّهات في نهايته (يحلّ الدورة) — نستورده أوّلاً ثمّ الموجِّه.
    import api.main  # noqa: F401, WPS433
    import api.routers.scouting as m  # noqa: WPS433

    return m


@pytest.fixture
def fields_mod():
    import api.main  # noqa: F401, WPS433
    import api.routers.fields as m  # noqa: WPS433

    return m


def _sample_row():
    """صفّ يُحاكي قراءة asyncpg (mapping بمفاتيح أعمدة scouting_pins)."""
    return {
        "pin_id": "pin-1",
        "field_id": "fld-1",
        "lat": 16.0,
        "lng": 45.0,
        "issue_category": "pest",
        "severity": "high",
        "status": "new",
        "persistence": "seasonal",
        "crop": "tomato",
        "issue_code": "tomato.tuta",
        "note_ar": "إصابة",
        "photo_uri": None,
        "color": "#ea580c",
        "created_by": "u-1",
        "created_at": _dt.datetime(2026, 6, 22, 8, 0, tzinfo=_dt.UTC),
    }


# ─── _row_to_pin (نقيّ) ────────────────────────────────────────────────────


def test_row_to_pin_maps_all_fields(scouting_mod):
    out = scouting_mod._row_to_pin(_sample_row())
    assert out["pin_id"] == "pin-1"
    assert out["field_id"] == "fld-1"
    assert out["issue_category"] == "pest"
    assert out["severity"] == "high"
    assert out["persistence"] == "seasonal"
    assert out["issue_code"] == "tomato.tuta"
    assert out["color"] == "#ea580c"
    # created_at يُنسّق ISO (timestamptz → نصّ)
    assert out["created_at"].startswith("2026-06-22T08:00:00")


def test_row_to_pin_handles_string_created_at(scouting_mod):
    row = _sample_row()
    row["created_at"] = "already-iso"
    out = scouting_mod._row_to_pin(row)
    assert out["created_at"] == "already-iso"


# ─── GET /api/v1/scouting/pins ─────────────────────────────────────────────


async def test_list_pins_db_off_returns_empty_with_reason(scouting_mod, monkeypatch):
    """القاعدة غير مفعّلة ⇒ قائمة فارغة + سبب (لا اختراع مشاهدات)."""
    monkeypatch.setattr(scouting_mod, "_DB_POOL", None, raising=True)
    out = await scouting_mod.list_scouting_pins(field_id="fld-1", user=_FakeUser())
    assert out["pins"] == []
    assert out["total"] == 0
    assert "note_ar" in out


async def test_list_pins_reads_filtered_ordered(scouting_mod, monkeypatch):
    """يُرشِّح بـfield_id ويُرتّب الأحدث أوّلاً ويُحوّل الصفوف — SQL بارامتريّ."""
    conn = _FakeConn(rows=[_sample_row()])
    monkeypatch.setattr(scouting_mod, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        scouting_mod, "tenant_connection", lambda user: _FakeTenantConn(conn), raising=True
    )

    out = await scouting_mod.list_scouting_pins(field_id="fld-1", user=_FakeUser())

    assert out["field_id"] == "fld-1"
    assert out["total"] == 1
    assert out["pins"][0]["pin_id"] == "pin-1"
    # SQL: من scouting_pins، مُرشَّح بـ$1، مُرتَّب الأحدث أوّلاً (بارامتريّ لا حقن).
    assert "FROM scouting_pins" in conn.fetch_sql
    assert "WHERE field_id = $1" in conn.fetch_sql
    assert "ORDER BY created_at DESC" in conn.fetch_sql
    assert conn.fetch_args == ("fld-1",)


async def test_list_pins_db_error_raises_503(scouting_mod, monkeypatch):
    """تعذّر القاعدة أثناء التنفيذ ⇒ 503 موثَّق (لا 500، لا تاريخ مخترَع)."""
    from fastapi import HTTPException

    class _BoomConn:
        async def fetchval(self, *a, **k):  # noqa: ANN001
            return 1

        async def fetch(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(scouting_mod, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        scouting_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )
    with pytest.raises(HTTPException) as ei:
        await scouting_mod.list_scouting_pins(field_id="fld-1", user=_FakeUser())
    assert ei.value.status_code == 503


# ─── إدامة POST: _persist_scouting_pin (best-effort) ───────────────────────


async def test_persist_pin_db_off_returns_false(fields_mod, monkeypatch):
    """القاعدة غير مفعّلة ⇒ False (لا استثناء — يبقى المسار offline-first سليماً)."""
    from api.scouting_pins import make_pin

    monkeypatch.setattr(fields_mod, "_DB_POOL", None, raising=True)
    pin = make_pin("pin-x", "fld-1", 16.0, 45.0, "pest")
    ok = await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert ok is False


async def test_persist_pin_inserts_parameterized(fields_mod, monkeypatch):
    """نجاح الإدامة: INSERT بارامتريّ على scouting_pins مع ON CONFLICT idempotent."""
    from api.scouting_pins import make_pin

    conn = _FakeConn()
    monkeypatch.setattr(fields_mod, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn), raising=True
    )
    user = _FakeUser()
    pin = make_pin("pin-y", "fld-1", 16.0, 45.0, "pest", "high", "new", "seasonal", crop="tomato")
    ok = await fields_mod._persist_scouting_pin(user, pin)

    assert ok is True
    assert "INSERT INTO scouting_pins" in conn.execute_sql
    assert "ON CONFLICT (pin_id) DO NOTHING" in conn.execute_sql
    # القيم مُمرَّرة بارامتريّاً: pin_id ثمّ tenant ثمّ field …
    assert conn.execute_args[0] == "pin-y"
    assert conn.execute_args[1] == str(user.tenant_id)
    assert conn.execute_args[2] == "fld-1"


async def test_persist_pin_failure_best_effort(fields_mod, monkeypatch):
    """فشل الإدامة لا يرفع — best-effort: يُرجَع False (persisted=false)."""
    from api.scouting_pins import make_pin

    class _BoomConn:
        async def execute(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(fields_mod, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )
    pin = make_pin("pin-z", "fld-1", 16.0, 45.0, "pest")
    ok = await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert ok is False
