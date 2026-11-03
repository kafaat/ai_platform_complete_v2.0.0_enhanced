"""v237 — تسرّبات عزل المستأجرين المقيسة (تدقيق 2026-11-01) مُغلَقة على PostgreSQL حيّة.

كلّ اختبار هنا **أحمر على main قبل v237** (مقيس على PG 16 مبنيّة من MANIFEST) وأخضر بعده،
ويحمل شاهداً موجباً حتى لا يُقرأ «منعُ كلّ شيء» عزلاً:

* T1 — VIEW يملكه superuser بلا security_invoker يُقرأ بصلاحيّة المالك فيتخطّى RLS.
* T2 — كتابة بلا سياق مستأجر لمستأجر آخر (webhook_subscriptions) كانت تنجح.
* T7 — صفوف tenant_id IS NULL مرئيّة لكلّ مستأجر؛ تفضيلات إشعار مستخدم آخر (هاتف) مرئيّة.
* T8 — بلا سياق مستأجر تُرى رموز الدعوات بنصّها.
* T9 — tenant_id = '' دلوٌ مشترك على جداول tenant_id النصّيّ.

الدور في ``TEST_DATABASE_URL`` يجب أن يكون مقيَّداً (يُتحقَّق قبل القياس). سياق المستأجر يُضبط
على مستوى الجلسة والاتّصال يُغلَق بعد كلّ قياس، والزرع يُحذف في ``finally``.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""
_A = "aaaaaaaa-3700-4000-8000-00000000000a"
_B = "bbbbbbbb-3700-4000-8000-00000000000b"

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً مُهاجَرة ودوراً مقيَّداً",
    )
)


async def _app(**gucs: str):
    conn = await asyncpg.connect(_APP_DSN)
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row is not None and not row["rolsuper"] and not row["rolbypassrls"], (
        "TEST_DATABASE_URL ليس دوراً مقيَّداً — لا يقيس عزلاً"
    )
    for name, value in gucs.items():
        await conn.execute("SELECT set_config($1, $2, false)", f"app.{name}", value)
    return conn


@pytest.mark.asyncio
async def test_t1_owner_views_no_longer_bypass_rls():
    tag = f"v237-ndvi-{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(
            "INSERT INTO ndvi_timeseries (field_id, acquisition_date, ndvi_mean, tenant_id) "
            "VALUES ($1, CURRENT_DATE, 0.5, $2::uuid)",
            tag,
            _B,
        )
        for tenant, expected in ((_A, 0), (_B, 1)):  # سالب ثمّ موجب
            app = await _app(current_tenant=tenant)
            try:
                seen = await app.fetchval(
                    "SELECT count(*) FROM v_latest_ndvi WHERE field_id = $1", tag
                )
            finally:
                await app.close()
            assert seen == expected, f"v_latest_ndvi as {tenant}: {seen} != {expected}"
        offenders = await admin.fetchval(
            """SELECT string_agg(c.relname, ', ') FROM pg_class c
               WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'v'
                 AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                                 AND d.objid = c.oid AND d.deptype = 'e')
                 AND NOT EXISTS (SELECT 1 FROM pg_options_to_table(c.reloptions) o
                                 WHERE o.option_name = 'security_invoker'
                                   AND lower(o.option_value) IN ('true','on','1','yes'))"""
        )
        assert offenders is None, f"owner-privilege views: {offenders}"
    finally:
        await admin.execute("DELETE FROM ndvi_timeseries WHERE field_id = $1", tag)
        await admin.close()


@pytest.mark.asyncio
async def test_t2_write_for_another_tenant_without_context_is_denied():
    url = f"https://v237-{uuid.uuid4().hex[:8]}.example/hook"
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await _app()
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute(
                "INSERT INTO webhook_subscriptions (tenant_id, url, secret_ref) "
                "VALUES ($1::uuid, $2, 'x')",
                _B,
                url,
            )
        async with app.transaction():  # موجب: كتابة المستأجر لنفسه داخل سياقه
            await app.execute("SELECT set_config('app.current_tenant', $1, true)", _A)
            await app.execute(
                "INSERT INTO webhook_subscriptions (tenant_id, url, secret_ref) "
                "VALUES ($1::uuid, $2, 'x')",
                _A,
                url,
            )
    finally:
        await app.close()
        await admin.execute("DELETE FROM webhook_subscriptions WHERE url = $1", url)
        await admin.close()


@pytest.mark.asyncio
async def test_t7_null_tenant_rows_and_other_users_prefs_are_hidden():
    tag = f"v237-{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(
            "INSERT INTO actuator_command_outbox (tenant_id, field_id, command_id, actuator_type, "
            "protocol, target_id, command, idempotency_key) "
            "VALUES (NULL, gen_random_uuid(), $1, 'valve', 'mqtt', 't', '{}', $1)",
            tag,
        )
        await admin.execute(
            "INSERT INTO notification_preferences (tenant_id, user_ref, sms_number) "
            "VALUES ($1::uuid, $2, '+966-private')",
            _A,
            f"{tag}-u2",
        )
        app = await _app(current_tenant=_A, current_user_id=f"{tag}-u1")
        try:
            assert (
                await app.fetchval(
                    "SELECT count(*) FROM actuator_command_outbox WHERE idempotency_key = $1", tag
                )
                == 0
            )
            assert (
                await app.fetchval(
                    "SELECT count(*) FROM notification_preferences WHERE user_ref = $1",
                    f"{tag}-u2",
                )
                == 0
            )
        finally:
            await app.close()
        owner = await _app(current_tenant=_A, current_user_id=f"{tag}-u2")  # موجب
        try:
            assert (
                await owner.fetchval(
                    "SELECT count(*) FROM notification_preferences WHERE user_ref = $1",
                    f"{tag}-u2",
                )
                == 1
            )
        finally:
            await owner.close()
    finally:
        await admin.execute("DELETE FROM actuator_command_outbox WHERE idempotency_key = $1", tag)
        await admin.execute("DELETE FROM notification_preferences WHERE user_ref = $1", f"{tag}-u2")
        await admin.close()


@pytest.mark.asyncio
async def test_t8_no_tenant_context_reveals_no_invitation_token():
    token = f"v237-tok-{uuid.uuid4().hex}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(
            "INSERT INTO invitations (token, email, tenant_id, role, expires_at) "
            "VALUES ($1, 'b@example.com', $2::uuid, 'viewer', now() + interval '1 day')",
            token,
            _B,
        )
        app = await _app()
        try:
            assert (
                await app.fetchval("SELECT count(*) FROM invitations WHERE token = $1", token) == 0
            )
        finally:
            await app.close()
        service = await _app(current_role="admin")  # موجب: مسار خدمة auth الصريح
        try:
            assert (
                await service.fetchval("SELECT count(*) FROM invitations WHERE token = $1", token)
                == 1
            )
        finally:
            await service.close()
    finally:
        await admin.execute("DELETE FROM invitations WHERE token = $1", token)
        await admin.close()


@pytest.mark.asyncio
async def test_t9_empty_tenant_is_not_a_shared_bucket():
    pid = f"v237-{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await _app(current_tenant_id="")
    try:
        with pytest.raises((asyncpg.InsufficientPrivilegeError, asyncpg.CheckViolationError)):
            await app.execute(
                "INSERT INTO soil_spatial_products (product_id, tenant_id, field_id, product_type, "
                "dataset_version, geometry_hash, payload) VALUES ($1, '', 'f', 't', 'v', $1, '{}')",
                pid,
            )
        with pytest.raises(asyncpg.CheckViolationError):  # حتى المالك لا يكتب مستأجراً فارغاً
            await admin.execute(
                "INSERT INTO soil_spatial_products (product_id, tenant_id, field_id, product_type, "
                "dataset_version, geometry_hash, payload) VALUES ($1, '', 'f', 't', 'v', $1, '{}')",
                pid,
            )
    finally:
        await app.close()
        await admin.execute("DELETE FROM soil_spatial_products WHERE product_id = $1", pid)
        await admin.close()
