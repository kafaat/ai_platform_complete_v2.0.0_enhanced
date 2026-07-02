"""tests_v9/test_irrigation_schedule_conflict_v29_5_op.py — كشف تعارُض جداول الريّ (v29.5-op-3).

الفجوة: ``create_schedule`` كان ``INSERT`` صرفاً بلا فحص تداخُل ⇒ جدولان فعّالان على
نفس الصمّام قد يتداخلان زمنيّاً ⇒ خطر *فتح مزدوج* للصمّام. جداول الريّ *متكرّرة* لا
مُطلقة (``start_time TIME`` + ``duration_min`` + ``days_of_week[]``؛ v25_irrigation.sql:43-45)
فلا يوجد ``tstzrange`` مفردة يُفرض عليها EXCLUDE عبر btree_gist — لذا الحارس على مستوى
التطبيق (409) عبر ``schedules_overlap`` (نمذجة أسبوعيّة 7×1440 دقيقة مع لفّ منتصف الليل).

طبقتان:
  • **وحدة** (``-m unit``، بلا قاعدة): المنطق النقيّ ``schedules_overlap`` — تداخُل/تلاصُق/
    تقاطُع الأيّام/لفّ منتصف الليل + فحص تعاقُد على مصدر ``create_schedule`` (وجود حارس 409).
  • **تكامل** (``-m integration``، Postgres عبر TEST_DATABASE_URL): إدراج صمّام + جدول فعّال،
    ثمّ تشغيل *نفس* استعلام الحارس وتغذيته إلى ``schedules_overlap`` على صفوف حقيقيّة من
    القاعدة (أنواع TIME وINTEGER[] كما يعيدها asyncpg): متداخِل ⇒ يُرفض؛ غير متداخِل ⇒ يُقبَل؛
    صمّام مختلف/جدول مُعطّل ⇒ يُقبَل. يتخطّى بوضوح إن غابت القاعدة.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import time

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
if CORE not in sys.path:
    sys.path.insert(0, CORE)


# ════════════════════════════ وحدة — المنطق النقيّ (بلا قاعدة) ════════════════════════════


@pytest.mark.unit
def test_overlap_same_day_windows():
    from api.irrigation_models import schedules_overlap

    # 06:00 لمدّة 120د (06:00–08:00) مقابل 07:00 لمدّة 60د (07:00–08:00) ⇒ تداخُل.
    assert schedules_overlap(time(6, 0), 120, None, time(7, 0), 60, None) is True
    # 06:00–08:00 مقابل 09:00–10:00 ⇒ لا تداخُل.
    assert schedules_overlap(time(6, 0), 120, None, time(9, 0), 60, None) is False


@pytest.mark.unit
def test_adjacent_windows_are_not_conflict():
    from api.irrigation_models import schedules_overlap

    # نوافذ نصف مفتوحة: 06:00–07:00 و07:00–08:00 متلاصقان لا متداخلان.
    assert schedules_overlap(time(6, 0), 60, None, time(7, 0), 60, None) is False


@pytest.mark.unit
def test_disjoint_days_never_conflict():
    from api.irrigation_models import schedules_overlap

    # نفس الوقت لكن أيّام مختلفة (الإثنين=0 مقابل الثلاثاء=1) ⇒ لا تداخُل.
    assert schedules_overlap(time(6, 0), 120, [0], time(6, 0), 120, [1]) is False
    # يوم مشترك (الإثنين) ⇒ تداخُل.
    assert schedules_overlap(time(6, 0), 120, [0, 2], time(7, 0), 60, [0, 3]) is True


@pytest.mark.unit
def test_none_days_means_daily_and_overlaps_any_day():
    from api.irrigation_models import schedules_overlap

    # None = يوميّاً ⇒ يتقاطع مع أيّ يوم محدّد في نفس النافذة الزمنيّة.
    assert schedules_overlap(time(6, 0), 120, None, time(6, 30), 60, [3]) is True


@pytest.mark.unit
def test_midnight_wrap_bleeds_into_next_day():
    from api.irrigation_models import schedules_overlap

    # الإثنين 23:00 لمدّة 120د يمتدّ إلى الثلاثاء 00:00–01:00 ⇒ يتعارض مع الثلاثاء 00:30.
    assert schedules_overlap(time(23, 0), 120, [0], time(0, 30), 30, [1]) is True
    # وأسبوعيّاً: الأحد (6) 23:00 لمدّة 120د يلتفّ إلى الإثنين (0) 00:00–01:00.
    assert schedules_overlap(time(23, 0), 120, [6], time(0, 30), 30, [0]) is True


@pytest.mark.unit
def test_create_schedule_source_has_409_guard():
    """فحص تعاقُد: مصدر ``create_schedule`` يستدعي الحارس ويرفع 409 قبل الإدراج."""
    path = os.path.join(CORE, "api", "routers", "irrigation.py")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    start = src.find("async def create_schedule(")
    assert start != -1, "لم يُعثر على create_schedule"
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    body = src[start : (start + 1 + nxt.start()) if nxt else len(src)]
    assert "schedules_overlap" in body, "الحارس schedules_overlap غير مُستدعى"
    assert "status_code=409" in body, "لا يرفع 409 عند التعارُض"
    # الحارس قبل الإدراج (يمنع الكتابة عند التعارُض).
    assert body.index("schedules_overlap") < body.index("INSERT INTO irrigation_schedules")


# ════════════════════════ تكامل — القاعدة الحقيقيّة (Postgres) ════════════════════════

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://sahool_test:test_password@127.0.0.1:5433/sahool_test"
)


def _conflicts_against_existing(conn_rows, new_start, new_dur, new_days) -> bool:
    """يعكس منطق حارس ``create_schedule``: أيّ صفّ قائم يتداخل مع الجديد ⇒ تعارُض."""
    from api.irrigation_models import schedules_overlap

    for row in conn_rows:
        other_days = list(row["days_of_week"]) if row["days_of_week"] is not None else None
        if schedules_overlap(
            new_start, new_dur, new_days, row["start_time"], row["duration_min"], other_days
        ):
            return True
    return False


@pytest.mark.integration
async def test_schedule_conflict_against_real_db():
    asyncpg = pytest.importorskip("asyncpg")
    pytest.importorskip("api.irrigation_models")
    try:
        conn = await asyncpg.connect(TEST_DB_URL, timeout=5, statement_cache_size=0)
    except Exception:  # noqa: BLE001
        pytest.skip("قاعدة الاختبار غير مشغّلة")

    tid = str(uuid.uuid4())
    valve_a = "vlv_" + uuid.uuid4().hex[:10]
    valve_b = "vlv_" + uuid.uuid4().hex[:10]

    # الاستعلام الفعليّ الذي يشغّله الحارس في create_schedule (نفس المرشّح).
    guard_sql = (
        "SELECT schedule_id, start_time, duration_min, days_of_week "
        "FROM irrigation_schedules WHERE valve_id = $1 AND enabled = TRUE"
    )

    try:
        tr = conn.transaction()
        await tr.start()
        try:
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tid)

            # صمّامان تحت نفس المستأجِر.
            for vid in (valve_a, valve_b):
                await conn.execute(
                    "INSERT INTO irrigation_valves (valve_id, tenant_id, name) "
                    "VALUES ($1, $2::uuid, $3)",
                    vid,
                    tid,
                    "صمّام اختبار",
                )

            # جدول فعّال قائم على valve_a: 06:00 لمدّة 120د، يوميّاً.
            await conn.execute(
                "INSERT INTO irrigation_schedules "
                "(schedule_id, tenant_id, valve_id, name, start_time, duration_min, enabled) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, TRUE)",
                "sch_" + uuid.uuid4().hex[:10],
                tid,
                valve_a,
                "قائم",
                time(6, 0),
                120,
            )
            # جدول مُعطّل على valve_a يغطّي منتصف النهار — يجب ألّا يُحسب تعارُضاً.
            await conn.execute(
                "INSERT INTO irrigation_schedules "
                "(schedule_id, tenant_id, valve_id, name, start_time, duration_min, enabled) "
                "VALUES ($1, $2::uuid, $3, $4, $5, $6, FALSE)",
                "sch_" + uuid.uuid4().hex[:10],
                tid,
                valve_a,
                "مُعطّل",
                time(12, 0),
                120,
            )

            rows_a = await conn.fetch(guard_sql, valve_a)
            rows_b = await conn.fetch(guard_sql, valve_b)

            # المرشّح غير الفعّال المُعطّل مُستبعَد بالمرشّح enabled=TRUE ⇒ صفّ واحد فقط.
            assert len(rows_a) == 1, f"متوقّع جدول فعّال واحد على valve_a، الفعليّ: {len(rows_a)}"

            # ① متداخِل على نفس الصمّام (07:00 لمدّة 60د داخل 06:00–08:00) ⇒ يُرفض (409).
            assert _conflicts_against_existing(rows_a, time(7, 0), 60, None) is True, (
                "جدول متداخِل على نفس الصمّام يجب أن يُرفض"
            )

            # ② غير متداخِل على نفس الصمّام (09:00 لمدّة 60د) ⇒ يُقبَل (لا حظر مشروع).
            assert _conflicts_against_existing(rows_a, time(9, 0), 60, None) is False, (
                "جدول غير متداخِل على نفس الصمّام يجب أن يُقبَل"
            )

            # ③ صمّام مختلف (valve_b) في نفس النافذة الزمنيّة ⇒ يُقبَل (لا صفوف ⇒ لا تعارُض).
            assert rows_b == [], "valve_b بلا جداول"
            assert _conflicts_against_existing(rows_b, time(7, 0), 60, None) is False, (
                "جدول على صمّام مختلف يجب أن يُقبَل"
            )

            # ④ التعارُض المتداخِل يحترم الأيّام: نفس الوقت لكن يوم منفصل ⇒ يُقبَل.
            #     (الجدول القائم يوميّ ⇒ يتقاطع مع أيّ يوم، فنستخدم مرشّحاً يوميّاً مغايراً زمنيّاً.)
            assert _conflicts_against_existing(rows_a, time(20, 0), 60, [3]) is False, (
                "نافذة زمنيّة منفصلة يجب أن تُقبَل حتى على نفس الصمّام"
            )
        finally:
            await tr.rollback()
    finally:
        await conn.close()
