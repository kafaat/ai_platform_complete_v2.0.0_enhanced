"""tests_v9/test_field_aggregate_ports_integration.py — تكامل منفذ `load_state`.

يتحقّق أنّ `api.field_aggregate_ports.load_state` يعكس حالة القاعدة الحقيقيّة
(وجود الحقل، الموسم النشط) ضمن سياق مستأجِر واحد.

يعمل عبر: ``pytest -m integration`` فقط — مُستثنى من بوّابة ``-m unit`` الافتراضيّة،
ويتطلّب Postgres+PostGIS مُهيّأً عبر ``TEST_DATABASE_URL``. يتخطّى بوضوح (SKIP) إن
لم تتوفّر القاعدة — كأشقّائه في ``tests_v9/`` (مثل ``test_rls_isolation.py``).

ملاحظات صدق:
  • GUC العزل هو ``app.current_tenant`` (سياسات RLS في
    ``migrations/v9_rls_tenant_isolation.sql`` وغيرها تقرأ
    ``current_setting('app.current_tenant', …)``) — نضبطه عبر ``set_config(…, false)``.
  • ``field_id`` بصيغة الإنتاج (``fld_…``، VARCHAR) — تمثيليّ.
  • ``lifecycle_state`` **لا يقرؤه** ``load_state`` عمداً (جدول ``field_lifecycle``
    مفتاحه UUID ≠ ``field_id`` النصّيّ، والنواة لا تستعمله) — فنؤكّد فقط أنّه يبقى
    ``None`` ولا نُدرِج في ذلك الجدول.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

# جذر منصّة sahool على sys.path كي يعمل ``import api.field_aggregate_ports``
# (نفس نمط ``tests_v9/test_db_integration.py``).
_PLATFORM = os.path.join(os.path.dirname(__file__), "..", "services", "sahool-platform")
if _PLATFORM not in sys.path:
    sys.path.insert(0, _PLATFORM)

asyncpg = pytest.importorskip("asyncpg", reason="asyncpg غير مثبّت")

from api.field_aggregate_ports import load_state  # noqa: E402

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://sahool_test:test_password@localhost:5433/sahool_test",
)


@pytest.fixture
async def conn():
    """اتّصال للإعداد + ضبط سياق مستأجِر (``app.current_tenant``).

    ينظّف صفوف الاختبار في الـteardown (seasons → fields). يتخطّى بوضوح إن لم تتوفّر
    القاعدة (CI offline / محليّاً بلا Postgres).
    """
    try:
        c = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"قاعدة البيانات غير متاحة: {type(e).__name__}")

    tenant = str(uuid.uuid4())
    field_id = f"fld_{uuid.uuid4().hex[:12]}"
    season_id = f"season-{uuid.uuid4().hex[:12]}"

    await c.execute("SELECT set_config('app.current_tenant', $1, false)", tenant)

    ctx = {"tenant": tenant, "field_id": field_id, "season_id": season_id}
    try:
        yield c, ctx
    finally:
        try:
            await c.execute("DELETE FROM seasons WHERE field_id = $1", field_id)
            await c.execute("DELETE FROM fields WHERE field_id = $1", field_id)
        finally:
            await c.close()


async def test_load_state_nonexistent_field(conn):
    """حقل غير موجود ⇒ ``exists is False`` (دلالة 404 في الـendpoints)."""
    c, _ = conn
    state = await load_state(c, f"fld_{uuid.uuid4().hex[:12]}")
    assert state.exists is False
    assert state.has_active_season is False
    assert state.active_season_id is None


async def test_load_state_reflects_real_db(conn):
    """يعكس وجود الحقل ثمّ ظهور الموسم النشط — قاعدة حقيقيّة."""
    c, ctx = conn
    field_id = ctx["field_id"]
    season_id = ctx["season_id"]
    tenant = ctx["tenant"]

    # (1) قبل أيّ إدراج — الحقل غير موجود.
    pre = await load_state(c, field_id)
    assert pre.exists is False

    # (2) أدرِج الحقل (الحدّ الأدنى الصالح: field_id, name, tenant_id) → موجود بلا موسم.
    await c.execute(
        "INSERT INTO fields (field_id, name, tenant_id) VALUES ($1, $2, $3)",
        field_id,
        "حقل اختبار التكامل",
        tenant,
    )
    after_field = await load_state(c, field_id)
    assert after_field.exists is True
    assert after_field.has_active_season is False
    assert after_field.active_season_id is None
    assert after_field.lifecycle_state is None  # لا يُقرأ عمداً — يبقى None

    # (3) أدرِج موسماً نشطاً (status='active') → الموسم النشط ينعكس.
    await c.execute(
        "INSERT INTO seasons (season_id, tenant_id, field_id, status) VALUES ($1, $2, $3, 'active')",
        season_id,
        tenant,
        field_id,
    )
    after_season = await load_state(c, field_id)
    assert after_season.exists is True
    assert after_season.has_active_season is True
    assert after_season.active_season_id == season_id
