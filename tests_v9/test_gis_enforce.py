"""DB-level geometry-validity enforcement (CI-enforced) — coverage audit layer 2.

is_valid_field_geom() existed since v13 but was used in the API layer only — a
direct INSERT (outside the API) of an invalid/self-intersecting polygon slipped
through. v27 adds a BEFORE-write trigger. This test exercises it against the
test DB (skips when no DB).
"""

from __future__ import annotations

import os
import uuid

import pytest

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)

_VALID = "POLYGON((0 0,0 1,1 1,1 0,0 0))"
_BOWTIE = "POLYGON((0 0,1 1,1 0,0 1,0 0))"  # متقاطع ذاتيّاً ⇒ ST_IsValid=false


@pytest.mark.integration
async def test_geom_validity_function_and_trigger():
    asyncpg = pytest.importorskip("asyncpg")
    try:
        conn = await asyncpg.connect(TEST_DB_URL, timeout=5)
    except Exception:  # noqa: BLE001
        pytest.skip("قاعدة الاختبار غير مشغّلة")

    try:
        # ① الدالّة: مربّع صالح ⇒ True، فراشة متقاطعة ذاتيّاً ⇒ False
        v = await conn.fetchval(
            "SELECT is_valid_field_geom(ST_SetSRID(ST_GeomFromText($1), 4326))", _VALID
        )
        assert v is True
        b = await conn.fetchval(
            "SELECT is_valid_field_geom(ST_SetSRID(ST_GeomFromText($1), 4326))", _BOWTIE
        )
        assert b is False

        # ② الـtrigger: إدراج هندسة باطلة في field_boundaries يجب أن يُرفَض
        tid = str(uuid.uuid4())
        tr = conn.transaction()
        await tr.start()
        try:
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tid)
            # نؤكّد رمز الخطأ المحدّد من enforce_valid_field_geom():
            # RAISE ... USING ERRCODE='check_violation' ⇒ SQLSTATE 23514. هكذا لا
            # يُعتبر أيّ فشل آخر (جدول مفقود/RLS/اتّصال) نجاحاً زائفاً (ملاحظة المراجعة).
            err_sqlstate = None
            try:
                await conn.execute(
                    "INSERT INTO field_boundaries (field_id, field_name, geom, tenant_id) "
                    "VALUES ($1, $2, ST_SetSRID(ST_GeomFromText($3), 4326), $4::uuid)",
                    "fld_gis_" + uuid.uuid4().hex[:8],
                    "اختبار",
                    _BOWTIE,
                    tid,
                )
            except Exception as e:  # noqa: BLE001
                err_sqlstate = getattr(e, "sqlstate", None)
            assert err_sqlstate == "23514", (
                f"متوقّع رفض الـtrigger بـcheck_violation (23514)، الفعليّ: {err_sqlstate}"
            )
        finally:
            await tr.rollback()
    finally:
        await conn.close()
