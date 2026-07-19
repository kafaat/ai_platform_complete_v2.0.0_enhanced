"""برهان حيّ لعامل إسقاط scout-ingest (SCOUT-INGEST-01 / B1.3) على PG أصليّ.

يُثبت البرهانَين المطلوبَين تحت الدور المقيَّد ``sahool_ingest`` + دالّتَي DEFINER (يملكهما resolver):
  • **المقبولة فقط تُسقَط:** صفّ accepted ⇒ مشاهدة تظهر · صفّ quarantined ⇒ **لا شيء** (برهان سلبيّ).
  • **إسقاط idempotent:** إعادة تشغيل العامل لا تُضاعف الصفوف (observation_id مشتقّ + ON CONFLICT).
  • field_id مفقود ⇒ dead_letter (لا مشاهدة يتيمة).
``-m integration`` فقط، يتخطّى بلا ``TEST_ADMIN_URL``. مُصادَق حيّاً على PG16.
"""

from __future__ import annotations

import importlib
import os
import uuid

import pytest

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.integration

ADMIN_URL = os.getenv("TEST_ADMIN_URL", "")
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SVC = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_T = "00000000-0000-0000-0000-0000000000cc"


async def _admin_setup():
    admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    for f in (
        "migrations/v197_external_submissions_ingest.sql",
        "migrations/v198_external_ingest_sources.sql",
        "migrations/v199_external_field_observations.sql",
    ):
        await admin.execute(open(os.path.join(_REPO, f), encoding="utf-8").read())
    await admin.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_ingest_resolver') THEN
            CREATE ROLE sahool_ingest_resolver NOLOGIN NOSUPERUSER NOINHERIT BYPASSRLS; END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sahool_ingest') THEN
            CREATE ROLE sahool_ingest LOGIN NOSUPERUSER NOINHERIT NOBYPASSRLS PASSWORD 'ingpw'; END IF;
        END $$;
        GRANT USAGE ON SCHEMA public TO sahool_ingest_resolver, sahool_ingest;
        -- least-grant: الإدراج فقط لـsahool_ingest؛ التحديث عبر DEFINER (المالك resolver).
        GRANT SELECT, INSERT ON external_submissions TO sahool_ingest;
        GRANT USAGE, SELECT ON SEQUENCE external_submissions_id_seq TO sahool_ingest;
        GRANT SELECT, INSERT ON external_field_observations TO sahool_ingest;
        GRANT SELECT, UPDATE ON external_submissions TO sahool_ingest_resolver;
        ALTER FUNCTION claim_submissions_for_projection(INT, INT) OWNER TO sahool_ingest_resolver;
        ALTER FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) OWNER TO sahool_ingest_resolver;
        GRANT EXECUTE ON FUNCTION claim_submissions_for_projection(INT, INT) TO sahool_ingest;
        GRANT EXECUTE ON FUNCTION complete_submission_projection(BIGINT, TEXT, TEXT) TO sahool_ingest;
    """)
    await admin.execute(
        "DELETE FROM external_field_observations; DELETE FROM external_submissions;"
    )
    # صفّان تحت المستأجِر: accepted (بحقل) + quarantined (بحقل) + accepted (بلا field_id).
    for key, _field, trust, payload in (
        ("k-accept", "fA", "accepted", {"field_id": "fA", "observed_property": "pest", "value": 3}),
        ("k-quar", "fQ", "quarantined", {"field_id": "fQ", "value": 9}),
        ("k-nofield", "-", "accepted", {"value": 1}),
    ):
        await admin.execute(
            "INSERT INTO external_submissions(tenant_id, submission_id, provider, server, form_id, "
            "instance_id, content_hash, idempotency_key, submitted_at, received_at, raw_ref, raw_payload, "
            "mapping_version, normalized_payload, trust_status) "
            "VALUES ($1,$2,'odk','s','fb',$2,$3,$4, now(), now(), 'urn:x', '{}'::jsonb, '1.0.0', $5::jsonb, $6)",
            uuid.UUID(_T),
            key,
            "c" * 64,
            key,
            __import__("json").dumps(payload),
            trust,
        )
    await admin.close()


@pytest.fixture
async def worker_mod():
    if not ADMIN_URL:
        pytest.skip("TEST_ADMIN_URL unset")
    try:
        await _admin_setup()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"admin PG unavailable: {type(exc).__name__}")
    os.environ["DATABASE_URL"] = "postgresql://sahool_ingest:ingpw@" + ADMIN_URL.split("@", 1)[1]
    os.environ["SCOUT_INGEST_PROJECTION_ENABLED"] = "1"
    if _SVC not in os.sys.path:
        os.sys.path.append(_SVC)
    import projection_worker

    importlib.reload(projection_worker)
    return projection_worker


async def test_accepted_only_idempotent_projection(worker_mod) -> None:
    conn = await worker_mod._connect()
    try:
        counts = await worker_mod.run_once(conn)
        assert (
            counts["projected"] == 1 and counts["dead_letter"] == 1
        )  # accepted+field ⇒ 1؛ no-field ⇒ dead
        await conn.execute("SELECT set_config('app.current_tenant', $1, false)", _T)
        # المقبول ظهر · المُحجَر (fQ) لم يظهر (برهان سلبيّ).
        fields = [
            r["field_id"]
            for r in await conn.fetch("SELECT field_id FROM external_field_observations")
        ]
        assert fields == ["fA"]
        # إعادة تشغيل العامل: لا مشاهدة جديدة (idempotent) — المقبول صار projected، والـdead لا يُعاد.
        counts2 = await worker_mod.run_once(conn)
        assert counts2["projected"] == 0
        total = await conn.fetchval("SELECT count(*) FROM external_field_observations")
        assert total == 1
    finally:
        await conn.close()
