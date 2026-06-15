"""طبقة تعريفات سير العمل التصريحيّة (declarative workflow definitions).

المحرّك `core.workflow_engine` ينفّذ `list[WorkflowStep]` — لكن التدفّقات
الملموسة (مثل `core.pest_escalation_flow`) تُصرِّح تلك القائمة في بايثون
مباشرةً (خطوات مكتوبة يدويّاً). هذه الطبقة تضيف مستوى تصريحيّاً فوق المحرّك:

- يُعرَّف الـworkflow كـ**بيانات وصفيّة** (metadata): مُعرِّف + اسم + خطوات مرتّبة.
- كلّ خطوة تشير إلى `handler_id` نصّي يُسجَّل في **سجلّ معالِجات** (registry).
- إضافة workflow جديد تصبح **مدخلة تهيئة** (config entry) — أسماء خطوات مرتّبة
  مربوطة بمعالِجات مسجَّلة — لا كتابة كود محرّك جديد. هذا يحقّق رؤية:
      workflow: steps: [validate, schedule, execute, verify]

العلاقة بالمحرّك: هذه الطبقة **مُضافة فقط** (additive). لا تلمس المحرّك ولا
تدفّق تصعيد الآفة القائم. `build_steps` يحلّل التعريف التصريحيّ إلى
`list[WorkflowStep]` حقيقيّة بالباني الدقيق للمحرّك، ثمّ تُمرَّر لـ`run_workflow`
كالمعتاد. التدفّقات القائمة (pest_escalation) تُهاجر إلى هذه الطبقة **تدريجيّاً
لاحقاً** — لا تُهاجَر هنا (صدق: لا تغيير على ما يعمل اليوم).

صدق: المعالِجات المبدئيّة المسجَّلة هنا (irrigation_cycle) **قوالب/سقالة
(scaffolding)** تُثبت الآليّة فقط — لا تنفّذ ريّاً حقيقيّاً. المعالِجات الفعليّة
تُسجَّل لاحقاً حين تُبنى منطق الخطوات الحقيقيّ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from core.workflow_engine import WorkflowStep

# توقيع المعالِج مطابق لما يتوقّعه المحرّك: `WorkflowStep.fn: Callable[[dict], Any]`.
# اصطلاحاً يأخذ السياق (ctx) ويُرجِع dict يُدمَج في سياق الـworkflow المتراكم.
WorkflowHandler = Callable[[dict], dict]


@dataclass(frozen=True)
class StepSpec:
    """وصف تصريحيّ لخطوة: اسم الخطوة + مُعرِّفات معالِجات نصّيّة (لا دوال).

    `handler_id` يُحلّ من سجلّ المعالِجات إلى دالّة فعليّة عند البناء.
    `compensate_id` / `suspends_id` اختياريّان — يُحلّان كذلك من السجلّ (تعويض
    Saga / تعليق مشروط) فيبقى التعريف بيانات نصّيّة بحتة قابلة للتخزين/التهيئة.
    """

    step_name: str
    handler_id: str
    compensate_id: str | None = None
    suspends_id: str | None = None


@dataclass(frozen=True)
class WorkflowDefinition:
    """تعريف workflow كبيانات وصفيّة: مُعرِّف + اسم عربيّ + خطوات مرتّبة."""

    id: str
    name_ar: str
    steps: tuple[StepSpec, ...]
    description_ar: str = ""


# ── سجلّ المعالِجات (handler registry) ───────────────────────────────
# يربط مُعرِّفاً نصّيّاً بدالّة معالِج. التسجيل عبر الديكوريتر `register_handler`.
_HANDLERS: dict[str, WorkflowHandler] = {}


def register_handler(handler_id: str) -> Callable[[WorkflowHandler], WorkflowHandler]:
    """ديكوريتر يسجّل معالِجاً تحت مُعرِّف نصّيّ. صدق: يرفض التسجيل المكرّر.

    التكرار خطأ تهيئة صامت محتمل (معالِجان بنفس المُعرِّف) ⇒ نُعلنه فشلاً واضحاً
    بدل أن يطغى أحدهما على الآخر بصمت.
    """

    def _decorate(fn: WorkflowHandler) -> WorkflowHandler:
        if handler_id in _HANDLERS:
            raise ValueError(
                f"مُعرِّف المعالِج '{handler_id}' مسجَّل مسبقاً — لا تسجيل مكرّر "
                "(تجنّب طغيان صامت). اختر مُعرِّفاً فريداً."
            )
        _HANDLERS[handler_id] = fn
        return fn

    return _decorate


def _resolve_handler(handler_id: str, *, role: str) -> WorkflowHandler:
    """يحلّ مُعرِّف معالِج إلى دالّة من السجلّ — أو يفشل بوضوح (fail-loud).

    صدق: مُعرِّف غير مسجَّل خطأ تهيئة لا يُتخطّى صامتاً (كان سيتحوّل إلى تنفيذ
    خطوة مفقودة) ⇒ نُعلنه فوراً مع قائمة المتاح للتشخيص.
    """
    fn = _HANDLERS.get(handler_id)
    if fn is None:
        متاح = ", ".join(sorted(_HANDLERS)) or "(لا معالِجات مسجَّلة)"
        raise KeyError(
            f"مُعرِّف المعالِج '{handler_id}' غير مسجَّل ({role}) — "
            f"سجّله عبر register_handler. المتاح: {متاح}"
        )
    return fn


def build_steps(defn: WorkflowDefinition) -> list[WorkflowStep]:
    """يحلّل تعريفاً تصريحيّاً إلى `list[WorkflowStep]` حقيقيّة للمحرّك.

    لكلّ StepSpec: يُحلّ handler_id (+ compensate_id/suspends_id إن وُجدا) من
    السجلّ، ويبني `WorkflowStep(step_id, fn, suspends=, compensate=)` بالباني
    الدقيق للمحرّك. النتيجة تُمرَّر مباشرةً لـ`run_workflow`. صدق: أيّ مُعرِّف غير
    مسجَّل يرفع خطأ واضحاً (fail-loud) قبل أيّ تنفيذ.
    """
    steps: list[WorkflowStep] = []
    for spec in defn.steps:
        fn = _resolve_handler(spec.handler_id, role="handler")
        compensate = (
            _resolve_handler(spec.compensate_id, role="compensate")
            if spec.compensate_id is not None
            else None
        )
        # `suspends` في المحرّك قد يكون bool أو دالّة (ctx)→bool؛ هنا نحلّه من
        # السجلّ كدالّة معالِج تُقيَّم على السياق (تعليق مشروط) إن صُرِّح.
        suspends = (
            _resolve_handler(spec.suspends_id, role="suspends")
            if spec.suspends_id is not None
            else False
        )
        steps.append(WorkflowStep(spec.step_name, fn, suspends=suspends, compensate=compensate))
    return steps


# ── سجلّ التعريفات (definitions registry) ────────────────────────────
_DEFINITIONS: dict[str, WorkflowDefinition] = {}


def register_definition(defn: WorkflowDefinition) -> WorkflowDefinition:
    """يسجّل تعريف workflow. صدق: يرفض مُعرِّفاً مكرّراً (تجنّب طغيان صامت)."""
    if defn.id in _DEFINITIONS:
        raise ValueError(f"تعريف الـworkflow '{defn.id}' مسجَّل مسبقاً — لا تسجيل مكرّر.")
    _DEFINITIONS[defn.id] = defn
    return defn


def list_workflows() -> list[dict]:
    """يُرجِع البيانات الوصفيّة لكلّ workflow مسجَّل (للعرض/الاكتشاف).

    لا يبني خطوات ولا يحلّ معالِجات — بيانات نصّيّة بحتة (id/اسم/أسماء الخطوات
    المرتّبة/وصف) مناسبة لواجهة أو فهرس.
    """
    return [
        {
            "id": defn.id,
            "name_ar": defn.name_ar,
            "description_ar": defn.description_ar,
            "step_names": [s.step_name for s in defn.steps],
            "step_count": len(defn.steps),
        }
        for defn in _DEFINITIONS.values()
    ]


def get_workflow(workflow_id: str) -> WorkflowDefinition:
    """يُرجِع تعريف workflow بمُعرِّفه — أو يفشل بوضوح إن لم يكن مسجَّلاً."""
    defn = _DEFINITIONS.get(workflow_id)
    if defn is None:
        متاح = ", ".join(sorted(_DEFINITIONS)) or "(لا تعريفات مسجَّلة)"
        raise KeyError(f"تعريف الـworkflow '{workflow_id}' غير موجود — المتاح: {متاح}")
    return defn


# ── معالِجات قالبيّة لـirrigation_cycle (سقالة — لا ريّ حقيقيّ) ──────────
#
# ⚠ صدق صريح: المعالِجات الأربعة أدناه **قوالب pass-through** تُثبت أنّ الآليّة
# التصريحيّة تعمل (تعريف → بناء → تنفيذ عبر المحرّك). كلّ منها يُرجِع علامة نجاح
# رمزيّة فقط — **لا يقرأ حسّاساً، لا يفتح صمّاماً، لا يجدول ريّاً فعليّاً**. المعالِجات
# الحقيقيّة (تحقّق رطوبة التربة، جدولة، تنفيذ أمر الريّ، التحقّق البعديّ) تُسجَّل
# لاحقاً حين تُبنى. لا تَبْنِ قراراً حقليّاً على هذه القوالب.


@register_handler("irrigation.validate")
def _irrigation_validate(ctx: dict) -> dict:
    # قالب: مكان التحقّق الحقيقيّ (رطوبة التربة/توفّر الماء) لاحقاً. لا تحقّق فعليّ.
    return {"validated": True, "_template": True}


@register_handler("irrigation.schedule")
def _irrigation_schedule(ctx: dict) -> dict:
    # قالب: مكان الجدولة الحقيقيّة (نافذة الريّ/الكمّيّة) لاحقاً. لا جدولة فعليّة.
    return {"scheduled": True, "_template": True}


@register_handler("irrigation.execute")
def _irrigation_execute(ctx: dict) -> dict:
    # قالب: مكان تنفيذ أمر الريّ الحقيقيّ (فتح صمّام/إرسال أمر) لاحقاً. لا تنفيذ فعليّ.
    return {"executed": True, "_template": True}


@register_handler("irrigation.verify")
def _irrigation_verify(ctx: dict) -> dict:
    # قالب: مكان التحقّق البعديّ الحقيقيّ (تأكّد وصول الماء) لاحقاً. لا تحقّق فعليّ.
    return {"verified": True, "_template": True}


# تعريف تصريحيّ تجريبيّ واحد يُثبت النمط: validate → schedule → execute → verify.
# صدق: هذا عرض للآليّة بمعالِجات قالبيّة — ليس تدفّق ريّ إنتاجيّاً.
register_definition(
    WorkflowDefinition(
        id="irrigation_cycle",
        name_ar="دورة الريّ (قالب توضيحيّ)",
        description_ar=(
            "عرض توضيحيّ للطبقة التصريحيّة: أربع خطوات مرتّبة "
            "(تحقّق → جدولة → تنفيذ → تحقّق بعديّ) بمعالِجات قالبيّة pass-through. "
            "ليست تدفّق ريّ حقيقيّاً — المعالِجات الفعليّة تُسجَّل لاحقاً."
        ),
        steps=(
            StepSpec(step_name="validate", handler_id="irrigation.validate"),
            StepSpec(step_name="schedule", handler_id="irrigation.schedule"),
            StepSpec(step_name="execute", handler_id="irrigation.execute"),
            StepSpec(step_name="verify", handler_id="irrigation.verify"),
        ),
    )
)

__all__ = [
    "StepSpec",
    "WorkflowDefinition",
    "register_handler",
    "register_definition",
    "build_steps",
    "list_workflows",
    "get_workflow",
]
