"""سياسةُ RLS على `imagery_automation_fields` — على القاعدة الحقيقيّة بعد الهجرات.

**الفجوةُ التي يسدّها:** `test_rls_tenant_isolation_live_pg.py` يُعلن حدَّه صراحةً —
يُنشئ جدولَه وسياستَه بنفسه، فيُثبِت أنّ **المحرّك يعزل** لا أنّ **سياساتِ الهجرات
صحيحة**. وأربعةُ جداول لها شاهدُها الحيّ، و`imagery_automation_fields` لم يكن لها
شاهد — رغم أنّها الجدولُ الذي وُلد منه عطلٌ صامت مقيس (#1009): المُجدوِل كان يقرؤها
بمسبح التطبيق بلا سياق، والسياسةُ فاشلةٌ-مغلقة، فتُرجِع **صفر صفوف بلا استثناء**
فيُقرأ «لا حقول مُتابَعة» صدقاً.

هنا تُقاس السياسةُ المُهاجَرة نفسُها، لا نسخةٌ منها:

1. **الدورُ مقيَّدٌ فعلاً** (`rolsuper=f` و`rolbypassrls=f`) — تُقاس الأداةُ أوّلاً.
2. **موجب:** بسياق المستأجر A يرى صفَّه.
3. **سالب:** بسياق A لا يرى صفَّ B.
4. **بلا سياق ⇒ صفر** — العطلُ الصامت مُثبَتاً لا موصوفاً: هذا هو سببُ ربط المُجدوِل
   بمسبح المهامّ.
5. **إبطالُ الفراغ:** الصفوفُ موجودةٌ فعلاً (يراها المُدير) — فالصفرُ في ٤ يقيس
   السياسةَ لا جدولاً فارغاً.

الحدُّ المُعلَن: يُقاس جدولٌ واحد. ولا يدّعي أنّ كلّ جداول الهجرة معزولةٌ صحيحاً.

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("IMAGERY_RLS_CERTIFICATION_REQUIRED") == "1"

# مراجعة #1014: `importorskip` قبل قراءة العَلَم كان يجعل غيابَ `asyncpg` على مُشغِّل الشهادة
# تخطّياً أخضرَ للوحدة كلّها — فالبوّابةُ تُعلِن شهادةً ولم تقِس شيئاً. النمطُ نفسُه في
# `test_irr_f01_reservation_live_pg.py`: تحت العَلَم يُرفَع خطأُ الاستيراد لا يُتخطّى.
try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""

_TABLE = "public.imagery_automation_fields"
_TENANT_A = "aaaaaaaa-0000-4000-8000-00000000000a"
_TENANT_B = "bbbbbbbb-0000-4000-8000-00000000000b"

if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "IMAGERY_RLS_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — "
        "الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً حيّة ودوراً مقيَّداً",
    )
)


def _field_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def _seed(admin, field_a: str, field_b: str) -> None:
    await admin.execute(
        f"INSERT INTO {_TABLE} (field_id, tenant_id, bbox_west, bbox_south, bbox_east, bbox_north)"
        " VALUES ($1,$2::uuid,44,15,45,16), ($3,$4::uuid,44,15,45,16)"
        " ON CONFLICT (field_id) DO NOTHING",
        field_a,
        _TENANT_A,
        field_b,
        _TENANT_B,
    )


async def _visible(conn, field_id: str) -> bool:
    return bool(
        await conn.fetchval(f"SELECT EXISTS(SELECT 1 FROM {_TABLE} WHERE field_id=$1)", field_id)
    )


@pytest.mark.asyncio
async def test_migrated_policy_isolates_and_returns_zero_without_context():
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await asyncpg.connect(_APP_DSN)
    field_a, field_b = _field_id("rls-a"), _field_id("rls-b")
    try:
        # (١) تُقاس الأداةُ قبل أن يُقاس بها: دورٌ خارق يتجاوز RLS بحكم المحرّك،
        # فلو مُرِّر DSN خارق لبدا كلُّ ما بعده بلا معنًى.
        role = await app.fetchval("SELECT current_user")
        privileges = await admin.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=$1", role
        )
        assert privileges is not None, f"الدور {role} غير موجود في pg_roles"
        assert not privileges["rolsuper"], f"الدور {role} خارق ⇒ يتجاوز RLS فلا يقيس شيئاً"
        assert not privileges["rolbypassrls"], f"الدور {role} يحمل BYPASSRLS"

        enabled = await admin.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid=$1::regclass",
            _TABLE,
        )
        assert enabled["relrowsecurity"], "RLS غير مُفعَّلة على الجدول بعد الهجرات"
        assert enabled["relforcerowsecurity"], "FORCE غائبة ⇒ المالكُ يتجاوز السياسة"

        await _seed(admin, field_a, field_b)
        # (٥) إبطالُ الفراغ: الصفّان موجودان فعلاً كما يراهما المُدير.
        assert await _visible(admin, field_a) and await _visible(admin, field_b)

        # (٢) و(٣): بسياق A يرى صفَّه ولا يرى صفَّ B.
        await app.execute("SELECT set_config('app.current_tenant', $1, false)", _TENANT_A)
        assert await _visible(app, field_a), "المستأجر لا يرى صفَّه ⇒ عمًى تامّ لا عزل"
        assert not await _visible(app, field_b), "تسريبٌ عبر المستأجرين"

        # (٤) بلا سياق ⇒ صفر صفوف **بلا استثناء**: العطلُ الصامت الذي أُغلق في #1009.
        #
        # **على اتّصالٍ جديد لا بـ`set_config('', …)` ولا بـ`RESET`** (مراجعة #1014
        # المكتومة). الفرقُ مقيسٌ على PostgreSQL 16 لا مُستنتَج:
        #
        #   غيرُ مضبوط  · `current_setting(name, true)`  ⇒ NULL
        #   غيرُ مضبوط  · `current_setting(name, false)` ⇒ **يرفع** unrecognized parameter
        #   مضبوطٌ فارغ · كلتا الصيغتين                  ⇒ سلسلةٌ فارغة بلا خطأ
        #
        # فضبطُه فارغاً يُنشئ حالةً **مختلفة** عن حالة المُجدوِل الحقيقيّة، وانحدارُ
        # السياسة من الصيغة المتساهلة إلى الصارمة كان يمرّ على هذا الشاهد بينما
        # القراءةُ الحيّة **تفشل بخطأ** لا تُرجِع صفراً. و`RESET` لا يكفي أيضاً:
        # قِيس أنّه يترك المُعامل مُعرَّفاً فارغاً. الاتّصالُ الجديد وحده يُعيد الغياب.
        fresh = await asyncpg.connect(_APP_DSN)
        try:
            with pytest.raises(asyncpg.exceptions.UndefinedObjectError):
                await fresh.fetchval("SELECT current_setting('app.current_tenant', false)")
            assert (
                await fresh.fetchval("SELECT current_setting('app.current_tenant', true)") is None
            )
            assert not await _visible(fresh, field_a)
            assert not await _visible(fresh, field_b)
            assert await fresh.fetchval(f"SELECT count(*) FROM {_TABLE}") == 0, (
                "قراءةٌ عابرةٌ للمستأجرين بلا سياق تُرجِع صفراً صامتاً — ولذلك يلزم دورٌ خدميّ"
            )
        finally:
            await fresh.close()
    finally:
        await app.close()
        try:
            await admin.execute(
                f"DELETE FROM {_TABLE} WHERE field_id = ANY($1::text[])", [field_a, field_b]
            )
        finally:
            await admin.close()
