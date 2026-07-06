#!/usr/bin/env python3
"""تشخيص «تشغيلة backfill عالقة في planned» (الخطّ الزمنيّ يُظهر الشهر الحاليّ فقط).

للقراءة فقط — لا يعدّل شيئاً. شغّله **داخل حاوية raster-service أو عامل الفحص**
(حيث تتوفّر ``JOBS_DATABASE_URL``/``DATABASE_URL`` و``RASTER_ASYNC_BACKFILL_ENABLED``):

    docker compose -f docker-compose.v9.yml exec sahool-raster-backfill-scan-worker \
        python /app/scripts/diagnose_backfill_stuck.py

أو ضدّ القاعدة مباشرةً:

    JOBS_DATABASE_URL=postgresql://sahool_jobs:***@localhost:5432/sahool \
        python scripts/diagnose_backfill_stuck.py

يفحص، بالترتيب، الأسباب الثلاثة التي تُبقي التشغيلة عالقة في ``planned``:
  ١) الرايةُ ``RASTER_ASYNC_BACKFILL_ENABLED`` — هل العامل مُفعَّل أصلاً؟
  ٢) انحراف المخطّط — هل عمود ``backfill_runs.source`` (v147) موجود؟ غيابه يجعل
     استعلام المطالبة يفشل كلّ دورة (يُبتلَع كـ«backfill scan cycle skipped»).
  ٣) هل يستطيع دور القاعدة رؤية صفوف planned فعلاً (BYPASSRLS للعامل)؟ ويُحاكي
     استعلام المطالبة الحقيقيّ (بـROLLBACK — لا يطالب فعليّاً) ويطبع أيّ خطأ.
"""

from __future__ import annotations

import asyncio
import os
import sys

try:
    import asyncpg
except Exception as e:  # noqa: BLE001
    print(f"✗ تعذّر استيراد asyncpg: {e}\n  شغّل السكربت داخل حاوية raster-service.")
    sys.exit(2)

_TRUE = ("1", "true", "yes", "on")


def _flag_enabled() -> bool:
    return str(os.getenv("RASTER_ASYNC_BACKFILL_ENABLED", "false")).strip().lower() in _TRUE


# نفس استعلام المطالبة الحرفيّ في backfill_scan_worker.run_once (دون FOR UPDATE، بـLIMIT).
_CLAIM_SQL = """
SELECT id, tenant_id, field_id, from_date, to_date, indices, max_cloud_pct,
       geometry_revision, clip_polygon_geojson, apply_cloud_mask, limit_per_month,
       COALESCE(source, 'sentinel-2') AS source
FROM backfill_runs
WHERE status = 'planned'
ORDER BY created_at
LIMIT 1
"""


async def _main() -> int:
    print("═══ تشخيص backfill العالق ═══\n")

    # ١) الراية.
    enabled = _flag_enabled()
    raw = os.getenv("RASTER_ASYNC_BACKFILL_ENABLED", "(غير مضبوطة → الافتراض false)")
    mark = "✓" if enabled else "✗"
    print(
        f"{mark} RASTER_ASYNC_BACKFILL_ENABLED = {raw!r} ⇒ العامل {'مُفعَّل' if enabled else 'خامل'}"
    )
    if not enabled:
        print(
            "  ← هذا وحده يفسّر العلوق: الـAPI يُنشئ تشغيلات planned بينما العامل خامل.\n"
            "    اضبط RASTER_ASYNC_BACKFILL_ENABLED=true للعامل والـAPI وأعِد التشغيل."
        )

    dsn = os.getenv("JOBS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        print("\n✗ لا JOBS_DATABASE_URL/DATABASE_URL — شغّل السكربت داخل الحاوية.")
        return 2

    try:
        conn = await asyncpg.connect(dsn=dsn)
    except Exception as e:  # noqa: BLE001
        print(f"\n✗ تعذّر الاتصال بالقاعدة: {e}")
        return 2

    try:
        # ٢) وجود العمود source (v147).
        has_source = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name='backfill_runs' AND column_name='source')"
        )
        mark = "✓" if has_source else "✗"
        print(f"\n{mark} عمود backfill_runs.source (v147) {'موجود' if has_source else 'مفقود'}")
        if not has_source:
            print(
                "  ← انحراف مخطّط: استعلام المطالبة يشير إلى source فيفشل كلّ دورة\n"
                "    (يظهر في سجلّ العامل: 'backfill scan cycle skipped: column source ...').\n"
                "    طبّق ترحيل v147 (scripts_v9/run_migrations.sql خطوة 153)."
            )

        # حالة التشغيلات.
        rows = await conn.fetch(
            "SELECT status, count(*) AS n, min(created_at) AS oldest "
            "FROM backfill_runs GROUP BY status ORDER BY n DESC"
        )
        print("\n— توزيع حالات backfill_runs —")
        if not rows:
            print("  (لا تشغيلات إطلاقاً — الـAPI لم يُنشئ أيّ صفّ؛ تحقّق من مسار الطلب/الراية.)")
        for r in rows:
            print(f"  {r['status']:<24} {r['n']:>4}   أقدم: {r['oldest']}")

        planned_n = await conn.fetchval("SELECT count(*) FROM backfill_runs WHERE status='planned'")
        if planned_n:
            oldest_age = await conn.fetchval(
                "SELECT now() - min(created_at) FROM backfill_runs WHERE status='planned'"
            )
            print(
                f"\n⚠ {planned_n} تشغيلة عالقة في planned (أقدمها منذ {oldest_age}). "
                "لو العامل حيّ وسليم، يجب أن تُلتقَط خلال ثوانٍ."
            )

        # ٣) محاكاة استعلام المطالبة (ROLLBACK — لا يطالب فعليّاً).
        print("\n— محاكاة استعلام المطالبة (backfill_scan_worker.run_once) —")
        tr = conn.transaction()
        await tr.start()
        try:
            claimed = await conn.fetch(_CLAIM_SQL)
            await tr.rollback()
            if claimed:
                run = dict(claimed[0])
                print(
                    f"  ✓ الاستعلام ينجح ويرى تشغيلة #{run['id']} "
                    f"(field={run['field_id']}, indices={run['indices']}, source={run['source']}).\n"
                    "    ← المخطّط سليم والصفّ مرئيّ ⇒ العامل غالباً غير مُشغَّل أو يتعطّل عند الإقلاع.\n"
                    "      افحص سجلّه: docker compose logs sahool-raster-backfill-scan-worker"
                )
            else:
                print("  ✓ الاستعلام ينجح لكن لا صفّ planned مرئيّ (إمّا لا يوجد، أو RLS يحجب).")
        except Exception as e:  # noqa: BLE001
            await tr.rollback()
            print(
                f"  ✗ استعلام المطالبة يرمي: {e}\n"
                "    ← هذا هو سبب العلوق مباشرةً (يُبتلَع كـ'backfill scan cycle skipped').\n"
                "      عالِج الخطأ أعلاه (غالباً ترحيل مفقود)."
            )
    finally:
        await conn.close()

    print("\n═══ انتهى التشخيص ═══")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
