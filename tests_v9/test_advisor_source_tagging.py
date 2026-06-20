"""اختبار وحدويّ: اختيار/وسم مصدر المستشار (llm-rag مقابل template).

يثبت أنّ منطق إغلاق الفجوة «الوعد غير المحقَّق» في AI-Advisor صادق:
- advisory_source (دالّة نقيّة): rag مضبوط وناجح ⇒ "llm-rag"؛ غائب أو فاشل ⇒ "template".
- مسار general_advice في execute يرتدّ للقوالب بصدق (source="template", calibrated=False)
  حين لا وصل (LOCAL_AI_RAG_URL غائب) — أي السلوك السابق محفوظ.
- عند توفّر إجابة RAG (محاكاة دالّة الاستدعاء نقيّاً، بلا HTTP حيّ) ⇒ source="llm-rag".
- مسارات pest_id/disease_id قوالب صريحة (calibrated=False) — لا ادّعاء VLM.

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


async def test_general_advice_uses_llm_rag_when_available(adv_mod, monkeypatch):
    # نحاكي توفّر الوصل والاستدعاء الناجح بلا HTTP حيّ: نضبط العلم ونستبدل الدالّة.
    monkeypatch.setattr(adv_mod, "LOCAL_AI_RAG_URL", "http://local-ai-rag:8000")

    async def _fake_rag(question, token):
        return {
            "answer": "إجابة مُؤرَّضة من النموذج المحليّ",
            "model": "qwen3:32b",
            "sources": [{"source": "kb.pdf"}],
        }

    monkeypatch.setattr(adv_mod, "_query_local_rag", _fake_rag)
    out = await _skill(adv_mod).execute(intent="general_advice", query="أيّ صنف قمح؟")
    assert out["source"] == "llm-rag"
    assert out["calibrated"] is True
    assert out["response"] == "إجابة مُؤرَّضة من النموذج المحليّ"
    assert out["model"] == "qwen3:32b"


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


# ── مسارات القوالب الثابتة موسومة بصدق (لا ادّعاء VLM) ────────────────────────────
async def test_pest_id_is_template_not_calibrated(adv_mod):
    out = await _skill(adv_mod).execute(intent="pest_id", query="أوراق صفراء")
    assert out["type"] == "pest_alert"
    assert out["source"] == "template"
    assert out["calibrated"] is False


async def test_disease_id_is_template_not_calibrated(adv_mod):
    out = await _skill(adv_mod).execute(intent="disease_id", query="بقع داكنة")
    assert out["type"] == "disease_alert"
    assert out["source"] == "template"
    assert out["calibrated"] is False
