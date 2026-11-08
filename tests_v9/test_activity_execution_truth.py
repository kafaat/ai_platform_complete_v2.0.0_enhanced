"""الأنشطة: «المُنفَّذ» لا يشمل المُخطَّط ولا المستقبل.

• دفتر المدخلات (``GET /fields/{id}/input-traceability``) كان يجمع كلّ نشاطٍ بلا ترشيح
  حالة، ويأخذ ``performed_on or scheduled_for`` تاريخاً — فتُعدّ كلفةُ عمليّةٍ مُخطَّطة
  أو مُتخطّاة كأنّها طُبِّقت. الآن: ``status='done' AND performed_on IS NOT NULL`` فقط.
• ``POST /fields/{id}/activities`` كان يُسجِّل ``done`` لأيّ ``performed_on`` ولو بعد
  سنة. الآن: 422 لما بعد الغد (سماحُ يومٍ للمناطق الزمنيّة).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_CORE = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
_TENANT = "00000000-0000-0000-0000-0000000000c3"


def _fields():
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    import api.main  # noqa: F401 — يحلّ دورة استيراد الموجِّهات
    import api.routers.fields as fields

    return fields


def _user():
    return SimpleNamespace(tenant_id=_TENANT, user_id="u1", role="farmer")


class _ActivitiesTable:
    """جدول أنشطة صغير يطبّق شرطَي الحالة/التاريخ **فقط إن وردا في SQL** —
    فلو أُزيل الترشيح من الاستعلام لعادت الصفوف المُخطَّطة وأحمرّ الاختبار."""

    def __init__(self, rows):
        self.rows = rows
        self.sql: list[str] = []

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if "area_ha" in sql:
            return 2.0
        return 1

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        out = list(self.rows)
        if "status = 'done'" in sql:
            out = [r for r in out if r["status"] == "done"]
        if "performed_on IS NOT NULL" in sql:
            out = [r for r in out if r["performed_on"] is not None]
        return out

    async def fetchrow(self, sql, *args):
        return None

    def transaction(self):
        class _Tx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *exc):
                return False

        return _Tx()


def _row(status, performed_on, scheduled_for, cost):
    return {
        "activity_type": "fertilizing",
        "details": {"product_name": "urea", "quantity": 50, "unit": "kg", "cost": cost},
        "status": status,
        "performed_on": performed_on,
        "scheduled_for": scheduled_for,
    }


@pytest.mark.asyncio
async def test_input_ledger_counts_only_done_activities_with_a_performed_date(monkeypatch):
    fields = _fields()
    table = _ActivitiesTable(
        [
            _row("done", date(2026, 3, 1), None, 100.0),
            _row("planned", None, date(2026, 4, 1), 900.0),
            _row("skipped", None, date(2026, 4, 2), 700.0),
        ]
    )

    @asynccontextmanager
    async def tenant_connection(user):
        yield table

    async def assert_field(conn, field_id):
        return None

    monkeypatch.setattr(fields, "tenant_connection", tenant_connection)
    monkeypatch.setattr(fields, "_assert_field_in_tenant", assert_field)
    ledger = await fields.field_input_traceability("f1", season_id=None, user=_user())

    act_sql = next(s for s in table.sql if "FROM activities" in s)
    assert "status = 'done'" in act_sql and "performed_on IS NOT NULL" in act_sql
    assert "scheduled_for" not in act_sql

    assert ledger["total_cost"] == 100.0, "كلفة نشاط غير مُنفَّذ دخلت الدفتر"
    assert sum(g["count"] for g in ledger["by_input_type"].values()) == 1


def test_future_performed_on_is_rejected_with_422():
    _fields()  # sys.path + import side effects, as the other tests
    from api import field_models as truth

    future = datetime.now(UTC).date() + timedelta(days=5)
    with pytest.raises(HTTPException) as e:
        truth.reject_future_performed_on(future)
    assert e.value.status_code == 422
    assert e.value.detail["code"] == "performed_on_in_future"


def test_performed_on_today_and_one_day_ahead_are_tolerated():
    _fields()
    from api import field_models as truth

    today = datetime.now(UTC).date()
    for d in (None, today - timedelta(days=30), today, today + timedelta(days=1)):
        truth.reject_future_performed_on(d)  # لا رفع


@pytest.mark.asyncio
async def test_create_activity_rejects_future_execution_before_touching_the_db(monkeypatch):
    fields = _fields()
    opened: list[object] = []

    @asynccontextmanager
    async def tenant_connection(user):
        opened.append(user)
        yield None

    monkeypatch.setattr(fields, "tenant_connection", tenant_connection)
    req = fields.ActivityCreateRequest(
        activity_type=next(iter(fields._ACTIVITY_TYPES)),
        title_ar="تسميد",
        performed_on=(datetime.now(UTC).date() + timedelta(days=10)).isoformat(),
    )
    with pytest.raises(HTTPException) as e:
        await fields.create_activity("f1", req, idem=None, user=_user())
    assert e.value.status_code == 422
    assert opened == []
