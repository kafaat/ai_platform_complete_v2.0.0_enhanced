"""اختبار وحدويّ: اختيار/وسم مصدر المستشار (llm-rag مقابل template).

يثبت أنّ منطق إغلاق الفجوة «الوعد غير المحقَّق» في AI-Advisor صادق:
- advisory_source (دالّة نقيّة): rag مضبوط وناجح ⇒ "llm-rag"؛ غائب أو فاشل ⇒ "template".
- مسار general_advice في execute يرتدّ للقوالب بصدق (source="template", calibrated=False)
  حين لا وصل (LOCAL_AI_RAG_URL غائب) — أي السلوك السابق محفوظ.
- إجابة RAG نثريّة تُحجَب (مُدقِّق الادعاءات المهيكلة يرفضها) ⇒ القالب يُجيب (airuntime-9).
- مسارات pest_id/disease_id لا تسمّي منتجاً: تشخيص المنصّة أو ردّ صريح بلا تشخيص (scout-12).

نواة نقيّة بلا خدمات؛ لا اتّصال شبكيّ حيّ.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
SUPERVISOR = os.path.join(ROOT, "services/supervisor-agent")
SKILL_PATH = os.path.join(SUPERVISOR, "skills/advisory_skill.py")


@pytest.fixture()
def adv_mod(monkeypatch):
    """يحمّل advisory_skill.py باسم فريد عبر importlib مع LOCAL_AI_RAG_URL غائب.

    إزالة العلم قبل الاستيراد ⇒ ثابت الوحدة LOCAL_AI_RAG_URL == "" (السلوك السابق).
    httpx/fastapi مطلوبان للاستيراد (لكن لا استدعاء حيّ هنا)؛ بيئة الوحدة الخفيفة في CI
    لا تثبّت fastapi ⇒ نتخطّى بدل الفشل (يُغطّيه job المنصّة الأثقل)."""
    pytest.importorskip("httpx")
    pytest.importorskip("fastapi")
    monkeypatch.delenv("LOCAL_AI_RAG_URL", raising=False)
    added = SUPERVISOR not in sys.path
    if added:
        sys.path.insert(0, SUPERVISOR)
    try:
        spec = importlib.util.spec_from_file_location("sahool_advisory_skill_test", SKILL_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if added and SUPERVISOR in sys.path:
            sys.path.remove(SUPERVISOR)


# ── الدالّة النقيّة advisory_source ──────────────────────────────────────────────
def test_source_llm_rag_when_url_set_and_ok(adv_mod):
    assert adv_mod.advisory_source("http://local-ai-rag:8000", True) == "llm-rag"


def test_source_template_when_url_set_but_failed(adv_mod):
    # وصل مفعّل لكن الاستدعاء فشل/ارتدّ ⇒ لا ندّعي ذكاءً غير محقَّق.
    assert adv_mod.advisory_source("http://local-ai-rag:8000", False) == "template"


def test_source_template_when_url_absent(adv_mod):
    # علم غائب (None أو فارغ) ⇒ template حتّى لو زعم rag_ok.
    assert adv_mod.advisory_source(None, True) == "template"
    assert adv_mod.advisory_source("", True) == "template"


# ── ارتداد القوالب في execute (لا وصل) ───────────────────────────────────────────
class _StubMCP:
    token = "stub-token"


def _skill(adv_mod):
    return adv_mod.AdvisorySkill(_StubMCP())


async def test_general_advice_falls_back_to_template(adv_mod):
    # LOCAL_AI_RAG_URL غائب ⇒ القالب يعمل كرجوع، موسوم template/calibrated=False.
    out = await _skill(adv_mod).execute(intent="general_advice", query="ري ذكي")
    assert out["source"] == "template"
    assert out["calibrated"] is False
    assert "الري الذكي" in out["response"]


async def test_general_advice_withholds_unchecked_llm_rag_prose(adv_mod, monkeypatch):
    """airuntime-9: a successful RAG call no longer publishes the model's prose.

    The answer goes through the shared structured-claims checker; free prose fails it,
    so the honest template answers and the withheld generation is named.
    """
    monkeypatch.setattr(adv_mod, "LOCAL_AI_RAG_URL", "http://local-ai-rag:8000")

    async def _fake_rag(question, token):
        return {
            "answer": "إجابة مُؤرَّضة من النموذج المحليّ",
            "model": "qwen3:32b",
            "sources": [{"source": "kb.pdf"}],
        }

    monkeypatch.setattr(adv_mod, "_query_local_rag", _fake_rag)
    out = await _skill(adv_mod).execute(intent="general_advice", query="أيّ صنف قمح؟")
    assert out["source"] == "template", f"unchecked prose labelled {out['source']}"
    assert out["calibrated"] is False, "templates are never calibrated"
    assert out.get("ai_generated") is not True, "withheld output is not presented as AI"
    assert out["generation_status"] == "suppressed_unvalidated_output", out
    assert "إجابة مُؤرَّضة من النموذج المحليّ" not in out["response"], "prose surfaced"
    assert out["sources"] == [], "a template reply cites no retrieved document"


async def test_general_advice_rag_failure_falls_back(adv_mod, monkeypatch):
    # الوصل مفعّل لكن الاستدعاء ارتدّ (None) ⇒ ارتداد صادق للقوالب.
    monkeypatch.setattr(adv_mod, "LOCAL_AI_RAG_URL", "http://local-ai-rag:8000")

    async def _fail_rag(question, token):
        return None

    monkeypatch.setattr(adv_mod, "_query_local_rag", _fail_rag)
    out = await _skill(adv_mod).execute(intent="general_advice", query="تسميد")
    assert out["source"] == "template"
    assert out["calibrated"] is False
    assert "التسميد المتوازن" in out["response"]


# ── الآفات/الأمراض: لا جدول محليّ ولا اسم منتج؛ التشخيص عند المنصّة (scout-12) ─────
async def test_pest_id_without_verified_bearer_is_unavailable_not_a_product(adv_mod):
    out = await _skill(adv_mod).execute(intent="pest_id", query="أوراق صفراء")
    assert out["type"] == "unavailable", f"no caller bearer, got {out['type']}"
    assert out["source"] == "template", "nothing was diagnosed"
    assert out["calibrated"] is False, "no calibrated claim without a diagnosis"
    assert "Mancozeb" not in str(out), "the removed keyword table named Mancozeb here"
    assert out.get("action_type") is None, "no pesticide proposal without a diagnosis"


async def test_disease_id_with_unknown_symptoms_asks_for_detail(adv_mod):
    out = await _skill(adv_mod).execute(intent="disease_id", query="بقع داكنة")
    assert out["type"] == "disease_unknown", f"unexpected type: {out['type']}"
    assert out["source"] == "template", "nothing was diagnosed"
    assert out["calibrated"] is False, "no calibrated claim without a diagnosis"
    assert "Copper" not in str(out), "the removed keyword table named copper here"


# ── Templates cite nothing; a paraphrased model refusal is still a refusal ──────
@pytest.mark.parametrize(
    ("intent", "query"),
    [
        ("pest_id", "أوراق صفراء"),
        ("disease_id", "بودرة بيضاء"),
        ("general_advice", "ري ذكي"),
    ],
)
async def test_keyword_templates_cite_no_source(adv_mod, intent, query):
    """A fixed keyword table is not a pest/disease database, a knowledge base or FAO guidance.

    The fallback used to cite "SAHOOL Pest Database", "Yemen Plant Protection",
    "SAHOOL Disease Database", "SAHOOL Agricultural Knowledge Base" and
    "FAO Yemen Guidelines". None of these exists behind the template, so a farmer
    would read an invented citation as evidence.
    """
    out = await _skill(adv_mod).execute(intent=intent, query=query)
    assert out["source"] == "template"
    assert out["sources"] == []


@pytest.mark.parametrize(
    "answer",
    [
        "لا تتوفر معلومات كافية في قاعدة المعرفة للاجابة على هذا السؤال",
        "«لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال.»",
        "عذراً، لا تتوفّر معلومات كافية في قاعدة المعرفة للإجابة على هذا السؤال.",
    ],
)
def test_a_paraphrased_rag_refusal_is_recognised(adv_mod, answer):
    """Exact equality let a quoted or diacritic-free refusal through as a grounded answer."""
    assert adv_mod._is_refusal_answer(answer)


def test_a_real_answer_is_not_mistaken_for_a_refusal(adv_mod):
    assert not adv_mod._is_refusal_answer("يُزرع القمح في نوفمبر حسب الأمطار.")


async def test_a_paraphrased_refusal_falls_back_instead_of_posing_as_llm_rag(adv_mod, monkeypatch):
    """End to end through _query_local_rag: the refusal must not surface as source=llm-rag."""
    import httpx

    monkeypatch.setattr(adv_mod, "LOCAL_AI_RAG_URL", "http://local-ai-rag:8000")
    refusal = "لا تتوفر معلومات كافية في قاعدة المعرفة للاجابة على هذا السؤال"
    real_client = httpx.AsyncClient

    def transport(request):
        return httpx.Response(
            200, json={"answer": refusal, "model": "llama3.2:3b", "sources": [{"source": "kb.pdf"}]}
        )

    monkeypatch.setattr(
        adv_mod.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw),
    )
    out = await _skill(adv_mod).execute(intent="general_advice", query="سؤال لا تغطيه المعرفة")
    assert out["source"] == "template"
    assert out["sources"] == []
