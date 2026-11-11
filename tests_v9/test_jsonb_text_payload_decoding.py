"""jsonb يصل نصّاً عبر asyncpg (لا ``set_type_codec`` مُسجَّل) — يُفكّ قبل الاستعمال.

• ``irrigation_closed_loop_runtime``: مسارا الإعادة (``reconcile_irrigation_run`` و
  ``finalize_irrigation_closed_loop``) كانا ينفّذان ``dict(existing["payload"] or {})``
  على نصّ JSON ⇒ ``ValueError`` فيتحوّل كلّ تسليمٍ مُكرَّر إلى رسالة سامّة.
(``OutboxWorker._send_one`` في ``event_bus.py`` يحمل العيب نفسه لـ``correlation_id`` لكنّه
مسارٌ مجمَّد في GATE-01 فيُترك لقرار المالك.)
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit

_PLATFORM = Path(__file__).resolve().parents[1] / "services" / "sahool-platform"
RUN = "00000000-0000-0000-0000-000000000001"


def _import(name: str):
    if str(_PLATFORM) not in sys.path:
        sys.path.insert(0, str(_PLATFORM))
    import importlib

    return importlib.import_module(name)


class _ReplayConn:
    """صفوف «سبق تنفيذه» بحمولة jsonb نصّيّة — كما يُعيدها asyncpg بلا codec."""

    def __init__(self, stored: dict):
        self.stored = json.dumps(stored)

    async def execute(self, sql, *args):
        return "SELECT 1"

    async def fetchrow(self, sql, *args):
        if "irrigation_closed_loop_records" in sql:
            return {"payload": self.stored}
        if "irrigation_water_ledger_reconciliations" in sql:
            return {"payload": self.stored}
        if "as_applied_irrigation_runs WHERE id" in sql:
            now = datetime.now(UTC)
            return {
                "id": RUN,
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "field_id": "field-1",
                "season_id": "season-1",
                "machine_id": "22222222-2222-2222-2222-222222222222",
                "controller_id": "33333333-3333-3333-3333-333333333333",
                "decision_id": "decision-1",
                "authorization_id": "auth-1",
                "execution_plan_id": "plan-1",
                "planned_start_at": now - timedelta(minutes=20),
                "planned_end_at": now - timedelta(minutes=5),
                "planned_depth_mm": 1.2,
                "planned_volume_m3": 60.0,
                "planned_area_ha": 5.0,
                "irrigation_capability_digest": "a" * 64,
                "commissioning_certification_digest": "a" * 64,
                "decision_content_digest": "a" * 64,
                "created_at": now,
            }
        return None

    async def fetch(self, sql, *args):
        return []


@pytest.mark.asyncio
async def test_reconcile_replay_decodes_text_jsonb_payload():
    mod = _import("api.irrigation_closed_loop_runtime")
    conn = _ReplayConn({"status": "reconciled", "ledger_event_id": "e1"})
    result = await mod.reconcile_irrigation_run(conn, run_id=RUN)
    assert result == {"status": "reconciled", "ledger_event_id": "e1", "idempotent_replay": True}


@pytest.mark.asyncio
async def test_finalize_replay_decodes_text_jsonb_payload():
    mod = _import("api.irrigation_closed_loop_runtime")
    conn = _ReplayConn({"record_digest": "d1"})
    result = await mod.finalize_irrigation_closed_loop(
        conn,
        run_id=RUN,
        measured_at=datetime.now(UTC),
        expected_depletion_after_mm=10.0,
        source_digests={"x": "y"},
    )
    assert result == {
        "status": "replayed",
        "idempotent_replay": True,
        "payload": {"record_digest": "d1"},
    }


class _OutboxConn:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, sql, *args):
        self.statements.append(sql)
        return "UPDATE 1"

    async def fetchval(self, sql, *args):
        return False

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Txn()
