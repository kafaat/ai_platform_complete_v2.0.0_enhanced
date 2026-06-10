"""محرّك workflow متعدّد الخطوات قابل للاستئناف (durable, resumable).

النمط مستلهَم من LangGraph/Temporal — لكن خفيف، نقيّ-بايثون، بلا تبعيّة ثقيلة
(لا broker، لا خادم منفصل). يسدّ فجوة حقيقيّة: النظام يملك state machine
(field_lifecycle) و exactly-once (command_store)، لكن لا محرّك يحفظ تقدّم
workflow متعدّد الخطوات ليُستأنف من حيث توقّف عند الفشل/إعادة التشغيل.

الاستخدام الزراعي: تصعيد الآفة (رصد→تأكيد→توصية→موافقة→تنفيذ→متابعة)، حلقة
قرار الريّ، التشخيص متعدّد المراحل. إن انقطع النظام في المنتصف، يُستأنف من
آخر خطوة مكتملة (لا يعيد ما نجح — idempotency على مستوى الخطوة).

المبادئ:
- كلّ خطوة لها id ثابت؛ نتيجتها تُحفَظ (step_results) فور نجاحها.
- الاستئناف يتخطّى الخطوات المكتملة (لا إعادة تنفيذ — مهمّ للخطوات ذات الأثر
  الجانبي مثل إرسال تنبيه أو دفع تكلفة).
- الحفظ عبر store قابل للحقن (DB/ملفّ/ذاكرة) — لا يفترض backend معيّناً.
- صدق: لا "نجاح زائف". الخطوة الفاشلة تُعلَن، والـworkflow يتوقّف عندها قابلاً
  للاستئناف (لا يتخطّاها صامتاً).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"  # خطوة فشلت — قابل للاستئناف
    SUSPENDED = "suspended"  # ينتظر حدثاً خارجيّاً (مثل موافقة بشريّة)
    COMPENSATED = "compensated"  # فشل + تراجع عن الخطوات المكتملة (Saga)


@dataclass
class WorkflowStep:
    """خطوة واحدة: id ثابت + دالّة تنفيذ. الدالّة تأخذ (context) وتُرجِع dict.

    compensate: دالّة تعويض اختياريّة (Saga). تُستدعى بالترتيب العكسي عند فشل
    خطوة لاحقة، لتتراجع عن أثر هذه الخطوة (مثلاً: إلغاء حجز، استرجاع دفعة).
    تأخذ (context) — صدق: لو لم تُوفَّر، الخطوة غير قابلة للتعويض (تُعلَن).
    """

    step_id: str
    fn: Callable[[dict], Any]
    # إن صحّ، الـworkflow يتوقّف بعد هذه الخطوة بانتظار استئناف خارجي. قد يكون
    # bool ثابتاً أو دالّة (ctx)→bool تُقيَّم بعد تنفيذ الخطوة (تعليق مشروط): مثلاً
    # خطوة موافقة تُعلّق فقط حين تكون الموافقة فعلاً مطلوبة (لا تعليق بلا داعٍ).
    suspends: bool | Callable[[dict], bool] = False
    # دالّة تعويض (Saga rollback) — تُستدعى عند فشل خطوة لاحقة
    compensate: Callable[[dict], Any] | None = None


@dataclass
class WorkflowState:
    """حالة workflow قابلة للحفظ/الاستئناف."""

    workflow_id: str
    tenant_id: str | None = None
    status: WorkflowStatus = WorkflowStatus.RUNNING
    completed_steps: list[str] = field(default_factory=list)
    step_results: dict = field(default_factory=dict)  # {step_id: result}
    context: dict = field(default_factory=dict)  # سياق مشترك متراكم
    current_step: str | None = None
    error: str | None = None
    compensated_steps: list[str] = field(default_factory=list)  # Saga rollback
    workflow_version: str = "1"  # نسخة التعريف (للكشف عن عدم تطابق لاحقاً)
    correlation_id: str | None = None  # خيط التتبّع الموحّد (يربط بالـtrace)

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "completed_steps": self.completed_steps,
            "step_results": self.step_results,
            "context": self.context,
            "current_step": self.current_step,
            "error": self.error,
            "compensated_steps": self.compensated_steps,
            "workflow_version": self.workflow_version,
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowState:
        return cls(
            workflow_id=d["workflow_id"],
            tenant_id=d.get("tenant_id"),
            status=WorkflowStatus(d.get("status", "running")),
            completed_steps=list(d.get("completed_steps", [])),
            step_results=dict(d.get("step_results", {})),
            context=dict(d.get("context", {})),
            current_step=d.get("current_step"),
            error=d.get("error"),
            compensated_steps=list(d.get("compensated_steps", [])),
            workflow_version=d.get("workflow_version", "1"),
            correlation_id=d.get("correlation_id"),
        )


class InMemoryWorkflowStore:
    """مخزن حالة افتراضي (ذاكرة). يُستبدَل بـDB store على بيئة التشغيل.

    العقد: save(state) / load(workflow_id) → WorkflowState | None.
    صدق: هذا للاختبار/التطوير؛ الإنتاج يحقن store مدعوماً بـPostgreSQL ليبقى
    التقدّم محفوظاً عبر إعادة التشغيل (الذاكرة تُفقَد عند إعادة التشغيل).
    """

    def __init__(self) -> None:
        self._store: dict = {}

    def save(self, state: WorkflowState) -> None:
        self._store[state.workflow_id] = state.to_dict()

    def load(self, workflow_id: str) -> WorkflowState | None:
        d = self._store.get(workflow_id)
        return WorkflowState.from_dict(d) if d else None


class PostgresWorkflowStore:
    """مخزن حالة معمّر على workflow_state (migrations v16+v17). يجعل الاستئناف
    يصمد عبر إعادة التشغيل (عكس InMemory الذي يُفقَد). نفس عقد save/load.

    ⚠ صدق: واجهة متزامنة فوق asyncpg عبر asyncio.run — لا تُستدعى من داخل event
    loop نشط (run_workflow متزامن أصلاً؛ في خدمة async استدعِه عبر executor).
    يفتح اتّصالاً قصير العمر لكلّ عمليّة (بسيط؛ الإنتاج عالي الإنتاجيّة يحقن pool).
    يضبط app.current_tenant عند الحفظ ليُطبَّق RLS (FORCE) على الإدراج.
    """

    def __init__(self, dsn: str, tenant_id: str | None = None) -> None:
        self._dsn = dsn
        # سياق المستأجر للقراءة (load): workflow_state عليه RLS+FORCE، فبدون ضبط
        # app.current_tenant تحجب السياسة كلّ الصفوف ⇒ load يُرجِع None دائماً
        # (الاستئناف عبر إعادة التشغيل لا يعمل). الحفظ يأخذ المستأجر من الحالة.
        self._tenant_id = tenant_id

    def _run(self, coro: Any) -> Any:
        import asyncio

        return asyncio.run(coro)

    def save(self, state: WorkflowState) -> None:
        # فشل مبكر واضح: workflow_state.tenant_id NOT NULL + RLS يعتمد المستأجر.
        # بدونه كان يقع خطأ قاعدة غامض (NOT NULL/سياسة) بعد فتح الاتّصال.
        if not state.tenant_id:
            raise ValueError(
                "PostgresWorkflowStore.save يتطلّب tenant_id غير فارغ "
                "(workflow_state.tenant_id NOT NULL + RLS) — شغّل run_workflow بـtenant_id."
            )
        self._run(self._save(state))

    async def _save(self, state: WorkflowState) -> None:
        import json

        import asyncpg

        d = state.to_dict()
        conn = await asyncpg.connect(self._dsn)
        try:
            await conn.execute(
                "SELECT set_config('app.current_tenant', $1, false)",
                str(d["tenant_id"] or ""),
            )
            await conn.execute(
                """
                INSERT INTO workflow_state
                  (workflow_id, tenant_id, status, completed_steps, step_results, context,
                   current_step, error, compensated_steps, workflow_version, correlation_id, updated_at)
                VALUES ($1,$2::uuid,$3,$4::jsonb,$5::jsonb,$6::jsonb,$7,$8,$9::jsonb,$10,$11,NOW())
                ON CONFLICT (workflow_id) DO UPDATE SET
                  status=EXCLUDED.status, completed_steps=EXCLUDED.completed_steps,
                  step_results=EXCLUDED.step_results, context=EXCLUDED.context,
                  current_step=EXCLUDED.current_step, error=EXCLUDED.error,
                  compensated_steps=EXCLUDED.compensated_steps,
                  workflow_version=EXCLUDED.workflow_version,
                  correlation_id=EXCLUDED.correlation_id, updated_at=NOW()
                """,
                d["workflow_id"],
                d["tenant_id"],
                d["status"],
                json.dumps(d["completed_steps"]),
                json.dumps(d["step_results"]),
                json.dumps(d["context"]),
                d["current_step"],
                d["error"],
                json.dumps(d["compensated_steps"]),
                d["workflow_version"],
                d["correlation_id"],
            )
        finally:
            await conn.close()

    def load(self, workflow_id: str) -> WorkflowState | None:
        return self._run(self._load(workflow_id))

    async def _load(self, workflow_id: str) -> WorkflowState | None:
        import json

        import asyncpg

        conn = await asyncpg.connect(self._dsn)
        try:
            # ضبط سياق المستأجر ليُمرِّر RLS (FORCE) القراءة — بدونه تُحجب الصفوف.
            if self._tenant_id:
                await conn.execute(
                    "SELECT set_config('app.current_tenant', $1, false)", str(self._tenant_id)
                )
            row = await conn.fetchrow(
                "SELECT * FROM workflow_state WHERE workflow_id=$1", workflow_id
            )
        finally:
            await conn.close()
        if not row:
            return None

        def _j(v: Any, default: Any) -> Any:
            if v is None:
                return default
            return v if isinstance(v, list | dict) else json.loads(v)

        return WorkflowState.from_dict(
            {
                "workflow_id": row["workflow_id"],
                "tenant_id": str(row["tenant_id"]) if row["tenant_id"] else None,
                "status": row["status"],
                "completed_steps": _j(row["completed_steps"], []),
                "step_results": _j(row["step_results"], {}),
                "context": _j(row["context"], {}),
                "current_step": row["current_step"],
                "error": row["error"],
                "compensated_steps": _j(row["compensated_steps"], []),
                "workflow_version": row["workflow_version"] or "1",
                "correlation_id": row["correlation_id"],
            }
        )


def _compensate(steps: list[WorkflowStep], state: WorkflowState, store: Any) -> None:
    """يتراجع عن الخطوات المكتملة بالترتيب العكسي (Saga compensation).

    يستدعي compensate لكلّ خطوة مكتملة عكسيّاً. الخطوة بلا compensate تُعلَن
    كغير قابلة للتعويض (صدق: لا ندّعي تعويضاً لم يحدث). يُحدِّث compensated_steps.
    """
    by_id = {s.step_id: s for s in steps}
    # عكسيّاً: آخر ما اكتمل يُعوَّض أوّلاً
    for sid in reversed(list(state.completed_steps)):
        step = by_id.get(sid)
        if step is None or step.compensate is None:
            continue  # لا تعويض لهذه الخطوة (تُترَك — تُعلَن في غير المُعوَّض)
        try:
            step.compensate(state.context)
            state.compensated_steps.append(sid)
            store.save(state)
        except Exception:  # noqa: BLE001 — فشل تعويض: نُكمل الباقي، نُعلن لاحقاً
            # لا نوقف سلسلة التعويض بفشل واحد (نُعوّض ما نستطيع)
            continue


def run_workflow(
    workflow_id: str,
    steps: list[WorkflowStep],
    *,
    store: Any,
    tenant_id: str | None = None,
    initial_context: dict | None = None,
    compensate_on_failure: bool = False,
    workflow_version: str = "1",
) -> WorkflowState:
    """يشغّل/يستأنف workflow. يتخطّى الخطوات المكتملة (idempotent).

    إن وُجدت حالة محفوظة لنفس workflow_id → يُستأنف من آخر خطوة مكتملة (لا
    يعيد تنفيذ ما نجح). إن لا → يبدأ جديداً. كلّ خطوة ناجحة تُحفَظ فوراً.

    compensate_on_failure: عند فشل خطوة، يتراجع عن الخطوات المكتملة بالترتيب
    العكسي (Saga) → status=COMPENSATED. بدونه يبقى FAILED قابلاً للاستئناف.

    workflow_version: نسخة التعريف. إن اختلفت عن المحفوظة → يُعلَن عدم التطابق
    (صدق: لا نستأنف workflow قديماً بتعريف جديد قد يكسر الخطوات).

    صدق: الخطوة الفاشلة تُعلَن (status=FAILED + error) ويتوقّف الـworkflow
    قابلاً للاستئناف — لا تخطّي صامت، لا نجاح زائف.
    """
    # استئناف أو بدء جديد
    state = store.load(workflow_id)
    if state is None:
        # التقاط correlation الحالي (إن وُجد) لربط الـworkflow بخيط التتبّع.
        # fallback-safe: لو لم تتوفّر طبقة correlation (بناء جزئي) → None.
        _corr = None
        try:
            from core.correlation import get_correlation_id

            _corr = get_correlation_id()
        except Exception:  # noqa: BLE001 — الربط اختياري لا يكسر المحرّك
            _corr = None
        state = WorkflowState(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            context=dict(initial_context or {}),
            workflow_version=workflow_version,
            correlation_id=_corr,
        )
        store.save(state)
    elif state.workflow_version != workflow_version:
        # عدم تطابق النسخة: لا نستأنف بتعريف مختلف (قد يكسر الخطوات)
        state.status = WorkflowStatus.FAILED
        state.error = (
            f"عدم تطابق نسخة الـworkflow: المحفوظة '{state.workflow_version}' "
            f"مقابل المطلوبة '{workflow_version}' — لا استئناف بتعريف مختلف."
        )
        store.save(state)
        return state

    # حالات طرفيّة لا تُستأنف: مكتمل أو مُعوَّض (Saga). COMPENSATED كان يُعاد
    # تشغيله خطأً (يُهمَل تعويضه) ⇒ نُعامله نهايةً كـCOMPLETED.
    if state.status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPENSATED):
        return state

    # دمج المدخلات الخارجيّة عند الاستئناف (قناة بيانات للتعليق/الاستئناف): بدونها
    # لا تصل موافقة الخبير (أو أيّ إدخال) للخطوات بعد الاستئناف فيُصبح التعليق بلا فائدة.
    if initial_context:
        state.context.update(initial_context)

    state.status = WorkflowStatus.RUNNING
    state.error = None

    for step in steps:
        # idempotency: تخطّي الخطوات المكتملة (مهمّ للأثر الجانبي)
        if step.step_id in state.completed_steps:
            continue

        state.current_step = step.step_id
        store.save(state)  # حفظ قبل التنفيذ (للاستئناف لو انقطع أثناءه)

        try:
            result = step.fn(state.context)
        except Exception as e:  # noqa: BLE001 — صدق: نُعلن الفشل لا نخفيه
            state.status = WorkflowStatus.FAILED
            state.error = f"خطوة '{step.step_id}' فشلت: {e}"
            store.save(state)
            # Saga: تراجع عن الخطوات المكتملة إن طُلب (rollback semantics)
            if compensate_on_failure and state.completed_steps:
                _compensate(steps, state, store)
                state.status = WorkflowStatus.COMPENSATED
                store.save(state)
            return state  # قابل للاستئناف: إعادة التشغيل تبدأ من هذه الخطوة

        # نجاح: نحفظ النتيجة ونعلّم الخطوة مكتملة (فوراً — durability)
        state.step_results[step.step_id] = result
        state.completed_steps.append(step.step_id)
        if isinstance(result, dict):
            state.context.update(result)  # تراكم السياق للخطوة التالية
        store.save(state)

        # خطوة معلِّقة (تنتظر حدثاً خارجيّاً مثل موافقة بشريّة). التعليق قد يكون
        # مشروطاً (دالّة تُقيَّم على السياق بعد التنفيذ) فلا نُعلّق بلا داعٍ.
        suspend_now = step.suspends(state.context) if callable(step.suspends) else step.suspends
        if suspend_now:
            state.status = WorkflowStatus.SUSPENDED
            store.save(state)
            return state

    state.status = WorkflowStatus.COMPLETED
    state.current_step = None
    store.save(state)
    return state


# ── رصد الـworkflows (observability خفيف) ────────────────────────
def workflow_trace(state: WorkflowState) -> dict:
    """أثر تنفيذ workflow: الخطوات المكتملة/المُعوَّضة + أين توقّف + لماذا.

    رؤية تشغيليّة (المراجعة: traces/stalled/dead-letter). نقيّ: يبني الأثر من
    الحالة المحفوظة، لا تتبّع حيّ منفصل.
    """
    total = len(state.completed_steps)
    return {
        "workflow_id": state.workflow_id,
        "status": state.status.value,
        "completed_steps": list(state.completed_steps),
        "compensated_steps": list(state.compensated_steps),
        "current_step": state.current_step,
        "steps_done": total,
        "error": state.error,
        "workflow_version": state.workflow_version,
        "is_stalled": state.status in (WorkflowStatus.FAILED, WorkflowStatus.SUSPENDED),
        "needs_attention": state.status == WorkflowStatus.FAILED,
    }


def summarize_workflows(states: list[WorkflowState]) -> dict:
    """ملخّص رصد لمجموعة workflows (عدد لكلّ حالة + العالقة)."""
    by_status: dict = {}
    stalled: list[str] = []
    for s in states:
        by_status[s.status.value] = by_status.get(s.status.value, 0) + 1
        if s.status in (WorkflowStatus.FAILED, WorkflowStatus.SUSPENDED):
            stalled.append(s.workflow_id)
    return {
        "total": len(states),
        "by_status": by_status,
        "stalled_workflows": stalled,
        "needs_attention": by_status.get("failed", 0) > 0,
    }
