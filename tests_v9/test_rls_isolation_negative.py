"""تدقيق عزل المستأجِرين (RLS) — حارس بنيويّ على مستوى الكتالوج، يُنفَّذ في CI.

سياق: مراجعة معماريّة ادّعت «ثغرات حرجة» (field_lifecycle/sharing_keys بلا سياسة).
التحقّق المباشر من الترحيلات أثبت أنّها **خاطئة** — لكلّ جدول tenant_id سياسة عزل
+ FORCE. وكان حارس RLS الوحيد سكربت shell يتيماً (tests_v9/test_rls_enforcement.sh
غير مربوط بـCI). هذا الاختبار يجعل الضمان **محروساً آليّاً** على قاعدة مُرحَّلة
فعليّة (وظيفة integration في CI تطبّق كلّ الترحيلات قبل التشغيل).

ثلاثة ثوابت (مُتحقَّقة ثابتاً من الترحيلات، فتمرّ في CI):
  A. لا جدول RLS مُفعَّل دون FORCE (مالك الجدول لا يتجاوز العزل).
  B. كلّ جدول RLS مُفعَّل له سياسة واحدة على الأقلّ (FORCE بلا سياسة = منع الكلّ).
  C. كلّ جدول قاعديّ يحوي عمود tenant_id عليه RLS مُفعَّل (ضمان عدم التسرّب).

يتخطّى تلقائيّاً إن لم تتوفّر قاعدة الاختبار (مثل بقيّة اختبارات integration).
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.integration]

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test",
)

# جداول مُعفاة صراحةً (بمبرّر) من الثابت C — فارغة الآن: كلّ جداول tenant_id مُغطّاة.
# أيّ إضافة هنا تتطلّب مبرّراً مكتوباً (لماذا جدول tenant_id لا يحتاج RLS).
_TENANT_RLS_EXEMPT: set[str] = set()


@pytest.fixture
async def conn():
    asyncpg = pytest.importorskip("asyncpg")
    try:
        c = await asyncpg.connect(DATABASE_URL, timeout=5)
    except Exception as e:  # noqa: BLE001 — قاعدة غير متاحة ⇒ تخطٍّ لا فشل زائف
        pytest.skip(f"قاعدة الاختبار غير متاحة: {type(e).__name__}")
    try:
        yield c
    finally:
        await c.close()


async def test_no_rls_table_without_force(conn):
    """A: لا جدول RLS مُفعَّل دون FORCE — وإلّا يتجاوز مالك الجدول العزل."""
    rows = await conn.fetch(
        """
        SELECT relname FROM pg_class
        WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
          AND relrowsecurity AND NOT relforcerowsecurity
        ORDER BY relname
        """
    )
    offenders = [r["relname"] for r in rows]
    assert offenders == [], f"جداول RLS بلا FORCE (تسرّب عبر مالك الجدول): {offenders}"


async def test_every_rls_table_has_policy(conn):
    """B: كلّ جدول RLS مُفعَّل له سياسة — FORCE بلا سياسة يمنع كلّ وصول (كسر وظيفيّ)."""
    rows = await conn.fetch(
        """
        SELECT c.relname FROM pg_class c
        WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
          AND c.relrowsecurity
          AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)
        ORDER BY c.relname
        """
    )
    offenders = [r["relname"] for r in rows]
    assert offenders == [], f"جداول RLS مُفعَّلة بلا أيّ سياسة: {offenders}"


async def test_every_tenant_table_has_rls(conn):
    """C: كلّ جدول قاعديّ بعمود tenant_id عليه RLS مُفعَّل — ضمان عدم التسرّب."""
    rows = await conn.fetch(
        """
        SELECT c.relname FROM pg_class c
        JOIN information_schema.columns col
          ON col.table_schema = 'public'
         AND col.table_name = c.relname
         AND col.column_name = 'tenant_id'
        WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
          AND NOT c.relrowsecurity
        ORDER BY c.relname
        """
    )
    offenders = sorted({r["relname"] for r in rows} - _TENANT_RLS_EXEMPT)
    assert offenders == [], f"جداول تحوي tenant_id دون RLS (تسرّب محتمل عبر المستأجِرين): {offenders}"


async def test_tenant_policy_uses_current_setting(conn):
    """تأكيد إضافيّ: سياسات العزل تستند إلى current_setting('app.current_tenant')،
    لا سياسة دائمة الصدق (USING true) تُبطِل العزل."""
    rows = await conn.fetch(
        """
        SELECT c.relname, p.polname, pg_get_expr(p.polqual, p.polrelid) AS qual
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        WHERE c.relnamespace = 'public'::regnamespace
          AND c.relrowsecurity
          AND p.polname LIKE '%tenant%'
        """
    )
    bad = [(r["relname"], r["polname"]) for r in rows if "current_setting" not in (r["qual"] or "")]
    assert bad == [], f"سياسات «tenant» لا تستند إلى current_setting (عزل وهميّ): {bad}"
