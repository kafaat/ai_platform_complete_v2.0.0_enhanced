"""اختبار تصليب دور القاعدة الذي يُفرَض عليه RLS (فجوة B2 — عزل المستأجِرين).

عزل المستأجِرين في سهول يُفرَض عبر Row-Level Security مع FORCE ROW LEVEL
SECURITY (راجع migrations/v9_rls_force_all.sql). لكن RLS — بما فيه FORCE —
**يُتجاوَز كليّاً** إن اتّصل التطبيق بدور قاعدة بيانات:
  • superuser (rolsuper = true)، أو
  • ذي تجاوز RLS صريح (rolbypassrls = true).
في تلك الحال تُقرأ/تُكتب صفوف كلّ المستأجِرين بلا تصفية ⇒ خطر IDOR/تسرّب
عابر للمستأجِرين رغم وجود السياسات. لا حارس آليّ كان يكشف هذا الخطأ التشغيليّ.

يحتوي:
  • اختبار **unit** خفيف (static) يثبّت أنّ المتطلّب موثَّق في الترحيل، حتى
    يبقى تذكيراً تشغيليّاً حيّاً عند تعديل سياسات RLS.
  • اختبار **integration** يتّصل بـTEST_DATABASE_URL ويتحقّق من كتالوج Postgres
    (pg_roles) أنّ دور الاتّصال الفعليّ ليس superuser ولا يتجاوز RLS. يتخطّى
    بأمان (pytest.skip) إن تعذّر الاتّصال بالقاعدة — كنمط tests_v9/test_db_wiring.

يعمل عبر: pytest -m integration (في وظيفة Integration Tests بعد رفع Postgres).
محليّاً بلا قاعدة: اختبار التكامل يُتخطّى (skip)، واختبار الوحدة يمرّ.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# نفس مصدر العنوان المستخدَم في conftest.py وtest_db_wiring.py.
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)

_RLS_FORCE_MIGRATION = os.path.join(ROOT, "migrations", "v9_rls_force_all.sql")


# ── unit: حارس توثيق المتطلّب التشغيليّ ──────────────────────────────────────
@pytest.mark.unit
def test_rls_force_migration_documents_role_requirement():
    """الترحيل يجب أن يوثّق أنّ دور التطبيق ليس superuser ولا BYPASSRLS.

    حارس static (بلا DB) يمنع حذف التذكير التشغيليّ من الترحيل: FORCE وحده
    لا يكفي إن اتّصل التطبيق بدور ممتاز يتجاوز RLS.
    """
    assert os.path.exists(_RLS_FORCE_MIGRATION), f"ترحيل فرض RLS مفقود: {_RLS_FORCE_MIGRATION}"
    with open(_RLS_FORCE_MIGRATION, encoding="utf-8") as fh:
        text = fh.read().lower()

    assert "superuser" in text, (
        "migrations/v9_rls_force_all.sql لا يوثّق متطلّب 'ليس superuser' — "
        "دور superuser يتجاوز RLS فيُبطل عزل المستأجِرين رغم FORCE."
    )
    assert "bypassrls" in text or "bypass rls" in text, (
        "migrations/v9_rls_force_all.sql لا يوثّق متطلّب NOBYPASSRLS — "
        "دور BYPASSRLS يتجاوز RLS فيُبطل عزل المستأجِرين رغم FORCE."
    )


# ── integration: تحقّق فعليّ من دور الاتّصال عبر pg_roles ─────────────────────
async def _connect():
    import asyncpg

    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@pytest.mark.integration
class TestRLSRoleHardening:
    """الدور المخصّص للوصول المعزول بـRLS (sahool_app إنتاجاً / sahool_rls_test اختباراً)
    يجب ألّا يكون superuser ولا BYPASSRLS — وإلّا يُتجاوَز RLS رغم FORCE (تسرّب مستأجِرين).

    لا نفحص current_user: اتّصال الإعداد في الاختبار/CI يستعمل دوراً ممتازاً عمداً
    (لتطبيق الهجرات وتهيئة البيانات)؛ العزل الفعليّ يُفرَض عبر دور غير ممتاز منفصل
    (test_db_wiring يستعمل sahool_rls_test صراحةً لذلك). فالحارس الصحيح يفحص هذا الدور."""

    # أدوار يُفترَض أن يُفرَض عليها RLS (إنتاج/اختبار) — نفحص الموجود منها.
    _RLS_ROLE_CANDIDATES = ("sahool_app", "sahool_rls_test")

    async def test_rls_enforcing_role_not_superuser_and_not_bypassrls(self):
        try:
            conn = await _connect()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

        try:
            rows = await conn.fetch(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = ANY($1::text[])",
                list(self._RLS_ROLE_CANDIDATES),
            )
        finally:
            await conn.close()

        if not rows:
            pytest.skip(
                "لا دور RLS مخصّص ("
                + "/".join(self._RLS_ROLE_CANDIDATES)
                + ") في هذه القاعدة — تعذّر التحقّق."
            )

        for row in rows:
            role = row["rolname"]
            assert row["rolsuper"] is False, (
                f"🚨 دور RLS '{role}' superuser ⇒ يتجاوز RLS كليّاً (عزل المستأجِرين "
                "مكسور، خطر IDOR). يجب أن يكون NOSUPERUSER."
            )
            assert row["rolbypassrls"] is False, (
                f"🚨 دور RLS '{role}' ذو BYPASSRLS ⇒ يتجاوز RLS كليّاً (عزل المستأجِرين "
                "مكسور، خطر IDOR). يجب أن يكون NOBYPASSRLS."
            )
