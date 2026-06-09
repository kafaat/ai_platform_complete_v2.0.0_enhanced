"""
api/decision_explainer.py — طبقة تفسير القرار بالذكاء الاصطناعي (فوق المحرّك)

الفكرة المعماريّة الجوهريّة (مبدأ: القواعد تقرّر، الذكاء يشرح):
  • محرّك القرار (decision_engine) يبقى قائماً على القواعد — شفّاف، موثوق،
    قابل للتتبّع، لا يهلوس. هو من «يقرّر».
  • هذه الطبقة تأخذ ناتج المحرّك وتستدعي Claude لـ«صياغة» شرح دافئ بلغة
    طبيعيّة للمزارع — تفسير وتواصل لا قرار.

لماذا هذا الفصل مهمّ؟
  لو ترك القرار للـAI التوليدي، قد يخترع أرقاماً أو يوصي بمحصول غير مناسب
  (هلوسة). بفصل «القرار» (قواعد) عن «الشرح» (AI)، نحصل على دقّة القواعد +
  ودّ اللغة الطبيعيّة، دون مخاطرة الهلوسة في التوصية نفسها.

التدفّق:
  decision_engine.decide_for_location() → ناتج منظّم (قواعد)
    → build_explanation_prompt() → نصّ موجّه لـClaude
    → [الخادم يستدعي Claude API عبر proxy آمن]
    → شرح بلغة طبيعيّة + بديل offline إن غاب الـAI

⚠ الـAI يشرح فقط ما قرّرته القواعد — لا يضيف توصيات من عنده. التعليمات
الموجّهة لـClaude تمنعه صراحةً من اختراع محاصيل أو أرقام. القرار يبقى للمزارع.
"""

from __future__ import annotations

# نموذج Claude المستخدم للتفسير (يُمرّر للـproxy الآمن في الخادم)
_EXPLAINER_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 800


def build_explanation_prompt(decision: dict, rag_context: str | None = None) -> dict:
    """يبني طلب Claude من ناتج محرّك القرار (rule-based).

    يُرجع dict جاهزاً لإرساله عبر proxy الخادم الآمن (لا مفتاح هنا).
    التعليمات تقيّد Claude بالشرح فقط — لا اختراع.
    rag_context: سياق اختياري من نظام RAG (معرفة الجوف الموثّقة) لإثراء الشرح
                 بمراجع محلّيّة دقيقة. يُجلب من خدمة local-ai-rag (/query).
    """
    # استخرج الحقائق من ناتج المحرّك (القواعد) لحقنها في السياق
    loc = decision.get("location_ar", {})
    facts_lines = []
    if loc:
        facts_lines.append(
            f"الموقع: {loc.get('governorate_ar') or loc.get('input_ar', '')} "
            f"— الإقليم: {loc.get('zone_name_ar', '')}"
        )
    if decision.get("suited_crops_ar"):
        facts_lines.append("محاصيل ملائمة: " + "، ".join(decision["suited_crops_ar"][:5]))
    if decision.get("avoid_ar"):
        facts_lines.append("يُتجنّب: " + "، ".join(decision["avoid_ar"][:4]))
    if decision.get("water_strategy_ar"):
        facts_lines.append("الماء: " + decision["water_strategy_ar"])
    if decision.get("actual_climate_data_ar"):
        c = decision["actual_climate_data_ar"]
        facts_lines.append(
            f"بيانات فعليّة: {c.get('annual_rainfall_mm')}مم مطر/سنة، "
            f"{c.get('heat_stress_days_per_year')} يوم إجهاد حراري"
        )
    if decision.get("salinity_alert_ar"):
        facts_lines.append(decision["salinity_alert_ar"])
    if decision.get("alkalinity_alert_ar"):
        facts_lines.append(decision["alkalinity_alert_ar"])
    if decision.get("chill_hours_ar"):
        facts_lines.append("ساعات البرودة: " + decision["chill_hours_ar"].get("verdict_ar", ""))
    if decision.get("high_value_opportunities_ar"):
        hv = decision["high_value_opportunities_ar"].get("top_3_ar", [])
        if hv:
            facts_lines.append("فرص عالية القيمة: " + "، ".join(hv))
    if decision.get("decision_summary_ar"):
        facts_lines.append("الخلاصة: " + decision["decision_summary_ar"])

    facts = "\n".join(f"- {line}" for line in facts_lines)

    rag_block = ""
    if rag_context and rag_context.strip():
        rag_block = (
            "\n\nمراجع محلّيّة موثّقة (من قاعدة معرفة الجوف — استند إليها إن "
            f"كانت ذات صلة، ولا تتجاوزها):\n{rag_context.strip()}\n"
        )

    system = (
        "أنت مرشد زراعي ودود يساعد مزارعاً يمنيّاً. مهمّتك: شرح التحليل التالي "
        "بلغة عربيّة بسيطة ودافئة، كأنّك تتحدّث مع مزارع في حقله.\n\n"
        "قواعد صارمة:\n"
        "• اشرح فقط الحقائق المعطاة أدناه — لا تضف محاصيل أو أرقاماً من عندك.\n"
        "• لا تخترع توصيات جديدة؛ القرار اتُّخذ بمعطيات موثّقة.\n"
        "• إن لم تكن معلومة موجودة، لا تخمّنها.\n"
        "• كن موجزاً (3-5 جُمل)، عمليّاً، ومشجّعاً دون مبالغة.\n"
        "• ذكّر بلطف أنّ القرار النهائي للمزارع وأنّ استشارة هيئة البحوث مفيدة.\n"
        "• تكلّم بصيغة المخاطب المباشر (أنت/حقلك)."
    )
    user = (
        "إليك تحليل حقل المزارع (من نظام قائم على القواعد والبيانات الموثّقة):\n\n"
        f"{facts}\n"
        f"{rag_block}\n"
        "اشرح له هذا بإيجاز ودفء: لماذا هذه المحاصيل تناسب أرضه، وما أهمّ "
        "نقطة ينتبه لها (ماء/ملوحة/توقيت)، وما خطوته التالية."
    )

    return {
        "model": _EXPLAINER_MODEL,
        "max_tokens": _MAX_TOKENS,
        # temperature=0 لأقصى حتميّة (نفس المدخل → نفس الصياغة) — يدعم
        # auditability/reproducibility (مراجعة #14). الحقائق من القواعد أصلاً؛
        # هذا يجعل حتّى صياغة الـAI قابلة لإعادة الإنتاج.
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "_meta": {
            "purpose": "decision_explanation",
            "rule_based_source": True,  # الحقائق من القواعد لا من الـAI
            "model_version": _EXPLAINER_MODEL,  # version pinning (auditability)
        },
    }


def offline_explanation(decision: dict) -> str:
    """بديل offline: شرح مولّد من القواعد دون AI (حين لا يتوفّر Claude).

    يضمن أنّ المزارع يحصل على شرح مفهوم حتّى بلا إنترنت (offline-first).
    """
    if not decision.get("supported"):
        return decision.get("needs_clarification_ar") or decision.get(
            "message_ar", "تعذّر تحليل الموقع — تأكّد من الإحداثيّات أو الاسم."
        )

    loc = decision.get("location_ar", {})
    parts = []
    zone = loc.get("zone_name_ar", "")
    gov = loc.get("governorate_ar") or loc.get("input_ar", "")
    if zone:
        parts.append(f"حقلك في {gov} يقع ضمن «{zone}».")
    crops = decision.get("suited_crops_ar") or []
    if crops:
        parts.append(f"الأنسب لمناخك: {'، '.join(crops[:4])}.")
    if not decision.get("rainfed_possible", True):
        parts.append("الأمطار لا تكفي — الريّ ضروري، فأدِر الماء بعناية (تنقيط).")
    if decision.get("salinity_alert_ar"):
        parts.append("انتبه للملوحة: اختر محاصيل وأصولاً متحمّلة.")
    if decision.get("chill_hours_ar", {}).get("estimated") == 0:
        parts.append("تجنّب الأشجار المحتاجة لبرودة شتويّة (كالتفاح) — مناخك حارّ.")
    if decision.get("decision_summary_ar"):
        parts.append(decision["decision_summary_ar"])
    parts.append(
        "القرار النهائي لك — افحص تربة حقلك واستشر هيئة البحوث والإرشاد الزراعي قبل التنفيذ."
    )
    return " ".join(parts)


def explain_decision(
    decision: dict, ai_response_text: str | None = None, rag_context: str | None = None
) -> dict:
    """يجمع التفسير: يستخدم نصّ Claude إن توفّر، وإلّا البديل offline.

    ai_response_text: نصّ شرح Claude (يأتي من الخادم بعد استدعاء الـproxy).
                      إن كان None → نستخدم الشرح offline من القواعد.
    rag_context: سياق اختياري من RAG (معرفة الجوف) يُحقن في prompt الخادم.
    """
    used_ai = bool(ai_response_text and ai_response_text.strip())
    explanation = ai_response_text.strip() if used_ai else offline_explanation(decision)
    return {
        "supported": decision.get("supported", False),
        "explanation_ar": explanation,
        "explanation_source": "ai" if used_ai else "rule_based_offline",
        "rag_used": bool(rag_context and rag_context.strip()),
        "note_ar": (
            "شرح بالذكاء الاصطناعي (Claude) — القرار نفسه من نظام القواعد الموثّق."
            if used_ai
            else "شرح من نظام القواعد (يعمل دون إنترنت). الذكاء الاصطناعي يضيف صياغة "
            "أدفأ عند توفّره."
        ),
        "prompt_for_server": (
            build_explanation_prompt(decision, rag_context) if not used_ai else None
        ),
        "disclaimer_ar": (
            "الذكاء الاصطناعي يشرح ولا يقرّر — التوصية من القواعد الموثّقة، والقرار النهائي لك."
        ),
    }
