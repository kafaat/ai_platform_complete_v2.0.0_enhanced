"""حارس: نتيجة قالب لا تُسجَّل اكتمالاً (P0-1، المسار الوحيد للنجاح غير الحقيقيّ).

الفجوة المُبرهَنة قبل هذا الحارس: `workflow_engine` كان يخزّن نتيجة المعالِج ويُعلّم
الخطوة مكتملة **بلا فحص محتوى إطلاقاً** — صفر `result.get(...)` في الملفّ كلّه. فكان
الاكتمال دالّة في «هل رمى المعالِج؟» وحدها، وقالبٌ يُعيد `{"validated": True,
"_template": True}` يبلغ `COMPLETED` بمسار **مطابق بايتاً** لمعالِج حقيقيّ. والوسم
`_template` لم يكن يقرؤه شيء في الإنتاج (قراءاته كلّها في الاختبارات) — إشارة ميتة
لا ضعيفة.

هذه الاختبارات تُثبِت أنّ الوسم صار مقروءاً حيث يُهمّ، في **كلا** مساري التشغيل.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from core.workflow_engine import (  # noqa: E402
    InMemoryWorkflowStore,
    WorkflowStatus,
    WorkflowStep,
    run_workflow,
)


def _template_step(step_id: str = "validate") -> WorkflowStep:
    return WorkflowStep(step_id=step_id, fn=lambda ctx: {"validated": True, "_template": True})


def _real_step(step_id: str = "validate") -> WorkflowStep:
    return WorkflowStep(step_id=step_id, fn=lambda ctx: {"validated": True, "_template": False})


def test_template_result_does_not_reach_completed():
    """قالب ⇒ لا COMPLETED. هذا هو جوهر الحارس."""
    store = InMemoryWorkflowStore()
    state = run_workflow("wf-tpl", [_template_step()], store=store, tenant_id="t1")
    assert state.status is not WorkflowStatus.COMPLETED, (
        "نتيجة قالب بلغت COMPLETED — النجاح غير الحقيقيّ ما زال ممكناً"
    )
    assert state.status is WorkflowStatus.FAILED
    assert "validate" not in state.completed_steps
    assert "_template" in (state.error or "")


def test_real_result_still_completes():
    """المسار الحقيقيّ لم يتغيّر — الحارس يميّز، لا يمنع الجميع."""
    store = InMemoryWorkflowStore()
    state = run_workflow("wf-real", [_real_step()], store=store, tenant_id="t1")
    assert state.status is WorkflowStatus.COMPLETED
    assert state.completed_steps == ["validate"]
    assert state.step_results["validate"]["_template"] is False


def test_template_in_later_step_stops_the_workflow():
    """قالب في خطوة متأخّرة يوقف السير — لا اكتمال جزئيّ يُقرأ نجاحاً كاملاً."""
    store = InMemoryWorkflowStore()
    steps = [_real_step("first"), _template_step("second"), _real_step("third")]
    state = run_workflow("wf-mixed", steps, store=store, tenant_id="t1")
    assert state.status is WorkflowStatus.FAILED
    assert state.completed_steps == ["first"]  # الأولى نجحت حقّاً
    assert "second" not in state.completed_steps
    assert "third" not in state.completed_steps


def test_template_triggers_saga_compensation_like_any_failure():
    """يرث مسار الفشل القائم بالكامل: التعويض يعمل كأيّ استثناء آخر."""
    store = InMemoryWorkflowStore()
    compensated: list[str] = []
    steps = [
        WorkflowStep(
            step_id="reserve",
            fn=lambda ctx: {"reserved": True, "_template": False},
            compensate=lambda ctx: compensated.append("reserve"),
        ),
        _template_step("charge"),
    ]
    state = run_workflow("wf-saga", steps, store=store, tenant_id="t1", compensate_on_failure=True)
    assert state.status is WorkflowStatus.COMPENSATED
    assert compensated == ["reserve"], "التعويض لم يُستدعَ — الحارس لم يرث مسار الفشل"


def test_async_path_rejects_template_too():
    """المسار async نظير المتزامن — لا ثغرة في أحدهما دون الآخر."""
    from core.workflow_engine import run_workflow_async

    class _Store:
        def __init__(self):
            self._d = {}

        async def save(self, state):
            self._d[state.workflow_id] = state

        async def load(self, workflow_id):
            return self._d.get(workflow_id)

    state = asyncio.run(
        run_workflow_async("wf-async-tpl", [_template_step()], store=_Store(), tenant_id="t1")
    )
    assert state.status is WorkflowStatus.FAILED
    assert "_template" in (state.error or "")
