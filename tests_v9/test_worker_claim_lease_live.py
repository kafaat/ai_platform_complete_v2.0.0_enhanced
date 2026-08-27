"""`WORKER-CLAIM-NOT-PINNED-BY-A-TRANSACTION-01` — البرهانُ الحيّ على PostgreSQL.

**ما يقيسه هذا الملفّ ولا يقيسه أخوه الساكن:** أنّ `FOR UPDATE SKIP LOCKED` في
اتّصالٍ بوضع autocommit **يُحرِّر القفلَ فور انتهاء عبارة `SELECT`** — وهي حقيقةٌ
في محرّك PostgreSQL لا في بنية الكود، فلا يبلغها تحليلُ شجرةٍ مهما دقّ.

**وقِيس فعلاً، لا استُنتِج:** عاملان متزامنان على أربعين صفّاً ⇒ **عشرون صفّاً
مُطالَبٌ مرّتين** بالنمط القديم، و**صفر** بالجديد. وفي `run_actuator_once` تعني
العشرون: عشرون طلبَ إرسالٍ فيزيائيٍّ مكرَّر — حركةُ صمّامٍ أو مضخّةٍ تُطلَب مرّتين.

**والاختبارُ يُثبِت الطرفين عمداً.** إثباتُ أنّ الجديد لا يُكرّر **وحدَه** لا يُثبِت
أنّ الاختبار يقيس شيئاً: قد يكون التوقيتُ لم يتقاطع أصلاً. فيُشترَط أن يُعيد النمطُ
القديم إنتاجَ العطل في الجولة نفسِها — وإلّا فالقياسُ غيرُ حاسم ويُعلَن كذلك.

التشغيل: ``TEST_DATABASE_URL=postgresql://… pytest -m integration``
"""

from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.security]

asyncpg = pytest.importorskip("asyncpg")

# **`DATABASE_URL` ليس مصدراً هنا — وهذا عطلٌ مقيسٌ لا احتياط.** أوّلُ صياغةٍ لهذا
# الملفّ رجعت إليه احتياطاً، فالتقطت ما تضعه وحداتٌ أخرى **زمنَ الاستيراد**
# (`test_services_functional.py:17` وأخواتها: `os.environ.setdefault` بـDSN مقبسٍ
# محلّيّ `host=/tmp/pgrun`). فصار `_DSN` غيرَ فارغٍ بلا قاعدةٍ حيّة، ولم يعمل
# `skipif`، وانفجر الاختباران بـ`FileNotFoundError` في وظيفة *Integration Tests*.
# ومتغيّرٌ يكتبه غيرُك عند الاستيراد ليس إعلانَ توفّرِ قاعدة. فالمصدرُ عرفُ المستودع
# `TEST_DATABASE_URL` (وهو ما تضعه الوظيفة فعلاً)، ثمّ `TEST_DB_DSN` للتشغيل اليدويّ.
_DSN = os.getenv("TEST_DATABASE_URL") or os.getenv("TEST_DB_DSN") or ""

# على غرار `IRR_F01_CERTIFICATION_REQUIRED`: التخطّي مقبولٌ في التطوير، ومرفوضٌ حين
# تُعلِن الوظيفةُ أنّها تشهد. فبلا هذا يمرّ غيابُ القاعدة خُضرةً صامتة.
_CERTIFICATION_REQUIRED = os.getenv("CLAIM_LEASE_CERTIFICATION_REQUIRED") == "1"

# مخطّطٌ خاصٌّ لا `public`: جدولُ المسبار بلا RLS، ولو أُنشئ في `public` لرآه أيُّ
# جردِ كتالوجٍ يمرّ بعده في الجلسة نفسِها فأدانه. ويُسقَط في `finally` أيّاً كان المآل.
_SCHEMA = "claim_lease_probe_ns"
_TABLE = f"{_SCHEMA}.probe"
_ROWS = 40
_BATCH = 20
# نافذةُ التقاطع: العملُ الذي يقع بين المطالبة والإنهاء. أطولُ من زمن دورةِ
# عاملٍ آخر بكثير، فيتقاطعان يقيناً بدل أن يتقاطعا مصادفة.
_HOLD_SECONDS = 0.30

if not _DSN and _CERTIFICATION_REQUIRED:
    raise RuntimeError(
        "CLAIM_LEASE_CERTIFICATION_REQUIRED=1 بلا TEST_DATABASE_URL — "
        "الوظيفةُ تُعلِن شهادةً ولا قاعدةَ تشهد عليها."
    )

pytestmark.append(
    pytest.mark.skipif(not _DSN, reason="يحتاج TEST_DATABASE_URL — قاعدةً حيّة لا محاكاة")
)


async def _seed(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
        await conn.execute(f"DROP TABLE IF EXISTS {_TABLE}")
        await conn.execute(f"""
            CREATE TABLE {_TABLE} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                status text NOT NULL DEFAULT 'pending',
                claim_token uuid,
                claimed_by text,
                lease_until timestamptz,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        await conn.executemany(f"INSERT INTO {_TABLE} (status) VALUES ('pending')", [()] * _ROWS)


async def _claim_the_old_way(pool, _worker: str) -> list[str]:
    """النمطُ الذي كان في الشجرة: `SKIP LOCKED` في autocommit بلا معاملة."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id FROM {_TABLE} WHERE status='pending' "
            f"ORDER BY created_at LIMIT {_BATCH} FOR UPDATE SKIP LOCKED"
        )
        await asyncio.sleep(_HOLD_SECONDS)  # القفلُ تحرَّر سلفاً؛ هنا يقع العملُ الشبكيّ
        for row in rows:
            await conn.execute(f"UPDATE {_TABLE} SET status='done' WHERE id=$1", row["id"])
        return [str(row["id"]) for row in rows]


async def _claim_the_new_way(pool, worker: str) -> list[str]:
    """النمطُ المُطبَّق: TX-1 مطالبةٌ تُثبَّت بـcommit · الشبكةُ خارجها · TX-2 بـCAS."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                f"""
                WITH claimed AS (
                    SELECT id FROM {_TABLE}
                    WHERE status='pending' AND claim_token IS NULL
                    ORDER BY created_at LIMIT {_BATCH}
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE {_TABLE} AS t
                SET claim_token = gen_random_uuid(), claimed_by = $1,
                    lease_until = now() + interval '300 seconds'
                FROM claimed WHERE t.id = claimed.id
                RETURNING t.id, t.claim_token
                """,
                worker,
            )
        await asyncio.sleep(_HOLD_SECONDS)  # خارج أيّ معاملة — لا أقفالَ محبوسة
        for row in rows:
            async with conn.transaction():
                await conn.execute(
                    f"UPDATE {_TABLE} SET status='done', claim_token=NULL "
                    "WHERE id=$1 AND claim_token=$2",
                    row["id"],
                    row["claim_token"],
                )
        return [str(row["id"]) for row in rows]


async def _measure_overlap(claim_fn) -> tuple[int, int]:
    pool = await asyncpg.create_pool(_DSN, min_size=4, max_size=8)
    try:
        await _seed(pool)
        first, second = await asyncio.gather(claim_fn(pool, "A"), claim_fn(pool, "B"))
        return len(set(first) & set(second)), len(first) + len(second)
    finally:
        try:
            async with pool.acquire() as conn:
                await conn.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        finally:
            await pool.close()


@pytest.mark.asyncio
async def test_the_old_pattern_really_does_double_claim_on_a_live_database():
    """**بلا هذا لا يُعرَف أنّ الاختبارَ يقيس شيئاً.**

    اختبارٌ يُثبِت أنّ الجديدَ لا يُكرّر — وحدَه — يمرّ أخضرَ لو لم يتقاطع
    التوقيتُ أصلاً. فيُشترَط إعادةُ إنتاج العطل في الجولة نفسِها.
    """
    overlap, total = await _measure_overlap(_claim_the_old_way)
    assert total == 2 * _BATCH, f"لم يلتقط العاملان دفعةً كاملة: {total}"
    assert overlap > 0, (
        "لم يُعَد إنتاجُ العطل — القياسُ غيرُ حاسم، لا الإصلاحُ مُثبَت. "
        f"أطِل _HOLD_SECONDS (الآن {_HOLD_SECONDS}ث)"
    )


@pytest.mark.asyncio
async def test_the_applied_pattern_never_double_claims_under_concurrent_workers():
    """معيارُ قبول المرحلة 1 رقم ٢: «عمّالٌ متزامنون بلا نشر مزدوج».

    والمقيسُ هنا **المطالبة** لا النشر: النشرُ مشروطٌ بها، فمطالبةٌ لا تتكرّر تعني
    نشراً لا يتكرّر.
    """
    overlap, total = await _measure_overlap(_claim_the_new_way)
    assert total == 2 * _BATCH, f"لم يلتقط العاملان دفعةً كاملة: {total}"
    assert overlap == 0, f"مطالبةٌ مزدوجةٌ رغم الإصلاح: {overlap} صفّاً"
