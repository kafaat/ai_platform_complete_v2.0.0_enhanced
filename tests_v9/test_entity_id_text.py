"""Integration: v18 — إصدار حدث بمعرّف حقل نصّيّ (الإصلاح البنيويّ).

قبل v18 كان emit_event(p_entity_id UUID) يرفض معرّفات الحقول النصّيّة
("fld_demo_001" — fields.field_id VARCHAR) بخطأ cast، فكلّ أحداث الحقول
(trueup وغيرها) مكسورة. هذا الاختبار يُثبت حيّاً (على قاعدة CI بعد تطبيق
MANIFEST حتى v18): الإصدار ينجح، outbox يُملأ، والـdedup يعمل.

ملاحظة: events جدول append-only (v9_append_only يمنع DELETE) ⇒ لا تنظيف؛
نستعمل معرّفاً نصّيّاً فريداً لكلّ تشغيل ليبقى الاختبار idempotent.

pytest -m integration (يتخطّى تلقائيّاً إن لم تتوفّر القاعدة).
"""

from __future__ import annotations

import os
import time

import pytest

DSN = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)
_TENANT = "33333333-3333-3333-3333-333333333333"
# معرّف نصّيّ (ليس UUID) فريد لكلّ تشغيل — نفس شكل fld_demo_001 الحقيقيّ.
_FIELD = f"fld_itest_{os.getpid()}_{int(time.time())}"


def _db_available() -> bool:
    try:
        import asyncio

        import asyncpg

        async def _ping():
            c = await asyncpg.connect(DSN)
            await c.execute("SELECT 1 FROM events LIMIT 0")  # v11+v18 مُطبَّقة؟
            await c.close()

        asyncio.run(_ping())
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_emit_event_accepts_text_field_id():
    if not _db_available():
        pytest.skip("TEST_DATABASE_URL/events غير متاح — اختبار تكامل")
    import asyncio

    import asyncpg

    async def _run():
        c = await asyncpg.connect(DSN)
        try:
            # سياق المستأجر (RLS fail-closed على events)
            await c.execute("SELECT set_config('app.current_tenant', $1, false)", _TENANT)

            # ① الإصدار بمعرّف نصّيّ ينجح (كان يرمي cast error قبل v18)
            event_id = await c.fetchval(
                "SELECT emit_event($1,$2,$3,$4::uuid,$5::jsonb,$6)",
                "trueup.applied",
                "field",
                _FIELD,
                _TENANT,
                '{"k_new": 1.05}',
                "system",
            )
            assert event_id is not None, "الإصدار بمعرّف نصّيّ فشل"

            # ② الحدث مخزَّن بمعرّفه النصّيّ كما هو + outbox مملوء (atomicity)
            row = await c.fetchrow("SELECT entity_id FROM events WHERE event_id=$1", event_id)
            assert row["entity_id"] == _FIELD
            outbox = await c.fetchval(
                "SELECT count(*) FROM event_outbox WHERE event_id=$1", event_id
            )
            assert outbox == 1, "outbox لم يُملأ (atomicity)"

            # ③ dedup: نفس الحدث في نفس اليوم ⇒ NULL (لا تكرار)
            dup = await c.fetchval(
                "SELECT emit_event($1,$2,$3,$4::uuid,$5::jsonb,$6)",
                "trueup.applied",
                "field",
                _FIELD,
                _TENANT,
                '{"k_new": 1.05}',
                "system",
            )
            assert dup is None, "dedup انكسر بعد v18"
        finally:
            await c.close()

    asyncio.run(_run())
