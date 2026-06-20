#!/usr/bin/env python3
"""
Advisory Skill Library for SAHOOL Supervisor Agent
Handles: Pest/disease ID · General agricultural advice · Q&A

الصدق التشغيليّ (راجع CLAUDE.md):
- مسار الآفات/الأمراض النصّيّ = مطابقة كلمات مفتاحيّة ثابتة (قوالب)، **لا** رؤية حاسوبيّة
  (VLM) ولا LLM. لا توجد خدمة VLM في المستودع، فلا ندّعي ذكاءً غير محقَّق.
- مسار النصيحة العامّة يدعم وصلاً **اختياريّاً** بخدمة local-ai-rag (LLM محليّ + RAG)
  خلف علم البيئة LOCAL_AI_RAG_URL. إن غاب العلم ⇒ السلوك السابق تماماً (قوالب).
  عند تفعيله ووصول إجابة ⇒ يُوسَم المصدر بدقّة: source="llm-rag"؛ وعند أيّ تعذّر
  (علم غائب، شبكة، خطأ خدمة) يرتدّ بأمان للقوالب ويُوسَم source="template".
"""

import logging
import os
from typing import Any

import httpx
from mcp_client import MCPClient

logger = logging.getLogger("supervisor.advisory")

# علم اختياريّ: عنوان خدمة local-ai-rag. غيابه ⇒ لا وصل، قوالب فقط (السلوك السابق).
LOCAL_AI_RAG_URL = os.getenv("LOCAL_AI_RAG_URL", "").strip()
# مهلة قصيرة: الوصل fail-soft — لا نُعطّل المستشار بانتظار LLM بطيء أو متعطّل.
RAG_TIMEOUT_S = float(os.getenv("LOCAL_AI_RAG_TIMEOUT_S", "8.0"))
# نصّ الرفض الصريح الذي تُرجِعه خدمة RAG حين لا تكفي قاعدة المعرفة — نعامله ارتداداً
# للقوالب (لا نُقدّم رفضاً مبهماً للمزارع حين لدينا قالب مفيد).
_RAG_NO_KNOWLEDGE_AR = "لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال."


def advisory_source(rag_url: str | None, rag_ok: bool) -> str:
    """دالّة نقيّة لاختيار وسم المصدر — قابلة للاختبار وحدويّاً.

    تُرجِع "llm-rag" فقط حين يكون الوصل مُفعّلاً (rag_url غير فارغ) **و** نجح الاستدعاء
    (rag_ok). فيما عدا ذلك (علم غائب أو فشل/ارتداد) تُرجِع "template". لا تدّعي ذكاءً
    لم يُحقَّق: غياب الوصل أو فشله ⇒ القوالب صراحةً.
    """
    if rag_url and rag_ok:
        return "llm-rag"
    return "template"


async def _query_local_rag(question: str, token: str | None) -> dict[str, Any] | None:
    """يستدعي خدمة local-ai-rag /query (httpx، مهلة قصيرة، fail-soft).

    يُرجِع dict إجابة الخدمة عند نجاح حقيقيّ ووجود محتوى مُجدٍ، وإلّا None (⇒ ارتداد
    للقوالب). لا يرمي: أيّ خطأ شبكة/خدمة/توكن يُسجَّل ويُترجَم إلى None بصمت آمن.
    خدمة RAG تشتقّ tenant_id من الـJWT، لذا نكتفي بتمرير توكن الخدمة في الترويسة.
    """
    if not LOCAL_AI_RAG_URL:
        return None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=RAG_TIMEOUT_S) as client:
            resp = await client.post(
                f"{LOCAL_AI_RAG_URL.rstrip('/')}/query",
                json={"question": question},
                headers=headers,
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — fail-soft: أيّ تعذّر ⇒ ارتداد للقوالب
        logger.warning("تعذّر استدعاء local-ai-rag (ارتداد للقوالب): %s", type(exc).__name__)
        return None

    answer = (data.get("answer") or "").strip()
    # إجابة فارغة أو رفض «لا معرفة كافية» ⇒ ارتداد للقوالب (لا نقدّم لا-جواب صريحاً).
    if not answer or answer == _RAG_NO_KNOWLEDGE_AR:
        return None
    return data


class AdvisorySkill:
    """
    Domain skill for agricultural advisory and pest/disease identification.

    التنفيذ الفعليّ: مطابقة كلمات مفتاحيّة (قوالب) للآفات/الأمراض، مع وصل اختياريّ
    بخدمة local-ai-rag (LLM محليّ + RAG) للنصيحة العامّة خلف علم LOCAL_AI_RAG_URL.
    لا يوجد تكامل VLM (لا خدمة رؤية حاسوبيّة في المستودع).
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    async def execute(  # ✅ timeout + fallback added
        self,
        intent: str,
        query: str = "",
        field_id: str | None = None,
        user_id: str = "",
        tenant_id: str = "",
        context: dict[str, Any] = None,
        objectives: list[str] = None,
    ) -> dict[str, Any]:

        if intent == "pest_id":
            # مطابقة كلمات مفتاحيّة ثابتة (قوالب) — لا VLM ولا LLM. لا خدمة رؤية في
            # المستودع، فلا ندّعي تشخيصاً من صورة. calibrated=false وsource=template.
            pest_keywords = {
                "أوراق صفراء": {
                    "pest": "ندفة صدئية",
                    "chemical": "Mancozeb",
                    "organic": "خلطة بيكربونات الصوديوم",
                },
                "ثقوب في الأوراق": {
                    "pest": "دودة ورقية",
                    "chemical": "Chlorpyrifos",
                    "organic": "Bacillus thuringiensis",
                },
                "بيض أبيض": {"pest": "منّ", "chemical": "Imidacloprid", "organic": "زيت النيم"},
                "عناكب": {"pest": "عنكبوت أحمر", "chemical": "Abamectin", "organic": "صابون زراعي"},
                "ذبول": {
                    "pest": "تعفن جذري",
                    "chemical": "Metalaxyl",
                    "organic": "Trichoderma harzianum",
                },
            }

            matched = None
            for keyword, info in pest_keywords.items():
                if keyword in query:
                    matched = info
                    break

            if matched:
                return {
                    "type": "pest_alert",
                    "alert": f"تم اكتشاف: **{matched['pest']}**",
                    "action": f"المعالجة الكيميائية: {matched['chemical']}\nالمعالجة العضوية: {matched['organic']}",
                    "severity": "متوسط",
                    # صدق: مطابقة قوالب لا تشخيص مُعايَر.
                    "source": "template",
                    "calibrated": False,
                    # بنية مهيكلة للحَوكمة الفعليّة (تقرؤها الطبقة الكيميائيّة)
                    "actionable": True,
                    "action_type": "pesticide",
                    "structured": {
                        "chemical": matched["chemical"],
                        "organic_alternative": matched["organic"],
                    },
                    "sources": ["SAHOOL Pest Database", "Yemen Plant Protection"],
                }

            return {
                "type": "pest_unknown",
                "response": "لم أتمكن من التعرف على الآفة من الوصف. يرجى إرسال صورة واضحة عبر Telegram Bot.",
                "source": "template",
                "calibrated": False,
                "sources": [],
            }

        elif intent == "disease_id":
            # مطابقة كلمات مفتاحيّة ثابتة (قوالب) — لا VLM ولا LLM. source=template.
            disease_keywords = {
                "بقع داكنة": {"disease": "بقع أوراق", "treatment": "Mancozeb + Copper oxychloride"},
                "بودرة بيضاء": {
                    "disease": "البياض الدقيقي",
                    "treatment": "Sulfur أو Propiconazole",
                },
                "عفن رمادي": {"disease": "Botrytis", "treatment": "تقليل الرطوبة + Iprodione"},
                "تعفن": {
                    "disease": "تعفن بكتيري",
                    "treatment": "Streptomycin sulfate (محظور في بعض الدول)",
                },
            }

            matched = None
            for keyword, info in disease_keywords.items():
                if keyword in query:
                    matched = info
                    break

            if matched:
                return {
                    "type": "disease_alert",
                    "alert": f"تم اكتشاف: **{matched['disease']}**",
                    "action": f"المعالجة: {matched['treatment']}",
                    "severity": "عالٍ" if "تعفن" in matched["disease"] else "متوسط",
                    # صدق: مطابقة قوالب لا تشخيص مُعايَر.
                    "source": "template",
                    "calibrated": False,
                    # بنية مهيكلة للحَوكمة الفعليّة (الطبقة الكيميائيّة تفحص treatment)
                    "actionable": True,
                    "action_type": "pesticide",
                    "structured": {"chemical": matched["treatment"]},
                    "sources": ["SAHOOL Disease Database"],
                }

            return {
                "type": "disease_unknown",
                "response": "لم أتمكن من التعرف على المرض. يرجى إرسال صورة.",
                "source": "template",
                "calibrated": False,
                "sources": [],
            }

        elif intent == "general_advice":
            # وصل اختياريّ بـlocal-ai-rag (LLM محليّ + RAG) خلف LOCAL_AI_RAG_URL.
            # إن غاب العلم أو فشل الاستدعاء ⇒ ارتداد للقوالب أدناه (السلوك السابق).
            token = getattr(self.mcp, "token", None)
            rag_data = await _query_local_rag(query, token)
            rag_ok = rag_data is not None
            source = advisory_source(LOCAL_AI_RAG_URL or None, rag_ok)

            if source == "llm-rag":
                # وسم دقيق: إجابة LLM حقيقيّة من قاعدة المعرفة المُؤرَّضة.
                rag_sources = rag_data.get("sources") or []
                return {
                    "type": "general_advice",
                    "response": rag_data.get("answer", ""),
                    "source": "llm-rag",
                    "calibrated": True,
                    "model": rag_data.get("model"),
                    "sources": rag_sources,
                }

            # ── ارتداد القوالب (المصدر الافتراضيّ الصادق) ──────────────────────────
            advice_templates = {
                "زراعة قمح": "🌾 **زراعة القمح في اليمن:**\n1. التوقيت: نوفمبر–ديسمبر\n2. الصنف: الحمداني أو البيضاني\n3. التسميد: 80kg N/ha عند الزراعة + 40kg عند التفرعات\n4. الري: 3–4 مرات حسب الأمطار\n5. الحصاد: مايو–يونيو",
                "ري ذكي": "💧 **الري الذكي:**\n1. استخدم مقياس رطوبة التربة\n2. ري عند 30% رطوبة\n3. الري بالتنقيط يوفر 40% مياه\n4. ري صباحاً لتقليل التبخر\n5. تجنب الري عند توقع أمطار",
                "تسميد": "🧪 **التسميد المتوازن:**\n1. حلل التربة أولاً\n2. NPK حسب المحصول والمرحلة\n3. لا تفرط في النيتروجين — يؤخر النضج\n4. استخدم السماد العضوي مع الكيميائي\n5. التسميد الجوري أفضل من البث",
                "حصاد": "🚜 **نصائح الحصاد:**\n1. راقب رطوبة الحبوب (13–14%)\n2. حصاد في الصباح الباكر\n3. تجفيف فوري إذا كانت الرطوبة >15%\n4. تخزين في صوامع نظيفة\n5. راقب درجة الحرارة في المخزن",
            }

            for keyword, template in advice_templates.items():
                if keyword in query:
                    return {
                        "type": "general_advice",
                        "response": template,
                        "source": "template",
                        "calibrated": False,
                        "sources": ["SAHOOL Agricultural Knowledge Base", "FAO Yemen Guidelines"],
                    }

            return {
                "type": "general_advice",
                "response": "شكراً على سؤالك. أنا أعمل على توسيع قاعدة المعرفة. للاستفسارات المحددة، يرجى التواصل مع فريق SAHOOL.",
                "source": "template",
                "calibrated": False,
                "sources": [],
            }

        else:
            return {"type": "error", "response": f"نوعية استعلام استشاري غير معروفة: {intent}"}
