"""إسقاط الحالة القانونيّة المُخزَّن (Canonical Field State — Phase 2).

يثبّت منطق recompute_field_state (كشف التبدّل + UPSERT) عبر conn وهميّ بلا قاعدة
بيانات، ووجود حدث FIELD_STATE_CHANGED + هجرة v53 في MANIFEST. التطبيق الفعليّ
للهجرة على Postgres يغطّيه Integration Tests (يطبّق كلّ migrations).
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _FakeConn:
    """conn وهميّ: يجيب fetchval/fetchrow حسب نصّ الاستعلام، ويسجّل execute."""

    def __init__(self, *, last_image_date=None, soil=None, weather=None, tenant_id="t1", prev=None):
        self.last_image_date = last_image_date
        self.soil = soil
        self.weather = weather
        self.tenant_id = tenant_id
        self.prev = prev
        self.executed: list = []

    def transaction(self):
        # SAVEPOINT وهميّ (gather يلفّ قراءة NDVI بمعاملة فرعيّة) — لا-عمل.
        class _Tx:
            async def __aenter__(self_):
                return None

            async def __aexit__(self_, *a):
                return False

        return _Tx()

    async def fetchval(self, sql, *args):
        if "imagery_automation_fields" in sql:
            return self.last_image_date
        if "soil_lab_tests" in sql:
            return self.soil
        if "weather_automation_cache" in sql:
            return self.weather
        if "FROM fields" in sql:
            return self.tenant_id
        return None

    async def fetchrow(self, sql, *args):
        if "FROM field_state" in sql:
            return self.prev
        return None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


@pytest.mark.asyncio
async def test_recompute_upserts_and_flags_changed_when_no_prev(core_on_path):
    from api.field_state_projection import recompute_field_state

    conn = _FakeConn(prev=None)  # لا صفّ سابق ⇒ changed
    res = await recompute_field_state(conn, "fld_1")
    assert res["changed"] is True
    assert res["state"]["validity"] == "insufficient"  # لا مصادر ⇒ بيانات ناقصة
    assert len(conn.executed) == 1  # UPSERT واحد
    # الوسيط الأوّل في UPSERT هو field_id، و12 وسيطاً ($1..$12؛ computed_at=NOW())
    assert conn.executed[0][1][0] == "fld_1"
    assert len(conn.executed[0][1]) == 12


@pytest.mark.asyncio
async def test_recompute_no_change_when_same_validity(core_on_path):
    from api.field_state_projection import recompute_field_state

    # حالة سابقة بنفس النتيجة (insufficient/human_review) ⇒ لا تبدّل
    conn = _FakeConn(prev={"validity": "insufficient", "execution_mode": "human_review"})
    res = await recompute_field_state(conn, "fld_1")
    assert res["changed"] is False
    assert len(conn.executed) == 1  # يُحفظ مع ذلك (تحديث computed_at)


@pytest.mark.asyncio
async def test_recompute_changed_when_validity_differs(core_on_path):
    from api.field_state_projection import recompute_field_state

    conn = _FakeConn(prev={"validity": "valid", "execution_mode": "auto"})
    res = await recompute_field_state(conn, "fld_1")
    assert res["changed"] is True  # valid → insufficient


@pytest.mark.asyncio
async def test_recompute_skips_upsert_for_unknown_field(core_on_path):
    from api.field_state_projection import recompute_field_state

    conn = _FakeConn(tenant_id=None)  # حقل غير موجود ضمن المستأجِر
    res = await recompute_field_state(conn, "ghost")
    assert res["changed"] is False
    assert conn.executed == []  # لا حفظ إسقاط يتيم


def test_field_state_changed_event_registered(core_on_path):
    from api.event_bus import EventType

    assert EventType["FIELD_STATE_CHANGED"].value == "field.state_changed"


def test_rls_tables_after_force_all_are_explicitly_forced():
    """كلّ جدول يُفعّل RLS ويُنشأ بعد v9_rls_force_all يجب أن يَفرض RLS صراحةً.

    v9_rls_force_all يفرض RLS على الجداول الموجودة وقت تشغيله فقط؛ الجداول المُنشأة
    بعده (في إقلاع نظيف) لا يلتقطها ⇒ يتجاوز مالكُ الجدول العزلَ. هذا الحارس يمنع
    تكرار الثغرة (ملاحظة مراجعة Copilot — PR #131).
    """
    mdir = os.path.join(ROOT, "migrations")
    with open(os.path.join(mdir, "MANIFEST.txt"), encoding="utf-8") as f:
        order = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    force_all_idx = order.index("v9_rls_force_all.sql")
    offenders = []
    for fname in order[force_all_idx + 1 :]:
        path = os.path.join(mdir, fname)
        if not os.path.exists(path):
            continue
        sql = open(path, encoding="utf-8").read()
        if "ENABLE ROW LEVEL SECURITY" in sql and "FORCE ROW LEVEL SECURITY" not in sql:
            offenders.append(fname)
    assert offenders == [], f"جداول تُفعّل RLS بلا FORCE بعد v9_rls_force_all: {offenders}"


def test_v53_migration_in_manifest_and_exists():
    manifest = os.path.join(ROOT, "migrations", "MANIFEST.txt")
    with open(manifest, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    assert "v53_field_state_projection.sql" in lines
    # يُطبَّق قبل فرض append-only (وإلّا لا توجد الجداول وقت الحظر)
    assert lines.index("v53_field_state_projection.sql") < lines.index(
        "v9_append_only_enforcement.sql"
    )
    assert os.path.exists(os.path.join(ROOT, "migrations", "v53_field_state_projection.sql"))
