from __future__ import annotations

import importlib.util
import re
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
    text = (
        ROOT / "services/sahool-platform/workers/canonical_execution_learning_worker.py"
    ).read_text(encoding="utf-8")
    assert "sahool.events.irrigation.execution.completed" in text
    assert "sahool.events.season.closed" in text
    assert "finalize_irrigation_closed_loop" in text
    assert "process_season_closed_event" in text
    assert "await msg.ack()" in text
    assert "await msg.nak(delay=5)" in text
    assert "await msg.term()" in text


@pytest.mark.asyncio
async def test_season_learning_excludes_immature_and_non_finite_rows_with_reasons():
    """U02: قيمة فعليّة قبل النضج لا تعدّ نحو الحدّ الأدنى ولا تدخل MAE؛ السبب يُعلَن."""
    mod = _load("services/sahool-platform/api/learning_feedback.py", "learning_feedback_u02")
    outcomes = [
        {
            "recommendation_id": "mature-1",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": 4.2,
            "accepted": True,
            "matured_within_lag": True,
        },
        # مقبولة لكن غير ناضجة وبقيمة مبكّرة — كانت تُحسَب.
        {
            "recommendation_id": "early-1",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": 4.4,
            "accepted": True,
            "matured_within_lag": False,
        },
        {
            "recommendation_id": "early-2",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": 4.5,
            "accepted": True,
            "matured_within_lag": False,
        },
        # مرفوضة لكن ناضجة — تدخل دراسة دقّة التوقّع (الحصاد لا يُمحى برفض التوصية).
        {
            "recommendation_id": "rejected-mature",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": 3.0,
            "accepted": False,
            "matured_within_lag": True,
        },
        {
            "recommendation_id": "nan-1",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": float("nan"),
            "accepted": True,
            "matured_within_lag": True,
        },
        # بلا قيمة فعليّة — كان الاستعلام يُسقِطها قبل السياسة فلا يظهر سببُها (Copilot على #1001).
        {
            "recommendation_id": "pending-1",
            "predicted_yield_t_ha": 4.0,
            "actual_yield_t_ha": None,
            "accepted": True,
            "matured_within_lag": False,
        },
    ]
    conn = Conn(outcomes=outcomes)
    result = await mod.process_season_closed_event(
        conn,
        event_id="evt-u02",
        tenant_id="00000000-0000-0000-0000-000000000001",
        field_id="fld-1",
        season_id="ssn-1",
    )
    evaluation = result["promotion_candidate"]["evidence"]
    assert evaluation["outcome_count"] == 2
    assert evaluation["excluded_count"] == 4
    assert evaluation["excluded_reasons"] == {
        "immature": 2,
        "non_finite_value": 1,
        "missing_actual": 1,
    }
    # السياسة تصنّف كلَّ الصفوف: الاستعلام لا يُسقِط الفارغة قبلها.
    fetch_sql = next(call[1] for call in conn.calls if call[0] == "fetch")
    assert "IS NOT NULL" not in fetch_sql
    assert evaluation["status"] == "blocked"  # اثنان < الحدّ الأدنى ٣ — لا ترشيح من قيم مبكّرة
    assert evaluation["mae_t_ha"] == 0.6  # (0.2 + 1.0) / 2 — الناضجتان فقط


def _recommendation_outcomes_columns() -> set[str]:
    """أعمدةُ الجدول كما يُعرِّفها v49 — مصدرُ الحقيقة لا الاستنتاج."""
    ddl = (ROOT / "migrations/v49_zone_key_recommendation_outcomes.sql").read_text(encoding="utf-8")
    body = ddl.split("CREATE TABLE IF NOT EXISTS recommendation_outcomes (", 1)[1].split(");", 1)[0]
    return {
        line.split()[0]
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    }


@pytest.mark.asyncio
async def test_season_learning_locks_before_the_replay_check_and_orders_by_real_columns():
    """Copilot على #1001 (مكتومتان): (أ) القفلُ الاستشاريّ قبل فحص الإعادة — تسليمان متزامنان
    كانا يريان «لا صفّ» معاً فيُصدِران الحدثَ مرّتين؛ (ب) ORDER BY بأعمدة v49 الفعليّة —
    كان `created_at,id` فيفشل كلُّ إغلاق موسم بعمود غير معرَّف."""
    mod = _load("services/sahool-platform/api/learning_feedback.py", "learning_feedback_lock")
    kw = dict(tenant_id="00000000-0000-0000-0000-000000000001", field_id="fld-1", season_id="ssn-1")

    replay = Conn(replay=True)
    result = await mod.process_season_closed_event(replay, event_id="evt-lock", **kw)
    assert result["idempotent_replay"] is True
    sqls = [call[1] for call in replay.calls]
    lock_at = next(i for i, s in enumerate(sqls) if "pg_advisory_xact_lock" in s)
    replay_check_at = next(i for i, s in enumerate(sqls) if "decision_learning_runs WHERE" in s)
    assert lock_at < replay_check_at, "فحصُ الإعادة يسبق القفل — نافذةُ إصدارٍ مزدوج"
    assert not any("emit_event" in s for s in sqls)

    fresh = Conn(outcomes=[])
    await mod.process_season_closed_event(fresh, event_id="evt-order", **kw)
    fetch_sql = next(call[1] for call in fresh.calls if call[0] == "fetch")
    order_by = fetch_sql.split("ORDER BY", 1)[1]
    referenced = set(re.findall(r"[a-z_]+", order_by))  # المعرّفات الصغيرة فقط (لا الدوالّ)
    columns = _recommendation_outcomes_columns()
    assert referenced and referenced <= columns, (referenced - columns, columns)
    assert "created_at" not in order_by and " id" not in order_by
