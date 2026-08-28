"""عزلُ المستأجرين بـRLS — مُثبَتٌ على PostgreSQL حيّة بدورٍ مقيَّد.

**ما يقيسه هذا الملفّ:** أنّ سياسةَ `RLS` تمنع دوراً مقيَّداً من رؤية صفوفِ مستأجرٍ
آخر — على قاعدةٍ حقيقيّة، لا بتحليلِ نصٍّ ولا بمحاكاة. وهو معيارُ قبولِ المرحلة ١
رقم ٤ («RLS حيّ بدور مقيّد»).

**والشاهدُ السالبُ وحدَه لا يُثبِت شيئاً — وهذا مقيسٌ لا مُرجَّح.** صيغةٌ سابقةٌ
لهذا الاختبار اكتفت بـ«لا يرى صفوفَ B ⇒ صفر» على جدولٍ فارغ. وقِيس على PG16:

    جدولٌ فارغ · RLS **مُفعَّلة**   ⇒ 0 صفّ ⇒ أخضر
    جدولٌ فارغ · RLS **مُعطَّلة**   ⇒ 0 صفّ ⇒ **أخضر أيضاً**

أي أنّ التأكيدَ يمرّ والعزلُ مُلغًى بالكامل. فالصفرُ كان يقيس **فراغَ الجدول** لا
عملَ السياسة. ولذلك ثلاثةُ شهودٍ هنا لا واحد:

1. **سالب:** المستأجر A لا يرى أيّاً من صفَّي B.
2. **موجب:** المستأجر A يرى صفَّه هو — فلو منع شيءٌ *كلَّ* القراءات (خطأُ صلاحيات،
   أو GUC فارغ) لبدا ذلك «عزلاً ناجحاً» وهو عمًى تامّ.
3. **إبطالُ الفراغ:** بتعطيل RLS تعود الصفوفُ الاثنان — فالتأكيدُ الأوّل يحمرّ
   حين يجب أن يحمرّ، ولا يخضرّ بالصدفة.

**ورابعٌ يسبقها جميعاً:** يُتحقَّق أنّ الدورَ المُعطى **مقيَّدٌ فعلاً**
(`rolsuper=f` و`rolbypassrls=f`). فالمستخدمُ الخارق يتجاوز RLS بحكم المحرّك، فلو
مُرِّر DSN خارقٌ لبدا الشاهدُ السالبُ فاشلاً والموجبُ ناجحاً بلا معنًى. تُقاس
الأداةُ قبل أن يُقاس بها.

**وعن `set_config(name, value, is_local)`:** الثالثةُ `true` تعني «محلّيٌّ
للمعاملة»، وعلى اتّصالٍ بوضع autocommit يُلغى فورَ انتهاء العبارة، فيقرأ الاستعلامُ
التالي سلسلةً فارغة ويسقط `::uuid`. وذلك عطلُ `GUC-SCOPE-GUARD-SEES-ONE-FILE-01`
بعينه. فهنا `false` (مستوى الجلسة) — والاتّصالُ يُغلَق بعد كلّ اختبار فلا يتسرّب.

**وحدُّ صدقٍ يُقال صراحةً:** هذا الملفّ يُنشئ جدولَه وسياستَه بنفسه. فالمُثبَتُ هنا
أنّ **المحرّكَ يعزل**، وأنّ **الدورَ مقيَّدٌ فعلاً**، وأنّ **مِقياسنا غيرُ فارغ** —
لا أنّ سياسات RLS المُعلَنة في هجرات المنصّة صحيحة. تلك شهادةٌ أخرى تحتاج قياساً على
جداول المنصّة نفسِها بعد تطبيق الهجرات، ولم تُدَّعَ هنا.

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg")

#: عرفُ المستودع نفسُه الذي تستعمله شهادتا IRR-F01 وH5.1: مُدير للتهيئة، ومقيَّدٌ
#: للقراءة المحروسة. **ولا قيمةَ افتراضيّة لأيّهما** — قيمةٌ افتراضيّة تُشغّل
#: الاختبارَ على قاعدةٍ لم يقصدها أحد، وقد وقع ذلك فعلاً في هذا المستودع حين رجع
#: اختبارٌ حيٌّ إلى `DATABASE_URL` فالتقط ما تكتبه وحداتٌ أخرى زمنَ الاستيراد.
_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""

#: على غرار `IRR_F01_CERTIFICATION_REQUIRED`: التخطّي مقبولٌ في التطوير، ومرفوضٌ
#: حين تُعلِن الوظيفةُ أنّها تشهد. وبلا هذا يمرّ غيابُ القاعدة خُضرةً صامتة.
_CERTIFICATION_REQUIRED = os.getenv("RLS_ISOLATION_CERTIFICATION_REQUIRED") == "1"

#: مخطّطٌ خاصٌّ لا `public`: جدولُ المسبار خارج الهجرات، ولو أُنشئ في `public` لرآه
#: أيُّ جردِ كتالوجٍ أو تأكيدِ RLS شاملٍ يمرّ بعده في الجلسة نفسِها فأدانه. ويُسقَط
#: في `finally` أيّاً كان المآل.
_SCHEMA = "rls_witness_ns"
_TABLE = f"{_SCHEMA}.fields"

_TENANT_A = "11111111-1111-1111-1111-111111111111"
_TENANT_B = "22222222-2222-2222-2222-222222222222"

if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "RLS_ISOLATION_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_ADMIN_URL "
        "وTEST_DATABASE_URL — الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً حيّة ودوراً مقيَّداً",
    )
)


async def _app_role_name(conn) -> str:
    return await conn.fetchval("SELECT current_user")


async def _seed(*, rls_enabled: bool) -> str:
    """يُهيّئ المخطَّط والسياسة والصفوف، ويُعيد اسمَ الدور المقيَّد كما تراه القاعدة."""
    app = await asyncpg.connect(_APP_DSN)
    try:
        role = await _app_role_name(app)
    finally:
        await app.close()

    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        await admin.execute(f"CREATE SCHEMA {_SCHEMA}")
        await admin.execute(
            f"CREATE TABLE {_TABLE} (id serial PRIMARY KEY, tenant_id uuid NOT NULL, name text)"
        )
        # **بلا `FORCE` عمداً — وذلك مقيسٌ لا إغفال.** زُرِعت طفرةٌ تنزعها فنجت
        # (٢ نجاح): الدورُ المقيَّد ليس مالكَ الجدول، فـ`FORCE` لا تُغيّر شيئاً في
        # هذا القياس. وسابقةُ هذا المستودع أن يُحذَف الاحتياطُ الذي ينجو من طفرته
        # بدل أن يبقى يُقرَأ حمايةً. (وهي تلزم حيث يقرأ **المالك** — وذلك قياسٌ آخر.)
        await admin.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
        await admin.execute(
            f"CREATE POLICY tenant_isolation ON {_TABLE} "
            "USING (tenant_id = current_setting('app.current_tenant_id')::uuid)"
        )
        await admin.execute(f'GRANT USAGE ON SCHEMA {_SCHEMA} TO "{role}"')
        await admin.execute(f'GRANT SELECT ON {_TABLE} TO "{role}"')
        await admin.executemany(
            f"INSERT INTO {_TABLE} (tenant_id, name) VALUES ($1, $2)",
            [
                (uuid.UUID(_TENANT_A), "field-A"),
                (uuid.UUID(_TENANT_B), "field-B1"),
                (uuid.UUID(_TENANT_B), "field-B2"),
            ],
        )
        if not rls_enabled:
            # شاهدُ إبطالِ الفراغ: تُنزَع الحمايةُ **بعد** الزرع، فيبقى كلُّ شيءٍ
            # آخرَ ثابتاً ولا يتغيّر إلّا المتغيّرُ المقصود.
            await admin.execute(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY")
    finally:
        await admin.close()
    return role


async def _drop() -> None:
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await admin.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
    finally:
        await admin.close()


async def _assert_role_is_actually_restricted(conn) -> None:
    """**تُقاس الأداةُ قبل أن يُقاس بها.**

    الدورُ الخارق يتجاوز RLS بحكم محرّك PostgreSQL لا بخللٍ في السياسة. فلو مُرِّر
    DSN خارقٌ في `TEST_DATABASE_URL` لصار هذا الملفّ يقيس شيئاً آخر تماماً ويُبلغ
    عنه باسم «العزل». فيُفشَل صراحةً بدل أن يُقرَأ حكماً على السياسة.
    """
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row is not None, "تعذّر قراءةُ خصائص الدور الحاليّ من pg_roles"
    assert not row["rolsuper"], (
        "الدورُ في TEST_DATABASE_URL خارق (rolsuper) — يتجاوز RLS بحكم المحرّك، "
        "فلا يقيس هذا الملفّ عزلاً. مرّر دوراً مقيَّداً."
    )
    assert not row["rolbypassrls"], (
        "الدورُ يحمل BYPASSRLS — السياسةُ لا تنطبق عليه أصلاً، والخُضرةُ هنا ستُقرَأ عزلاً وهي تجاوزٌ صريح."
    )


async def _read_as_tenant(tenant: str, target: str) -> int:
    """يفتح اتّصالاً مقيَّداً، يضبط الـGUC على مستوى الجلسة، ويعدّ صفوفَ `target`."""
    app = await asyncpg.connect(_APP_DSN)
    try:
        await _assert_role_is_actually_restricted(app)
        # `false` = مستوى الجلسة. و`true` تعني «محلّيٌّ للمعاملة» فيُلغى فورَ انتهاء
        # العبارة في وضع autocommit، فيقرأ التالي سلسلةً فارغة ويسقط `::uuid`.
        await app.execute("SELECT set_config('app.current_tenant_id', $1, false)", tenant)
        rows = await app.fetch(f"SELECT id FROM {_TABLE} WHERE tenant_id = $1", uuid.UUID(target))
        return len(rows)
    finally:
        await app.close()


@pytest.mark.asyncio
async def test_a_restricted_role_sees_its_own_rows_and_none_of_the_other_tenants():
    """الشاهدان معاً — والموجبُ ليس تزيّناً.

    السالبُ وحدَه يخضرّ على عمًى تامّ: خطأُ صلاحيّاتٍ يمنع كلَّ قراءة، أو GUC فارغ،
    كلاهما يُنتِج صفراً ويُقرَأ «عزلاً ناجحاً». فيُشترَط أن يرى A صفَّه في الجولة
    نفسِها، وإلّا فما قِيس ليس عزلاً بل انقطاع.
    """
    await _seed(rls_enabled=True)
    try:
        leaked = await _read_as_tenant(_TENANT_A, _TENANT_B)
        assert leaked == 0, f"تسريب: المستأجر A رأى {leaked} صفّاً من صفوف B"

        own = await _read_as_tenant(_TENANT_A, _TENANT_A)
        assert own == 1, f"المستأجر A لا يرى صفَّه ({own}) — فالصفرُ في الشاهد السالب عمًى لا عزل"
    finally:
        await _drop()


@pytest.mark.asyncio
async def test_the_isolation_assertion_is_not_vacuous_when_rls_is_off():
    """**بلا هذا لا يُعرَف أنّ الاختبارَ فوقه يقيس شيئاً.**

    قِيس على PG16 أنّ التأكيدَ «صفرُ صفوفٍ من B» يمرّ **أخضرَ** على جدولٍ فارغ
    سواءٌ كانت RLS مُفعَّلةً أم مُعطَّلةً كلّيّاً. فالشاهدُ الحقيقيُّ أن يعود الصفّان
    حين تُنزَع الحماية: عندئذٍ فقط يكون خضرةُ الاختبار الأوّل خبراً عن السياسة.
    """
    await _seed(rls_enabled=False)
    try:
        visible = await _read_as_tenant(_TENANT_A, _TENANT_B)
        assert visible == 2, (
            f"بتعطيل RLS ظهر {visible} صفّاً بدل 2 — التأكيدُ في الاختبار الأوّل "
            "لا يقيس العزل، بل يخضرّ لسببٍ آخر (فراغٌ أو انقطاعُ صلاحيّات)."
        )
    finally:
        await _drop()
