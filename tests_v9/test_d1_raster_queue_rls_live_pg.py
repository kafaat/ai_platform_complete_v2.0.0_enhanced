"""سياسةُ RLS على `raster_cache_invalidations` — على القاعدة الحقيقيّة بعد الهجرات.

**الفجوةُ التي يسدّها:** D1 نقلت الكتابةَ إلى مالكها، وطابورُ الإبطال صار الجدولَ
الذي يحمل نيّاتِ مستأجرين مختلفين على **الحقل نفسِه** (المُوصِّلُ يُسلّم بعد الالتزام،
فصفّا مستأجِرَين بمفتاح طلبٍ متطابقِ النصّ يتجاوران). والشاهدُ الحيّ في
`test_d1_raster_invalidation_owner_api_integration.py` يؤكّد العزلَ **بشرط**
`rolsuper OR rolbypassrls`، ودورُ الجولة العامّة `sahool_test` خارقٌ فيُتخطّى الشرطُ
دائماً: أخضرُ لا يقيس شيئاً. هنا يُقاس بدورٍ مقيَّد فعلاً، على السياسة المُهاجَرة
نفسِها (v96: `ENABLE` + `FORCE` + `tenant_isolation`) لا على نسخةٍ منها.

خمسةُ شهود، على منوال `test_imagery_automation_rls_live_pg.py`:

1. **الدورُ مقيَّدٌ فعلاً** (`rolsuper=f` و`rolbypassrls=f`) — تُقاس الأداةُ أوّلاً،
   وإلّا كان كلُّ ما بعدها بلا معنًى.
2. **إبطالُ الفراغ:** الصفّان موجودان فعلاً كما يراهما المُدير — فالصفرُ لاحقاً يقيس
   السياسةَ لا جدولاً فارغاً. (الدرسُ المقيس في `test_rls_tenant_isolation_live_pg.py`:
   جدولٌ فارغ يُخرِج صفراً سواءٌ أكانت RLS مُفعَّلةً أم مُعطَّلة.)
3. **موجب:** بسياق المستأجر A يرى صفَّه.
4. **سالب:** بسياق A لا يرى صفَّ B — ولا حتّى باستعلامٍ صريحٍ عن مُعرّف مستأجِره.
5. **بلا سياق ⇒ صفر بلا استثناء** على اتّصالٍ جديد: وهو بعينه سببُ ربط المُوصِّل
   بمسبح الوظائف (`JOBS_DATABASE_URL`) — الحدُّ المُعلَن في docstring `claim_due`.

الحدُّ المُعلَن: يُقاس جدولٌ واحد، ولا يُدّعى أنّ كلّ جداول D1 معزولةٌ صحيحاً.
و`processing_jobs` (نيّةُ المنصّة) خارج هذا الملفّ — عزلُه شريحةٌ أخرى.

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

_CERTIFICATION_REQUIRED = os.getenv("RASTER_QUEUE_RLS_CERTIFICATION_REQUIRED") == "1"

# النمطُ نفسُه المُقرَّر في `test_imagery_automation_rls_live_pg.py` (مراجعة #1014):
# `importorskip` قبل قراءة العَلَم يجعل غيابَ `asyncpg` على مُشغِّل الشهادة تخطّياً
# أخضرَ للوحدة كلّها — فالوظيفةُ تُعلِن شهادةً ولم تقِس شيئاً.
try:
    import asyncpg
except ImportError:
    if _CERTIFICATION_REQUIRED:
        raise
    asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

_ADMIN_DSN = os.getenv("TEST_DATABASE_ADMIN_URL") or ""
_APP_DSN = os.getenv("TEST_DATABASE_URL") or ""

_TABLE = "public.raster_cache_invalidations"
_TENANT_A = "aaaaaaaa-0000-4000-8000-0000000000a1"
_TENANT_B = "bbbbbbbb-0000-4000-8000-0000000000b1"

if not (_ADMIN_DSN and _APP_DSN) and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "RASTER_QUEUE_RLS_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_ADMIN_URL "
        "وTEST_DATABASE_URL — الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(
        not (_ADMIN_DSN and _APP_DSN),
        reason="يحتاج TEST_DATABASE_ADMIN_URL وTEST_DATABASE_URL — قاعدةً حيّة ودوراً مقيَّداً",
    )
)


async def _seed(admin, field_id: str) -> tuple[int, int]:
    """صفّا إبطالٍ لمستأجِرَين على **الحقل نفسِه** — الشكلُ الذي يُنتجه مُوصِّل D1.

    `$3::text` تحويلٌ لازمٌ لا زينة: `jsonb_build_object` مُعامِلاتُها من الصنف
    ``"any"``، فلا يستنتج المُخطِّط نوعَ مُعامِلٍ حرٍّ داخلها ويرفع
    ``IndeterminateDatatypeError``. الصنفُ نفسُه أصاب `UPDATE` إنهاءِ المُوصِّل في D1
    (`$4::text`) — مقيسٌ مرّتين في هذه الشريحة، فيُكتَب هنا كي لا يُعاد ثالثةً.
    """
    request_id = f"field.geometry.updated:{field_id}:rev1"
    sql = (
        f"INSERT INTO {_TABLE} (tenant_id, field_id, reason, metadata) "
        "VALUES ($1::uuid, $2, 'field.geometry.updated', "
        "jsonb_build_object('request_id', $3::text)) RETURNING id"
    )
    row_a = await admin.fetchval(sql, _TENANT_A, field_id, request_id)
    row_b = await admin.fetchval(sql, _TENANT_B, field_id, request_id)
    return int(row_a), int(row_b)


async def _visible(conn, row_id: int) -> bool:
    return bool(await conn.fetchval(f"SELECT EXISTS(SELECT 1 FROM {_TABLE} WHERE id=$1)", row_id))


@pytest.mark.asyncio
async def test_migrated_policy_isolates_the_owner_queue_and_is_blind_without_context():
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await asyncpg.connect(_APP_DSN)
    field_id = f"fld-rls-{uuid.uuid4().hex[:12]}"
    row_a = row_b = None
    try:
        # (١) تُقاس الأداةُ قبل أن يُقاس بها.
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
        assert enabled["relrowsecurity"], "RLS غير مُفعَّلة على طابور الإبطال بعد الهجرات"
        assert enabled["relforcerowsecurity"], "FORCE غائبة ⇒ المالكُ يتجاوز السياسة"
        policy = await admin.fetchval(
            "SELECT count(*) FROM pg_policies WHERE schemaname='public' "
            "AND tablename='raster_cache_invalidations' AND policyname='tenant_isolation'"
        )
        assert policy == 1, f"سياسةُ tenant_isolation المُهاجَرة (v96) غائبة: {policy}"

        row_a, row_b = await _seed(admin, field_id)
        # (٢) إبطالُ الفراغ: الصفّان موجودان فعلاً كما يراهما المُدير.
        assert await _visible(admin, row_a) and await _visible(admin, row_b)

        # (٣) و(٤): بسياق A يرى صفَّه ولا يرى صفَّ B.
        await app.execute("SELECT set_config('app.current_tenant', $1, false)", _TENANT_A)
        assert await _visible(app, row_a), "المستأجر لا يرى صفَّه ⇒ عمًى تامّ لا عزل"
        assert not await _visible(app, row_b), "تسريبٌ عبر المستأجرين في طابور الإبطال"
        leaked = await app.fetchval(
            f"SELECT count(*) FROM {_TABLE} WHERE tenant_id=$1::uuid", _TENANT_B
        )
        assert leaked == 0, "استعلامٌ صريحٌ عن مستأجِرٍ آخر تسرّب رغم السياسة"
        # والحقلُ نفسُه يحمل صفَّين، فلا يرى منهما إلّا واحداً.
        mine = await app.fetchval(f"SELECT count(*) FROM {_TABLE} WHERE field_id=$1", field_id)
        assert mine == 1, f"عددُ الصفوف المرئيّة على الحقل المشترك {mine} لا 1"

        # (٥) بلا سياق ⇒ صفر بلا استثناء، على اتّصالٍ جديد لا بـ`set_config('', …)`
        # ولا بـ`RESET`: كلاهما يترك المُعامل مُعرَّفاً فارغاً فيصنع حالةً مختلفة عن
        # حالة العامل الحقيقيّة (مقيسٌ في `test_imagery_automation_rls_live_pg.py`).
        fresh = await asyncpg.connect(_APP_DSN)
        try:
            with pytest.raises(asyncpg.exceptions.UndefinedObjectError):
                await fresh.fetchval("SELECT current_setting('app.current_tenant', false)")
            assert (
                await fresh.fetchval("SELECT current_setting('app.current_tenant', true)") is None
            )
            assert not await _visible(fresh, row_a)
            assert not await _visible(fresh, row_b)
            assert (
                await fresh.fetchval(f"SELECT count(*) FROM {_TABLE} WHERE field_id=$1", field_id)
                == 0
            ), (
                "مطالبةٌ عابرةٌ للمستأجرين بلا سياق تُرجِع صفراً صامتاً — ولذلك يلزم "
                "مسبحُ الوظائف للمُوصِّل، وهو الحدُّ المُعلَن في docstring claim_due"
            )
        finally:
            await fresh.close()
    finally:
        await app.close()
        try:
            await admin.execute(f"DELETE FROM {_TABLE} WHERE field_id=$1", field_id)
        finally:
            await admin.close()
