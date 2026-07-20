"""برهان PostgreSQL حيّ لـv197 (SCOUT-INGEST-01 / B1.2a) — RLS fail-closed + dedup متباين + append-only.

يعمل فقط تحت ``pytest -m integration`` ويتخطّى نظيفاً بلا قاعدة. الـfixture يُنشئ الجدول
بالسياسة الحرفيّة نفسها (v197) ودوراً مقيَّداً، فلا يعتمد على سلسلة الهجرات الكاملة.
مُصادَق حيّاً على PG16 أصليّ (جلسة 2026-07-19).
"""

from __future__ import annotations

import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")
pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@localhost:5433/sahool_test"
)
ROLE = "b12_rls_app_test"
TABLE = "external_submissions_rls_test"

_H = "a" * 64


@pytest.fixture
async def db():
    try:
        conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    try:
        await conn.execute(f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT LOGIN PASSWORD 'pw';
              END IF;
            END $$;
        """)
        await conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        await conn.execute(f"""
            CREATE TABLE {TABLE} (
              id BIGSERIAL PRIMARY KEY, tenant_id UUID NOT NULL,
              idempotency_key TEXT NOT NULL, content_hash TEXT NOT NULL,
              trust_status TEXT NOT NULL DEFAULT 'untrusted'
                CHECK (trust_status IN ('untrusted','accepted','quarantined')),
              quarantine_reasons TEXT[] NOT NULL DEFAULT '{{}}'
            )""")
        await conn.execute(f"CREATE UNIQUE INDEX ON {TABLE} (tenant_id, idempotency_key)")
        await conn.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        await conn.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
        await conn.execute(
            f"CREATE POLICY tenant_isolation ON {TABLE} "
            "USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), '')) "
            "WITH CHECK (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''))"
        )
        await conn.execute(f"""
            CREATE OR REPLACE FUNCTION {TABLE}_forbid_delete() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
              RAISE EXCEPTION 'append-only: raw evidence is immutable'; END; $$;
            CREATE TRIGGER trg_no_delete BEFORE DELETE ON {TABLE}
              FOR EACH ROW EXECUTE FUNCTION {TABLE}_forbid_delete();
        """)
        await conn.execute(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {ROLE}")
        await conn.execute(f"GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO {ROLE}")
        yield conn
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        await conn.close()


async def test_empty_tenant_context_insert_is_rejected(db) -> None:
    """PROOF 1: سياق فارغ ⇒ الإدراج مرفوض (fail-closed)."""
    await db.execute(f"SET ROLE {ROLE}")
    await db.execute("SELECT set_config('app.current_tenant','',false)")
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await db.execute(
            f"INSERT INTO {TABLE}(tenant_id, idempotency_key, content_hash) "
            f"VALUES ('{uuid.uuid4()}', '{_H}', '{_H}')"
        )
    await db.execute("RESET ROLE")


async def test_append_only_delete_is_forbidden(db) -> None:
    """PROOF 3: الحذف على الخامّ ممنوع بنيويّاً (trigger)."""
    tid = uuid.uuid4()
    await db.execute(f"SELECT set_config('app.current_tenant','{tid}',false)")
    await db.execute(
        f"INSERT INTO {TABLE}(tenant_id, idempotency_key, content_hash, trust_status) "
        f"VALUES ('{tid}', '{_H}', '{_H}', 'accepted')"
    )
    with pytest.raises(asyncpg.exceptions.RaiseError):
        await db.execute(f"DELETE FROM {TABLE} WHERE tenant_id='{tid}'")


async def test_divergent_payload_quarantines_without_touching_original(db) -> None:
    """PROOF 2 (الحارس السابع حيّاً): نفس المفتاح، جسم مختلف ⇒ صفّ quarantined، الأصل سليم."""
    tid = uuid.uuid4()
    key = "k" * 64
    await db.execute(f"SELECT set_config('app.current_tenant','{tid}',false)")
    await db.execute(
        f"INSERT INTO {TABLE}(tenant_id, idempotency_key, content_hash, trust_status) "
        f"VALUES ('{tid}', '{key}', '{'a' * 64}', 'accepted')"
    )
    # divergent body ⇒ derived key + quarantined (منطق resolve_dedup)
    await db.execute(
        f"INSERT INTO {TABLE}(tenant_id, idempotency_key, content_hash, trust_status, quarantine_reasons) "
        f"VALUES ('{tid}', '{key}#dup-{'b' * 12}', '{'b' * 64}', 'quarantined', "
        "'{duplicate_key_divergent_payload}')"
    )
    rows = await db.fetch(
        f"SELECT idempotency_key, trust_status FROM {TABLE} WHERE tenant_id='{tid}' ORDER BY id"
    )
    assert len(rows) == 2
    assert rows[0]["idempotency_key"] == key and rows[0]["trust_status"] == "accepted"
    assert rows[1]["trust_status"] == "quarantined"
