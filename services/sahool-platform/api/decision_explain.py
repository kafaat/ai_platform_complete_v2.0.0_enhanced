"""api/decision_explain.py — استخراج سلسلة شرح القرار من decision_value (Explainable)

يُغلق رأس «لماذا هذا القرار؟»: المنصّة تُدِيم القرار الكامل (decision_value JSONB في
decision_record v78 — ناتج unified_decision/crop_twin/profit_aware)، وهذا يحوي بالفعل
سلسلة شرح كاملة (ثقة، حالة المدخلات، سياسة، قيود، إجراء) متناثرة في حقوله. هذه الطبقة
**النقيّة** تستخرجها وتُهيكلها في سلسلة شرح موحّدة قابلة للعرض/الإعادة (Replay)، دون
إعادة حساب ودون قاعدة بيانات.

نقيّ حتميّ (لا I/O، لا قاعدة، لا ساعة): الموجِّه يقرأ decision_record عبر RLS ويُمرّر
decision_value هنا. هذا يجعل المنطق قابلاً للاختبار وحدويّاً بلا قاعدة.

الصدق (مبدأ مركزيّ): **الحقل الغائب ⇒ غياب صريح/None لا اختلاق.** لا تُفبرَك قيمة لم
يحملها القرار؛ يُكشَف الغياب (present=False) لا يُخفى. كلّ سلسلة الشرح موسومة
calibrated=False (مشتقّة من قرار غير معايَر). يدعم crop_twin/irrigation_plan/profit_aware
(نفس البنية الأساس من unified_decision؛ profit_aware يضيف policy_decision/economic_state).
"""

from __future__ import annotations

from typing import Any


def _is_mapping(v: Any) -> bool:
    """هل القيمة قاموس (كتلة فرعيّة قابلة للاستخراج)؟ — يحرس ضدّ مدخلات مُشوَّهة."""
    return isinstance(v, dict)


def _explain_confidence(dv: dict) -> dict:
    """الثقة في القرار + جودة البيانات — None صريح إن غابا (لا اختلاق درجة)."""
    return {
        "value": dv.get("confidence"),  # None إن لم يحملها القرار (لا تُفبرَك)
        "data_quality": dv.get("data_quality"),
        "present": "confidence" in dv and dv.get("confidence") is not None,
    }


def _explain_signals(dv: dict) -> dict:
    """حالة المدخلات (الإشارات) التي قاد القرار عليها: ماء/إجهاد/تربة من twin/risks.

    صدق: كلّ إشارة غائبة ⇒ present=False وقيمها None — لا تُختلق حالة لم يحملها القرار.
    المخاطر تُمرَّر كما وَردت (level_ar قد يكون «يحتاج بيانات» — غياب صريح يُكشَف لا يُخفى).
    """
    water = dv.get("water_state") if _is_mapping(dv.get("water_state")) else {}
    nutrient = dv.get("nutrient_state") if _is_mapping(dv.get("nutrient_state")) else {}
    pheno = dv.get("phenology") if _is_mapping(dv.get("phenology")) else {}
    risks = dv.get("risks") if isinstance(dv.get("risks"), list) else []
    stress_flags = dv.get("stress_flags") if isinstance(dv.get("stress_flags"), list) else []

    return {
        "water": {
            "present": bool(water),
            "needs_irrigation": water.get("needs_irrigation"),
            "depletion_mm": water.get("depletion_mm"),
            "deficit_mm": water.get("deficit_mm"),
        },
        "nutrient": {
            "present": bool(nutrient),
            "stage": nutrient.get("stage"),
            "remaining_need_kg_ha": nutrient.get("remaining_need_kg_ha"),
        },
        "phenology": {
            "present": bool(pheno),
            "stage": pheno.get("stage"),
            "past_maturity": pheno.get("past_maturity"),
        },
        # المخاطر كما وردت (key/label_ar/level_ar) — «يحتاج بيانات» غياب صريح يُكشَف.
        "risks": [
            {"key": r.get("key"), "label_ar": r.get("label_ar"), "level_ar": r.get("level_ar")}
            for r in risks
            if _is_mapping(r)
        ],
        # أعلام الإجهاد المفعّلة (عجز مائيّ/تجاوز نضج/تسميد مستحقّ) — قائمة قد تكون فارغة.
        "stress_flags": [
            {"code": f.get("code"), "label_ar": f.get("label_ar")}
            for f in stress_flags
            if _is_mapping(f)
        ],
    }


def _explain_policy(dv: dict) -> dict:
    """قرار السياسة: المُختار (resolved) vs المُطبَّق (applied) + auto + أسبابه.

    profit_aware يحمل policy_decision صريحةً (resolved≠applied محتمل عند نقص الأسعار).
    crop_twin البسيط لا يحمل policy_decision ⇒ نشتقّ السياسة المُطبَّقة من irrigation
    /irrigation_plan إن توفّرت (صدق: applied فقط؛ resolved=None — لم يُختَر آليّاً).
    """
    pd = dv.get("policy_decision")
    if _is_mapping(pd):
        return {
            "present": True,
            "resolved": pd.get("resolved_policy"),  # ما اختاره الاقتصاد/السياق
            "applied": pd.get("applied_policy"),  # ما طبّقته الخطّة فعلاً
            "auto": pd.get("auto"),
            "reasons_ar": list(pd.get("reasons_ar", []))
            if isinstance(pd.get("reasons_ar"), list)
            else [],
        }

    # لا policy_decision (crop_twin بسيط): نكشف السياسة المُطبَّقة من الخطّة إن وُجدت.
    applied = None
    irrig = dv.get("irrigation")
    if _is_mapping(irrig):
        applied = irrig.get("policy")
    if applied is None:
        plan = dv.get("irrigation_plan")
        if _is_mapping(plan):
            applied = plan.get("policy")
    return {
        "present": applied is not None,
        "resolved": None,  # لم تُختَر سياسة آليّاً (لا اختلاق)
        "applied": applied,
        "auto": False,
        "reasons_ar": [],
    }


def _explain_constraints(dv: dict) -> dict:
    """القيود التي حدّت القرار: ميزانيّة/سقف تطبيق (من الخطّة) + المخاطر المرتفعة + اقتصاد.

    صدق: السقوف غير المُمرَّرة ⇒ None (لا قيد مُختلق). المخاطر «يحتاج بيانات» لا تُحتسب
    قيداً فاعلاً (غياب لا تقييد). economic_state يُكشَف بحالته (not_configured صريح).
    """
    plan = dv.get("irrigation_plan") if _is_mapping(dv.get("irrigation_plan")) else {}
    risks = dv.get("risks") if isinstance(dv.get("risks"), list) else []

    # المخاطر الفاعلة فقط: «يحتاج بيانات»/«منخفض» ليست قيداً (لا تُضخَّم كقيد مُختلق).
    _inactive = {"يحتاج بيانات", "منخفض", None, ""}
    active_risks = [
        {"key": r.get("key"), "label_ar": r.get("label_ar"), "level_ar": r.get("level_ar")}
        for r in risks
        if _is_mapping(r) and r.get("level_ar") not in _inactive
    ]

    econ = dv.get("economic_state") if _is_mapping(dv.get("economic_state")) else None

    return {
        # سقوف الخطّة (إن مُرِّرت إليها) — None غياب صريح لا قيد مُختلق.
        "max_application_mm": plan.get("max_application_mm"),
        "season_budget_mm": plan.get("season_budget_mm"),
        "budget_exhausted": plan.get("budget_exhausted"),
        "active_risks": active_risks,  # مخاطر فاعلة (مرتفع/متوسط) — قد تكون فارغة
        # حالة الاقتصاد كقيد محتمل (تكلفة/ربح) — not_configured يُكشَف لا يُخفى.
        "economic_status": (econ.get("status") if econ is not None else None),
    }


def _explain_final(dv: dict) -> dict:
    """الإجراء النهائيّ الموصى به + الكمّيّة: من irrigation (المُؤلَّف) أو irrigation_plan.

    صدق: لا إجراء صريح ⇒ recommended_action=None وpresent=False (لا يُختلق إجراء). نُفضّل
    كتلة irrigation المُؤلَّفة (action_ar/next_event_mm) ونرجع للخطّة الخام عند غيابها.
    """
    irrig = dv.get("irrigation") if _is_mapping(dv.get("irrigation")) else {}
    plan = dv.get("irrigation_plan") if _is_mapping(dv.get("irrigation_plan")) else {}
    fert = dv.get("fertilization") if _is_mapping(dv.get("fertilization")) else {}

    action_ar = irrig.get("action_ar")
    # الكمّيّة الموصى بها: حدث الريّ التالي (mm) إن وُجد، وإلّا إجماليّ الخطّة.
    next_mm = irrig.get("next_event_mm")
    total_mm = irrig.get("total_mm")
    if total_mm is None:
        total_mm = plan.get("total_irrigation_mm")

    return {
        "present": bool(action_ar) or total_mm is not None,
        "recommended_action": action_ar,  # None إن لم يحمله القرار (لا اختلاق)
        "next_event_mm": next_mm,
        "total_irrigation_mm": total_mm,
        "next_event_day": irrig.get("next_event_day"),
        "dynamic_kc": dv.get("dynamic_kc"),
        # التسميد كإجراء مرافق (مستحقّ؟ + احتياج متبقٍّ) — قد يغيب.
        "fertilization": {
            "present": bool(fert),
            "due": fert.get("due"),
            "action_ar": fert.get("action_ar"),
        },
    }


def explain_decision(decision_value: dict | None) -> dict:
    """يستخرج سلسلة شرح مُهيكَلة من decision_value المُدام — نقيّ حتميّ، بلا قاعدة.

    decision_value: القرار الكامل كما أُدِيم (ناتج unified_decision/crop_twin/profit_aware).
    يعيد سلسلة الشرح المُهيكَلة: confidence → signals (حالة المدخلات) → policy → constraints
    → final (الإجراء + الكمّيّة)، كلّ كتلة تكشف حضورها/غيابها صراحةً.

    الصدق: الحقل الغائب ⇒ None/present=False لا اختلاق؛ calibrated=False (مشتقّ من قرار
    غير معايَر). decision_value فارغ/None ⇒ سلسلة بكتل غائبة (لا انهيار، لا تلفيق).
    """
    dv = decision_value if _is_mapping(decision_value) else {}
    return {
        "crop": dv.get("crop"),
        "crop_known": dv.get("crop_known", False),
        "decision_id": dv.get("decision_id"),
        "field_id": dv.get("field_id"),
        "confidence": _explain_confidence(dv),
        "signals": _explain_signals(dv),
        "policy": _explain_policy(dv),
        "constraints": _explain_constraints(dv),
        "final": _explain_final(dv),
        # أوسمة صدق على مستوى السلسلة:
        "calibrated": False,  # مشتقّ من قرار غير معايَر — يُعلَن لا يُخفى
        "has_decision_value": bool(dv),  # decision_value فارغ/None ⇒ False (لا تلفيق)
    }
