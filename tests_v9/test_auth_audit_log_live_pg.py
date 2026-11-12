"""R-H3: سجلّ التدقيق الأمنيّ لـauth يصل فعلاً إلى ``audit_log`` — على القاعدة الحقيقيّة.

**العطل المقيس:** من كلّ أحداث auth كانت أربعة أنواعٍ فقط تصل؛ الدخول والتسجيل
والأدوار وكلمات المرور وMFA تضيع صامتةً لثلاثة أسباب مجتمعة:
  1. ``audit_log`` تحت FORCE RLS بـWITH CHECK (v237) يشترط ``tenant_id`` = مستأجِر السياق،
     وauth لا تضبط ``app.current_tenant`` ⇒ كلّ صفّ يحمل ``tenant_id`` يُرفَض.
  2. مواقع النداء تمرّر ``"authenticated"``/``"system"`` إلى عمود ``inet`` ⇒ يُرفَض الصفّ كلّه.
  3. المساعِد يبتلع الخطأ.

يُقاس هنا بالمساعِد الحقيقيّ (``main.audit_log``) على مسبح asyncpg حقيقيّ بدورٍ مقيَّد
(لا بديلَ اتّصال — FAKE-CONNECTION-ENFORCES-NOTHING-01)، والصفوف تُقرأ بالدور المدير.

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from tests_v9.service_module import load_service_main

pytestmark = [pytest.mark.integration, pytest.mark.slow]

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً حيّة ودوراً مقيَّداً",
    )
)

_CLIENT = "203.0.113.25"


async def _scenario(main):
    admin = await asyncpg.connect(_ADMIN_DSN)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=2, statement_cache_size=0)
    saved = main._pool
    tenant = str(uuid.uuid4())
    marker = f"rh3-{uuid.uuid4().hex[:10]}"
    try:
        role = await pool.fetchval("SELECT current_user")
        priv = await admin.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=$1", role
        )
        assert priv is not None and not priv["rolsuper"] and not priv["rolbypassrls"], (
            f"الدور {role} يتجاوز RLS ⇒ لا يقيس WITH CHECK"
        )
        user_id = await admin.fetchval(
            "INSERT INTO users (email, password_hash, full_name, tenant_id) "
            "VALUES ($1, 'x', 'R-H3 witness', $2::uuid) RETURNING id",
            f"{marker}@example.invalid",
            tenant,
        )
        main._pool = pool
        results = {
            # register/login: المستأجِر مُمرَّر صراحةً (كانت WITH CHECK ترفضه).
            "login": await main.audit_log(
                "login", user_id, _CLIENT, details=marker, tenant_id=tenant
            ),
            # change_password/MFA/reset: كانت تمرّر وسماً نصّيّاً بدل العنوان، وبلا مستأجِر.
            "mfa_disabled": await main.audit_log("mfa_disabled", user_id, _CLIENT, details=marker),
            "password_reset_confirm": await main.audit_log(
                "password_reset_confirm", user_id, "system", details=marker
            ),
        }
        rows = await admin.fetch(
            "SELECT action, host(ip_address) AS ip, tenant_id::text AS tenant "
            "FROM audit_log WHERE details=$1 ORDER BY id",
            marker,
        )
        return results, [dict(r) for r in rows], tenant
    finally:
        main._pool = saved
        await pool.close()
        await admin.close()


def test_auth_security_events_reach_the_audit_log_with_tenant_and_valid_ip():
    main = load_service_main("services/auth", required_attrs=("audit_log", "_acquire"))
    results, rows, tenant = asyncio.run(_scenario(main))
    by_action = {r["action"]: r for r in rows}
    assert set(by_action) == {"login", "mfa_disabled", "password_reset_confirm"}, rows
    assert all(r["tenant"] == tenant for r in rows), rows
    assert by_action["login"]["ip"] == _CLIENT
    assert by_action["mfa_disabled"]["ip"] == _CLIENT
    assert by_action["password_reset_confirm"]["ip"] is None  # وسمٌ غير عنوان ⇒ NULL لا ضياع
    assert results == dict.fromkeys(results, True)


def test_a_failed_audit_write_is_reported_not_swallowed(caplog):
    """قاعدةٌ ترفض الصفّ (مستأجِرٌ يخالف مستأجِر المستخدم) ⇒ ``False`` + سطر error مرئيّ."""
    main = load_service_main("services/auth", required_attrs=("audit_log", "_acquire"))

    async def run():
        pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=1, statement_cache_size=0)
        saved = main._pool
        main._pool = pool
        try:
            return await main.audit_log("login", None, _CLIENT, tenant_id="not-a-uuid")
        finally:
            main._pool = saved
            await pool.close()

    with caplog.at_level("ERROR"):
        ok = asyncio.run(run())
    assert ok is False
    assert any("audit_log row LOST" in r.getMessage() for r in caplog.records)
