"""`RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01` — القبولُ الحيّ.

شرطُ إغلاق هذه الفجوة المكتوبُ في السجلّ منذ تسجيلها: **دليلُ إغلاقٍ حيّ**. الشاهدُ
الساكن (`test_reconciliation_cursor_resumption.py`) يقيس حكمَ الدالّة ببديل اتّصالٍ
صارم، وهو يقيس **المنطق** لا العقدَ الفعليّ: أنواعُ الأعمدة، و`CHECK` على مفردات
السبب، و`ON CONFLICT` على المفتاح المركّب، و`ANY($2::bigint[])`، وRLS على الجدول
الجديد — لا يقولها إلّا PostgreSQL.

وكان هذا القبولُ مؤجَّلاً بحجّة أنّه «يحتاج قاعدةً حيّة» غيرَ متاحة. **الحجّةُ سقطت
بالقياس:** وظيفةُ *Integration Tests* سياقٌ **مطلوب** أصلاً، وتُشغّل PostgreSQL+PostGIS
على `localhost:5433` وتُطبّق بيانَ الهجرات عليها مرّتين (الثانيةُ لقياس التكرار).

**والتخطّي ليس خُضرة.** بلا `RECONCILIATION_RESUMPTION_CERTIFICATION_REQUIRED=1` يُتخطّى
هذا الملفّ في التطوير؛ ومعه يصير غيابُ الـDSN خطأً صريحاً — فنزعُ `TEST_DATABASE_URL`
يوماً ما لا يُحوّل الشهادةَ إلى تخطٍّ أخضر. نفسُ عرف `CLAIM_LEASE_CERTIFICATION_REQUIRED`.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

pytestmark = [pytest.mark.integration]

_DSN = os.getenv("TEST_DATABASE_URL") or os.getenv("TEST_DB_DSN") or ""
_CERTIFICATION_REQUIRED = os.getenv("RECONCILIATION_RESUMPTION_CERTIFICATION_REQUIRED") == "1"

if not _DSN and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "RECONCILIATION_RESUMPTION_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_URL — "
        "الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(not _DSN, reason="يحتاج TEST_DATABASE_URL — قاعدةً حيّة لا محاكاة")
)

SOURCE = "device_telemetry"


def _reconcile():
    """الدالّةُ الإنتاجيّةُ نفسُها، لا نسخةٌ مُعاد كتابتها.

    التسجيلُ في `sys.modules` **قبل** التنفيذ ليس زينة: `@dataclass` يقرأ
    `sys.modules[cls.__module__].__dict__` وقتَ إنشاء `Stats`، فبدونه يسقط الاستيراد
    بـ`AttributeError: 'NoneType' object has no attribute '__dict__'`. مقيسٌ على هذا
    المصدر بعينه قبل شحن هذا الملفّ. والاستعادةُ في `finally` تمنع تلويثاً يمسّ
    اختباراتٍ لاحقةً في الجلسة نفسِها (#1017).
    """
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts/soil/reconcile_historical.py"
    spec = importlib.util.spec_from_file_location("_live_reconcile", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    return module


@pytest.fixture
async def live():
    try:
        conn = await asyncpg.connect(_DSN, statement_cache_size=0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(exc).__name__}")
    tenant = str(uuid.uuid4())
    await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)
    try:
        yield conn, tenant
    finally:
        # تنظيفٌ مقصورٌ على مستأجرِ هذا الاختبار — لا `TRUNCATE` لجدولٍ مشترك.
        for table in (
            "soil_reconciliation_deferrals",
            "soil_reconciliation_checkpoints",
            "soil_observations",
            "soil_profile_projection_jobs",
            "device_telemetry",
            "iot_devices",
            "fields",
        ):
            try:
                await conn.execute(f"DELETE FROM {table} WHERE tenant_id=$1::uuid", tenant)  # noqa: S608
            except Exception:  # noqa: BLE001, S110 — جدولٌ غائبٌ لا يُبطِل تنظيفَ البقيّة
                pass
        await conn.close()


#: حقلٌ خاصٌّ بهذا الاختبار. `iot_devices.field_id` **مفتاحٌ أجنبيٌّ إلى `fields`**
#: (`v24_iot_devices.sql`)، فربطُ جهازٍ بحقلٍ لا وجودَ له يسقط على القيد لا على المنطق.
_FIELD = "field_live_recon"


async def _seed(conn, tenant: str, *, bind_device: bool) -> list[int]:
    """يُهيّئ الحدَّ الأدنى بالمخطَّط **الحقيقيّ**.

    أوّلُ صياغةٍ لي أدرجت في `iot_devices` بثلاثة أعمدة فقط، والمخطَّطُ يشترط `name`
    و`type` NOT NULL (و`type` تحت `CHECK`)، و`field_id` مقيَّدٌ بـ`fields`. فسقط
    الشاهدُ في CI بـ`NotNullViolationError` — ولم يمسكه قياسي المحلّيّ لأنّ هذه
    الحاوية بلا PostGIS فتعذّر تطبيق `v9`/`v24`، فقِستُ عقدَ v231 وحدَه. **الشاهدُ
    الحيُّ كشف ما لا يكشفه الساكن: العقدَ الفعليَّ للجداول المجاورة.**
    """
    moment = datetime(2026, 9, 19, tzinfo=UTC)
    await conn.execute(
        "INSERT INTO fields(field_id,name,tenant_id) VALUES ($1,$2,$3::uuid) "
        "ON CONFLICT (field_id) DO NOTHING",
        _FIELD,
        "حقلُ شاهدِ المصالحة",
        tenant,
    )
    for device, bound in (("dev_live_10", bind_device), ("dev_live_11", True)):
        await conn.execute(
            "INSERT INTO iot_devices(device_id,tenant_id,name,type,field_id) "
            "VALUES ($1,$2::uuid,$3,'soil_moisture',$4)",
            device,
            tenant,
            f"جهازُ {device}",
            _FIELD if bound else None,
        )
    # المعرّفُ يُولَّد ولا يُملى: `telemetry_id` مفتاحٌ أوّليٌّ **عابرٌ للمستأجرين**،
    # وقاعدةُ *Integration Tests* مشتركة — ففرضُ 10/11 يتصادم مع صفوفِ اختبارٍ آخر.
    ids: list[int] = []
    for device in ("dev_live_10", "dev_live_11"):
        ids.append(
            await conn.fetchval(
                """INSERT INTO device_telemetry(tenant_id,device_id,sensor_type,
                                                value,unit,recorded_at,received_at)
                   VALUES ($1::uuid,$2,'soil_moisture',25.0,'%',$3,$3)
                   RETURNING telemetry_id""",
                tenant,
                device,
                moment,
            )
        )
    return ids


async def test_the_deferral_ledger_exists_with_its_declared_contract(live) -> None:
    """v231 موجودٌ بعقده — أنواعاً ومفتاحاً ومفرداتِ سببٍ مغلقة وRLS.

    الشاهدُ الساكن لا يستطيع قولَ أيٍّ من هذه: بديلُ الاتّصال يقبل ما تُمليه بايثون.
    """
    conn, tenant = live
    columns = {
        r["column_name"]: r["data_type"]
        for r in await conn.fetch(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_name='soil_reconciliation_deferrals'"
        )
    }
    assert columns, "جدولُ التأجيل غائبٌ — لم تُطبَّق v231"
    assert columns["source_id"] == "bigint"
    assert columns["resolved_at"] == "timestamp with time zone"

    # مفرداتُ السبب مغلقةٌ في القاعدة لا في بايثون وحدَها.
    with pytest.raises(asyncpg.PostgresError):
        await conn.execute(
            "INSERT INTO soil_reconciliation_deferrals(source_name,tenant_id,source_id,reason) "
            "VALUES ($1,$2::uuid,$3,'a_reason_nothing_reexamines')",
            SOURCE,
            tenant,
            1,
        )

    rls = await conn.fetchrow(
        "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
        "WHERE relname='soil_reconciliation_deferrals'"
    )
    assert rls["relrowsecurity"] and rls["relforcerowsecurity"], "RLS غيرُ مفروضةٍ على السجلّ"


async def test_a_passed_row_is_recorded_then_recovered_on_live_postgres(live) -> None:
    """الدعوى كاملةً على قاعدةٍ حيّة: المؤشّرُ يتجاوز · السجلُّ يحفظ · الجولةُ تستردّ."""
    conn, tenant = live
    module = _reconcile()
    low, high = await _seed(conn, tenant, bind_device=False)

    first = await module.reconcile_device_telemetry(conn, tenant, 100)
    assert first.deferred == 1, f"لم يُسجَّل التأجيل: {first}"
    assert (
        await conn.fetchval(
            "SELECT last_source_id FROM soil_reconciliation_checkpoints "
            "WHERE source_name=$1 AND tenant_id=$2::uuid",
            SOURCE,
            tenant,
        )
        == high
    ), "المؤشّرُ لم يتجاوز — النموذجُ صار يتوقّف بدل أن يكتب"
    row = await conn.fetchrow(
        "SELECT reason,resolved_at FROM soil_reconciliation_deferrals "
        "WHERE source_name=$1 AND tenant_id=$2::uuid AND source_id=$3",
        SOURCE,
        tenant,
        low,
    )
    assert row["reason"] == "device_field_unbound" and row["resolved_at"] is None

    # زوالُ السبب: رُبط الجهازُ بحقل.
    await conn.execute(
        "UPDATE iot_devices SET field_id=$1 WHERE device_id='dev_live_10' AND tenant_id=$2::uuid",
        _FIELD,
        tenant,
    )
    second = await module.reconcile_device_telemetry(conn, tenant, 100)
    assert second.resolved == 1, f"لم تُستردَّ القراءةُ بعد زوال السبب: {second}"
    assert second.scanned == 0, "المسحُ إلى الأمام أعاد صفوفاً — الاستردادُ ليس من المؤجَّلات"

    persisted = await conn.fetchval(
        "SELECT count(*) FROM soil_observations WHERE tenant_id=$1::uuid "
        "AND provenance->>'legacy_id'=$2",
        tenant,
        str(low),
    )
    assert persisted == 1, "القراءةُ 10 لم تبلغ soil_observations على قاعدةٍ حيّة"

    kept = await conn.fetchrow(
        "SELECT resolved_at,examinations FROM soil_reconciliation_deferrals "
        "WHERE source_name=$1 AND tenant_id=$2::uuid AND source_id=$3",
        SOURCE,
        tenant,
        low,
    )
    assert kept is not None, "المدخلُ حُذِف عند الحسم — الفراغُ يصير ذا معنيين"
    assert kept["resolved_at"] is not None and kept["examinations"] >= 2


async def test_a_second_run_is_idempotent_and_does_not_reopen_a_resolved_deferral(live) -> None:
    """إعادةُ التشغيل آمنة: لا مشاهدةَ مكرّرة ولا مؤجَّلٌ محسومٌ يُفتَح ثانيةً."""
    conn, tenant = live
    module = _reconcile()
    await _seed(conn, tenant, bind_device=True)

    await module.reconcile_device_telemetry(conn, tenant, 100)
    again = await module.reconcile_device_telemetry(conn, tenant, 100)
    assert again.inserted == 0 and again.deferred == 0, f"إعادةُ التشغيل ليست محايدة: {again}"
    assert (
        await conn.fetchval(
            "SELECT count(*) FROM soil_observations WHERE tenant_id=$1::uuid", tenant
        )
        == 2
    )
    assert (
        await conn.fetchval(
            "SELECT count(*) FROM soil_reconciliation_deferrals WHERE tenant_id=$1::uuid", tenant
        )
        == 0
    ), "سُجِّل تأجيلٌ لصفوفٍ مؤهّلةٍ كلِّها"
