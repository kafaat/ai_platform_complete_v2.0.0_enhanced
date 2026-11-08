"""PATCH /api/v1/fields/{field_id}/activities/{activity_id} — تدفّق المعالِج.

بديل اتّصال مصغّر يسجّل الاستعلامات ويُعيد صفّاً مُعدّاً: يتحقّق من 404/409، ومن أنّ
الحالة نفسها لا تكتب ولا تُصدِر حدثاً، ومن أنّ planned→done يكتب بشرط status='planned'
ويُصدِر الحدث المحدَّد بحمولة تحمل performed_on. لا يدّعي سلوك القاعدة (CHECK/RLS).
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace

import api.main  # noqa: F401 — التطبيق أوّلاً: الراوتر يُستورَد من ذيل main (دائريّ)
import pytest
from api.field_models import ActivityTransitionRequest
from api.routers import tasks as tasks_router
from fastapi import HTTPException

pytestmark = pytest.mark.unit

USER = SimpleNamespace(user_id="u1", tenant_id="00000000-0000-0000-0000-000000000001")


def _row(status="planned", details=None, performed_on=None):
    return {
        "activity_id": "act_1",
        "field_id": "fld_1",
        "season_id": "ssn_1",
        "activity_type": "fertilization",
        "title_ar": None,
        "details": json.dumps(details or {"product_name": "يوريا", "quantity": 50}),
        "scheduled_for": date(2026, 3, 1),
        "performed_on": performed_on,
        "status": status,
        "created_at": None,
    }


class _StandInConn:
    def __init__(self, row, field_exists=True):
        self.row = row
        self.field_exists = field_exists
        self.updates: list[tuple] = []

    async def fetchval(self, query, *args):
        return 1 if self.field_exists else None

    async def fetchrow(self, query, *args):
        if query.startswith("SELECT"):
            return self.row
        self.updates.append((query, args))
        if self.row is None or self.row["status"] != "planned":
            return None
        return {**self.row, "status": args[2], "performed_on": args[3], "details": args[4]}


def _run(monkeypatch, conn, req):
    events: list[tuple] = []

    @asynccontextmanager
    async def _tenant_connection(user):
        yield conn

    async def _emit(conn_, user, event_type, entity_type, entity_id, payload):
        events.append((event_type, entity_type, entity_id, payload))

    async def _recompute(conn_, field_id):
        return {"changed": False, "state": {}}

    import api.field_state_projection as fsp

    monkeypatch.setattr(tasks_router, "tenant_connection", _tenant_connection)
    monkeypatch.setattr(tasks_router, "_emit_domain_event", _emit)
    monkeypatch.setattr(fsp, "recompute_field_state", _recompute)
    result = asyncio.run(
        tasks_router.transition_activity("fld_1", "act_1", req, idem=None, user=USER)
    )
    return result, events


def test_planned_to_done_updates_guarded_row_and_emits_specific_event(monkeypatch):
    conn = _StandInConn(_row())
    req = ActivityTransitionRequest(
        status="done", performed_on="2026-03-04", actual_quantity=42, actual_cost=900
    )
    result, events = _run(monkeypatch, conn, req)
    assert result["status"] == "done" and result["performed_on"] == "2026-03-04"
    assert result["details"]["quantity"] == 42 and result["details"]["planned_quantity"] == 50
    ((query, args),) = conn.updates
    assert "status = 'planned'" in query  # لا كتابة فوق صفّ انتقل
    assert args[2] == "done" and args[3] == date(2026, 3, 4)
    ((event_type, entity_type, entity_id, payload),) = events
    assert event_type == "FERTILIZER_APPLIED" and entity_type == "activity"
    assert entity_id == "act_1"
    assert payload["performed_on"] == "2026-03-04"
    assert payload["scheduled_for"] == "2026-03-01"
    assert payload["previous_status"] == "planned"


def test_planned_to_skipped_emits_generic_event_without_execution(monkeypatch):
    conn = _StandInConn(_row())
    result, events = _run(monkeypatch, conn, ActivityTransitionRequest(status="skipped"))
    assert result["status"] == "skipped" and result["performed_on"] is None
    assert events[0][0] == "ACTIVITY_RECORDED" and events[0][3]["status"] == "skipped"


def test_same_target_state_returns_row_without_write_or_event(monkeypatch):
    conn = _StandInConn(_row(status="done", performed_on=date(2026, 3, 2)))
    req = ActivityTransitionRequest(status="done", performed_on="2026-03-04")
    result, events = _run(monkeypatch, conn, req)
    assert result["status"] == "done" and result["performed_on"] == "2026-03-02"
    assert conn.updates == [] and events == []


@pytest.mark.parametrize(
    ("current", "req"),
    [
        ("skipped", ActivityTransitionRequest(status="done", performed_on="2026-03-04")),
        ("done", ActivityTransitionRequest(status="skipped")),
    ],
)
def test_illegal_transition_is_409(monkeypatch, current, req):
    conn = _StandInConn(_row(status=current))
    with pytest.raises(HTTPException) as exc:
        _run(monkeypatch, conn, req)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "invalid_activity_transition"
    assert conn.updates == []


def test_unknown_activity_or_foreign_field_is_404(monkeypatch):
    req = ActivityTransitionRequest(status="skipped")
    for conn in (_StandInConn(None), _StandInConn(_row(), field_exists=False)):
        with pytest.raises(HTTPException) as exc:
            _run(monkeypatch, conn, req)
        assert exc.value.status_code == 404
