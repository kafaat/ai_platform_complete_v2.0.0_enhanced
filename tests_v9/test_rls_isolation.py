"""
tests_v9/test_rls_isolation.py — Real RLS Cross-Tenant Isolation Tests

يتحقّق أنّ RLS يمنع تسرّب البيانات بين المستأجرين عمليّاً.

FIX (هذا الملف كان لا يعمل إطلاقاً — أخطاء متعدّدة صُحّحت):
  • العمود كان 'name' والصحيح 'field_name' (UndefinedColumn).
  • متغيّر الجلسة كان 'app.tenant_id' بينما السياسات تقرأ 'app.current_tenant'.
  • كان 'SET LOCAL ...' خارج معاملة ⇒ لا يدوم (asyncpg autocommit) ⇒ استُبدل
    بـset_config(..., is_local=false) الذي يدوم على الاتّصال.
  • كان يتّصل كـsuperuser فيتجاوز RLS كليّاً ⇒ الآن ننفّذ استعلامات المستأجر
    عبر دور غير ممتاز (SET ROLE) ليُطبَّق RLS فعلاً.

يعمل عبر: pytest -m integration   (يتخطّى تلقائيّاً إن لم تتوفّر قاعدة البيانات)
"""

import os
import uuid

import asyncpg
import pytest

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@localhost:5433/sahool_test",
)

RLS_ROLE = "sahool_rls_test"  # دور غير ممتاز يُطبَّق عليه RLS


async def _connect():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@pytest.fixture
async def db():
    """اتّصال superuser للإعداد/التنظيف + تهيئة دور غير ممتاز يُطبَّق عليه RLS."""
    try:
        conn = await _connect()
    except Exception as e:
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")
    # دور غير ممتاز (idempotent) + صلاحيّات على الجداول المستخدمة
    await conn.execute(f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{RLS_ROLE}') THEN
                CREATE ROLE {RLS_ROLE} NOSUPERUSER NOBYPASSRLS;
            END IF;
        END $$;
    """)
    await conn.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
    await conn.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON field_boundaries, ndvi_timeseries TO {RLS_ROLE}"
    )
    yield conn
    await conn.execute("RESET ROLE")
    await conn.close()


async def _as_tenant(db, tenant):
    """نفّذ ما يلي كمستأجر عبر دور غير ممتاز (RLS يُطبَّق) + اضبط السياق."""
    await db.execute(f"SET ROLE {RLS_ROLE}")
    await db.execute("SELECT set_config('app.current_tenant', $1, false)", str(tenant))


@pytest.fixture
async def setup_two_tenants(db):
    """ينشئ حقلاً لكلّ من المستأجرَين A و B (كـsuperuser، RLS متجاوَز للإعداد)."""
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    field_a_id, field_b_id = f"rls-A-{uuid.uuid4().hex[:8]}", f"rls-B-{uuid.uuid4().hex[:8]}"

    await db.execute("RESET ROLE")
    await db.execute(
        """
        INSERT INTO field_boundaries (field_id, tenant_id, geom, field_name)
        VALUES ($1, $2, ST_GeomFromText('POLYGON((44 15, 44.01 15, 44.01 15.01, 44 15.01, 44 15))', 4326), 'حقل A'),
               ($3, $4, ST_GeomFromText('POLYGON((45 16, 45.01 16, 45.01 16.01, 45 16.01, 45 16))', 4326), 'حقل B')
        ON CONFLICT (field_id) DO NOTHING
    """,
        field_a_id,
        tenant_a,
        field_b_id,
        tenant_b,
    )

    yield {
        "tenant_a": tenant_a,
        "field_a_id": field_a_id,
        "tenant_b": tenant_b,
        "field_b_id": field_b_id,
    }

    # تنظيف (يعود لـsuperuser أوّلاً)
    await db.execute("RESET ROLE")
    await db.execute(
        "DELETE FROM ndvi_timeseries WHERE field_id IN ($1, $2)", field_a_id, field_b_id
    )
    await db.execute(
        "DELETE FROM field_boundaries WHERE field_id IN ($1, $2)", field_a_id, field_b_id
    )


@pytest.mark.integration
class TestRLSCrossTenant:
    """يتحقّق أنّ RLS فعلاً يمنع التسرّب بين المستأجرين."""

    async def test_tenant_a_sees_only_own_fields(self, db, setup_two_tenants):
        s = setup_two_tenants
        await _as_tenant(db, s["tenant_a"])
        ids = [r["field_id"] for r in await db.fetch("SELECT field_id FROM field_boundaries")]
        assert s["field_a_id"] in ids, "A يجب أن يرى حقله"
        assert s["field_b_id"] not in ids, "🚨 تسرّب! A يرى حقل B (RLS مكسور)"

    async def test_tenant_b_cannot_read_a_data(self, db, setup_two_tenants):
        s = setup_two_tenants
        await _as_tenant(db, s["tenant_b"])
        rows = await db.fetch("SELECT * FROM field_boundaries WHERE field_id = $1", s["field_a_id"])
        assert len(rows) == 0, "🚨 B استطاع قراءة حقل A بالـid المباشر"

    async def test_tenant_b_cannot_update_a_data(self, db, setup_two_tenants):
        s = setup_two_tenants
        await _as_tenant(db, s["tenant_b"])
        result = await db.execute(
            "UPDATE field_boundaries SET field_name = 'HACKED' WHERE field_id = $1", s["field_a_id"]
        )
        assert int(result.split()[-1]) == 0, "🚨 B استطاع تعديل حقل A"
        await _as_tenant(db, s["tenant_a"])
        row = await db.fetchrow(
            "SELECT field_name FROM field_boundaries WHERE field_id = $1", s["field_a_id"]
        )
        assert row["field_name"] == "حقل A", "اسم الحقل تغيّر — RLS مكسور!"

    async def test_tenant_b_cannot_delete_a_data(self, db, setup_two_tenants):
        s = setup_two_tenants
        await _as_tenant(db, s["tenant_b"])
        result = await db.execute(
            "DELETE FROM field_boundaries WHERE field_id = $1", s["field_a_id"]
        )
        assert int(result.split()[-1]) == 0, "🚨 B استطاع حذف حقل A"

    async def test_no_session_tenant_means_no_access(self, db, setup_two_tenants):
        s = setup_two_tenants
        await _as_tenant(db, "")  # سياق فارغ
        ids = [r["field_id"] for r in await db.fetch("SELECT field_id FROM field_boundaries")]
        assert s["field_a_id"] not in ids, "🚨 بدون مستأجر يرى حقل A"
        assert s["field_b_id"] not in ids, "🚨 بدون مستأجر يرى حقل B"


@pytest.mark.integration
class TestRLSIndicatorsTimeseries:
    """RLS على ndvi_timeseries — مستأجر لا يرى timeseries غيره."""

    async def test_ndvi_isolated_by_tenant(self, db, setup_two_tenants):
        s = setup_two_tenants
        await db.execute("RESET ROLE")
        await db.execute(
            """
            INSERT INTO ndvi_timeseries (field_id, tenant_id, acquisition_date, ndvi_mean, source)
            VALUES ($1, $2, CURRENT_DATE, 0.65, 'sentinel-2')
        """,
            s["field_a_id"],
            s["tenant_a"],
        )
        await _as_tenant(db, s["tenant_b"])
        rows = await db.fetch("SELECT * FROM ndvi_timeseries WHERE field_id = $1", s["field_a_id"])
        assert len(rows) == 0, "🚨 B يرى NDVI الخاص بـA"


@pytest.mark.integration
class TestRLSEdgeCases:
    """حالات قد يستغلّها مهاجم."""

    async def test_sql_injection_in_tenant_id_no_bypass(self, db, setup_two_tenants):
        s = setup_two_tenants
        await db.execute(f"SET ROLE {RLS_ROLE}")
        # قيمة خبيثة في السياق — السياسة تقارن UUID؛ القيمة غير الصالحة لا تطابق
        await db.execute("SELECT set_config('app.current_tenant', $1, false)", "' OR '1'='1")
        try:
            ids = [
                str(r["field_id"]) for r in await db.fetch("SELECT field_id FROM field_boundaries")
            ]
            assert s["field_a_id"] not in ids and s["field_b_id"] not in ids, (
                "🚨 SQL injection اخترق RLS"
            )
        except asyncpg.PostgresError:
            pass  # متوقّع: cast لـUUID يفشل على القيمة غير الصالحة (لا تسرّب)
