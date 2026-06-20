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

صدق: معالِجات irrigation_cycle لها مساران — قوالب pass-through (سقالة) ومعالِجات
حقيقيّة حتميّة فوق الطبقات النقيّة (soil_water/irrigation_policy/irrigation_mpc).
الاختيار خلف علم `FEATURE_IRRIGATION_WORKFLOW_REAL` (إغلاق مرن): مُطفأ ⇒ القوالب
تماماً (صفر كسر)؛ مُفعَّل ⇒ المعالِجات الحقيقيّة مع تعليق HITL وتعويض Saga.
المعالِجات الحقيقيّة منطق قرار حتميّ فقط — لا تحرّك صمّاماً (التنفيذ الفيزيائيّ
يبقى لطبقة actuator؛ execute يُرجِع نيّة تنفيذ موسومة لا أمر عتاد مباشر).
"""

from __future__ import annotations

import os
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
# الحقيقيّة (تحقّق رطوبة التربة، جدولة، تنفيذ أمر الريّ، التحقّق البعديّ) مسجَّلة
# أدناه خلف علم `FEATURE_IRRIGATION_WORKFLOW_REAL` (إغلاق مرن). القوالب تبقى
# المسار الافتراضيّ حين يكون العلم مُطفأً — صفر كسر على السلوك القائم.


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


# ── معالِجات الريّ الحقيقيّة (حتميّة، تعيد استخدام الطبقات النقيّة) ──────────
#
# صدق صريح: هذه المعالِجات **منطق قرار حتميّ** فوق الطبقات النقيّة القائمة
# (soil_water / irrigation_policy / irrigation_mpc). لا تلمس عتاداً ولا تفتح
# صمّاماً — التنفيذ الفيزيائيّ يبقى لطبقة actuator. `irrigation.real.execute`
# يُرجِع **نيّة تنفيذ موسومة** (intent) لا أمر MQTT مباشر، ويحترم HITL تماماً
# كـpest_escalation_flow (لا تنفيذ بلا موافقة معتمَدة). كلّ معالِج يَسِم
# `_template=False` ليُميَّز عن القوالب أعلاه.

# حالات الموافقة التي تسمح بالتنفيذ (HITL) — نفس اصطلاح pest_escalation_flow.
_IRRIGATION_APPROVAL_CLEARED = frozenset({"approved", "not_required"})

_TRUTHY = {"1", "true", "yes", "on"}


def _irrigation_workflow_real_enabled() -> bool:
    """هل معالِجات الريّ الحقيقيّة مُفعَّلة؟ (مُطفأة افتراضاً — إغلاق مرن).

    عند الإطفاء: تُستعمل القوالب pass-through تماماً (صفر كسر على السلوك القائم).
    """
    return os.getenv("FEATURE_IRRIGATION_WORKFLOW_REAL", "").strip().lower() in _TRUTHY


def _as_float(value: object, default: float | None = None) -> float | None:
    """يحوّل قيمة سياق إلى float بأمان — None إن تعذّر (لا اختلاق صفر صامت)."""
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


@register_handler("irrigation.real.validate")
def _irrigation_real_validate(ctx: dict) -> dict:
    """تحقّق حقيقيّ من مدخلات الريّ — يرفض الناقص بصدق (لا validated:true أعمى).

    يتطلّب: مُعرِّف الحقل (field_id) + نسيج تربة (texture) لاشتقاق TAW + توقّعات
    جوّيّة (forecast غير فارغة) للجدولة. الميزانيّة الموسميّة وسقف الدفعة اختياريّان
    لكن إن وُردا سالبَين يُرفَضان. السياسة إن وُردت تُتحقّق من كونها معروفة.
    صدق: التحقّق فعليّ — أيّ مُدخَل أساسيّ ناقص ⇒ valid=False مع أسباب صريحة.
    """
    from api.irrigation_policy import _coerce_policy

    errors: list[str] = []

    field_id = ctx.get("field_id")
    if not field_id:
        errors.append("field_id مفقود — لا يُحدَّد الحقل المستهدَف")

    texture = ctx.get("texture")
    if not texture:
        errors.append("texture (نسيج التربة) مفقود — لا يُشتقّ TAW لجدولة واعية بالتربة")

    forecast = ctx.get("forecast")
    if not isinstance(forecast, list) or len(forecast) == 0:
        errors.append("forecast (توقّعات الأفق) مفقودة/فارغة — لا يُبنى جدول ريّ")

    budget = _as_float(ctx.get("season_budget_mm"))
    if budget is not None and budget < 0:
        errors.append("season_budget_mm سالبة — ميزانيّة غير صالحة")

    max_app = _as_float(ctx.get("max_application_mm"))
    if max_app is not None and max_app <= 0:
        errors.append("max_application_mm ≤ 0 — سقف دفعة غير صالح")

    policy = ctx.get("policy")
    if policy is not None and _coerce_policy(policy) is None:
        errors.append(f"policy غير معروفة ({policy}) — اختر سياسة صالحة أو اتركها للمُحلِّل")

    if errors:
        # صدق: نرفع خطأً ليتوقّف الـworkflow عند خطوة validate (status=FAILED،
        # قابل للاستئناف بعد تصحيح المدخلات) بدل تمرير نجاح زائف.
        raise ValueError("فشل تحقّق مدخلات الريّ: " + "؛ ".join(errors))

    return {
        "validated": True,
        "_template": False,
        "validation_errors_ar": [],
        "field_id": field_id,
    }


@register_handler("irrigation.real.schedule")
def _irrigation_real_schedule(ctx: dict) -> dict:
    """يبني جدول ريّ حتميّاً عبر plan_irrigation فوق الطبقات النقيّة.

    يشتقّ TAW/RAW من النسيج وعمق الجذور (soil_water)، يحلّ السياسة من السياق إن
    لم تُمرَّر صراحةً (irrigation_policy.resolve_policy)، ثمّ يخطّط عبر الأفق
    (irrigation_mpc.plan_irrigation). صدق: حتميّ بالكامل — نفس المدخلات نفس الجدول.
    """
    from api.irrigation_mpc import ForecastDay, plan_irrigation
    from api.irrigation_policy import PolicyContext, resolve_policy
    from api.soil_water import soil_water_params

    swp = soil_water_params(
        ctx.get("texture"),
        root_depth_m=_as_float(ctx.get("root_depth_m")),
        raw_fraction=_as_float(ctx.get("raw_fraction"), 0.5) or 0.5,
    )
    taw_mm = swp["taw_mm"]
    raw_fraction = swp["raw_fraction"]

    policy = ctx.get("policy")
    policy_reasons: list[str] = []
    if policy is None:
        policy, policy_reasons = resolve_policy(
            PolicyContext(
                region=ctx.get("region"),
                crop=ctx.get("crop"),
                water_source=ctx.get("water_source"),
                water_cost=ctx.get("water_cost"),
                energy_cost=ctx.get("energy_cost"),
            )
        )

    forecast = [
        ForecastDay(
            et0_mm=_as_float(d.get("et0_mm"), 0.0) or 0.0,
            kc=_as_float(d.get("kc"), 0.0) or 0.0,
            rain_mm=_as_float(d.get("rain_mm"), 0.0) or 0.0,
            runoff_mm=_as_float(d.get("runoff_mm"), 0.0) or 0.0,
        )
        for d in ctx.get("forecast", [])
    ]

    plan = plan_irrigation(
        forecast,
        taw_mm=taw_mm,
        raw_fraction=raw_fraction,
        policy=policy,
        initial_depletion_mm=_as_float(ctx.get("initial_depletion_mm"), 0.0) or 0.0,
        max_application_mm=_as_float(ctx.get("max_application_mm")),
        season_budget_mm=_as_float(ctx.get("season_budget_mm")),
        water_price_per_m3=_as_float(ctx.get("water_price_per_m3")),
        yield_value_per_ha=_as_float(ctx.get("yield_value_per_ha")),
    )
    plan_dict = plan.to_dict()
    return {
        "scheduled": True,
        "_template": False,
        "irrigation_plan": plan_dict,
        "planned_total_mm": plan_dict["total_irrigation_mm"],
        "planned_n_events": plan_dict["n_events"],
        "soil_water_params": swp,
        "policy_reasons_ar": policy_reasons,
    }


@register_handler("irrigation.real.execute")
def _irrigation_real_execute(ctx: dict) -> dict:
    """ينتج **نيّة تنفيذ ريّ موسومة** — يحترم HITL، لا يحرّك صمّاماً.

    HITL (كـpest_escalation_flow): لا تنفيذ إلّا بموافقة معتمَدة (approval_status
    ضمن approved/not_required). قبلها لا نُصدِر نيّة تنفيذ (executed=False). صدق:
    لا أمر MQTT مباشر هنا — نُرجِع نيّة منطقيّة (intent) تستهلكها طبقة actuator.
    """
    approval = ctx.get("approval_status")
    plan = ctx.get("irrigation_plan") or {}
    planned_total = _as_float(plan.get("total_irrigation_mm"), 0.0) or 0.0

    if approval not in _IRRIGATION_APPROVAL_CLEARED:
        # HITL فعليّ: لا نيّة تنفيذ بلا موافقة (لا نُنفّذ صمتاً رغم pending).
        return {
            "executed": False,
            "_template": False,
            "execution_intent": None,
            "note_ar": "بانتظار موافقة الخبير — لم تُصدَر نيّة تنفيذ ريّ",
        }

    if planned_total <= 0.0:
        # لا ماء مجدول ⇒ لا نيّة تنفيذ (صدق: لا نختلق أمر ريّ بلا حاجة).
        return {
            "executed": False,
            "_template": False,
            "execution_intent": None,
            "note_ar": "الجدول لا يتطلّب ريّاً (إجماليّ صفر) — لا نيّة تنفيذ",
        }

    intent = {
        "type": "irrigation_command_intent",
        "field_id": ctx.get("field_id"),
        "total_mm": round(planned_total, 2),
        "total_m3_ha": _as_float(plan.get("total_irrigation_m3_ha"), 0.0),
        "n_events": plan.get("n_events"),
        "policy": plan.get("policy"),
        "approval_status": approval,
        # نيّة منطقيّة فقط — طبقة actuator تترجمها لأمر فيزيائيّ (لا MQTT هنا).
        "dispatched": False,
    }
    return {
        "executed": True,
        "_template": False,
        "execution_intent": intent,
        "executed_total_mm": intent["total_mm"],
        "note_ar": "صدرت نيّة تنفيذ ريّ منطقيّة (لم يُحرَّك صمّام — تُسلَّم لطبقة actuator)",
    }


@register_handler("irrigation.real.execute.compensate")
def _irrigation_real_execute_compensate(ctx: dict) -> dict:
    """تعويض Saga لخطوة التنفيذ: يبطل نيّة التنفيذ إن فشلت خطوة لاحقة.

    صدق: لم يُحرَّك صمّام أصلاً (نيّة منطقيّة)، فالتعويض يَسِم النيّة ملغاةً
    ليلتقطها مُستهلِك actuator فلا ينفّذها (لا ادّعاء تراجع فيزيائيّ).
    """
    intent = ctx.get("execution_intent")
    if isinstance(intent, dict):
        intent["cancelled"] = True
    ctx["execution_cancelled"] = True
    return {"execution_cancelled": True, "_template": False}


@register_handler("irrigation.real.verify")
def _irrigation_real_verify(ctx: dict) -> dict:
    """يقارن المُخطَّط بالمُنفَّذ — تحقّق بعديّ منطقيّ (لا قراءة عتاد).

    صدق: التحقّق هنا اتّساق منطقيّ بين كمّيّة الجدول وكمّيّة نيّة التنفيذ، لا تأكّد
    فيزيائيّ لوصول الماء (ذاك يحتاج حسّاساً — طبقة لاحقة). نُعلن الفجوة إن وُجدت.
    """
    plan = ctx.get("irrigation_plan") or {}
    planned_total = _as_float(plan.get("total_irrigation_mm"), 0.0) or 0.0
    executed = bool(ctx.get("executed"))
    executed_total = _as_float(ctx.get("executed_total_mm"), 0.0) or 0.0

    if not executed:
        # لم يُنفَّذ (HITL معلّق أو لا حاجة) ⇒ التحقّق يعكس ذلك بصدق.
        return {
            "verified": False,
            "_template": False,
            "planned_mm": round(planned_total, 2),
            "executed_mm": 0.0,
            "match": planned_total <= 0.0,
            "note_ar": "لم يُنفَّذ ريّ — لا شيء للتحقّق منه فيزيائيّاً",
        }

    delta = round(abs(planned_total - executed_total), 4)
    match = delta < 1e-6
    return {
        "verified": match,
        "_template": False,
        "planned_mm": round(planned_total, 2),
        "executed_mm": round(executed_total, 2),
        "delta_mm": delta,
        "match": match,
        "note_ar": (
            "تطابق المُخطَّط والمُنفَّذ (منطقيّاً)"
            if match
            else "فجوة بين المُخطَّط والمُنفَّذ — راجِع طبقة التنفيذ"
        ),
    }


# تعريف تصريحيّ لدورة الريّ: validate → schedule → execute → verify.
# اختيار المعالِجات بالعلم (إغلاق مرن): العلم مُطفأ ⇒ قوالب pass-through تماماً
# (السلوك القائم، صفر كسر)؛ مُفعَّل ⇒ المعالِجات الحقيقيّة الحتميّة أعلاه مع
# تعليق HITL على execute (لا تنفيذ بلا موافقة) وتعويض Saga على نيّة التنفيذ.
@register_handler("irrigation.real.approval_gate")
def _irrigation_real_approval_gate(ctx: dict) -> dict:
    """بوّابة موافقة (HITL): خطوة لا-أثرية تُعلَّق عبر suspends المشروط أدناه.

    تكتمل فوراً؛ التعليق الفعليّ يقرّره `irrigation.real.suspend_until_approved`
    المُقيَّم على السياق بعد التنفيذ (نمط pest_escalation_flow await_approval).
    """
    return {
        "approval_gate": True,
        "_template": False,
        "approval_status": ctx.get("approval_status", "pending"),
    }


@register_handler("irrigation.real.suspend_until_approved")
def _irrigation_real_suspend_until_approved(ctx: dict) -> bool:
    """تعليق مشروط (HITL): يُعلّق الـworkflow قبل execute حين تكون الموافقة معلّقة.

    لا نُعلّق إن كانت الموافقة معتمَدة/غير مطلوبة — تماماً كـpest_escalation_flow.
    `build_steps` يحلّ suspends_id من السجلّ كدالّة (ctx)→bool تُقيَّم بعد الخطوة.
    """
    return ctx.get("approval_status") not in _IRRIGATION_APPROVAL_CLEARED


if _irrigation_workflow_real_enabled():
    register_definition(
        WorkflowDefinition(
            id="irrigation_cycle",
            name_ar="دورة الريّ (معالِجات حقيقيّة)",
            description_ar=(
                "تدفّق ريّ حتميّ فوق الطبقات النقيّة (soil_water/irrigation_policy/"
                "irrigation_mpc): تحقّق المدخلات → جدولة عبر plan_irrigation → بوّابة "
                "موافقة (HITL) → تنفيذ منطقيّ (نيّة تنفيذ، لا صمّام) → تحقّق بعديّ. "
                "المعالِجات حتميّة؛ التنفيذ الفيزيائيّ يبقى لطبقة actuator."
            ),
            steps=(
                StepSpec(step_name="validate", handler_id="irrigation.real.validate"),
                StepSpec(step_name="schedule", handler_id="irrigation.real.schedule"),
                # بوّابة موافقة معلِّقة (HITL): تُعلّق الـworkflow حين الموافقة معلّقة،
                # فلا يصل التنفيذ بلا موافقة — يُستأنف بعد approval_status=approved.
                StepSpec(
                    step_name="approval_gate",
                    handler_id="irrigation.real.approval_gate",
                    suspends_id="irrigation.real.suspend_until_approved",
                ),
                StepSpec(
                    step_name="execute",
                    handler_id="irrigation.real.execute",
                    compensate_id="irrigation.real.execute.compensate",
                ),
                StepSpec(step_name="verify", handler_id="irrigation.real.verify"),
            ),
        )
    )
else:
    # تعريف تصريحيّ توضيحيّ بمعالِجات قالبيّة pass-through (السلوك الافتراضيّ القائم).
    # صدق: عرض للآليّة — ليس تدفّق ريّ إنتاجيّاً (العلم مُطفأ).
    register_definition(
        WorkflowDefinition(
            id="irrigation_cycle",
            name_ar="دورة الريّ (قالب توضيحيّ)",
            description_ar=(
                "عرض توضيحيّ للطبقة التصريحيّة: أربع خطوات مرتّبة "
                "(تحقّق → جدولة → تنفيذ → تحقّق بعديّ) بمعالِجات قالبيّة pass-through. "
                "ليست تدفّق ريّ حقيقيّاً — المعالِجات الفعليّة خلف "
                "FEATURE_IRRIGATION_WORKFLOW_REAL."
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
