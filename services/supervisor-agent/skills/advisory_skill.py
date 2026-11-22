#!/usr/bin/env python3
"""
Advisory Skill Library for SAHOOL Supervisor Agent
Handles: Pest/disease ID · General agricultural advice · Q&A

الصدق التشغيليّ (راجع CLAUDE.md):
- مسار الآفات/الأمراض لا يملك جدولاً محليّاً ولا يسمّي أيّ منتج كيميائيّ (scout-12): يستخرج
  رموز الأعراض من نصّ المزارع ويستدعي مالك التشخيص الوحيد، المنصّة ``POST /api/v1/diagnose``
  (قواعد أعراض شفّافة، غير مُعايَرة). الردّ مرشّحون + خطوة تأكيد، بلا مادّة ولا جرعة.
  لا VLM ولا LLM في هذا المسار.
- مسار النصيحة العامّة يدعم وصلاً **اختياريّاً** بخدمة local-ai-rag (LLM محليّ + RAG)
  خلف علم البيئة LOCAL_AI_RAG_URL. إجابة النموذج لا تُنشَر نصّاً حرّاً (airuntime-9): تمرّ على
  مُدقِّق الادعاءات المهيكلة المشترك ``shared.ai.structured_advisory`` مقابل لقطة المالك
  القانونيّة الحاليّة. ما لا يجتازه (نثر، اسم مبيد، جرعة) يُحجَب ويُجيب القالب بصدق
  (source="template"، generation_status="suppressed_unvalidated_output").
"""

import logging
import os
import re
import unicodedata
from typing import Any

import httpx
from mcp_client import MCPClient

from shared.ai.structured_advisory import AdvisoryRejected, preview_advisory

logger = logging.getLogger("supervisor.advisory")

# علم اختياريّ: عنوان خدمة local-ai-rag. غيابه ⇒ لا وصل، قوالب فقط (السلوك السابق).
LOCAL_AI_RAG_URL = os.getenv("LOCAL_AI_RAG_URL", "").strip()
# مهلة قصيرة: الوصل fail-soft — لا نُعطّل المستشار بانتظار LLM بطيء أو متعطّل.
RAG_TIMEOUT_S = float(os.getenv("LOCAL_AI_RAG_TIMEOUT_S", "8.0"))
# مهلة استدعاء تشخيص المنصّة؛ تجاوزها يرفع httpx.TimeoutException فيتدهور المسار بصدق.
DIAGNOSE_TIMEOUT_S = float(os.getenv("PLATFORM_DIAGNOSE_TIMEOUT_S", "10.0"))
# نصّ الرفض الصريح الذي تُرجِعه خدمة RAG حين لا تكفي قاعدة المعرفة — نعامله ارتداداً
# للقوالب (لا نُقدّم رفضاً مبهماً للمزارع حين لدينا قالب مفيد).
_RAG_NO_KNOWLEDGE_AR = "لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال."
# Closing line of every fixed template: why it states no figure, and whom to ask.
_NO_REVIEWED_FIGURES_AR = (
    "لا تُذكَر هنا أرقام أو مواعيد أو جرعات لعدم توفّر مصدر مُراجَع لها في هذه القناة؛ "
    "راجِع مهندساً زراعيّاً مختصّاً لتحديدها لحقلك."
)


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
                f"{LOCAL_AI_RAG_URL.rstrip('/')}/v1/query",
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
    # الرفض يُعرَف ولو اقتُبِس أو جُرِّد من التشكيل: المساواة الحرفيّة كانت تُمرِّر رفضاً
    # مُعاد الصياغة إجابةً «مؤرَّضة» موسومة llm-rag ومستشهِدةً بمقاطع لم تدعمه.
    if not answer or _is_refusal_answer(answer):
        return None
    return data


_ALEF_FORMS = str.maketrans({"\u0623": "\u0627", "\u0625": "\u0627", "\u0622": "\u0627"})


def _normalize_refusal_text(text: str) -> str:
    """local-ai-rag's refusal normalisation (quotes, diacritics, tatweel), plus alef forms.

    A model that writes «للاجابة» for «للإجابة» is still refusing; hamza-bearing alef
    is folded to bare alef so the spelling variant is not read as a grounded answer.
    """
    return "".join(
        ch
        for ch in (text or "").translate(_ALEF_FORMS)
        if not ch.isspace()
        and ch not in "«»\"'“”.,،:؛!"
        and not ("\u064b" <= ch <= "\u0652")
        and ch != "\u0640"
    )


def _is_refusal_answer(answer: str) -> bool:
    """Did local-ai-rag return its refusal, possibly quoted or without diacritics?"""
    refusal = _normalize_refusal_text(_RAG_NO_KNOWLEDGE_AR)
    return bool(refusal) and refusal in _normalize_refusal_text(answer)


def _source_labels(sources: Any) -> list[str]:
    """RAG sources are dicts ({source, page, snippet}); the API exposes string labels."""
    labels: list[str] = []
    for item in sources if isinstance(sources, list) else []:
        if isinstance(item, dict):
            item = item.get("title") or item.get("source_uri") or item.get("source")
        if isinstance(item, str) and item.strip() and item.strip() not in labels:
            labels.append(item.strip())
    return labels


# ── التحقّق من إجابة النموذج (airuntime-9) ─────────────────────────────────────────
async def _validated_generation(
    answer: str, *, tenant_id: str, field_id: str | None, context: dict[str, Any]
) -> dict[str, Any] | None:
    """Run a model answer through the shared structured-claims checker; None = withhold.

    The checker accepts only a ``sahool.structured_advisory.v1`` document whose numeric
    claims equal the owner's CURRENT canonical snapshot, and rebuilds the published text
    from that snapshot (never from model prose). The snapshot must be the server-fetched
    ``canonical_field_state`` in the bound field state; the route strips any body-supplied
    ``field_state``. No owner candidates are offered here, so the model cannot select an
    action. Anything else fails closed: prose, an unknown claim, a stale snapshot, a
    missing field, or a checker error.
    """
    field_state = context.get("field_state") if isinstance(context, dict) else None
    state = field_state.get("canonical_field_state") if isinstance(field_state, dict) else None
    if not field_id or not tenant_id or not isinstance(state, dict):
        return None
    try:
        preview = await preview_advisory(
            answer, tenant_id=tenant_id, field_id=field_id, state=state, candidates=[]
        )
    except AdvisoryRejected:
        return None
    except Exception:  # noqa: BLE001 — a checker fault never releases unchecked text
        logger.warning("advisory: structured-claims checker failed; output withheld")
        return None
    if (
        not isinstance(preview, dict)
        or preview.get("executes_action") is not False
        or preview.get("candidate_previews")
        or not preview.get("claims")
        or not isinstance(preview.get("answer_ar"), str)
        or not preview["answer_ar"].strip()
    ):
        return None
    return preview


# ── التشخيص عبر مالكه (scout-12) ──────────────────────────────────────────────────
# Free-text cues -> the platform's symptom codes (api/disease_diagnosis.list_symptoms).
# Codes only: this table names no pest, disease or product. A unit test pins every code
# to the platform catalog so the two cannot drift apart silently.
_SYMPTOM_CUES: dict[str, tuple[str, ...]] = {
    "insects_on_leaves": ("حشره", "حشرات", "insect", "aphid", "bug"),
    "sticky_honeydew": ("ندوه عسليه", "عسليه", "لزج", "honeydew", "sticky"),
    "curled_leaves": ("ملتفه", "التفاف", "ملتويه", "curled"),
    "ants_present": ("نمل", "ants"),
    "orange_pustules": ("بثور", "pustule"),
    "powder_on_touch": ("مسحوق عند اللمس",),
    "orange_powder_underside": ("مسحوق برتقالي",),
    "yellow_spots_upperside": ("بقع صفراء",),
    "leaf_yellowing": ("اصفرار", "اوراق صفراء", "yellowing", "yellow leaves"),
    "general_yellowing": ("اصفرار عام",),
    "interveinal_chlorosis": ("بين العروق", "interveinal"),
    "young_leaves_affected": ("الاوراق الحديثه", "اوراق حديثه", "young leaves"),
    "old_leaves_affected": ("الاوراق القديمه", "اوراق قديمه", "old leaves"),
    "stunted_growth": ("تقزم", "متقزم", "stunted"),
    "small_leaves": ("اوراق صغيره", "small leaves"),
    "short_internodes": ("سلاميات قصيره",),
    "leaf_drop": ("تساقط", "leaf drop"),
    "wilting": ("ذبول", "ذابل", "wilt"),
    "leaf_curl": ("تجعد", "leaf curl"),
    "dry_soil": ("تربه جافه", "dry soil"),
    "midday_drooping": ("الظهيره",),
    "leaf_tip_burn": ("احتراق اطراف", "حرق اطراف", "tip burn"),
    "white_soil_crust": ("قشره بيضاء", "salt crust"),
    "alkaline_soil": ("تربه قلويه", "alkaline"),
}

# Crop words -> the rule keys the platform matches (it also resolves aliases itself).
_CROP_WORDS: dict[str, str] = {
    "قمح": "wheat",
    "wheat": "wheat",
    "شعير": "barley",
    "barley": "barley",
    "بن": "coffee",
    "قهوه": "coffee",
    "coffee": "coffee",
    "قات": "qat",
    "qat": "qat",
    "حمضيات": "citrus",
    "citrus": "citrus",
}
_CLITICS = ("وال", "بال", "فال", "كال", "لل", "ال")


def _fold(text: str) -> str:
    """Lower-case, NFKC, no diacritics/tatweel, alef/ya/ta-marbuta folded."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\u0640\u064b-\u065f\u0670]", "", text)
    return text.translate(str.maketrans("أإآٱىة", "اااايه"))


def _cue_in(cue: str, folded: str) -> bool:
    """Arabic cues match inside clitic-prefixed words; Latin cues need a word start
    ("ants" must not fire inside "plants", nor "bug" inside "debug")."""
    if cue.isascii():
        return re.search(r"(?<![a-z])" + re.escape(cue), folded) is not None
    return cue in folded


def _extract_symptoms(query: str) -> list[str]:
    folded = _fold(query)
    return sorted(
        code for code, cues in _SYMPTOM_CUES.items() if any(_cue_in(c, folded) for c in cues)
    )


def _extract_crop(query: str, context: dict[str, Any]) -> str:
    for token in re.findall(r"\w+", _fold(query)):
        for clitic in _CLITICS:
            if token.startswith(clitic) and len(token) - len(clitic) >= 2:
                token = token[len(clitic) :]
                break
        if token in _CROP_WORDS:
            return _CROP_WORDS[token]
    crop = context.get("crop") if isinstance(context, dict) else None
    return crop.strip()[:64] if isinstance(crop, str) else ""


def _diagnosis_reply(intent: str, payload: Any) -> dict[str, Any]:
    """Whitelist the owner's fields; product names, doses and free keys never pass."""
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise httpx.DecodingError("diagnose: unexpected response shape")
    candidates = []
    for item in payload["candidates"][:3]:
        if not isinstance(item, dict) or not isinstance(item.get("name_ar"), str):
            continue
        score = item.get("score", item.get("confidence"))
        candidates.append(
            {
                "issue_code": str(item.get("issue_code") or "")[:64],
                "name_ar": item["name_ar"][:80],
                "category": str(item.get("category") or "")[:32],
                "score": score if isinstance(score, (int, float)) else None,
                "score_semantics": "rule_match",
                "is_calibrated": False,
            }
        )
    next_step = payload.get("next_step_ar")
    lines = ["🔎 **تشخيص أوّلي بقواعد الأعراض (ليس قاطعاً):**"]
    for c in candidates:
        pct = f" — درجة تطابق أعراض {c['score']:.0%} (غير مُعايَرة)" if c["score"] else ""
        lines.append(f"• {c['name_ar']}{pct}")
    if not candidates:
        lines.append("• لا تطابق واضح مع الأعراض الموصوفة.")
    if isinstance(next_step, str) and next_step.strip():
        lines.append(f"الخطوة التالية: {next_step.strip()[:400]}")
    for note in (payload.get("advisory_notes_ar") or [])[:3]:
        if isinstance(note, str) and note.strip():
            lines.append(f"ملاحظة: {note.strip()[:200]}")
    lines.append("لا تُستخدَم أيّ مادّة مكافحة قبل تأكيد التشخيص ووصفة من مهندس زراعيّ مختصّ.")
    return {
        "type": "diagnosis_preliminary",
        "intent": intent,
        "response": "\n".join(lines),
        "source": "platform-diagnose",
        "calibrated": False,
        # Information only: no product, no dose, nothing to execute or govern.
        "actionable": False,
        "structured": {
            "crop": payload.get("crop") if isinstance(payload.get("crop"), str) else "",
            "observed_symptoms": [
                s for s in payload.get("observed_symptoms") or [] if isinstance(s, str)
            ],
            "candidates": candidates,
            "producer": "sahool-platform:/api/v1/diagnose",
        },
        "sources": ["SAHOOL symptom rules (/api/v1/diagnose)"],
    }


async def _diagnose_via_platform(
    intent: str, query: str, field_id: str | None, context: dict[str, Any]
) -> dict[str, Any]:
    """Pest/disease questions go to the platform's diagnosis owner, never a local table."""
    unknown_type = "pest_unknown" if intent == "pest_id" else "disease_unknown"
    symptoms = _extract_symptoms(query)
    if not symptoms:
        return {
            "type": unknown_type,
            "response": (
                "لم أتعرّف على أعراض محدّدة في الوصف. صف ما تراه (مثل: حشرات على الأوراق، "
                "ندوة عسليّة، اصفرار، بثور برتقاليّة، ذبول) أو أنشئ نقطة استكشاف بصورة واضحة."
            ),
            "source": "template",
            "calibrated": False,
            "sources": [],
        }
    bearer = context.get("_platform_bearer")
    if not isinstance(bearer, str) or not bearer.strip():
        return {
            "type": "unavailable",
            "response": "تعذّر التشخيص الآن: يلزم طلب مُصادَق لاستدعاء خدمة التشخيص.",
            "source": "template",
            "calibrated": False,
            "structured": {"reason": "platform_bearer_required"},
            "sources": [],
        }
    platform = os.getenv(
        "PLATFORM_SERVICE_URL", os.getenv("PLATFORM_URL", "http://sahool-platform:8000")
    ).rstrip("/")
    body: dict[str, Any] = {"crop": _extract_crop(query, context), "symptoms": symptoms}
    if field_id:
        body["field_id"] = str(field_id)
    # Transport/HTTP errors propagate: the route turns them into its degraded reply
    # (confidence 0), never into a guessed diagnosis or a product name.
    async with httpx.AsyncClient(timeout=DIAGNOSE_TIMEOUT_S) as client:
        resp = await client.post(
            f"{platform}/api/v1/diagnose",
            json=body,
            headers={"Authorization": f"Bearer {bearer}"},
        )
    resp.raise_for_status()
    return _diagnosis_reply(intent, resp.json())


class AdvisorySkill:
    """
    Domain skill for agricultural advisory and pest/disease identification.

    التنفيذ الفعليّ: الآفات/الأمراض عبر تشخيص المنصّة بقواعد الأعراض (/api/v1/diagnose)
    بلا أسماء منتجات، والنصيحة العامّة بقوالب مع وصل اختياريّ بـlocal-ai-rag لا يُنشَر
    منه إلّا ما اجتاز مُدقِّق الادعاءات المهيكلة. لا يوجد تكامل VLM.
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

        if intent in {"pest_id", "disease_id"}:
            # No local pest/disease table and no product names: the platform's
            # symptom-rule diagnosis (/api/v1/diagnose) is the single owner.
            return await _diagnose_via_platform(intent, query, field_id, context or {})

        elif intent == "general_advice":
            # وصل اختياريّ بـlocal-ai-rag (LLM محليّ + RAG) خلف LOCAL_AI_RAG_URL.
            # إن غاب العلم أو فشل الاستدعاء ⇒ ارتداد للقوالب أدناه (السلوك السابق).
            token = getattr(self.mcp, "token", None)
            rag_data = await _query_local_rag(query, token)
            rag_ok = rag_data is not None
            source = advisory_source(LOCAL_AI_RAG_URL or None, rag_ok)

            generation_status = "attempted_failed" if LOCAL_AI_RAG_URL else "not_attempted"
            if source == "llm-rag":
                # Free model prose is never published as advice (airuntime-9): it goes
                # through the shared structured-claims checker first. Only an answer the
                # checker reconstructs from the owner's current canonical snapshot is
                # surfaced; anything else (prose, a pesticide name, a dose) is withheld
                # and the honest template fallback below answers instead.
                validated = await _validated_generation(
                    rag_data.get("answer", ""),
                    tenant_id=tenant_id,
                    field_id=field_id,
                    context=context or {},
                )
                if validated is not None:
                    return {
                        "type": "general_advice",
                        "response": validated["answer_ar"],
                        "source": "llm-rag",
                        "calibrated": False,
                        "ai_generated": True,
                        "model": rag_data.get("model"),
                        "generation_status": "validated_structured_facts",
                        "claim_validation": validated["validation_scope"],
                        "sources": _source_labels(rag_data.get("sources")),
                    }
                generation_status = "suppressed_unvalidated_output"
                logger.info("advisory: withheld unvalidated local-ai-rag output")

            # ── ارتداد القوالب (المصدر الافتراضيّ الصادق) ──────────────────────────
            # No figure, month, count or time of day is stated here: a fixed template cites
            # no reviewed source (`sources == []`). Those slots stay empty until an agronomist
            # supplies reviewed content; the text says so and refers the farmer to one.
            advice_templates = {
                "زراعة قمح": "🌾 **زراعة القمح في اليمن:**\n• الصنف: الحمداني أو البيضاني\n• التسميد: حسب تحليل تربة معتمد ووصفة تسميد مراجعة للحقل (لا جرعة عامة)",
                "ري ذكي": "💧 **الري الذكي:**\n• استخدم مقياس رطوبة التربة\n• تجنب الري عند توقع أمطار",
                "تسميد": "🧪 **التسميد المتوازن:**\n• حلل التربة أولاً\n• NPK حسب المحصول والمرحلة\n• لا تفرط في النيتروجين — يؤخر النضج\n• استخدم السماد العضوي مع الكيميائي\n• التسميد الجوري أفضل من البث",
                "حصاد": "🚜 **نصائح الحصاد:**\n• راقب رطوبة الحبوب\n• تخزين في صوامع نظيفة\n• راقب درجة الحرارة في المخزن",
            }

            for keyword, template in advice_templates.items():
                if keyword in query:
                    return {
                        "type": "general_advice",
                        "response": f"{template}\n{_NO_REVIEWED_FIGURES_AR}",
                        "source": "template",
                        "calibrated": False,
                        "generation_status": generation_status,
                        # A fixed template is not drawn from a knowledge base or FAO guidance.
                        "sources": [],
                    }

            return {
                "type": "general_advice",
                "response": (
                    "شكراً على سؤالك. أنا أعمل على توسيع قاعدة المعرفة. للاستفسارات المحددة، "
                    f"يرجى التواصل مع فريق SAHOOL.\n{_NO_REVIEWED_FIGURES_AR}"
                ),
                "source": "template",
                "calibrated": False,
                "generation_status": generation_status,
                "sources": [],
            }

        else:
            return {"type": "error", "response": f"نوعية استعلام استشاري غير معروفة: {intent}"}
