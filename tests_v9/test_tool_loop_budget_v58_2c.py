"""تحقّق V58.2c — حماية إساءة حلقة الأدوات: ميزانية إجماليّة + dedupe + إيقاف عند البوّابة.

على tool_loop.run_tool_calls (منطق صرف، جالب محقون):

- ``run_budget``/``run_spent``: يقصّ الاستدعاءات عند تجاوز الميزانية الإجماليّة ويرفع
  ``budget_exhausted`` مع ``handled_count`` للمتّصِل ليجمع عبر الجولات.
- ``dedupe_seen``: استدعاء بنفس ``tool+input_hash`` يُرفَض (``duplicate_tool_call``) بلا تنفيذ.
- ``stop_on_pending``: بعد أوّل طلب موافقة تُتخطّى بقيّة أدوات الدفعة (``skipped_pending_gate``).
- التوافق الخلفيّ: بلا هذه الوسائط السلوك مطابق لـV56.

وظيفة Unit Tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_agronomist import tool_loop as L  # noqa: E402

_TS = "2026-07-01T00:00:00Z"


def _fetcher(name, params):
    return {"index": params.get("index", "ndvi"), "value": 0.5}


def _read(field="f1", index="ndvi", days=30, cid="c"):
    return {
        "tool": "get_index_timeline",
        "params": {"field_id": field, "index": index, "days": days},
        "id": cid,
    }


def _run(calls, **kw):
    return L.run_tool_calls(
        calls,
        allowed_capabilities=[
            "can_read_field_data",
            "can_read_historical_imagery",
            "can_create_tasks",
        ],
        fetcher=_fetcher,
        tenant_id="t1",
        actor="ai",
        timestamp=_TS,
        **kw,
    )


# ── ميزانية إجماليّة ─────────────────────────────────────────────────────────
def test_run_budget_caps_across_prior_spend():
    # ميزانية 3، أُنفِق 2 سابقاً ⇒ يُعالَج استدعاء واحد فقط ثمّ budget_exhausted.
    out = _run(
        [_read(cid="a"), _read(index="ndmi", cid="b"), _read(days=60, cid="c")],
        run_budget=3,
        run_spent=2,
    )
    assert out["handled_count"] == 1
    assert out["budget_exhausted"] is True
    assert out["truncated"] is True
    assert len(out["tool_calls"]) == 1


def test_no_budget_processes_all():
    out = _run([_read(cid="a"), _read(index="ndmi", cid="b")])
    assert out["handled_count"] == 2
    assert out["budget_exhausted"] is False
    assert len(out["tool_calls"]) == 2


# ── dedupe ───────────────────────────────────────────────────────────────────
def test_dedupe_rejects_identical_call_within_run():
    seen: set[str] = set()
    out = _run([_read(cid="a"), _read(cid="b")], dedupe_seen=seen)  # نفس الوسائط تماماً
    outcomes = [r["outcome"] for r in out["tool_calls"]]
    assert outcomes[0] == "executed"
    assert outcomes[1] == L.OUTCOME_DUPLICATE_TOOL_CALL
    assert out["tool_calls"][1]["data"] is None
    assert out["handled_count"] == 2  # كلاهما محسوب على الميزانية (منع الحلقات)


def test_dedupe_allows_distinct_inputs():
    seen: set[str] = set()
    out = _run([_read(index="ndvi", cid="a"), _read(index="ndmi", cid="b")], dedupe_seen=seen)
    assert [r["outcome"] for r in out["tool_calls"]] == ["executed", "executed"]


def test_dedupe_persists_across_batches_via_shared_set():
    seen: set[str] = set()
    _run([_read(cid="a")], dedupe_seen=seen)
    out2 = _run([_read(cid="b")], dedupe_seen=seen)  # نفس الاستدعاء في دفعة تالية
    assert out2["tool_calls"][0]["outcome"] == L.OUTCOME_DUPLICATE_TOOL_CALL


# ── إيقاف عند البوّابة ───────────────────────────────────────────────────────
def test_stop_on_pending_skips_rest_of_batch():
    calls = [
        {"tool": "create_scouting_task", "params": {"field_id": "f", "zone": "z"}, "id": "gate"},
        _read(cid="after1"),
        _read(index="ndmi", cid="after2"),
    ]
    out = _run(calls, stop_on_pending=True)
    by_id = {r["tool_call_id"]: r for r in out["tool_calls"]}
    assert by_id["gate"]["outcome"] == L.OUTCOME_PENDING_APPROVAL
    assert by_id["after1"]["outcome"] == L.OUTCOME_SKIPPED_PENDING_GATE
    assert by_id["after2"]["outcome"] == L.OUTCOME_SKIPPED_PENDING_GATE
    assert len(out["pending_approvals"]) == 1


def test_without_stop_on_pending_continues():
    calls = [
        {"tool": "create_scouting_task", "params": {"field_id": "f", "zone": "z"}, "id": "gate"},
        _read(cid="after1"),
    ]
    out = _run(calls, stop_on_pending=False)
    by_id = {r["tool_call_id"]: r for r in out["tool_calls"]}
    assert by_id["gate"]["outcome"] == L.OUTCOME_PENDING_APPROVAL
    assert by_id["after1"]["outcome"] == "executed"  # يُنفَّذ (السلوك القديم)


# ── التوافق الخلفيّ ──────────────────────────────────────────────────────────
def test_backward_compatible_defaults():
    out = _run([_read(cid="a"), _read(cid="b")])  # لا تكرار مرفوض بلا dedupe_seen
    assert [r["outcome"] for r in out["tool_calls"]] == ["executed", "executed"]
    assert out["handled_count"] == 2
    assert "budget_exhausted" in out
