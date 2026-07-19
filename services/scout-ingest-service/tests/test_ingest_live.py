"""برهان HTTP حيّ لـscout-ingest-service (SCOUT-INGEST-01 / B1.2b) على PG أصليّ.

يقود الخدمة الفعليّة (TestClient) تحت الدور المقيَّد ``sahool_ingest``: 401 (بلا توكن) · 403 (مجهول) ·
403 (مصدر معطَّل لا يمسّ غيره) · 200 accepted (تحت المستأجِر الصحيح) · idempotent · 202 quarantined
(نفس الخانة جسم مختلف). ``-m integration`` فقط، يتخطّى بلا قاعدة. مُصادَق حيّاً على PG16 (2026-07-19).

يتطلّب: ``TEST_ADMIN_URL`` (superuser، للإعداد) — إن غاب يتخطّى.
"""

from __future__ import annotations

import hashlib
import importlib
import os

import pytest

asyncpg = pytest.importorskip("asyncpg")
pytestmark = pytest.mark.integration

ADMIN_URL = os.getenv("TEST_ADMIN_URL", "")
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SVC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)  # للـ`import main` (خدمة scout-ingest)
_A = "00000000-0000-0000-0000-0000000000aa"
_B = "00000000-0000-0000-0000-0000000000bb"


def _h(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


@pytest.fixture
async def live_app():
    if not ADMIN_URL:
        pytest.skip("TEST_ADMIN_URL unset")
    try:
        admin = await asyncpg.connect(ADMIN_URL, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"admin PG unavailable: {type(exc).__name__}")
    for f in (
        "migrations/v197_external_submissions_ingest.sql",
        "migrations/v198_external_ingest_sources.sql",
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
        GRANT SELECT ON external_ingest_sources TO sahool_ingest_resolver;
        ALTER FUNCTION resolve_ingest_source(TEXT) OWNER TO sahool_ingest_resolver;
        GRANT SELECT, INSERT ON external_submissions TO sahool_ingest;
        GRANT USAGE, SELECT ON SEQUENCE external_submissions_id_seq TO sahool_ingest;
        GRANT EXECUTE ON FUNCTION resolve_ingest_source(TEXT) TO sahool_ingest;
        CREATE TABLE IF NOT EXISTS fields (field_id TEXT PRIMARY KEY, tenant_id UUID NOT NULL);
        ALTER TABLE fields ENABLE ROW LEVEL SECURITY; ALTER TABLE fields FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS t ON fields;
        CREATE POLICY t ON fields USING (tenant_id::text = NULLIF(current_setting('app.current_tenant', true), ''));
        GRANT SELECT ON fields TO sahool_ingest;
    """)
    # TRUNCATE لا يُطلق trigger الحذف الصفّيّ (الجدول append-only) — تنظيف سليم بين الاختبارات.
    await admin.execute("DELETE FROM external_ingest_sources; TRUNCATE external_submissions;")
    await admin.execute(
        "INSERT INTO fields VALUES ('fb',$1) ON CONFLICT DO NOTHING", __import__("uuid").UUID(_B)
    )
    await admin.execute(
        "INSERT INTO external_ingest_sources(tenant_id,provider,server,form_id,token_hash,mapping_version,enabled)"
        " VALUES ($1,'odk','sA','fb',$2,'1.0.0',false),($3,'odk','sB','fb',$4,'1.0.0',true),"
        "        ($3,'kobo','sK','fb',$5,'1.0.0',true)",  # B1.4: مصدر Kobo مُفعَّل
        __import__("uuid").UUID(_A),
        _h("tokA"),
        __import__("uuid").UUID(_B),
        _h("tokB"),
        _h("tokK"),
    )
    await admin.close()

    os.environ["DATABASE_URL"] = "postgresql://sahool_ingest:ingpw@" + ADMIN_URL.split("@", 1)[1]
    os.environ["SCOUT_INGEST_ENABLED"] = "1"
    for p in (_REPO, _SVC):  # _REPO لـshared، _SVC لـ`import main`
        if p not in os.sys.path:
            os.sys.path.append(p)
    import main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    yield TestClient(main.app)


def _post(client, tok, body, path="odk"):
    h = {"X-Scout-Ingest-Token": tok} if tok else {}
    return client.post(f"/internal/ingest/submissions/{path}", json=body, headers=h)


async def test_full_ingest_path_live(live_app) -> None:
    c = live_app
    assert _post(c, None, {"field_id": "fb"}).status_code == 401
    assert _post(c, "nope", {"field_id": "fb"}).status_code == 403
    assert _post(c, "tokA", {"field_id": "fb"}).status_code == 403  # disabled source, B untouched
    r = _post(c, "tokB", {"meta": {"instanceID": "i1"}, "field_id": "fb", "value": 3})
    assert r.status_code == 200 and r.json()["outcome"] == "accepted"
    r = _post(c, "tokB", {"meta": {"instanceID": "i1"}, "field_id": "fb", "value": 3})
    assert r.status_code == 200 and r.json()["outcome"] == "idempotent_replay"
    r = _post(c, "tokB", {"meta": {"instanceID": "i1"}, "field_id": "fb", "value": 999})
    assert r.status_code == 202 and r.json()["outcome"] == "quarantined"
    assert "duplicate_key_divergent_payload" in r.json()["quarantine_reasons"]


async def test_kobo_path_live(live_app) -> None:
    """B1.4: مسار Kobo — نفس المسار المُصادَق، محوّل Kobo (meta/instanceID مسطّح + _submission_time)."""
    c = live_app
    assert _post(c, None, {"field_id": "fb"}, path="kobo").status_code == 401
    r = _post(
        c,
        "tokK",
        {
            "meta/instanceID": "uuid:k1",
            "_submission_time": "2026-07-19T08:00:00",
            "field_id": "fb",
            "value": 5,
        },
        path="kobo",
    )
    assert r.status_code == 200 and r.json()["outcome"] == "accepted"
    # نفس الخانة (نفس instanceID) بنفس الجسم ⇒ إعادة idempotent؛ توكن ODK لا يصل لمصدر Kobo.
    r = _post(
        c,
        "tokK",
        {
            "meta/instanceID": "uuid:k1",
            "_submission_time": "2026-07-19T08:00:00",
            "field_id": "fb",
            "value": 5,
        },
        path="kobo",
    )
    assert r.status_code == 200 and r.json()["outcome"] == "idempotent_replay"
