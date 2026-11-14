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
  ⑦  the evidence context names only the v246 task pointer (field_tasks.source_scouting_pin_id,
      column SELECT), fails closed for another tenant/field, a worker and a lost object
  ⑧  v262 season links: accepted seasons of the same tenant and field only, idempotent retries,
      predecessor fence, correction and revocation, actor-attributed history; RLS, immutability,
      composite FKs, one root and one successor under the NOBYPASSRLS role

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
_PIN_CTX = "pin-a-context"
_PIN_LINK_RACE = "pin-a-link-race"


# Privileged cleanup of this suite's ledgers, grants, seasons and tasks. Their guards refuse DELETE,
# so the migration owner disables the user triggers for the purge only (as the v262-v272 comments
# describe a privileged purge), then re-enables them. Children before parents.
_LEDGERS = (
    "scout_treatment_review_events",
    "scout_photo_human_review_events",
    "scout_tissue_custody_events",
    "scout_plant_tissue_samples",
    "scout_photo_detection_link_events",
    "scout_photo_lab_link_events",
    "scout_photo_retention_events",
    "scout_photo_season_link_events",
)
_TENANT_LEDGERS = (
    "scout_specialist_credential_events",
    "scout_photo_retention_policy_events",
    "scout_photo_grant_audit_events",
    "scout_photo_field_access_grants",
)
_PURGE_LINKS = (
    "".join(
        f"ALTER TABLE {t} DISABLE TRIGGER USER;\nDELETE FROM {t} WHERE pin_id LIKE 'pin-%';\n"
        f"ALTER TABLE {t} ENABLE TRIGGER USER;\n"
        for t in _LEDGERS
    )
    + "".join(
        f"ALTER TABLE {t} DISABLE TRIGGER USER;\nDELETE FROM {t} WHERE tenant_id IN "
        f"('00000000-0000-0000-0000-0000000000aa', '00000000-0000-0000-0000-0000000000bb');\n"
        f"ALTER TABLE {t} ENABLE TRIGGER USER;\n"
        for t in _TENANT_LEDGERS
    )
    + "DELETE FROM season_records WHERE notes = 'scout-photo-live';\n"
    + "DELETE FROM field_tasks WHERE source_scouting_pin_id LIKE 'pin-%';\n"
)


async def _purge(admin) -> None:
    """One statement per transaction: a deferred FK event must not block the next ALTER."""
    for statement in filter(None, (line.strip() for line in _PURGE_LINKS.splitlines())):
        await admin.execute(statement)


# The people of this suite: (key, tenant, users.role). Their ids are SERIAL, read back into USERS.
_PEOPLE = (
    ("owner", _A, "owner"),
    ("admin", _A, "admin"),
    ("inspector", _A, "farmer"),
    ("viewer", _A, "viewer"),
    ("worker", _A, "worker"),
    ("manager", _A, "manager"),
    ("expert", _A, "expert"),
    ("expert2", _A, "agronomist"),
    ("nogrant", _A, "farmer"),
    ("expired", _A, "farmer"),
    ("demoted", _A, "farmer"),
    ("inspector_b", _B, "farmer"),
    ("expert_b", _B, "expert"),
)
USERS: dict[str, dict] = {}
# Standing grants on field-a (tenant A) and field-b (tenant B), all issued by the tenant owner.
_STANDING = {
    "inspector": ("photo.upload", "photo.read", "photo.context"),
    "viewer": ("photo.read",),
    "worker": ("photo.upload", "photo.read"),
    "manager": ("photo.read", "photo.context"),
    "expert": ("photo.upload", "photo.read", "photo.context", "photo.season_link"),
    "expert2": ("photo.read", "photo.season_link"),
    "admin": ("photo.read", "photo.context", "photo.season_link"),
    "demoted": ("photo.read",),
    "inspector_b": ("photo.upload", "photo.read", "photo.context"),
    "expert_b": ("photo.read", "photo.season_link"),
}


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
    await _purge(admin)
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
        (_A, _FIELD, _PIN_CTX),
        (_A, _FIELD, _PIN_LINK_RACE),
        (_B, "field-b", _PIN_B),
    ):
        await admin.execute(
            "INSERT INTO scouting_pins (pin_id, tenant_id, field_id, lat, lng, issue_category) "
            "VALUES ($1, $2::uuid, $3, 15.3, 44.2, 'pest')",
            pin,
            tenant,
            field,
        )
    await _people_fields_and_grants(admin)
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
    yield app, s3, ingest_url
    # The v262 FKs keep a linked season (and photo) from being deleted; other live suites on the
    # same database (test_season_live) delete tenant A's seasons, so this file removes its links.
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        await _purge(admin)
    finally:
        await admin.close()


async def grant(admin, user, scope, *, field=_FIELD, granted_days_ago=0, lease_days=30):
    """Issue a grant the way the admin API does: audit event + grant in one transaction (v265)."""
    person, owner = USERS[user], USERS["owner" if USERS[user]["tenant"] == _A else "owner_b"]
    grant_id, event_id = uuid.uuid4(), uuid.uuid4()
    async with admin.transaction():
        await admin.execute(
            "INSERT INTO scout_photo_grant_audit_events (event_id, tenant_id, field_id, grant_id, "
            "actor_user_id, target_user_id, scope, action, request_sha256, reason) "
            "VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'issue', $8, 'live test standing grant')",
            event_id,
            person["tenant"],
            field,
            grant_id,
            owner["id"],
            person["id"],
            scope,
            hashlib.sha256(str(event_id).encode()).hexdigest(),
        )
        await admin.execute(
            "INSERT INTO scout_photo_field_access_grants (grant_id, tenant_id, field_id, user_id, "
            "scope, granted_by, granted_at, expires_at) VALUES ($1, $2::uuid, $3, $4, $5, $6, "
            "now() - make_interval(days => $7), now() - make_interval(days => $7) "
            "+ make_interval(days => $8))",
            grant_id,
            person["tenant"],
            field,
            person["id"],
            scope,
            owner["id"],
            granted_days_ago,
            lease_days,
        )
    return grant_id


async def _people_fields_and_grants(admin) -> None:
    for field, tenant in ((_FIELD, _A), ("field-b", _B), ("field-other", _A)):
        await admin.execute(
            "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $1, $2::uuid) "
            "ON CONFLICT (field_id) DO NOTHING",
            field,
            tenant,
        )
    for key, tenant, role in (*_PEOPLE, ("owner_b", _B, "owner")):
        row = await admin.fetchrow(
            "INSERT INTO users (email, password_hash, full_name, role, tenant_id, active) "
            "VALUES ($1, 'x', $2, $3, $4::uuid, true) ON CONFLICT (email) DO UPDATE "
            "SET role=EXCLUDED.role, tenant_id=EXCLUDED.tenant_id, active=true "
            "RETURNING id, role, tenant_id::text AS tenant",
            f"scout-live-{key}@example.org",
            key,
            role,
            tenant,
        )
        USERS[key] = {"id": row["id"], "role": row["role"], "tenant": row["tenant"]}
    for user, scopes in _STANDING.items():
        field = _FIELD if USERS[user]["tenant"] == _A else "field-b"
        for scope in scopes:
            await grant(admin, user, scope, field=field)
    # Negative controls: an expired grant (started 31 days ago, 30-day lease) and a user whose
    # role changed after the grant (the trusted 'farmer' claim no longer matches users.role).
    await grant(admin, "expired", "photo.read", granted_days_ago=31, lease_days=30)
    await admin.execute("UPDATE users SET role='viewer' WHERE id=$1", USERS["demoted"]["id"])


def _hdr(tenant=None, role=None, uid=None, data=b"", ctype="image/jpeg", user="inspector"):
    """Identity headers of a suite user (overridable to forge a claim)."""
    person = USERS[user]
    return {
        "X-Scout-Media-Token": _TOKEN,
        "X-Tenant-Id": tenant or person["tenant"],
        "X-User-Id": uid or str(person["id"]),
        "X-User-Role": role or person["role"],
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
        assert rows[0]["tenant_id"] == _A and rows[0]["uploaded_by"] == str(
            USERS["inspector"]["id"]
        )
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
        # Tenant B (its own user, or A's user with a forged tenant claim) holds no grant on field-a.
        cross = await c.post(_path(), content=data, headers=_hdr(user="inspector_b", data=data))
        assert cross.status_code == 403
        assert (await c.get(_path(), headers=_hdr(tenant=_B))).status_code == 403
        wrong_field = await c.get(_path(field="field-b"), headers=_hdr())
        assert wrong_field.status_code == 403  # no grant on another tenant's field
        assert len(s3.objects) == 1

        got = await c.get(_path(), headers=_hdr(user="viewer"))
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
        assert len(rows) == 1 and rows[0]["uploaded_by"] == str(USERS["inspector"]["id"])
        assert re.fullmatch(r"[0-9a-f]{64}", rows[0]["content_sha256"].strip())
    finally:
        await admin.close()


# ─── evidence context and explicit season links (owner phases 4-5; v262) ────────────────────


async def _upload(c, pin, color):
    data = _picture(color=color)
    res = await c.post(_path(pin), content=data, headers=_hdr(data=data))
    assert res.status_code == 200, res.text


async def _season(tenant=_A, field=_FIELD, *, status="accepted") -> str:
    """A season_records row as scout-ingest stores it (accepted rows carry the reviewer)."""
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        accepted = status == "accepted"
        return str(
            await admin.fetchval(
                "INSERT INTO season_records (tenant_id, field_id, observed_at_from, "
                "observed_at_to, trust_status, accepted_by, accepted_at, notes) "
                "VALUES ($1::uuid, $2, DATE '2026-01-01', DATE '2026-05-01', $3, $4, "
                "CASE WHEN $5 THEN now() END, 'scout-photo-live') RETURNING id",
                tenant,
                field,
                status,
                "reviewer-1" if accepted else None,
                accepted,
            )
        )
    finally:
        await admin.close()


def _jhdr(user="expert", tenant=None):
    """Identity headers for a JSON request (no photo Content-Type or digest)."""
    return {
        k: v
        for k, v in _hdr(tenant=tenant, user=user).items()
        if k not in ("Content-Type", "X-Content-SHA256")
    }


def _link_path(pin=_PIN_CTX, field=_FIELD):
    return _path(pin, field) + "/season-link-events"


def _body(action="link", season=None, *, eid=None, previous=None, reason=None):
    return {
        "event_id": str(eid or uuid.uuid4()),
        "action": action,
        "season_id": season,
        "previous_event_id": previous,
        "reason": reason,
    }


async def test_context_names_only_the_v246_task_and_fails_closed(live):
    app, s3, _ = live
    async with await _client(app) as c:
        await _upload(c, _PIN_CTX, (12, 34, 56))
        ctx = await c.get(_path(_PIN_CTX) + "/context", headers=_hdr())
        assert ctx.status_code == 200, ctx.text
        body = ctx.json()
        assert body["schema"] == "sahool.scout-photo-evidence-context/v1"
        assert body["source"] == {"kind": "scouting_pin", "field_id": _FIELD, "pin_id": _PIN_CTX}
        assert body["evidence"]["persisted"] is True and "object_ref" not in body["evidence"]
        assert body["inspection"] == {"state": "not_linked"}
        assert body["season"] == {"state": "explicit_link_required", "season_id": None}
        assert body["decision"]["state"] == "not_authorized"
        assert body["automatic_pesticide_action_authorized"] is False
        assert ctx.headers["cache-control"] == "private, no-store"

        # A task on the same field that does not name the pin is never "nearby" evidence.
        admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
        try:
            await admin.execute(
                "INSERT INTO field_tasks (field_id, tenant_id, task_type, status) "
                "VALUES ($1, $2::uuid, 'inspection', 'pending')",
                _FIELD,
                _A,
            )
            assert (await c.get(_path(_PIN_CTX) + "/context", headers=_hdr())).json()[
                "inspection"
            ] == {"state": "not_linked"}
            task = await admin.fetchval(
                "INSERT INTO field_tasks (field_id, tenant_id, task_type, status, "
                "source_scouting_pin_id) VALUES ($1, $2::uuid, 'inspection', 'in_progress', $3) "
                "RETURNING task_id",
                _FIELD,
                _A,
                _PIN_CTX,
            )
        finally:
            await admin.close()
        linked = (await c.get(_path(_PIN_CTX) + "/context", headers=_hdr(user="expert"))).json()
        assert linked["inspection"] == {
            "state": "linked",
            "task_id": str(task),
            "status": "in_progress",
            "link_proof": "field_tasks.source_scouting_pin_id:v246",
        }
        # Another tenant, the wrong field, a worker: no context (no grant there, or the role gate).
        assert (
            await c.get(_path(_PIN_CTX) + "/context", headers=_hdr(user="inspector_b"))
        ).status_code == 403
        assert (
            await c.get(_path(_PIN_CTX, "field-b") + "/context", headers=_hdr())
        ).status_code == 403
        assert (
            await c.get(_path(_PIN_CTX) + "/context", headers=_hdr(user="worker"))
        ).status_code == 403
        # The object lost behind the row: the context is not served from the row alone.
        s3.objects.clear()
        lost = await c.get(_path(_PIN_CTX) + "/context", headers=_hdr())
        assert (
            lost.status_code == 503 and lost.json()["detail"] == "scout_photo_object_not_verified"
        )


async def test_season_link_chain_accepted_only_append_only_and_idempotent(live, monkeypatch):
    app, _, _ = live
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    expert = _jhdr()
    untrusted = await _season(status="untrusted")
    foreign_field = await _season(field="field-other")
    foreign_tenant = await _season(tenant=_B, field=_FIELD)
    first_season, second_season = await _season(), await _season()
    async with await _client(app) as c:
        await _upload(c, _PIN_CTX, (90, 10, 10))
        for season in (untrusted, foreign_field, foreign_tenant, str(uuid.uuid4())):
            res = await c.post(_link_path(), json=_body(season=season), headers=expert)
            assert res.status_code == 422, res.text
            assert res.json()["detail"] == "scout_photo_accepted_season_not_found"
        assert (
            await c.post(_link_path(), json=_body(season=first_season), headers=_jhdr("inspector"))
        ).status_code == 403

        link = _body(season=first_season)
        first = await c.post(_link_path(), json=link, headers=expert)
        assert first.status_code == 200, first.text
        assert first.json()["idempotent"] is False and first.json()["is_current"] is True
        assert first.json()["season"] == {
            "state": "linked_accepted",
            "season_id": first_season,
            "link_event_id": link["event_id"],
            "link_proof": "scout_photo_season_link_events:v262",
        }
        replay = await c.post(_link_path(), json=link, headers=expert)
        assert replay.status_code == 200 and replay.json()["idempotent"] is True
        # The same event id with another body, or by another person, is not a retry.
        assert (
            await c.post(_link_path(), json={**link, "season_id": second_season}, headers=expert)
        ).status_code == 409
        assert (await c.post(_link_path(), json=link, headers=_jhdr("expert2"))).status_code == 409
        # A second root, or a revision naming a stale head, is a predecessor conflict.
        assert (
            await c.post(_link_path(), json=_body(season=second_season), headers=expert)
        ).json()["detail"] == "scout_photo_link_predecessor_conflict"

        fix = _body(season=second_season, previous=link["event_id"], reason="wrong season picked")
        corrected = await c.post(_link_path(), json=fix, headers=expert)
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["season"]["season_id"] == second_season
        stale = _body(season=first_season, previous=link["event_id"], reason="stale head")
        assert (await c.post(_link_path(), json=stale, headers=expert)).status_code == 409

        revoke = _body("revoke", previous=fix["event_id"], reason="photo is from last season")
        revoked = await c.post(_link_path(), json=revoke, headers=_jhdr("admin"))
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["season"] == {
            "state": "revoked",
            "season_id": None,
            "link_event_id": revoke["event_id"],
        }

        history = await c.get(_link_path(), headers=expert)
        assert (
            history.status_code == 200 and history.headers["cache-control"] == "private, no-store"
        )
        events = history.json()["events"]
        assert [e["event_id"] for e in events] == [
            link["event_id"],
            fix["event_id"],
            revoke["event_id"],
        ]
        expert_id, admin_id = str(USERS["expert"]["id"]), str(USERS["admin"]["id"])
        assert [e["actor_id"] for e in events] == [expert_id, expert_id, admin_id]
        assert history.json()["current"]["state"] == "revoked"
        ctx = (await c.get(_path(_PIN_CTX) + "/context", headers=_hdr())).json()
        assert ctx["season"]["state"] == "revoked"
        # Another tenant sees no chain: its expert holds no grant on field-a.
        assert (await c.get(_link_path(), headers=_jhdr("expert_b"))).status_code == 403

    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "0")
    async with await _client(app) as c:
        assert (await c.get(_link_path(), headers=expert)).status_code == 404
        ctx = (await c.get(_path(_PIN_CTX) + "/context", headers=_hdr())).json()
        assert ctx["season"] == {"state": "explicit_link_required", "season_id": None}


async def test_concurrent_season_links(live, monkeypatch):
    app, _, _ = live
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    expert = _jhdr()
    one, two = await _season(), await _season()
    async with await _client(app) as c:
        await _upload(c, _PIN_LINK_RACE, (3, 200, 3))
        same = _body(season=one)
        replies = await asyncio.gather(
            *[c.post(_link_path(_PIN_LINK_RACE), json=same, headers=expert) for _ in range(6)]
        )
        assert [r.status_code for r in replies] == [200] * 6, [r.text for r in replies]
        assert sum(1 for r in replies if r.json()["idempotent"] is False) == 1
        # Two different successors of the same head: the unique successor admits one.
        a, b = await asyncio.gather(
            c.post(
                _link_path(_PIN_LINK_RACE),
                json=_body(season=two, previous=same["event_id"], reason="correction a"),
                headers=expert,
            ),
            c.post(
                _link_path(_PIN_LINK_RACE),
                json=_body("revoke", previous=same["event_id"], reason="correction b"),
                headers=expert,
            ),
        )
        assert sorted([a.status_code, b.status_code]) == [200, 409], (a.text, b.text)
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM scout_photo_season_link_events WHERE pin_id=$1",
                _PIN_LINK_RACE,
            )
            == 2
        )
    finally:
        await admin.close()


async def test_season_link_sql_rls_immutability_and_fences_under_nobypassrls(live, monkeypatch):
    app, _, ingest_url = live
    monkeypatch.setenv("SCOUT_MEDIA_SEASON_LINK_ENABLED", "1")
    season = await _season()
    other_field_season = await _season(field="field-other")
    root = _body(season=season)
    async with await _client(app) as c:
        await _upload(c, _PIN_CTX, (44, 44, 200))
        assert (await c.post(_link_path(), json=root, headers=_jhdr())).status_code == 200

    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        forced = await admin.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE oid='scout_photo_season_link_events'::regclass"
        )
        assert (forced["relrowsecurity"], forced["relforcerowsecurity"]) == (True, True)
        for stmt in (
            "UPDATE scout_photo_season_link_events SET reason='rewritten'",
            "DELETE FROM scout_photo_season_link_events",
        ):
            with pytest.raises(
                asyncpg.PostgresError, match="scout_photo_season_link_event_immutable"
            ) as exc:
                await admin.execute(stmt)
            assert exc.value.sqlstate == "55000"
    finally:
        await admin.close()

    insert = (
        "INSERT INTO scout_photo_season_link_events "
        "(event_id, tenant_id, field_id, pin_id, season_id, action, previous_event_id, actor_id, reason) "
        "VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6, $7::uuid, 'probe', $8)"
    )
    a = await _as(ingest_url, _A)
    try:
        assert await a.fetchval("SELECT count(*) FROM scout_photo_season_link_events") == 1
        # A season of another field of the same tenant: the composite FK refuses it.
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await a.execute(
                insert,
                str(uuid.uuid4()),
                _A,
                _FIELD,
                _PIN_CTX,
                other_field_season,
                "link",
                root["event_id"],
                "other field",
            )
        # A second root for the same photo.
        with pytest.raises(asyncpg.UniqueViolationError):
            await a.execute(
                insert, str(uuid.uuid4()), _A, _FIELD, _PIN_CTX, season, "link", None, None
            )
        # Two successors of the same event: the unique successor fences the race in SQL, also
        # when two API calls read the same head at the same instant.
        await a.execute(
            insert,
            str(uuid.uuid4()),
            _A,
            _FIELD,
            _PIN_CTX,
            season,
            "link",
            root["event_id"],
            "first correction",
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await a.execute(
                insert,
                str(uuid.uuid4()),
                _A,
                _FIELD,
                _PIN_CTX,
                season,
                "link",
                root["event_id"],
                "second correction",
            )
        # A revocation without a reason.
        with pytest.raises(asyncpg.CheckViolationError):
            await a.execute(
                insert,
                str(uuid.uuid4()),
                _A,
                _FIELD,
                _PIN_CTX,
                None,
                "revoke",
                root["event_id"],
                None,
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await a.execute("UPDATE scout_photo_season_link_events SET reason='x'")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await a.execute("DELETE FROM scout_photo_season_link_events")
        # field_tasks: the granted columns only, and no write.
        await a.fetch(
            "SELECT tenant_id, field_id, source_scouting_pin_id, task_id, status FROM field_tasks"
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await a.fetch("SELECT notes FROM field_tasks")
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await a.execute("UPDATE field_tasks SET status='done'")
    finally:
        await a.close()

    b = await _as(ingest_url, _B)
    try:
        assert await b.fetchval("SELECT count(*) FROM scout_photo_season_link_events") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="row-level security"):
            await b.execute(
                insert,
                str(uuid.uuid4()),
                _A,
                _FIELD,
                _PIN_CTX,
                season,
                "link",
                root["event_id"],
                "x",
            )
    finally:
        await b.close()
    none = await _as(ingest_url, None)
    try:
        assert await none.fetchval("SELECT count(*) FROM scout_photo_season_link_events") == 0
    finally:
        await none.close()


# ─── field grants (owner phases 6-8; v263-v265) ─────────────────────────────────────────────


async def test_every_photo_route_needs_a_live_field_grant(live, monkeypatch):
    """No grant, an expired grant, a revoked grant, a changed role, another tenant: all 403."""
    app, _, _ = live
    data = _picture(color=(120, 60, 200))
    async with await _client(app) as c:
        assert (await c.post(_path(), content=data, headers=_hdr(data=data))).status_code == 200
        for user in ("nogrant", "expired", "demoted", "inspector_b"):
            res = await c.get(_path(), headers=_hdr(user=user))
            assert res.status_code == 403, (user, res.text)
            assert res.json()["detail"] == "scout_media_field_scope_denied"
        # A grant for one scope is not another: the viewer may read, not see the context.
        assert (await c.get(_path(), headers=_hdr(user="viewer"))).status_code == 200
        ctx = await c.get(_path() + "/context", headers=_hdr(user="viewer"))
        assert ctx.status_code == 403  # viewer is outside the context roles
        manager_upload = await c.post(
            _path(_PIN_RACE), content=data, headers=_hdr(user="manager", data=data)
        )
        assert manager_upload.status_code == 403  # manager holds read+context, not upload
        # Revoking (audit + revocation in one transaction) takes effect on the next request.
        admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
        try:
            gid = await admin.fetchval(
                "SELECT grant_id FROM scout_photo_field_access_grants WHERE user_id=$1 "
                "AND scope='photo.read' AND revoked_at IS NULL",
                USERS["viewer"]["id"],
            )
            event = uuid.uuid4()
            async with admin.transaction():
                await admin.execute(
                    "INSERT INTO scout_photo_grant_audit_events (event_id, tenant_id, field_id, "
                    "grant_id, actor_user_id, target_user_id, scope, action, request_sha256, "
                    "reason) VALUES ($1, $2::uuid, $3, $4, $5, $6, 'photo.read', 'revoke', $7, "
                    "'live test revocation')",
                    event,
                    _A,
                    _FIELD,
                    gid,
                    USERS["owner"]["id"],
                    USERS["viewer"]["id"],
                    hashlib.sha256(str(event).encode()).hexdigest(),
                )
                await admin.execute(
                    "UPDATE scout_photo_field_access_grants SET revoked_at=now(), revoked_by=$2, "
                    "revocation_reason='live test revocation' WHERE grant_id=$1",
                    gid,
                    USERS["owner"]["id"],
                )
        finally:
            await admin.close()
        assert (await c.get(_path(), headers=_hdr(user="viewer"))).status_code == 403


async def test_grant_table_rules_hold_in_sql_under_nobypassrls(live):
    _, _, ingest_url = live
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    try:
        for table in ("scout_photo_field_access_grants", "scout_photo_grant_audit_events"):
            forced = await admin.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
                table,
            )
            assert (forced["relrowsecurity"], forced["relforcerowsecurity"]) == (True, True)
        # v265: a grant without its audit event is refused at COMMIT; so is a lease > 90 days.
        with pytest.raises(asyncpg.PostgresError, match="missing_issuance_audit"):
            await admin.execute(
                "INSERT INTO scout_photo_field_access_grants (tenant_id, field_id, user_id, "
                "scope, granted_by, expires_at) VALUES ($1::uuid, $2, $3, 'photo.read', $4, "
                "now() + interval '1 day')",
                _A,
                _FIELD,
                USERS["nogrant"]["id"],
                USERS["owner"]["id"],
            )
        with pytest.raises(asyncpg.PostgresError, match="expiry_policy_violation"):
            await grant(admin, "nogrant", "photo.read", lease_days=91)
        # v263: a grant row is history; only a documented revocation may change it.
        gid = await admin.fetchval(
            "SELECT grant_id FROM scout_photo_field_access_grants WHERE user_id=$1 LIMIT 1",
            USERS["inspector"]["id"],
        )
        with pytest.raises(asyncpg.PostgresError, match="scout_photo_grant_immutable"):
            await admin.execute(
                "UPDATE scout_photo_field_access_grants SET scope='photo.upload' WHERE grant_id=$1",
                gid,
            )
        with pytest.raises(asyncpg.PostgresError, match="scout_photo_grant_deletion_forbidden"):
            await admin.execute(
                "DELETE FROM scout_photo_field_access_grants WHERE grant_id=$1", gid
            )
    finally:
        await admin.close()
    a = await _as(ingest_url, _A)
    try:
        assert await a.fetchval("SELECT count(*) FROM scout_photo_field_access_grants") > 0
        for stmt in (
            "UPDATE scout_photo_field_access_grants SET revoked_at=now()",
            "DELETE FROM scout_photo_field_access_grants",
            "SELECT count(*) FROM scout_photo_grant_audit_events",
            "SELECT password_hash FROM users",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await a.execute(stmt)
    finally:
        await a.close()
    b = await _as(ingest_url, _B)
    try:
        rows = await b.fetch(
            "SELECT DISTINCT tenant_id::text AS t FROM scout_photo_field_access_grants"
        )
        assert [r["t"] for r in rows] == [_B]
    finally:
        await b.close()
    none = await _as(ingest_url, None)
    try:
        assert await none.fetchval("SELECT count(*) FROM scout_photo_field_access_grants") == 0
    finally:
        await none.close()
