"""اختبارات منفذ القراءة الحيّ `load_state` (offline) — جسر الـAggregate بالقاعدة.

يتحقّق من أنّ `load_state` (api/field_aggregate_ports.py) يبني `FieldState` مطابِقاً
لِما تفحصه endpoints الإنتاج باتّصال **وهميّ** (لا قاعدة): قصرٌ عند غياب الحقل (لا
يُصدِر استعلام الموسم)، والموسم النشط (LIMIT 1). كما يثبّت أنّ المنفذ **لا يستعلم**
`field_lifecycle` إطلاقاً (نوع field_id فيه UUID ≠ النصّ؛ والنواة لا تستعمل
lifecycle_state) — حارس انحدار صريح. ويثبّت نصوص الـSQL الفعليّة (FROM fields /
status='active') صدقاً مع عقد القاعدة.
"""

import pytest
from api.field_aggregate import FieldState
from api.field_aggregate_ports import load_state

pytestmark = pytest.mark.unit


class _FakeConn:
    """اتّصال وهميّ يحاكي `fetchval`/`fetchrow` لـasyncpg بقيم مُعلَّبة حسب نصّ الـSQL.

    يوزّع حسب جزءٍ من الـSQL: "FROM fields" → فحص الوجود، "FROM seasons" → الموسم
    النشط (fetchrow ⇒ صفّ Record-like = dict). أيّ استعلام لـ`field_lifecycle` خطأ
    (المنفذ يجب ألّا يلمسه). يسجّل كلّ نصوص الـSQL في `seen_sql` لتأكيد العقد.
    """

    def __init__(self, *, exists=True, season_row=None):
        self._exists = exists
        self._season_row = season_row
        self.seen_sql: list[str] = []

    async def fetchval(self, sql, *args):
        self.seen_sql.append(sql)
        if "field_lifecycle" in sql:
            raise AssertionError("المنفذ يجب ألّا يستعلم field_lifecycle (نوع UUID ≠ النصّ)")
        if "FROM fields" in sql:
            return 1 if self._exists else None
        raise AssertionError(f"fetchval غير متوقَّع: {sql!r}")

    async def fetchrow(self, sql, *args):
        self.seen_sql.append(sql)
        if "FROM seasons" in sql:
            return self._season_row
        raise AssertionError(f"fetchrow غير متوقَّع: {sql!r}")


async def test_missing_field_short_circuits_without_extra_queries():
    # حقل غير موجود ⇒ FieldState(exists=False)، ولا يُصدَر استعلام الموسم.
    conn = _FakeConn(exists=False)
    state = await load_state(conn, "f1")
    assert state == FieldState(field_id="f1", exists=False)
    assert len(conn.seen_sql) == 1
    assert "FROM fields" in conn.seen_sql[0]
    assert not any("FROM seasons" in s for s in conn.seen_sql)


async def test_existing_field_without_active_season():
    # حقل موجود بلا موسم نشط ⇒ has_active_season=False, active_season_id=None.
    conn = _FakeConn(exists=True, season_row=None)
    state = await load_state(conn, "f1")
    assert state.exists is True
    assert state.has_active_season is False
    assert state.active_season_id is None
    assert state.lifecycle_state is None


async def test_existing_field_with_active_season():
    # موسم نشط (صفّ Record-like) ⇒ has_active_season=True, active_season_id=قيمة الصفّ.
    conn = _FakeConn(exists=True, season_row={"season_id": "ssn_x"})
    state = await load_state(conn, "f1")
    assert state.has_active_season is True
    assert state.active_season_id == "ssn_x"


async def test_lifecycle_state_never_read_stays_none():
    # عقد صريح: المنفذ لا يقرأ field_lifecycle (نوع UUID مقابل field_id النصّيّ، ولا
    # حاجة له في الـinvariants) ⇒ lifecycle_state دائماً None ولا استعلام للجدول.
    conn = _FakeConn(exists=True, season_row={"season_id": "ssn_x"})
    state = await load_state(conn, "f1")
    assert state.lifecycle_state is None
    assert not any("field_lifecycle" in s for s in conn.seen_sql)


async def test_issued_sql_matches_expected_contract():
    # يثبّت نصوص الـSQL التي يُصدِرها المنفذ: وجود + موسم نشط فقط (لا field_lifecycle).
    conn = _FakeConn(exists=True, season_row={"season_id": "ssn_x"})
    await load_state(conn, "f1")
    existence = next(s for s in conn.seen_sql if "FROM fields" in s)
    season = next(s for s in conn.seen_sql if "FROM seasons" in s)
    assert "SELECT 1 FROM fields" in existence
    assert "status = 'active'" in season
    assert "LIMIT 1" in season
    assert not any("field_lifecycle" in s for s in conn.seen_sql)
