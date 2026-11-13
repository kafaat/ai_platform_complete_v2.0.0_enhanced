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
    monkeypatch.setattr(scouting_mod.api_main, "_DB_POOL", None, raising=True)
    out = await scouting_mod.list_scouting_pins(field_id="fld-1", user=_FakeUser())
    assert out["pins"] == []
    assert out["total"] == 0
    assert "note_ar" in out


async def test_list_pins_reads_filtered_ordered(scouting_mod, monkeypatch):
    """يُرشِّح بـfield_id ويُرتّب الأحدث أوّلاً ويُحوّل الصفوف — SQL بارامتريّ."""
    conn = _FakeConn(rows=[_sample_row()])
    monkeypatch.setattr(scouting_mod.api_main, "_DB_POOL", object(), raising=True)
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

    monkeypatch.setattr(scouting_mod.api_main, "_DB_POOL", object(), raising=True)
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

    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", None, raising=True)
    pin = make_pin("pin-x", "fld-1", 16.0, 45.0, "pest")
    ok = await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert ok is False


async def test_persist_pin_inserts_parameterized(fields_mod, monkeypatch):
    """نجاح الإدامة: INSERT بارامتريّ على scouting_pins مع ON CONFLICT idempotent."""
    from api.scouting_pins import make_pin

    conn = _FakeConn()
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
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
    assert isinstance(conn.execute_args[-1], _dt.datetime)
    assert conn.execute_args[-1].tzinfo is not None


async def test_persist_pin_failure_best_effort(fields_mod, monkeypatch):
    """فشل الإدامة لا يرفع — best-effort: يُرجَع False (persisted=false)."""
    from api.scouting_pins import make_pin

    class _BoomConn:
        async def execute(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("table missing")

    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(_BoomConn()), raising=True
    )
    pin = make_pin("pin-z", "fld-1", 16.0, 45.0, "pest")
    ok = await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert ok is False


# ─── حدود الإدامة: حقلٌ خارج المستأجِر، إعادة إرسال مطابقة/متعارضة، عدم تطابق المسار ───


class _ExistingPinConn(_FakeConn):
    """conn يحاكي دبّوساً مخزَّناً مسبقاً (ON CONFLICT ⇒ INSERT 0 0) ثمّ يُرجِع صفّه."""

    def __init__(self, stored: dict):
        super().__init__()
        self._stored = stored

    async def execute(self, sql, *args):  # noqa: ANN001
        self.execute_sql = sql
        self.execute_args = args
        return "INSERT 0 0"

    async def fetchrow(self, sql, *args):  # noqa: ANN001
        return self._stored


async def test_persist_pin_field_outside_tenant_is_404(fields_mod, monkeypatch):
    """حقلٌ لا يُرى ضمن مستأجِر المستدعي (RLS) ⇒ 404 قبل أيّ INSERT."""
    from api.scouting_pins import make_pin
    from fastapi import HTTPException

    class _NoFieldConn(_FakeConn):
        async def fetchval(self, sql, *args):  # noqa: ANN001
            return None

    conn = _NoFieldConn()
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    with pytest.raises(HTTPException) as exc:
        await fields_mod._persist_scouting_pin(
            _FakeUser(), make_pin("p1", "fld-x", 16.0, 45.0, "pest")
        )
    assert exc.value.status_code == 404
    assert conn.execute_sql is None


async def test_persist_pin_identical_resend_returns_stored_row(fields_mod, monkeypatch):
    """إعادة إرسال مطابقة ⇒ True ويُرجَع created_at المخزَّن (لا تكرار ولا ختم جديد)."""
    from api.scouting_pins import make_pin

    pin = make_pin("p2", "fld-1", 16.0, 45.0, "pest")
    stored_at = _dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=_dt.UTC)
    stored = {k: v for k, v in pin.to_dict().items() if k != "created_at"} | {
        "created_at": stored_at
    }
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(_ExistingPinConn(stored))
    )
    assert await fields_mod._persist_scouting_pin(_FakeUser(), pin) is True
    assert pin.created_at == stored_at.isoformat()


async def test_persist_pin_conflicting_resend_is_409(fields_mod, monkeypatch):
    """المُعرِّف نفسه بإحداثيات مختلفة ⇒ 409 (لا يُعلَن نجاحٌ بحمولةٍ غير المخزَّنة)."""
    from api.scouting_pins import make_pin
    from fastapi import HTTPException

    pin = make_pin("p3", "fld-1", 16.0, 45.0, "pest")
    stored = pin.to_dict() | {"lat": 16.5}
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(_ExistingPinConn(stored))
    )
    with pytest.raises(HTTPException) as exc:
        await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert exc.value.status_code == 409


async def test_create_pin_rejects_body_field_differing_from_path(fields_mod):
    """field_id في الجسم يخالف المسار ⇒ 422 قبل التحقّق والإدامة."""
    from api.api_models import PinCreateRequest
    from fastapi import HTTPException

    req = PinCreateRequest(
        pin_id="p4", field_id="fld-other", lat=16.0, lng=45.0, issue_category="pest"
    )
    with pytest.raises(HTTPException) as exc:
        await fields_mod.create_pin("fld-1", req, _FakeUser())
    assert exc.value.status_code == 422


# ─── v257: مصدر الموقع ودقّته، وصورة الدبّوس في مخزن المرفقات ─────────────────


def test_location_source_defaults_to_unknown_and_round_trips():
    from api.scouting_pins import make_pin

    legacy = make_pin("p-old", "fld-1", 16.0, 45.0, "pest")
    assert legacy.location_source == "unknown" and legacy.accuracy_m is None
    gps = make_pin("p-gps", "fld-1", 16.0, 45.0, "pest", location_source="gps", accuracy_m=7.5)
    assert gps.to_dict()["location_source"] == "gps"
    assert gps.to_dict()["accuracy_m"] == 7.5


@pytest.mark.parametrize(
    "source,accuracy",
    [
        ("field_centroid", 5.0),
        ("manual", 1.0),
        ("unknown", 3.0),
        ("gps", -1.0),
        ("satellite", None),
    ],
)
def test_accuracy_belongs_to_a_gps_fix_only(source, accuracy):
    from api.scouting_pins import make_pin

    with pytest.raises(ValueError):
        make_pin("p", "fld-1", 16.0, 45.0, "pest", location_source=source, accuracy_m=accuracy)


def test_request_model_rejects_unknown_source_and_defaults_unknown():
    from api.api_models import PinCreateRequest
    from pydantic import ValidationError

    base = {"pin_id": "p", "field_id": "f", "lat": 16.0, "lng": 45.0, "issue_category": "pest"}
    assert PinCreateRequest(**base).location_source == "unknown"
    with pytest.raises(ValidationError):
        PinCreateRequest(**base, location_source="satellite")


async def test_persist_pin_writes_source_and_accuracy(fields_mod, monkeypatch):
    from api.scouting_pins import make_pin

    conn = _FakeConn()
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    pin = make_pin("p-src", "fld-1", 16.0, 45.0, "pest", location_source="gps", accuracy_m=4.0)
    assert await fields_mod._persist_scouting_pin(_FakeUser(), pin) is True
    assert "location_source, accuracy_m" in conn.execute_sql
    assert conn.execute_args[15:17] == ("gps", 4.0)


async def test_persist_pin_resend_with_other_source_is_409(fields_mod, monkeypatch):
    from api.scouting_pins import make_pin
    from fastapi import HTTPException

    pin = make_pin("p5", "fld-1", 16.0, 45.0, "pest", location_source="gps", accuracy_m=3.0)
    stored = pin.to_dict() | {"location_source": "field_centroid", "accuracy_m": None}
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(
        fields_mod, "tenant_connection", lambda user: _FakeTenantConn(_ExistingPinConn(stored))
    )
    with pytest.raises(HTTPException) as exc:
        await fields_mod._persist_scouting_pin(_FakeUser(), pin)
    assert exc.value.status_code == 409


def test_row_to_pin_reads_source_accuracy_and_photo(scouting_mod):
    row = _sample_row() | {
        "location_source": "gps",
        "accuracy_m": 6.0,
        "photo_document_id": "pinph_x",
        "photo_content_type": "image/jpeg",
        "photo_size_bytes": 1234,
    }
    out = scouting_mod._row_to_pin(row)
    assert (out["location_source"], out["accuracy_m"]) == ("gps", 6.0)
    assert out["photo"] == {
        "document_id": "pinph_x",
        "status": "stored",
        "content_url": "/api/v1/documents/pinph_x?content=true",
        "content_type": "image/jpeg",
        "size_bytes": 1234,
    }


def test_row_to_pin_legacy_row_is_unknown_without_photo(scouting_mod):
    out = scouting_mod._row_to_pin(_sample_row())
    assert out["location_source"] == "unknown"
    assert out["accuracy_m"] is None
    assert out["photo"] is None


def test_list_sql_selects_source_accuracy_and_photo(scouting_mod):
    cols = scouting_mod._PIN_SELECT_COLS
    for name in ("location_source", "accuracy_m", "photo_document_id", "photo_content_type"):
        assert name in cols


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode()


JPEG = b"\xff\xd8\xff\xe0" + b"x" * 32


def test_decode_pin_photo_types_by_magic_bytes_and_hashes():
    import hashlib

    from api.scouting_pins import decode_pin_photo

    p = decode_pin_photo(_b64(JPEG))
    assert (p.content_type, p.ext, p.sha256) == (
        "image/jpeg",
        "jpg",
        hashlib.sha256(JPEG).hexdigest(),
    )
    png = decode_pin_photo(_b64(b"\x89PNG\r\n\x1a\n" + b"y" * 8))
    assert png.content_type == "image/png"


@pytest.mark.parametrize(
    "payload,sha,status",
    [
        ("not base64!!", None, 422),
        (_b64(b"%PDF-1.4"), None, 415),
        (_b64(b"GIF89a"), None, 415),
        (_b64(JPEG), "0" * 64, 422),
    ],
)
def test_decode_pin_photo_refusals(payload, sha, status):
    from api.scouting_pins import decode_pin_photo
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        decode_pin_photo(payload, sha)
    assert exc.value.status_code == status


def test_decode_pin_photo_size_is_measured_after_decoding(monkeypatch):
    import api.scouting_pins as sp
    from fastapi import HTTPException

    monkeypatch.setattr(sp, "MAX_PIN_PHOTO_BYTES", len(JPEG) - 1)
    with pytest.raises(HTTPException) as exc:
        sp.decode_pin_photo(_b64(JPEG))
    assert exc.value.status_code == 413


def test_photo_ids_and_keys_are_server_derived_and_tenant_bound():
    from api.scouting_pins import (
        decode_pin_photo,
        pin_photo_document_id,
        pin_photo_key,
        pin_photo_ref_belongs_to,
    )

    t1, t2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    photo = decode_pin_photo(_b64(JPEG))
    assert pin_photo_document_id(t1, "p") == pin_photo_document_id(t1, "p")
    assert pin_photo_document_id(t1, "p") != pin_photo_document_id(t2, "p")
    assert len(pin_photo_document_id(t1, "p")) <= 50  # documents.doc_id VARCHAR(50)
    key = pin_photo_key(t1, "../../etc/passwd", photo)
    assert key.startswith(f"scouting-pin-photos/{t1}/") and ".." not in key
    assert key.endswith(f"/{photo.sha256}.jpg")
    assert pin_photo_ref_belongs_to(f"s3://bucket/{key}", t1)
    assert pin_photo_ref_belongs_to(f"file:///data/blobs/{key}", t1)
    assert not pin_photo_ref_belongs_to(f"s3://bucket/{key}", t2)
    assert not pin_photo_ref_belongs_to("file:///etc/passwd", t1)
    assert not pin_photo_ref_belongs_to(f"file:///x/scouting-pin-photos/{t1}/../../etc/passwd", t1)
    assert not pin_photo_ref_belongs_to(f"s3://bucket/other/{key}", t1)
    assert not pin_photo_ref_belongs_to(None, t1)


class _PhotoConn(_FakeConn):
    """conn يحاكي دبّوساً بلا صورة ثمّ يسجّل ما يُكتب في documents والربط."""

    def __init__(self, current=None, stored_ref=None):
        super().__init__()
        self.current = current
        self.stored_ref = stored_ref
        self.executes: list[tuple[str, tuple]] = []

    async def execute(self, sql, *args):  # noqa: ANN001
        self.executes.append((sql, args))
        return "INSERT 0 1"

    async def fetchval(self, sql, *args):  # noqa: ANN001
        if "photo_document_id" in sql:
            return self.current
        return 1

    async def fetchrow(self, sql, *args):  # noqa: ANN001
        if "FROM documents" in sql and self.stored_ref is not None:
            return {"storage_ref": self.stored_ref}
        return None


async def test_photo_is_stored_in_blob_store_and_bound_once(fields_mod, monkeypatch, tmp_path):
    from api.scouting_pins import decode_pin_photo, make_pin, pin_photo_document_id

    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "LOCAL_DIR", str(tmp_path))
    monkeypatch.setattr(blob_store, "S3_BUCKET", "")
    conn = _PhotoConn()
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    user = _FakeUser()
    pin = make_pin("p-ph", "fld-1", 16.0, 45.0, "pest")
    assert await fields_mod._persist_scouting_pin(user, pin, decode_pin_photo(_b64(JPEG))) is True
    doc_id = pin_photo_document_id(user.tenant_id, "p-ph")
    assert pin.photo_document_id == doc_id
    inserts = [a for s, a in conn.executes if s.startswith("INSERT INTO documents")]
    binds = [
        a for s, a in conn.executes if s.startswith("UPDATE scouting_pins SET photo_document_id")
    ]
    assert len(inserts) == 1 and inserts[0][0] == doc_id and inserts[0][5] == "image/jpeg"
    assert "ON CONFLICT (doc_id) DO NOTHING" in next(
        s for s, _ in conn.executes if s.startswith("INSERT INTO documents")
    )
    assert binds == [("p-ph", str(user.tenant_id), doc_id)]
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].read_bytes() == JPEG


async def test_photo_retry_with_same_content_writes_nothing(fields_mod, monkeypatch, tmp_path):
    from api.scouting_pins import decode_pin_photo, make_pin, pin_photo_key

    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "LOCAL_DIR", str(tmp_path))
    user = _FakeUser()
    photo = decode_pin_photo(_b64(JPEG))
    key = pin_photo_key(str(user.tenant_id), "p-r", photo)
    conn = _PhotoConn(current="pinph_existing", stored_ref=f"file://{tmp_path}/{key}")
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    pin = make_pin("p-r", "fld-1", 16.0, 45.0, "pest")
    assert await fields_mod._persist_scouting_pin(user, pin, photo) is True
    assert pin.photo_document_id == "pinph_existing"
    assert [s for s, _ in conn.executes if "documents" in s or "SET photo_document_id" in s] == []
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


async def test_a_different_photo_for_a_photographed_pin_is_409(fields_mod, monkeypatch):
    from api.scouting_pins import decode_pin_photo, make_pin
    from fastapi import HTTPException

    conn = _PhotoConn(
        current="pinph_existing", stored_ref="s3://b/scouting-pin-photos/t/x/other.jpg"
    )
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    with pytest.raises(HTTPException) as exc:
        await fields_mod._persist_scouting_pin(
            _FakeUser(), make_pin("p-c", "fld-1", 16.0, 45.0, "pest"), decode_pin_photo(_b64(JPEG))
        )
    assert exc.value.status_code == 409


async def test_photo_store_failure_is_503_not_a_silent_success(fields_mod, monkeypatch):
    from api.scouting_pins import decode_pin_photo, make_pin
    from fastapi import HTTPException

    from shared.storage import blob_store

    def boom(*a, **k):  # noqa: ANN001
        raise blob_store.BlobStoreError("down")

    monkeypatch.setattr(blob_store, "upload_bytes", boom)
    conn = _PhotoConn()
    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", object(), raising=True)
    monkeypatch.setattr(fields_mod, "tenant_connection", lambda user: _FakeTenantConn(conn))
    with pytest.raises(HTTPException) as exc:
        await fields_mod._persist_scouting_pin(
            _FakeUser(), make_pin("p-d", "fld-1", 16.0, 45.0, "pest"), decode_pin_photo(_b64(JPEG))
        )
    assert exc.value.status_code == 503


async def test_create_pin_reports_photo_not_stored_when_db_is_off(fields_mod, monkeypatch):
    from api.api_models import PinCreateRequest

    monkeypatch.setattr(fields_mod.api_main, "_DB_POOL", None, raising=True)
    req = PinCreateRequest(
        pin_id="p-off",
        field_id="fld-1",
        lat=16.0,
        lng=45.0,
        issue_category="pest",
        photo={"content_b64": _b64(JPEG)},
    )
    out = await fields_mod.create_pin("fld-1", req, _FakeUser())
    assert out["persisted"] is False
    assert out["photo"] == {"status": "not_stored"}


def test_blob_read_bytes_stays_inside_the_local_store(monkeypatch, tmp_path):
    from shared.storage import blob_store

    monkeypatch.setattr(blob_store, "LOCAL_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(blob_store, "S3_BUCKET", "")
    (tmp_path / "store").mkdir()
    inside = tmp_path / "store" / "a.jpg"
    inside.write_bytes(JPEG)
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"secret")
    assert blob_store.read_bytes(f"file://{inside}", 1024) == JPEG
    for ref in (f"file://{outside}", f"file://{tmp_path}/store/../secret.txt", "ftp://x/y"):
        with pytest.raises(blob_store.BlobStoreError):
            blob_store.read_bytes(ref, 1024)
    with pytest.raises(blob_store.BlobStoreError):
        blob_store.read_bytes(f"file://{inside}", 4)  # larger than the cap ⇒ refused, not truncated
