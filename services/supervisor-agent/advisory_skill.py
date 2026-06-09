#!/usr/bin/env python3
"""
Advisory Skill Library for SAHOOL Supervisor Agent
Handles: Pest/disease ID · General agricultural advice · Q&A
"""

from typing import Any

from mcp_client import MCPClient


class AdvisorySkill:
    """
    Domain skill for agricultural advisory and pest/disease identification.
    Production: integrates VLM (YOLOv8-World/Agri-LLaVA) + LLM (AraGPT).
    """

    def __init__(self, mcp_client: MCPClient):
        self.mcp = mcp_client

    async def execute(
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
            # Production: call VLM service
            # For MVP: rule-based + RAG lookup
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
                    "sources": ["SAHOOL Pest Database", "Yemen Plant Protection"],
                }

            return {
                "type": "pest_unknown",
                "response": "لم أتمكن من التعرف على الآفة من الوصف. يرجى إرسال صورة واضحة عبر Telegram Bot.",
                "sources": [],
            }

        elif intent == "disease_id":
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
                    "sources": ["SAHOOL Disease Database"],
                }

            return {
                "type": "disease_unknown",
                "response": "لم أتمكن من التعرف على المرض. يرجى إرسال صورة.",
                "sources": [],
            }

        elif intent == "general_advice":
            # Production: call LLM (AraGPT) with RAG
            # For MVP: template-based responses

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
                        "sources": ["SAHOOL Agricultural Knowledge Base", "FAO Yemen Guidelines"],
                    }

            return {
                "type": "general_advice",
                "response": "شكراً على سؤالك. أنا أعمل على توسيع قاعدة المعرفة. للاستفسارات المحددة، يرجى التواصل مع فريق SAHOOL.",
                "sources": [],
            }

        else:
            return {"type": "error", "response": f"نوعية استعلام استشاري غير معروفة: {intent}"}
