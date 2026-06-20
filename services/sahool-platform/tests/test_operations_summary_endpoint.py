"""اختبارات نقطة تلخيص العمليّات (routers/operations) — استدعاء مباشر للمعالِج.

نختبر المعالِج مباشرةً متفادين TestClient/المصادقة: العلم المُطفأ ⇒ 404؛ المُفعَّل مع
اتّصال قاعدة مُحاكى (best-effort) ⇒ تلخيص مُشكَّل صحيح، ومع فشل اتّصال المستأجِر ⇒ 503.
يُثبت أيضاً تسجيل النقطة في app.routes. لا قاعدة حقيقيّة (المسار التكامليّ منفصل).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import api.main  # noqa: F401 — تهيئة api.main كاملةً قبل استيراد الموجِّه
import pytest
from api.routers.operations import operations_summary_endpoint
from core.canonical_schemas import UserRole, UserSchema
from fastapi import HTTPException

pytestmark = pytest.mark.unit

_USER = UserSchema(
    user_id="u-ops",
    tenant_id="00000000-0000-0000-0000-000000000002",
    role=UserRole.OWNER,
    name_ar="مُشغِّل",
)


class _FakeConn:
    """اتّصال مُحاكى: fetchval يعيد قيماً ثابتة، fetch يعيد صفوف الخطورة.

    ``fail_tables`` مجموعة أسماء جداول تُطلِق استثناءً لمحاكاة جدول غائب (best-effort).
    """

    def __init__(self, fail_tables=None):
        self._fail = fail_tables or set()

    async def fetchval(self, sql, *args):
        for t in self._fail:
            if t in sql:
                raise RuntimeError(f"relation {t} does not exist")
        if "COUNT(*) FROM fields" in sql:
            return 8
        if "COUNT(*) FROM equipment" in sql:
            return 5
        if "COUNT(*) FROM iot_devices" in sql:
            return 12
        if "COUNT(*) FROM decision_record" in sql:
            return 7
        if "COUNT(*) FROM irrigation_valves" in sql:
            return 4
        if "COUNT(*) FROM irrigation_schedules" in sql:
            return 2
        if "MAX(created_at) FROM alerts" in sql:
            return None
        if "MAX(created_at) FROM decision_record" in sql:
            return None
        return 0

    async def fetch(self, sql, *args):
        if "FROM alerts" in sql and "GROUP BY severity" in sql:
            for t in self._fail:
                if t in sql:
                    raise RuntimeError("relation alerts does not exist")
            return [
                {"severity": "info", "count": 2},
                {"severity": "warning", "count": 3},
                {"severity": "critical", "count": 1},
            ]
        return []


def _patch_conn(monkeypatch, conn=None, raise_open=False):
    @asynccontextmanager
    async def _fake_tenant_connection(user):
        if raise_open:
            raise RuntimeError("pool unavailable")
        yield conn

    # نرقّع المرجع في وحدة الموجِّه (المُستورَد من api.main).
    monkeypatch.setattr("api.routers.operations.tenant_connection", _fake_tenant_connection)


async def test_flag_off_returns_404(monkeypatch):
    monkeypatch.delenv("FEATURE_OPERATIONS_WALL", raising=False)
    with pytest.raises(HTTPException) as e:
        await operations_summary_endpoint(user=_USER)
    assert e.value.status_code == 404


async def test_flag_on_full_summary(monkeypatch):
    monkeypatch.setenv("FEATURE_OPERATIONS_WALL", "true")
    _patch_conn(monkeypatch, conn=_FakeConn())
    out = await operations_summary_endpoint(user=_USER)
    assert out["totals"]["fields"] == 8
    assert out["totals"]["active_alerts"] == 6
    assert out["alerts"]["by_severity"] == {"info": 2, "warning": 3, "critical": 1}
    assert out["irrigation"] == {"valves": 4, "schedules": 2, "available": True}
    assert out["provenance"]["calibrated"] == "not_applicable"
    assert "note_ar" not in out["provenance"]  # كلّ المصادر حاضرة
    assert out["tenant_id"] == "00000000-0000-0000-0000-000000000002"


async def test_flag_on_missing_table_is_best_effort(monkeypatch):
    # جدول equipment غائب ⇒ 0 + note، البقيّة سليمة، لا انهيار، لا 503.
    monkeypatch.setenv("FEATURE_OPERATIONS_WALL", "1")
    _patch_conn(monkeypatch, conn=_FakeConn(fail_tables={"equipment"}))
    out = await operations_summary_endpoint(user=_USER)
    assert out["totals"]["fields"] == 8  # مصدر آخر سليم
    assert out["totals"]["equipment"] == 0
    assert "equipment" in out["provenance"]["note_ar"]


async def test_flag_on_db_open_failure_returns_503(monkeypatch):
    monkeypatch.setenv("FEATURE_OPERATIONS_WALL", "yes")
    _patch_conn(monkeypatch, raise_open=True)
    with pytest.raises(HTTPException) as e:
        await operations_summary_endpoint(user=_USER)
    assert e.value.status_code == 503


def test_endpoint_registered_in_app():
    from api.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/operations/summary" in paths
