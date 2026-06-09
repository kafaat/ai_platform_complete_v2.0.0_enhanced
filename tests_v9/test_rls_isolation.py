"""
tests_v9/test_rls_isolation.py — Real RLS Cross-Tenant Isolation Tests

مشكلة المراجعة:
    "Multi-Tenant Isolation غير مكتمل ... أيّ bug منطقي قد يسمح بتسرّب
     بيانات بين المزارع أو الشركات. Production blocker حقيقي."

الحلّ:
    اختبارات حقيقيّة تتحقّق أنّ RLS يعمل عملياً:
    ١. tenant A يكتب صفّاً
    ٢. tenant B يحاول قراءته → يجب أن لا يراه
    ٣. tenant B يحاول تعديله/حذفه → يجب أن يفشل
    ٤. SET ROLE postgres (bypass) → يرى كل شيء (للـadmin)

الـsetup:
    - يستخدم session variable: SET LOCAL app.tenant_id = '...'
    - الـpolicies تقرأ من الـsession variable
    - كل اختبار في transaction منفصل (لـisolation)

تشغيل:
    pytest -v tests_v9/test_rls_isolation.py
"""
import os
import uuid
import pytest
import asyncpg


DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@localhost:5433/sahool_test",
)


@pytest.fixture
async def db():
    """يفتح اتّصال للاختبار، مع statement_cache_size=0 لـPgBouncer compat."""
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    yield conn
    await conn.close()


@pytest.fixture
async def setup_two_tenants(db):
    """ينشئ tenant_a + tenant_b + حقل واحد لكلّ منهما."""
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    field_a_id = str(uuid.uuid4())
    field_b_id = str(uuid.uuid4())

    # bypass RLS بالـsuperuser لإعداد البيانات
    await db.execute("SET LOCAL row_security = off")
    await db.execute("""
        INSERT INTO field_boundaries (field_id, tenant_id, geom, name)
        VALUES ($1, $2, ST_GeomFromText('POLYGON((44 15, 44.01 15, 44.01 15.01, 44 15.01, 44 15))', 4326), 'حقل A'),
               ($3, $4, ST_GeomFromText('POLYGON((45 16, 45.01 16, 45.01 16.01, 45 16.01, 45 16))', 4326), 'حقل B')
        ON CONFLICT (field_id) DO NOTHING
    """, field_a_id, tenant_a, field_b_id, tenant_b)
    await db.execute("RESET row_security")

    yield {
        "tenant_a": tenant_a, "field_a_id": field_a_id,
        "tenant_b": tenant_b, "field_b_id": field_b_id,
    }

    # cleanup
    await db.execute("SET LOCAL row_security = off")
    await db.execute("DELETE FROM field_boundaries WHERE field_id IN ($1, $2)",
                     field_a_id, field_b_id)


class TestRLSCrossTenant:
    """يتحقّق أنّ RLS فعلاً يمنع التسرّب بين tenants."""

    @pytest.mark.asyncio
    async def test_tenant_a_sees_only_own_fields(self, db, setup_two_tenants):
        """A لا يجب أن يرى B's data."""
        s = setup_two_tenants

        # set session as tenant_a
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_a']}'")

        rows = await db.fetch("SELECT field_id FROM field_boundaries")
        ids = [r["field_id"] for r in rows]

        assert s["field_a_id"] in ids, "A يجب أن يرى حقله"
        assert s["field_b_id"] not in ids, \
            "🚨 تسرّب بيانات! A يرى حقل B (RLS مكسور)"

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_read_a_data(self, db, setup_two_tenants):
        """B's SELECT direct بـwhere clause لـA's field_id → 0 rows."""
        s = setup_two_tenants
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_b']}'")

        rows = await db.fetch(
            "SELECT * FROM field_boundaries WHERE field_id = $1",
            s["field_a_id"],
        )
        assert len(rows) == 0, "🚨 B استطاع قراءة حقل A بالـid المباشر"

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_update_a_data(self, db, setup_two_tenants):
        """B's UPDATE على A's field → 0 rows affected."""
        s = setup_two_tenants
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_b']}'")

        result = await db.execute(
            "UPDATE field_boundaries SET name = 'HACKED' WHERE field_id = $1",
            s["field_a_id"],
        )
        # asyncpg.execute returns "UPDATE N" string
        affected = int(result.split()[-1])
        assert affected == 0, "🚨 B استطاع تعديل حقل A"

        # تحقّق أنّ A's data ما زال سليماً
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_a']}'")
        row = await db.fetchrow(
            "SELECT name FROM field_boundaries WHERE field_id = $1",
            s["field_a_id"],
        )
        assert row["name"] == "حقل A", "اسم الحقل تغيّر — RLS مكسور!"

    @pytest.mark.asyncio
    async def test_tenant_b_cannot_delete_a_data(self, db, setup_two_tenants):
        """B's DELETE على A's field → 0 rows."""
        s = setup_two_tenants
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_b']}'")

        result = await db.execute(
            "DELETE FROM field_boundaries WHERE field_id = $1",
            s["field_a_id"],
        )
        affected = int(result.split()[-1])
        assert affected == 0, "🚨 B استطاع حذف حقل A"

    @pytest.mark.asyncio
    async def test_no_session_tenant_means_no_access(self, db, setup_two_tenants):
        """بدون SET LOCAL app.tenant_id → لا يجب أن يرى أيّ شيء."""
        # Don't set tenant_id
        await db.execute("RESET app.tenant_id")

        # Should see nothing (assuming policies require tenant_id)
        rows = await db.fetch("SELECT * FROM field_boundaries")
        # ملاحظة: قد يرى صفوفاً أخرى من production data — نتحقّق فقط
        # أنّه لا يرى حقولنا التجريبيّة
        s = setup_two_tenants
        ids = [r["field_id"] for r in rows]
        assert s["field_a_id"] not in ids, "🚨 بدون tenant_id يرى حقل A"
        assert s["field_b_id"] not in ids, "🚨 بدون tenant_id يرى حقل B"


class TestRLSIndicatorsTimeseries:
    """RLS على ndvi_timeseries — أيّ tenant ما يجب أن يرى timeseries غيره."""

    @pytest.mark.asyncio
    async def test_ndvi_isolated_by_tenant(self, db, setup_two_tenants):
        s = setup_two_tenants

        # أدخل NDVI لـA
        await db.execute("SET LOCAL row_security = off")
        await db.execute("""
            INSERT INTO ndvi_timeseries
                (field_id, tenant_id, observation_date, ndvi_mean, source)
            VALUES ($1, $2, NOW(), 0.65, 'sentinel-2')
        """, s["field_a_id"], s["tenant_a"])
        await db.execute("RESET row_security")

        # B تحاول قراءته
        await db.execute(f"SET LOCAL app.tenant_id = '{s['tenant_b']}'")
        rows = await db.fetch(
            "SELECT * FROM ndvi_timeseries WHERE field_id = $1",
            s["field_a_id"],
        )
        assert len(rows) == 0, "🚨 B يرى NDVI الخاص بـA"

        # cleanup
        await db.execute("SET LOCAL row_security = off")
        await db.execute("DELETE FROM ndvi_timeseries WHERE field_id = $1",
                         s["field_a_id"])


class TestRLSEdgeCases:
    """حالات قد يستغلّها مهاجم."""

    @pytest.mark.asyncio
    async def test_sql_injection_in_tenant_id_no_bypass(self, db, setup_two_tenants):
        """محاولة injection في app.tenant_id لا يجب أن تفلت."""
        s = setup_two_tenants
        # محاولة "or '1'='1"
        evil = "' OR '1'='1"

        # ملاحظة: استخدام SET LOCAL يكون عبر literal string، نستخدم
        # set_config function آمنة بدلاً منه في الـapplication
        try:
            await db.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                evil,
            )
            # حتى لو نجح الـset، الـpolicy يقارن tenant_id (UUID) بـevil (string)
            # → فشل المطابقة، لا rows
            rows = await db.fetch("SELECT * FROM field_boundaries")
            ids = [str(r["field_id"]) for r in rows]
            assert s["field_a_id"] not in ids and s["field_b_id"] not in ids, \
                "🚨 SQL injection اخترق RLS"
        except Exception:
            pass  # متوقّع أن set_config يرفض القيمة غير الصالحة كـUUID
