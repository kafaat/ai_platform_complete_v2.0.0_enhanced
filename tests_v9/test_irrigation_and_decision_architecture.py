from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Conn:
    def __init__(self, *, replay=False, outcomes=None):
        self.replay = replay
        self.outcomes = outcomes or []
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return "INSERT 0 1"

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        if "decision_learning_runs" in sql and self.replay:
            return {"evaluation": {"status": "review_ready"}}
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.outcomes

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        if "emit_event" in sql:
            return "00000000-0000-0000-0000-000000000001"
        return 0


@pytest.mark.asyncio
async def test_season_learning_reads_persisted_outcomes_and_never_auto_promotes():
    mod = _load("services/sahool-platform/api/learning_feedback.py", "learning_feedback_arch")
    outcomes = [
        {
            "recommendation_id": f"r{i}",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": 4.2,
            "accepted": True,
            "matured_within_lag": True,
        }
        for i in range(3)
    ]
    conn = Conn(outcomes=outcomes)
    result = await mod.process_season_closed_event(
        conn,
        event_id="evt-1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld-1",
        season_id="ssn-1",
    )
    assert result["status"] == "review_ready"
    assert result["promotion_candidate"]["review_required"] is True
    assert result["promotion_candidate"]["auto_promote"] is False
    assert any("FROM recommendation_outcomes" in call[1] for call in conn.calls)
    assert any("governed_model_promotion_candidates" in call[1] for call in conn.calls)


@pytest.mark.asyncio
async def test_season_learning_replay_is_idempotent_and_emits_nothing():
    mod = _load("services/sahool-platform/api/learning_feedback.py", "learning_feedback_replay")
    conn = Conn(replay=True)
    result = await mod.process_season_closed_event(
        conn,
        event_id="evt-1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld-1",
        season_id="ssn-1",
    )
    assert result["idempotent_replay"] is True
    assert not any("emit_event" in call[1] for call in conn.calls)


def test_v227_is_rls_governed_and_auto_promotion_is_forbidden():
    text = (ROOT / "migrations/v227_decision_learning_runtime.sql").read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in text
    assert "auto_promote BOOLEAN NOT NULL DEFAULT FALSE CHECK (NOT auto_promote)" in text
    manifest = (ROOT / "migrations/MANIFEST.txt").read_text(encoding="utf-8")
    assert manifest.index("v227_decision_learning_runtime.sql") < manifest.index(
        "v206_rls_final_hardening.sql"
    )


def test_registered_worker_is_an_executable_root_for_both_event_chains():
    text = (ROOT / "scripts/workers/canonical_execution_learning_worker.py").read_text(
        encoding="utf-8"
    )
    assert "sahool.events.irrigation.execution.completed" in text
    assert "sahool.events.season.closed" in text
    assert "finalize_irrigation_closed_loop" in text
    assert "process_season_closed_event" in text
    assert "await msg.ack()" in text
    assert "await msg.nak(delay=5)" in text
    assert "await msg.term()" in text
