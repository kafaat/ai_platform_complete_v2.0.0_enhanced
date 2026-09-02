"""اختبارات وحدة (unit): دفتر المياه اليوميّ المُخزَّن — منطق نقيّ + قراءة/إدامة.

تثبت بلا قاعدة حيّة (conn مزيّف + tenant_connection مُرقَّع) أنّ:

  • الوحدة النقيّة ``water_ledger_compute`` تُطبِّع المدخل وتحوّل الصفّ↔dict:
    - ``parse_ledger_date`` يقبل date/datetime/نصّ ISO ويرفض الفاسد (ValueError).
    - ``normalize_ledger_input`` يُبقي الناقص None (⇒ NULL، لا تلفيق)، يرفض المدخل
      غير الصالح، ويلزم ``ledger_date``.
    - ``row_to_ledger_entry`` نقيّ: يُنسّق التواريخ ISO ويُمرّر كلّ القيم (None تبقى None).
  • نقطة القراءة ``GET …/water-ledger`` تُرشِّح بـfield_id + مدى تاريخ بارامتريّ،
    تُرتّب تصاعديّاً بالتاريخ، وترجع dict مطابقاً. القاعدة معطّلة ⇒ قائمة فارغة + سبب.
  • نقطة الإدامة ``POST …/water-ledger`` upsert بارامتريّ على water_ledger مع
    ``ON CONFLICT (field_id, ledger_date) DO UPDATE`` (idempotent)؛ القاعدة معطّلة ⇒ 503؛
    مدخل غير صالح ⇒ 422.

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


def _sample_row():
    """صفّ يُحاكي قراءة asyncpg (mapping بمفاتيح أعمدة water_ledger). كثير منها None."""
    return {
        "field_id": "fld-1",
        "ledger_date": _dt.date(2026, 6, 22),
        "et0_mm": 5.4,
        "kc": 1.05,
        "etc_mm": 5.67,
        "rain_mm": 0.0,
        "irrigation_mm": 4.0,
        "soil_moisture_pct": None,  # ناقص ⇒ يبقى None (لا تلفيق)
        "depletion_mm": 12.3,
        "deficit_mm": 8.3,
        "stage": "mid",
        "decision": "irrigate",
        "confidence": None,  # ناقص ⇒ يبقى None
        "created_by": "u-1",
        "created_at": _dt.datetime(2026, 6, 22, 8, 0, tzinfo=_dt.UTC),
    }


# ─── الوحدة النقيّة: parse_ledger_date ─────────────────────────────────────


def test_parse_ledger_date_accepts_iso_string():
    from api.water_ledger_compute import parse_ledger_date

    assert parse_ledger_date("2026-06-22") == _dt.date(2026, 6, 22)


def test_parse_ledger_date_accepts_date_and_datetime():
    from api.water_ledger_compute import parse_ledger_date

    assert parse_ledger_date(_dt.date(2026, 6, 22)) == _dt.date(2026, 6, 22)
    assert parse_ledger_date(_dt.datetime(2026, 6, 22, 9, 30)) == _dt.date(2026, 6, 22)


def test_parse_ledger_date_rejects_garbage():
    from api.water_ledger_compute import parse_ledger_date

    with pytest.raises(ValueError):
        parse_ledger_date("not-a-date")
    with pytest.raises(ValueError):
        parse_ledger_date(12345)  # نوع غير مدعوم


# ─── الوحدة النقيّة: normalize_ledger_input ────────────────────────────────


def test_normalize_keeps_missing_as_none_no_fabrication():
    """الحقول الناقصة تبقى None (⇒ NULL) — لا تلفيق ولا تصفير."""
    from api.water_ledger_compute import normalize_ledger_input

    out = normalize_ledger_input({"ledger_date": "2026-06-22", "et0_mm": 5.4})
    assert out["ledger_date"] == _dt.date(2026, 6, 22)
    assert out["et0_mm"] == 5.4
    # كلّ ما لم يُمرَّر يبقى None (ليس 0.0)
    assert out["kc"] is None
    assert out["rain_mm"] is None
    assert out["confidence"] is None
    assert out["stage"] is None
    assert out["decision"] is None


def test_normalize_coerces_numeric_strings_and_empty():
    from api.water_ledger_compute import normalize_ledger_input

    out = normalize_ledger_input(
        {"ledger_date": "2026-06-22", "rain_mm": "3.2", "kc": "", "stage": "  mid  "}
    )
    assert out["rain_mm"] == 3.2
    assert out["kc"] is None  # نصّ فارغ ⇒ None (لا تلفيق)
    assert out["stage"] == "mid"  # نصّ مُشذَّب


def test_normalize_requires_ledger_date():
    from api.water_ledger_compute import normalize_ledger_input

    with pytest.raises(ValueError):
        normalize_ledger_input({"et0_mm": 5.4})
    with pytest.raises(ValueError):
        normalize_ledger_input({"ledger_date": "", "et0_mm": 5.4})


def test_normalize_rejects_invalid_numeric():
    from api.water_ledger_compute import normalize_ledger_input

    with pytest.raises(ValueError):
        normalize_ledger_input({"ledger_date": "2026-06-22", "et0_mm": "abc"})
    # bool مرفوض صراحةً (لا معنى عدديّ)
    with pytest.raises(ValueError):
        normalize_ledger_input({"ledger_date": "2026-06-22", "kc": True})


def test_normalize_rejects_non_string_text_field():
    from api.water_ledger_compute import normalize_ledger_input

    with pytest.raises(ValueError):
        normalize_ledger_input({"ledger_date": "2026-06-22", "decision": 42})


# ─── الوحدة النقيّة: row_to_ledger_entry ───────────────────────────────────


def test_row_to_entry_maps_all_fields_iso_dates():
    from api.water_ledger_compute import row_to_ledger_entry

    out = row_to_ledger_entry(_sample_row())
    assert out["field_id"] == "fld-1"
    assert out["ledger_date"] == "2026-06-22"
    assert out["etc_mm"] == 5.67
    assert out["decision"] == "irrigate"
    # القيم الناقصة تبقى None (لا تلفيق)
    assert out["soil_moisture_pct"] is None
    assert out["confidence"] is None
    assert out["created_at"].startswith("2026-06-22T08:00:00")


def test_row_to_entry_handles_string_dates():
    from api.water_ledger_compute import row_to_ledger_entry

    row = _sample_row()
    row["ledger_date"] = "2026-06-22"
    row["created_at"] = "already-iso"
    out = row_to_ledger_entry(row)
    assert out["ledger_date"] == "2026-06-22"
    assert out["created_at"] == "already-iso"


# ─── الراوتر: fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def wl_mod():
    pytest.importorskip("fastapi")
    # api.main يستورد الموجِّهات في نهايته (يحلّ الدورة) — نستورده أوّلاً ثمّ الموجِّه.
    import api.main  # noqa: F401, WPS433
    import api.routers.water_ledger as m  # noqa: WPS433

    return m


# ─── GET /api/v1/fields/{field_id}/water-ledger ────────────────────────────


async def test_list_db_off_returns_empty_with_reason(wl_mod, monkeypatch):
    """القاعدة غير مفعّلة ⇒ قائمة فارغة + سبب (لا اختراع قيود)."""
    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", None, raising=True)
    out = await wl_mod.list_water_ledger(
        field_id="fld-1", date_from=None, date_to=None, user=_FakeUser()
    )
    assert out["entries"] == []
    assert out["total"] == 0
    assert "note_ar" in out


async def test_list_reads_filtered_ordered_parameterized(wl_mod, monkeypatch):
    """يُرشِّح بـfield_id + مدى تاريخ، يُرتّب تصاعديّاً، SQL بارامتريّ (لا حقن)."""
    conn = _FakeConn(rows=[_sample_row()])
    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        wl_mod, "tenant_connection", lambda user: _FakeTenantConn(conn), raising=True
    )

    out = await wl_mod.list_water_ledger(
        field_id="fld-1", date_from="2026-06-01", date_to="2026-06-30", user=_FakeUser()
    )

    assert out["field_id"] == "fld-1"
    assert out["total"] == 1
    assert out["entries"][0]["field_id"] == "fld-1"
    assert "FROM water_ledger" in conn.fetch_sql
    assert "WHERE field_id = $1" in conn.fetch_sql
    assert "ORDER BY ledger_date ASC" in conn.fetch_sql
    # المدى بارامتريّ: field_id ثمّ from ثمّ to
    assert conn.fetch_args[0] == "fld-1"
    assert conn.fetch_args[1] == _dt.date(2026, 6, 1)
    assert conn.fetch_args[2] == _dt.date(2026, 6, 30)


async def test_list_rejects_bad_date_range(wl_mod, monkeypatch):
    """تاريخ مدى غير صالح ⇒ 422 (لا 500)."""
    from fastapi import HTTPException

    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    with pytest.raises(HTTPException) as ei:
        await wl_mod.list_water_ledger(
            field_id="fld-1", date_from="bad", date_to=None, user=_FakeUser()
        )
    assert ei.value.status_code == 422


async def test_list_db_error_raises_503(wl_mod, monkeypatch):
    """تعذّر القاعدة أثناء التنفيذ ⇒ 503 موثَّق (لا 500، لا قيود مخترَعة)."""
    from fastapi import HTTPException

    class _BoomConn:
        async def fetchval(self, *a, **k):  # noqa: ANN001
            return 1

        async def fetch(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        wl_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )
    with pytest.raises(HTTPException) as ei:
        await wl_mod.list_water_ledger(
            field_id="fld-1", date_from=None, date_to=None, user=_FakeUser()
        )
    assert ei.value.status_code == 503


# ─── POST /api/v1/fields/{field_id}/water-ledger (upsert) ──────────────────


async def test_upsert_db_off_returns_503(wl_mod, monkeypatch):
    """القاعدة غير مفعّلة ⇒ 503 موثَّق (لا ادّعاء حفظ)."""
    from fastapi import HTTPException

    req = wl_mod.WaterLedgerUpsertRequest(ledger_date="2026-06-22", et0_mm=5.4)
    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", None, raising=True)
    with pytest.raises(HTTPException) as ei:
        await wl_mod.upsert_water_ledger(req=req, field_id="fld-1", user=_FakeUser())
    assert ei.value.status_code == 503


async def test_upsert_invalid_date_returns_422(wl_mod, monkeypatch):
    """مدخل تاريخ غير صالح ⇒ 422 (قبل أيّ لمس للقاعدة)."""
    from fastapi import HTTPException

    req = wl_mod.WaterLedgerUpsertRequest(ledger_date="not-a-date")
    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    with pytest.raises(HTTPException) as ei:
        await wl_mod.upsert_water_ledger(req=req, field_id="fld-1", user=_FakeUser())
    assert ei.value.status_code == 422


async def test_upsert_idempotent_parameterized(wl_mod, monkeypatch):
    """نجاح الإدامة: INSERT بارامتريّ على water_ledger مع ON CONFLICT DO UPDATE."""
    conn = _FakeConn()
    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        wl_mod, "tenant_connection", lambda user: _FakeTenantConn(conn), raising=True
    )
    user = _FakeUser()
    req = wl_mod.WaterLedgerUpsertRequest(
        ledger_date="2026-06-22", et0_mm=5.4, etc_mm=5.67, decision="irrigate"
    )
    out = await wl_mod.upsert_water_ledger(req=req, field_id="fld-1", user=user)

    assert out["persisted"] is True
    assert out["ledger_date"] == "2026-06-22"
    assert "INSERT INTO water_ledger" in conn.execute_sql
    assert "ON CONFLICT (field_id, ledger_date) DO UPDATE" in conn.execute_sql
    # القيم بارامتريّة: tenant ثمّ field ثمّ التاريخ …
    assert conn.execute_args[0] == str(user.tenant_id)
    assert conn.execute_args[1] == "fld-1"
    assert conn.execute_args[2] == _dt.date(2026, 6, 22)


async def test_upsert_db_error_raises_503(wl_mod, monkeypatch):
    """تعذّر القاعدة أثناء الكتابة ⇒ 503 موثَّق (لا 500)."""
    from fastapi import HTTPException

    class _BoomConn:
        async def fetchval(self, *a, **k):  # noqa: ANN001
            return 1

        async def execute(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(wl_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        wl_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )
    req = wl_mod.WaterLedgerUpsertRequest(ledger_date="2026-06-22", et0_mm=5.4)
    with pytest.raises(HTTPException) as ei:
        await wl_mod.upsert_water_ledger(req=req, field_id="fld-1", user=_FakeUser())
    assert ei.value.status_code == 503
