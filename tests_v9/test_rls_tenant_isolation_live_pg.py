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

**وحدُّ صدقٍ يُقال صراحةً:** الشهودُ الثلاثة الأولى تُنشئ جدولَها وسياستَها بنفسها. فالمُثبَتُ
بها أنّ **المحرّكَ يعزل**، وأنّ **الدورَ مقيَّدٌ فعلاً**، وأنّ **مِقياسنا غيرُ فارغ** —
لا أنّ سياسات RLS المُعلَنة في هجرات المنصّة صحيحة.

**والقسمُ الأخير يقيس السياساتِ المُهاجَرة نفسَها** — عائلةً عائلةً باسم الـGUC الذي تقرؤه
(``TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01``): جدولٌ ممثِّلٌ لكلّ اسمٍ من الثلاثة،
والكاتبُ الحقيقيّ حيث يُستورَد بلا خدمة. وحدُّه: ثلاثةُ جداول من ٣٣٠، لا الشجرة كلّها.

التشغيل: ``TEST_DATABASE_ADMIN_URL=… TEST_DATABASE_URL=… pytest -m integration``
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_drawing_migration_reapplies_and_isolates_runtime_dml():
    """Apply the real migration twice, including adoption of a legacy app-owned table.

    The temporary schema keeps this probe away from production tables. Ownership,
    catalog protection, tenant writes, and connection reuse are all tested on PG.
    """
    from pathlib import Path

    schema = "drawing_witness_" + uuid.uuid4().hex
    table = f"{schema}.drawing_features"
    migration = (
        Path(__file__).resolve().parents[1] / "migrations/v230_drawing_features.sql"
    ).read_text(encoding="utf-8")
    app = await asyncpg.connect(_APP_DSN)
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await _assert_role_is_actually_restricted(app)
        role = await _app_role_name(app)
        quoted_role = '"' + role.replace('"', '""') + '"'
        owner = await admin.fetchval("SELECT current_user")
        await admin.execute(f"CREATE SCHEMA {schema}")
        await admin.execute(f"SET search_path TO {schema}, public")
        await admin.execute(migration)
        await admin.execute(f"ALTER TABLE {table} OWNER TO {quoted_role}")
        await admin.execute(migration)
        catalog = await admin.fetchrow(
            "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) AS owner "
            "FROM pg_class WHERE oid = $1::regclass",
            table,
        )
        assert dict(catalog) == {
            "relrowsecurity": True,
            "relforcerowsecurity": True,
            "owner": owner,
        }
        await admin.execute(f"GRANT USAGE ON SCHEMA {schema} TO {quoted_role}")
        # These are the grants apply_in_compose.sh supplies to its APP_DB_ROLE.
        await admin.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {quoted_role}")
        await admin.executemany(
            f"INSERT INTO {table} (feature_id, tenant_id, kind, geometry) VALUES ($1, $2, 'scout-pin', '{{}}')",
            [("a", uuid.UUID(_TENANT_A)), ("b", uuid.UUID(_TENANT_B))],
        )
        assert not await app.fetchval(
            "SELECT has_schema_privilege(current_user, $1, 'CREATE')", schema
        )
        for tenant, own_id, other_id in [(_TENANT_A, "a", "b"), (_TENANT_B, "b", "a")]:
            # Reuse one connection and transaction-local GUC, as tenant_connection does.
            async with app.transaction():
                await app.execute("SELECT set_config('app.current_tenant', $1, true)", tenant)
                assert await app.fetchval(f"SELECT feature_id FROM {table}") == own_id
                assert (
                    await app.execute(
                        f"UPDATE {table} SET draft = false WHERE feature_id = $1", other_id
                    )
                    == "UPDATE 0"
                )
                assert (
                    await app.execute(
                        f"UPDATE {table} SET draft = false WHERE feature_id = $1", own_id
                    )
                    == "UPDATE 1"
                )
                await app.execute(
                    f"INSERT INTO {table} (feature_id, tenant_id, kind, geometry) VALUES ('own-insert', $1, 'scout-pin', '{{}}')",
                    uuid.UUID(tenant),
                )
                assert (
                    await app.execute(f"DELETE FROM {table} WHERE feature_id = 'own-insert'")
                    == "DELETE 1"
                )
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with app.transaction():
                        await app.execute(
                            f"INSERT INTO {table} (feature_id, tenant_id, kind, geometry) VALUES ('bad', $1, 'scout-pin', '{{}}')",
                            uuid.UUID(_TENANT_B if tenant == _TENANT_A else _TENANT_A),
                        )
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with app.transaction():
                        await app.execute(
                            f"UPDATE {table} SET tenant_id = $1 WHERE feature_id = $2",
                            uuid.UUID(_TENANT_B if tenant == _TENANT_A else _TENANT_A),
                            own_id,
                        )
            assert await app.fetchval(f"SELECT count(*) FROM {table}") == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute(
                f"INSERT INTO {table} (feature_id, tenant_id, kind, geometry) VALUES ('no-context', $1, 'scout-pin', '{{}}')",
                uuid.UUID(_TENANT_A),
            )
    finally:
        await app.close()
        try:
            await admin.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        finally:
            await admin.close()


# ═══════════ عائلاتُ اسمِ الـGUC على الجداول المُهاجَرة — السياسةُ نفسُها لا نسخةٌ منها ═══════════
#
# TENANT-GUC-NAME-DIVERGES-ACROSS-POLICY-FAMILIES-01. مقيسٌ على قاعدةٍ طُبِّق عليها البيانُ
# القانونيّ كاملاً (٢٣١ هجرة، PG16.13، `pg_policies` لا نصُّ الهجرات): ٣٣٠ جدولاً تحت
# ENABLE+FORCE، وكلُّ سياسةٍ فعّالة تقرأ اسمَها بـ`missing_ok=true`، والأسماءُ ثلاثة:
#
#     app.current_tenant      ٢٨٧ جدولاً (منها ١٢٠ تقبل app.tenant_id أيضاً عبر
#                             sahool_effective_tenant_id — ٩٤ منها في WITH CHECK وحدَه)
#     app.tenant_id           ٢٦ جدولاً — كاتبُها الوحيد phase_runtime_store/workers
#     app.current_tenant_id   ١٤ جدولاً — كاتبُها الوحيد soil p1/p2/p3_store
#
# وكلُّ كاتبٍ في الشجرة يضبط الاسمَ الذي تقرؤه سياسةُ جداوله (مصفوفةٌ مقيسة: صفرُ تباين).
# **فالتباينُ كامنٌ لا جارٍ** — وشكلُ فشله إن وقع: الاسمُ الخاطئ ⇒ صفرُ صفوفٍ بلا استثناء
# في القراءة، و42501 من WITH CHECK في الكتابة.
#
# وما يحمرّ هنا تسريبٌ أو عمًى: سياقٌ يعيش بعد معاملته، أو كاتبٌ حقيقيّ لا يرى صفَّه.

#: (اسمُ الـGUC، الجدول، عمودُ الوسم، زرعُ صفٍّ بـ$1=المستأجِر و$2=الوسم). والعائلةُ
#: الأولى مرّتين عمداً: شكلا مقارنةٍ مختلفا الأثر حين يرتدّ الـGUC إلى `''` بعد المعاملة
#: (مقيس): `tenant_id::text = NULLIF(…, '')` ⇒ صفرٌ صامت، و`tenant_id = …::uuid` بلا
#: NULLIF ⇒ **22P02 صاخب** (٢٩ جدولاً). والخاصّيّةُ المطلوبة من كليهما واحدة: لا صفوف.
_GUC_FAMILIES = [
    pytest.param(
        "app.current_tenant",
        "water_ledger",
        "field_id",
        "INSERT INTO water_ledger (tenant_id, field_id, ledger_date) "
        "VALUES ($1::uuid, $2, date '2026-01-01')",
        id="app.current_tenant:text-nullif:water_ledger",
    ),
    pytest.param(
        "app.current_tenant",
        "signal_anomalies",
        "anomaly_ref",
        "INSERT INTO signal_anomalies (anomaly_ref, tenant_id, field_id, season_id, status, "
        "version, payload_json) VALUES ($2, $1::uuid, $2, 's', 'detected', 1, '{}'::jsonb)",
        id="app.current_tenant:bare-uuid-cast:signal_anomalies",
    ),
    pytest.param(
        "app.tenant_id",
        "model_versions_runtime",
        "model_id",
        "INSERT INTO model_versions_runtime (tenant_id, model_id, model_name, version, task, "
        "artifact_uri, artifact_hash) VALUES ($1::uuid, $2, 'm', '1', 't', 'u', 'h')",
        id="app.tenant_id:model_versions_runtime",
    ),
    pytest.param(
        "app.current_tenant_id",
        "soil_spatial_products",
        "product_id",
        "INSERT INTO soil_spatial_products (product_id, tenant_id, field_id, product_type, "
        "dataset_version, geometry_hash, payload) "
        "VALUES ($2, $1, $2, 'soilgrids_polygon', 'v', 'g', '{}'::jsonb)",
        id="app.current_tenant_id:soil_spatial_products",
    ),
]


async def _tagged(conn, table: str, key: str, prefix: str) -> int:
    return await conn.fetchval(f"SELECT count(*) FROM {table} WHERE {key} LIKE $1", prefix + "%")


async def _rows_or_refusal(conn, table: str, key: str, prefix: str) -> int | str:
    """عددُ الصفوف المرئيّة، أو SQLSTATE الرفض — **وكلاهما فشلٌ مغلق**، والمحظورُ صفٌّ واحد."""
    try:
        return await _tagged(conn, table, key, prefix)
    except asyncpg.PostgresError as exc:
        return exc.sqlstate


async def _seed_pair(admin, table: str, key: str, seed: str, tag: str) -> None:
    catalog = await admin.fetchrow(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = $1::regclass", table
    )
    assert catalog is not None, f"{table} غائب — البيانُ لم يُطبَّق على هذه القاعدة"
    assert catalog["relrowsecurity"] and catalog["relforcerowsecurity"], (
        f"{table} بلا ENABLE+FORCE بعد الهجرات"
    )
    await admin.execute(seed, _TENANT_A, f"{tag}-a")
    await admin.execute(seed, _TENANT_B, f"{tag}-b")
    # الشاهدُ السالبُ للأداة: المُديرُ الخارق يرى الصفّين — فالمِقياسُ قادرٌ على رؤية تسريب.
    assert await _tagged(admin, table, key, tag) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("guc", "table", "key", "seed"), _GUC_FAMILIES)
async def test_each_guc_family_isolates_its_migrated_table_only_inside_the_transaction(
    guc, table, key, seed
):
    """(أ) داخل المعاملة: A يرى صفَّه ولا يرى صفَّ B. (ب) بعد الالتزام على الاتّصال نفسِه:
    الـGUC `''` لا NULL، ولا صفّ. (د) جلسةٌ لم يُضبَط فيها قطّ: NULL وصفرٌ صامت — ثمنُ
    `missing_ok`، وبدونه 42704 على كلّ استعلام. وكتابةٌ بلا سياق تُرفَض 42501 لا تُقبَل.
    """
    tag = f"gucfam-{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await asyncpg.connect(_APP_DSN)
    try:
        await _assert_role_is_actually_restricted(app)
        await _seed_pair(admin, table, key, seed, tag)

        assert await app.fetchval("SELECT current_setting($1, true)", guc) is None
        assert await _tagged(app, table, key, tag) == 0
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app.execute(seed, _TENANT_A, f"{tag}-nocontext")

        async with app.transaction():
            await app.execute("SELECT set_config($1, $2, true)", guc, _TENANT_A)
            assert await _tagged(app, table, key, f"{tag}-a") == 1, (
                f"{guc} مضبوطٌ ولا يرى المستأجرُ صفَّه في {table} — عمًى لا عزل"
            )
            assert await _tagged(app, table, key, tag) == 1, f"تسريبٌ عبر المستأجرين في {table}"

        assert await app.fetchval("SELECT current_setting($1, true)", guc) == ""
        assert await _rows_or_refusal(app, table, key, tag) in (0, "22P02"), (
            f"سياقُ {guc} عاش بعد معاملته على {table} — تسريبٌ إلى وحدة العمل التالية"
        )
    finally:
        await app.close()
        try:
            await admin.execute(f"DELETE FROM {table} WHERE {key} LIKE $1", tag + "%")
        finally:
            await admin.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(("guc", "table", "key", "seed"), _GUC_FAMILIES)
async def test_a_tx_local_tenant_set_outside_any_transaction_reaches_no_later_statement(
    guc, table, key, seed
):
    """العطلُ الذي يجعل موضعاً من أساس `tenant_guc_scope_guard` عطلاً حقيقيّاً.

    asyncpg بلا معاملةٍ صريحة في autocommit: `set_config(…, true)` معاملةُ نفسِه. **يُعيد
    القيمةَ كأنّه نجح**، والعبارةُ التالية تقرأ `''` — لا شيءَ ضُبِط. ومقيسٌ بالكاتب
    الحقيقيّ: `phase_runtime_store.persist_runtime_event` يُرفَض 42501 لهذا السبب بعينه.
    """
    tag = f"gucauto-{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    app = await asyncpg.connect(_APP_DSN)
    try:
        await _assert_role_is_actually_restricted(app)
        await _seed_pair(admin, table, key, seed, tag)
        assert not app.is_in_transaction()
        assert await app.fetchval("SELECT set_config($1, $2, true)", guc, _TENANT_A) == _TENANT_A
        assert await app.fetchval("SELECT current_setting($1, true)", guc) == ""
        assert await _rows_or_refusal(app, table, key, tag) in (0, "22P02")
    finally:
        await app.close()
        try:
            await admin.execute(f"DELETE FROM {table} WHERE {key} LIKE $1", tag + "%")
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_a_session_level_tenant_outlives_its_transaction_unless_the_pool_resets_it():
    """(ج) التسريبُ الكامن: `set_config(…, false)` يعيش عبر المعاملات على اتّصالٍ مُعاد.

    والشاهدُ ثلاثيّ كي يُقرَأ كلٌّ بمعناه:

    1. اتّصالٌ خامٌ مُعاد: وحدةُ عملٍ لاحقة **لم تضبط شيئاً** ترى صفَّ A — التسريبُ نفسُه،
       وهو الشاهدُ السالب الذي يُثبِت أنّ المِقياس يرى تسريباً.
    2. مسبحُ asyncpg الافتراضيّ: التحريرُ يُنفِّذ `RESET ALL`، فالاكتسابُ التالي — على
       **الخادم الخلفيّ نفسِه** (pid مطابق) — يقرأ `''` ولا صفّ. هذا ما يعتمد عليه تصميمُ
       auth (يُعيد ضبطَ admin على كلّ اكتساب) ومخزنُ سير العمل غيرُ المتزامن.
    3. مسبحٌ بلا إعادة ضبط — نموذجُ مُجمِّعٍ بلا `server_reset_query`/`DISCARD ALL` (مثل
       PgBouncer بوضع المعاملة): التسريبُ يعود. **ولا مُجمِّعَ في أيّ حزمةٍ اليوم** — فهذا
       شرطٌ مسبق لإدخاله لا عطلٌ جارٍ.
    """
    guc, table, key = "app.current_tenant", "water_ledger", "field_id"
    seed = _GUC_FAMILIES[0].values[3]
    tag = f"gucsess-{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    try:
        await _seed_pair(admin, table, key, seed, tag)

        raw = await asyncpg.connect(_APP_DSN)
        try:
            await _assert_role_is_actually_restricted(raw)
            async with raw.transaction():
                await raw.execute("SELECT set_config($1, $2, false)", guc, _TENANT_A)
            async with raw.transaction():
                assert await _tagged(raw, table, key, tag) == 1, (
                    "مستوى الجلسة لم يعش عبر المعاملة — المِقياس لا يرى التسريب الذي يحرسه"
                )
        finally:
            await raw.close()

        async def _no_reset(_conn) -> None:
            return None

        for reset, expected_guc, expected_rows in ((None, "", 0), (_no_reset, _TENANT_A, 1)):
            kwargs = {} if reset is None else {"reset": reset}
            pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=1, **kwargs)
            try:
                async with pool.acquire() as conn:
                    first = conn.get_server_pid()
                    await conn.execute("SELECT set_config($1, $2, false)", guc, _TENANT_A)
                async with pool.acquire() as conn:
                    assert conn.get_server_pid() == first, "المسبح لم يُعِد الخادم نفسَه"
                    assert await conn.fetchval("SELECT current_setting($1, true)", guc) == (
                        expected_guc
                    )
                    assert await _tagged(conn, table, key, tag) == expected_rows
            finally:
                await pool.close()
    finally:
        try:
            await admin.execute(f"DELETE FROM {table} WHERE {key} LIKE $1", tag + "%")
        finally:
            await admin.close()


def _load_service_module(name: str, rel: str):
    """وحدةُ خدمةٍ بمجلّدٍ مُوصَّل (`soil-service`) — لا تُستورَد باسم حزمة."""
    path = Path(__file__).resolve().parents[1] / rel
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_real_soil_p1_writer_sets_the_name_its_policy_reads():
    """الكاتبُ الحقيقيّ لعائلة `app.current_tenant_id` — لا جملةٌ منسوخةٌ منه.

    الإدراجُ تحت FORCE يمرّ من WITH CHECK **فقط** إن ضبط الكاتبُ الاسمَ الذي تقرؤه السياسة
    وداخل المعاملة نفسِها؛ فنجاحُه شاهدٌ على الاسم والنطاق معاً. ثمّ القارئُ الحقيقيّ بسياق
    B لا يرى الصفّ. (ولا يُقرأ صفُّ A عبر `get_latest`: يرمي على `jsonb` الذي يُعيده asyncpg
    نصّاً بلا codec — عطلٌ آخر مقيس، خارج هذا الصنف.)
    """
    p1_store = _load_service_module("soil_p1_store_rls_probe", "services/soil-service/p1_store.py")
    tag = f"gucp1-{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=1)
    product = SimpleNamespace(
        product_id=tag,
        tenant_id=_TENANT_A,
        field_id=tag,
        dataset_version="v1",
        geometry_hash="g",
        model_dump=lambda mode="json": {"probe": True},
    )
    try:
        async with pool.acquire() as conn:
            await _assert_role_is_actually_restricted(conn)
        assert await p1_store.save_spatial(pool, product) == tag
        assert await _tagged(admin, "soil_spatial_products", "product_id", tag) == 1
        assert (
            await p1_store.get_latest(pool, _TENANT_B, "soil_spatial_products", "field_id", tag)
            is None
        ), "القارئُ الحقيقيّ بسياق B رأى صفَّ A"
    finally:
        await pool.close()
        try:
            await admin.execute(
                "DELETE FROM soil_spatial_products WHERE product_id LIKE $1", tag + "%"
            )
        finally:
            await admin.close()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    raises=asyncpg.InsufficientPrivilegeError,
    reason=(
        "phase_runtime_store._set_rls_tenant يضبط الاسمين بـset_config(…, true) خارج أيّ معاملة "
        "في مواضعه الأحد عشر ⇒ يضيعان قبل الإدراج ⇒ WITH CHECK يرفض (42501) تحت مسبح التطبيق "
        "المقيَّد. الملفّ مجمَّدٌ بـGATE-01: المسموحُ الاختبارُ لا الإصلاح."
    ),
)
async def test_phase_runtime_store_persists_under_the_restricted_app_role():
    """**العيبُ قائم — والاختبارُ يوثّقه تنفيذيّاً لا نثراً** (سابقة `test_compensation_killswitch`).

    `strict=True` يمنعه من أن يصير نسياناً: يوم يدخل الإصلاح (لفُّ `_set_rls_tenant` والكتابة
    في `conn.transaction()`) ينجح الاختبارُ **على غير توقّع** فيحمرّ الجناح ويُطالِب بنزع
    العلامة. و`raises` يحصر التوقّعَ في رفض RLS وحده: فشلُ استيرادٍ أو اتّصالٍ يبقى فشلاً.
    """
    from api import phase_runtime_store

    tag = f"gucprs-{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(_ADMIN_DSN)
    pool = await asyncpg.create_pool(_APP_DSN, min_size=1, max_size=1)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=pool)), headers={})
    try:
        async with pool.acquire() as conn:
            await _assert_role_is_actually_restricted(conn)
        result = await phase_runtime_store.persist_runtime_event(
            request,
            tenant=uuid.UUID(_TENANT_A),
            field=None,
            aggregate_type="rls-probe",
            aggregate_id=tag,
            event_type="rls.probe",
            payload={},
        )
        assert result == {"persisted": True, "event_type": "rls.probe"}
        assert (
            await admin.fetchval(
                "SELECT count(*) FROM runtime_event_outbox WHERE aggregate_id = $1", tag
            )
            == 1
        )
    finally:
        await pool.close()
        try:
            await admin.execute("DELETE FROM runtime_event_outbox WHERE aggregate_id = $1", tag)
        finally:
            await admin.close()
