"""Live PostgreSQL proof for scout photo evidence (v260 ``scout_photo_evidence``).

Drives the real media API (``media_api.router``) and real SQL under the restricted
``sahool_ingest`` role (NOBYPASSRLS) with the grants copied **verbatim** from
``migrations/bootstrap_postgres.sh``. Proves what needs a real database:

  ①  RLS: another tenant can neither see nor insert rows; no tenant context ⇒ zero rows
  ②  immutability: sahool_ingest has no UPDATE/DELETE; a role that has them, and the owner,
      are refused by the BEFORE UPDATE OR DELETE trigger (55000)
  ③  the FK (tenant_id, field_id, pin_id) → scouting_pins holds (23503), and a pin with a
      photo cannot be deleted from under it
  ④  HTTP: first upload, idempotent resubmit, conflicting bytes (409), cross-tenant and
      wrong-field 404, presigned read with ``Cache-Control: private, no-store``
  ⑤  success only when the object exists (HEAD after commit), poisoned ``object_ref`` refused
  ⑥  concurrent resubmits of the same bytes: one row, every reply 200; concurrent different
      bytes: one 200 and one 409

The object store is a boto3-client double behind ``shared.storage.blob_store`` (the real
blob_store code runs; only the network client is replaced). ``-m integration`` only.
Requires ``TEST_ADMIN_URL`` (superuser) on a database with the full MANIFEST applied
(``scripts/ci/apply_migration_manifest.sh``); skips without it unless
``CI_INTEGRATION_REQUIRED=1``, which turns every skip into a failure.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
import sys
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg")
pytest.importorskip("PIL")
pytestmark = pytest.mark.integration

ADMIN_URL = os.getenv("TEST_ADMIN_URL", "")
_REQUIRE_DB = os.getenv("CI_INTEGRATION_REQUIRED", "").strip().lower() in ("1", "true", "yes")
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SVC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_A = "00000000-0000-0000-0000-0000000000aa"
_B = "00000000-0000-0000-0000-0000000000bb"
_TOKEN = "media-svc-token"  # noqa: S105 — test value
_BUCKET = "sahool-scout-ingest"
_FIELD = "field-a"
_PIN = "pin-a-1"
_PIN_RACE = "pin-a-race"
_PIN_RACE2 = "pin-a-race2"
_PIN_POISON = "pin-a-poison"
_PIN_B = "pin-b-1"


def _skip_or_fail(msg: str) -> None:
    if _REQUIRE_DB:
        pytest.fail(f"{msg} but CI_INTEGRATION_REQUIRED=1")
    pytest.skip(msg)


def _picture(color=(60, 180, 55), size=(64, 40)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _grant_block() -> str:
    """The sahool_ingest grant ``DO`` block exactly as bootstrap_postgres.sh runs it."""
    src = open(os.path.join(_REPO, "migrations/bootstrap_postgres.sh"), encoding="utf-8").read()
    at = src.index("GRANT SELECT, INSERT ON scout_photo_evidence TO sahool_ingest;")
    start = src.rindex("DO $$", 0, at)
    end = src.index("END $$;", at) + len("END $$;")
    return src[start:end]


class _FakeS3:
    """boto3 S3 client double: put/head/presign on an in-memory dict."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.fail_head = False

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: N803
        self.objects[(Bucket, Key)] = bytes(Body)

    def head_object(self, Bucket, Key):  # noqa: N803
        if self.fail_head or (Bucket, Key) not in self.objects:
            raise RuntimeError("404")
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        return (
            f"https://objects.example.org/{Params['Bucket']}/{Params['Key']}"
            f"?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=test"
        )


@pytest.fixture
async def live(monkeypatch):
    if not ADMIN_URL:
        _skip_or_fail("TEST_ADMIN_URL unset")
    try:
        admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        _skip_or_fail(f"admin PG unavailable: {type(exc).__name__}")
    if await admin.fetchval("SELECT to_regclass('public.scout_photo_evidence')") is None:
        await admin.close()
        _skip_or_fail("scout_photo_evidence absent: apply the full MANIFEST first")
    await admin.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_ingest') THEN
            CREATE ROLE sahool_ingest LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS PASSWORD 'ingpw'; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='photo_mutator') THEN
            CREATE ROLE photo_mutator LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS PASSWORD 'mutpw'; END IF;
        END $$;
        GRANT USAGE ON SCHEMA public TO sahool_ingest, photo_mutator;
        GRANT SELECT, UPDATE, DELETE ON scout_photo_evidence TO photo_mutator;
    """)
    await admin.execute(_grant_block())
    # Clean slate between runs: the trigger refuses DELETE, so the owner disables it for the
    # cleanup only (a privileged purge, as the migration comment describes), then re-enables.
    await admin.execute("""
        ALTER TABLE scout_photo_evidence DISABLE TRIGGER scout_photo_evidence_immutable_guard;
        DELETE FROM scout_photo_evidence WHERE pin_id LIKE 'pin-%';
        ALTER TABLE scout_photo_evidence ENABLE TRIGGER scout_photo_evidence_immutable_guard;
        DELETE FROM scouting_pins WHERE pin_id LIKE 'pin-%';
    """)
    for tenant, field, pin in (
        (_A, _FIELD, _PIN),
        (_A, _FIELD, _PIN_RACE),
        (_A, _FIELD, _PIN_RACE2),
        (_A, _FIELD, _PIN_POISON),
        (_B, "field-b", _PIN_B),
    ):
        await admin.execute(
            "INSERT INTO scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category) "
            "VALUES ($1, $2::uuid, $3, 15.3, 44.2, 'pest')",
            pin,
            tenant,
            field,
        )
    await admin.close()

    ingest_url = "postgresql://sahool_ingest:ingpw@" + ADMIN_URL.split("@", 1)[1]
    for p in (_REPO, _SVC):
        if p not in sys.path:
            sys.path.insert(0, p)
    import media_api
    import season_api

    monkeypatch.setattr(season_api, "DATABASE_URL", ingest_url)
    monkeypatch.setenv("SCOUT_MEDIA_ENABLED", "1")
    monkeypatch.setenv("SCOUT_MEDIA_SERVICE_TOKEN", _TOKEN)
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    store = media_api.blob_store
    monkeypatch.setattr(store, "S3_BUCKET", _BUCKET)
    monkeypatch.setattr(store, "S3_ENDPOINT", "https://objects.example.org")
    monkeypatch.setattr(store, "S3_PUBLIC_ENDPOINT", "")
    monkeypatch.setattr(store, "S3_USE_SSL", None)
    s3 = _FakeS3()
    monkeypatch.setattr(store, "_s3_client", lambda endpoint_url=None: s3)

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(media_api.router)
    return app, s3, ingest_url


def _hdr(tenant=_A, role="farmer", uid="inspector-1", data=b"", ctype="image/jpeg"):
    return {
        "X-Scout-Media-Token": _TOKEN,
        "X-Tenant-Id": tenant,
        "X-User-Id": uid,
        "X-User-Role": role,
        "X-Content-SHA256": hashlib.sha256(data).hexdigest(),
        "Content-Type": ctype,
    }


def _path(pin=_PIN, field=_FIELD):
    return f"/internal/scouting-media/fields/{field}/pins/{pin}/photo"


async def _client(app):
    import httpx

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://ingest")


async def _admin_rows(pin):
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        return await admin.fetch(
            "SELECT tenant_id::text AS tenant_id, field_id, pin_id, object_ref, "
            "content_sha256, uploaded_by FROM scout_photo_evidence WHERE pin_id=$1",
            pin,
        )
    finally:
        await admin.close()


async def test_upload_resubmit_conflict_isolation_and_presigned_read(live):
    app, s3, _ = live
    data = _picture()
    digest = hashlib.sha256(data).hexdigest()
    async with await _client(app) as c:
        first = await c.post(_path(), content=data, headers=_hdr(data=data))
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["persisted"] is True and body["idempotent"] is False
        assert (body["field_id"], body["pin_id"], body["sha256"]) == (_FIELD, _PIN, digest)
        assert "object_ref" not in body and "url" not in body
        rows = await _admin_rows(_PIN)
        assert len(rows) == 1
        assert rows[0]["tenant_id"] == _A and rows[0]["uploaded_by"] == "inspector-1"
        assert rows[0]["object_ref"] == f"s3://{_BUCKET}/scouting-photos/v1/{_A}/{_PIN}/{digest}"
        assert s3.objects == {(_BUCKET, f"scouting-photos/v1/{_A}/{_PIN}/{digest}"): data}

        replay = await c.post(_path(), content=data, headers=_hdr(data=data))
        assert replay.status_code == 200 and replay.json()["idempotent"] is True
        assert replay.json()["evidence_id"] == body["evidence_id"]

        other = _picture(color=(200, 10, 10))
        changed = await c.post(_path(), content=other, headers=_hdr(data=other))
        assert changed.status_code == 409
        assert len(await _admin_rows(_PIN)) == 1 and len(s3.objects) == 1

        # Tenant B cannot reach tenant A's pin (RLS on scouting_pins and on the photo table).
        cross = await c.post(_path(), content=data, headers=_hdr(tenant=_B, data=data))
        assert cross.status_code == 404
        assert (await c.get(_path(), headers=_hdr(tenant=_B))).status_code == 404
        wrong_field = await c.get(_path(field="field-b"), headers=_hdr())
        assert wrong_field.status_code == 404
        assert len(s3.objects) == 1

        got = await c.get(_path(), headers=_hdr(role="viewer"))
        assert got.status_code == 200, got.text
        assert got.json()["url"].startswith("https://objects.example.org/")
        assert got.json()["expires_in_seconds"] == 120
        assert got.headers["cache-control"] == "private, no-store"
        assert got.headers["pragma"] == "no-cache"

        # Object lost behind the row ⇒ never reported as stored.
        s3.objects.clear()
        assert (await c.get(_path(), headers=_hdr())).json()["detail"] == (
            "scout_photo_object_not_verified"
        )
        lost = await c.post(_path(), content=data, headers=_hdr(data=data))
        assert lost.status_code == 503
        assert lost.json()["detail"] == "scout_photo_object_not_verified"


async def test_new_upload_needs_the_head_check_after_commit(live):
    app, s3, _ = live
    s3.fail_head = True
    data = _picture(color=(1, 2, 3))
    async with await _client(app) as c:
        res = await c.post(_path(_PIN_RACE2), content=data, headers=_hdr(data=data))
    assert res.status_code == 503
    assert res.json()["detail"] == "scout_photo_object_not_verified"
    assert len(await _admin_rows(_PIN_RACE2)) == 1  # the row is committed, success is not claimed


async def test_poisoned_object_ref_is_never_presigned(live):
    app, s3, _ = live
    data = _picture(color=(9, 9, 9))
    digest = hashlib.sha256(data).hexdigest()
    key = f"scouting-photos/v1/{_A}/{_PIN_POISON}/{digest}"
    s3.objects[("other-bucket", key)] = data
    s3.objects[(_BUCKET, key.replace(_A, _B))] = data
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        await admin.execute(
            "INSERT INTO scout_photo_evidence (tenant_id, field_id, pin_id, object_ref, "
            "content_sha256, mime_type, size_bytes, image_width, image_height, uploaded_by) "
            "VALUES ($1::uuid, $2, $3, $4, $5, 'image/jpeg', $6, 64, 40, 'forged')",
            _A,
            _FIELD,
            _PIN_POISON,
            f"s3://other-bucket/{key}",
            digest,
            len(data),
        )
    finally:
        await admin.close()
    async with await _client(app) as c:
        res = await c.get(_path(_PIN_POISON), headers=_hdr())
        assert res.status_code == 503
        assert res.json()["detail"] == "scout_photo_reference_invalid"
        replay = await c.post(_path(_PIN_POISON), content=data, headers=_hdr(data=data))
        assert replay.status_code == 503
        assert replay.json()["detail"] == "scout_photo_reference_invalid"


async def test_concurrent_resubmits(live):
    app, s3, _ = live
    data = _picture(color=(5, 120, 5))
    async with await _client(app) as c:
        replies = await asyncio.gather(
            *[c.post(_path(_PIN_RACE), content=data, headers=_hdr(data=data)) for _ in range(8)]
        )
    assert [r.status_code for r in replies] == [200] * 8, [r.text for r in replies]
    assert sum(1 for r in replies if r.json()["idempotent"] is False) == 1
    assert len({r.json()["evidence_id"] for r in replies}) == 1
    assert len(await _admin_rows(_PIN_RACE)) == 1


async def test_concurrent_different_bytes_one_wins(live):
    app, s3, _ = live
    one, two = _picture(color=(10, 10, 200)), _picture(color=(200, 200, 10))
    async with await _client(app) as c:
        a, b = await asyncio.gather(
            c.post(_path(_PIN_RACE2), content=one, headers=_hdr(data=one)),
            c.post(_path(_PIN_RACE2), content=two, headers=_hdr(data=two)),
        )
    assert sorted([a.status_code, b.status_code]) == [200, 409], (a.text, b.text)
    rows = await _admin_rows(_PIN_RACE2)
    assert len(rows) == 1
    winner = a if a.status_code == 200 else b
    assert rows[0]["content_sha256"].strip() == winner.json()["sha256"]


async def _as(url: str, tenant: str | None):
    conn = await asyncpg.connect(url, statement_cache_size=0)
    if tenant is not None:
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    return conn


def _insert_sql() -> str:
    return (
        "INSERT INTO scout_photo_evidence (tenant_id, field_id, pin_id, object_ref, "
        "content_sha256, mime_type, size_bytes, image_width, image_height, uploaded_by) "
        "VALUES ($1::uuid, $2, $3, $4, $5, 'image/jpeg', 10, 1, 1, 'probe')"
    )


async def test_sql_rls_immutability_and_fk_under_nobypassrls_roles(live):
    app, _, ingest_url = live
    data = _picture(color=(77, 77, 77))
    async with await _client(app) as c:
        assert (await c.post(_path(), content=data, headers=_hdr(data=data))).status_code == 200

    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        attrs = await admin.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='sahool_ingest'"
        )
        assert (attrs["rolsuper"], attrs["rolbypassrls"]) == (False, False)
        forced = await admin.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid='scout_photo_evidence'::regclass"
        )
        assert (forced["relrowsecurity"], forced["relforcerowsecurity"]) == (True, True)
    finally:
        await admin.close()

    sha = "b" * 64
    ref_b = f"s3://{_BUCKET}/scouting-photos/v1/{_B}/{_PIN_B}/{sha}"

    # ① RLS — tenant B sees nothing of A, cannot write a row for A; no context ⇒ nothing.
    b = await _as(ingest_url, _B)
    try:
        assert (
            await b.fetchval(
                "SELECT count(*) FROM scout_photo_evidence WHERE tenant_id=$1::uuid", _A
            )
            == 0
        )
        assert await b.fetchval("SELECT count(*) FROM scout_photo_evidence") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            await b.execute(_insert_sql(), _A, _FIELD, _PIN, "s3://x/y", sha)
        # ③ FK — tenant B naming A's (field, pin) under its own tenant: no such pin.
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await b.execute(_insert_sql(), _B, _FIELD, _PIN, ref_b, sha)
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await b.execute(_insert_sql(), _B, "field-b", "no-such-pin", ref_b, sha)
        # B's own pin is accepted (the FK is satisfied by a real pin).
        await b.execute(_insert_sql(), _B, "field-b", _PIN_B, ref_b, sha)
        assert await b.fetchval("SELECT count(*) FROM scout_photo_evidence") == 1
        with pytest.raises(asyncpg.CheckViolationError):
            await b.execute(
                "INSERT INTO scout_photo_evidence (tenant_id, field_id, pin_id, object_ref, "
                "content_sha256, mime_type, size_bytes, image_width, image_height, uploaded_by) "
                "VALUES ($1::uuid, 'field-b', $2, 'file:///etc/passwd', $3, 'image/jpeg', 1, 1, 1, 'p')",
                _B,
                _PIN_B,
                sha,
            )
        # ② sahool_ingest has no UPDATE/DELETE at all.
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await b.execute("UPDATE scout_photo_evidence SET uploaded_by='x'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await b.execute("DELETE FROM scout_photo_evidence")
    finally:
        await b.close()

    none = await _as(ingest_url, None)
    try:
        assert await none.fetchval("SELECT count(*) FROM scout_photo_evidence") == 0
    finally:
        await none.close()

    a = await _as(ingest_url, _A)
    try:
        assert (
            await a.fetchval("SELECT count(*) FROM scout_photo_evidence WHERE pin_id=$1", _PIN) == 1
        )
        assert (
            await a.fetchval(
                "SELECT count(*) FROM scout_photo_evidence WHERE tenant_id=$1::uuid", _B
            )
            == 0
        )
    finally:
        await a.close()

    # ② a NOBYPASSRLS role that does hold UPDATE/DELETE, and the owner: the trigger refuses.
    mut = await _as("postgresql://photo_mutator:mutpw@" + ADMIN_URL.split("@", 1)[1], _A)
    try:
        for stmt in (
            "UPDATE scout_photo_evidence SET uploaded_by='rewritten' WHERE pin_id='pin-a-1'",
            "DELETE FROM scout_photo_evidence WHERE pin_id='pin-a-1'",
        ):
            with pytest.raises(
                asyncpg.PostgresError, match="scout_photo_evidence_immutable"
            ) as exc:
                await mut.execute(stmt)
            assert exc.value.sqlstate == "55000"
    finally:
        await mut.close()
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        with pytest.raises(asyncpg.PostgresError, match="scout_photo_evidence_immutable"):
            await admin.execute(
                "UPDATE scout_photo_evidence SET content_sha256=$1 WHERE pin_id=$2", sha, _PIN
            )
        with pytest.raises(asyncpg.PostgresError, match="scout_photo_evidence_immutable"):
            await admin.execute("DELETE FROM scout_photo_evidence WHERE pin_id=$1", _PIN)
        # ③ the pin cannot be deleted from under its photo.
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await admin.execute("DELETE FROM scouting_pins WHERE pin_id=$1", _PIN)
        # The FK is backed by v246's unique index on scouting_pins (tenant_id, field_id, pin_id).
        fk = await admin.fetchrow(
            "SELECT c.conname, i.relname AS idx FROM pg_constraint c "
            "JOIN pg_class i ON i.oid = c.conindid "
            "WHERE c.conname = 'scout_photo_evidence_pin_fk'"
        )
        assert fk["idx"] == "scouting_pins_tenant_field_pin_uq"
        rows = await _admin_rows(_PIN)
        assert len(rows) == 1 and rows[0]["uploaded_by"] == "inspector-1"
        assert re.fullmatch(r"[0-9a-f]{64}", rows[0]["content_sha256"].strip())
    finally:
        await admin.close()
