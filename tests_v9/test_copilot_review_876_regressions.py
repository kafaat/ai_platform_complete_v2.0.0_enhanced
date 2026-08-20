"""أربعة عيوب أمسكها مراجعٌ آليّ على #876 — كلٌّ منها مُثبَّتٌ باختبارٍ يُكذِّبه.

المراجعة وحدها لا تمنع العودة: العيب الذي يُصلَح بلا حارس يعود في أوّل إعادة إرساء —
وهو الدرس المقيس ثلاث مرّات في هذه السلسلة نفسها (وسمُ Ollama في خريطة الخدمات).
فكلُّ إصلاحٍ هنا يحمل تأكيداً يحمرّ إن نُقِض.

والأربعة **عيوبُ عقدٍ لا أسلوب**: سلوكٌ يخالف ما يَعِد به التوقيع أو النصّ المُرسَل.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(relpath: str, name: str):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / relpath))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── ① الجذر المُطبَّع: `…/v1` + `/v1` = نقطةٌ لا وجود لها ──────────────────────
def _resolve_local(monkeypatch, base_url: str):
    if str(ROOT / "services/sahool-platform") not in sys.path:
        sys.path.insert(0, str(ROOT / "services/sahool-platform"))
    from api import ai_provider_config as M

    monkeypatch.setenv("OLLAMA_BASE_URL", base_url)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return M.resolve_ai_provider()


def test_a_base_url_already_ending_in_v1_is_not_doubled(monkeypatch):
    """`OLLAMA_BASE_URL` متغيّر بيئة، وضبطُه على نقطة OpenAI كاملة عادةٌ شائعة.

    وبلا تطبيع يصير المسار `…/v1/v1/chat/completions` — 404 لا يسمّي سببه، على
    إعدادٍ يبدو صحيحاً لقارئه.
    """
    cfg = _resolve_local(monkeypatch, "http://sahool-ollama:11434/v1")
    assert cfg.base_url == "http://sahool-ollama:11434/v1", cfg.base_url
    assert "/v1/v1" not in cfg.base_url


def test_a_bare_root_still_gets_the_v1_suffix(monkeypatch):
    """التطبيع لا يُفقِد اللاحقة عمّن لم يكتبها — وإلّا عالجنا حالةً وكسرنا الشائعة."""
    cfg = _resolve_local(monkeypatch, "http://sahool-ollama:11434")
    assert cfg.base_url == "http://sahool-ollama:11434/v1", cfg.base_url


# ── ② خطأُ مُدخَلٍ يُسمّى: `float(None)` تُعطي TypeError عارياً ────────────────
def test_a_position_missing_lat_or_lon_raises_a_named_value_error():
    m = _load("shared/precision_agriculture/pail_om_edge.py", "r876_pail")
    for bad in ({"lon": 10.0}, {"lat": 20.0}, {"lat": None, "lon": 10.0}):
        with pytest.raises(ValueError) as ei:
            m.project_observation(
                observation_id="obs-1",
                property_code="soil_moisture",
                feature_of_interest="field-1",
                observed_at="2026-08-20T00:00:00Z",
                source_ref="sensor-1",
                value=1.0,
                position=bad,
            )
        assert "position missing" in str(ei.value), str(ei.value)


def test_a_valid_position_still_projects():
    """الحارس يمنع الغياب ولا يمنع المسار السعيد."""
    m = _load("shared/precision_agriculture/pail_om_edge.py", "r876_pail_ok")
    out = m.project_observation(
        observation_id="obs-2",
        property_code="soil_moisture",
        feature_of_interest="field-1",
        observed_at="2026-08-20T00:00:00Z",
        source_ref="sensor-1",
        value=1.0,
        position={"lat": 24.7, "lon": 46.7},
    )
    assert out.observation["position"] == {"lat": 24.7, "lon": 46.7}


# ── ③ القاموس الفارغ تمثيلٌ صريح، لا طلبٌ للافتراضيّ ──────────────────────────
def test_an_explicitly_empty_capability_map_is_honoured_not_replaced():
    """التوقيع `dict | None`: `None` تعني «الافتراضيّ»، و`{}` تعني «لا شيء».

    و`caps = capabilities or DEFAULT` تخلط المعنيين فتُرجِع قدراتٍ لم تُطلَب — وهو
    فرقٌ يهمّ في إسقاطٍ يصف ما **يستطيعه** جهاز.
    """
    m = _load("shared/iot_execution_runtime.py", "r876_iot")
    empty = m.project_thing_model(device_model_id="dev-1", capabilities={})
    default = m.project_thing_model(device_model_id="dev-1")
    assert empty["functions"] == [], empty["functions"]
    assert default["functions"], "الافتراضيّ ما يزال يُعطي قدرات عند `None`"


# ── ④ فحصُ الدخان يقيس العقد لا مجرّد «عاد شيء» ───────────────────────────────
def _probe_module():
    return _load("scripts/ci/ollama_runtime_probe.py", "r876_probe")


def _run_probe(monkeypatch, chat_content: str):
    m = _probe_module()

    def fake_request(base_url, path, *, payload=None, timeout_s=20.0):
        if path == "/api/version":
            return {"version": m.DEFAULT_EXPECTED_VERSION}
        if path == "/v1/models":
            return {"data": [{"id": m.DEFAULT_CHAT_MODEL}, {"id": m.DEFAULT_EMBED_MODEL}]}
        if path == "/api/embeddings":
            return {"embedding": [0.1, 0.2]}
        if path == "/v1/chat/completions":
            return {"choices": [{"message": {"content": chat_content}}]}
        raise AssertionError(path)

    monkeypatch.setattr(m, "_request_json", fake_request)
    checks, _ = m.probe(
        base_url="http://sahool-ollama:11434",
        expected_version=m.DEFAULT_EXPECTED_VERSION,
        chat_model=m.DEFAULT_CHAT_MODEL,
        embed_model=m.DEFAULT_EMBED_MODEL,
        smoke=True,
        timeout_s=1.0,
    )
    return next(c for c in checks if c.name == "chat_smoke")


def test_chat_smoke_rejects_a_reply_that_ignores_the_contract(monkeypatch):
    """الطلب يقول «Reply with exactly: SAHOOL_OK» — فردٌّ آخر ليس نجاحاً.

    قبولُ أيّ نصٍّ غير فارغ يجعل الفحص يقيس «أنّ الخدمة ردّت» لا «أنّ الاستدلال
    يعمل»، فيخضرّ على نموذجٍ يهذي.
    """
    assert _run_probe(monkeypatch, "I'm sorry, I can't do that.").ok is False
    assert _run_probe(monkeypatch, "").ok is False


def test_chat_smoke_tolerates_harmless_decoration(monkeypatch):
    """التثبيت الحرفيّ التامّ يجعله هشّاً أمام نقطةٍ زائدة — والتطبيع يحفظ الصرامة."""
    for reply in ("SAHOOL_OK", " SAHOOL_OK ", "SAHOOL_OK.", "sahool_ok"):
        assert _run_probe(monkeypatch, reply).ok is True, reply


# ── ⑤ الادّعاء الخامس: قفلٌ حول ترطيب الفهرس — **غير قائم اليوم، ويصير قائماً بتحويلٍ واحد** ──
def test_the_sparse_index_callers_stay_async_which_is_what_makes_a_lock_unnecessary():
    """المراجع اقترح قفلاً حول `_ensure_sparse_index` خوفاً من تسابق طلبين.

    **ولا تسابق اليوم، مقيساً على الشيفرة:** الدالّة متزامنة تماماً، ولا `await`
    داخلها، وتُستدعى استدعاءً مباشراً من نقطتين `async def`. وفي حلقة asyncio ذات
    الخيط الواحد يجري النداء المتزامن إلى تمامه بلا نقطة تسليم — فلا تتداخل
    مُعاملتان داخله. وتعدّد عمّال uvicorn عمليّاتٌ منفصلة لكلٍّ منها متغيّراتها،
    فالقفل داخل العمليّة لا يصفها أصلاً.

    **لكنّ الأمان مشروطٌ بخاصّيّةٍ واحدة قد تُنقَض بصمت:** لو حُوِّلت إحدى النقطتين
    إلى `def` متزامنة، لأجراها FastAPI في مجمَّع خيوط — فيصير التسابق **حقيقيّاً**
    على `_sparse_ready`/`_sparse_report`، ويتحقّق وصفُ المراجع حرفيّاً.

    فبدل قفلٍ يعالج خطراً غير قائم، يُثبَّت الشرط الذي ينفيه. وإن أُريد التحويل
    لاحقاً، يحمرّ هذا الاختبار فيُقرأ القفل شرطاً لا تحسيناً.
    """
    text = (ROOT / "services/rag-retrieval/main.py").read_text(encoding="utf-8")
    assert "def _ensure_sparse_index(" in text and "async def _ensure_sparse_index(" not in text
    body_start = text.index("def _ensure_sparse_index(")
    body_end = text.index("\nclass ChunkIn", body_start)
    assert "await" not in text[body_start:body_end], (
        "نقطةُ تسليمٍ داخل الترطيب تجعل التداخل ممكناً — يلزم قفلٌ عندئذٍ"
    )
    for endpoint in ("readyz", "search"):
        assert f"async def {endpoint}(" in text, (
            f"`{endpoint}` لم تعد `async def` ⇒ يُجريها FastAPI في مجمَّع خيوط، "
            "فيصير التسابق على حالة الفهرس حقيقيّاً ويلزم قفلٌ حول إعادة البناء"
        )


def test_the_prompt_and_the_expected_token_share_one_source():
    """نسختان من الرمز تنحرفان: يُرسَل واحد ويُقارَن آخر فيخضرّ الفحص أبداً أو يحمرّ أبداً."""
    text = (ROOT / "scripts/ci/ollama_runtime_probe.py").read_text(encoding="utf-8")
    assert 'CHAT_SMOKE_TOKEN = "SAHOOL_OK"' in text
    assert "Reply with exactly: {CHAT_SMOKE_TOKEN}" in text
    assert text.count('"SAHOOL_OK"') == 1, "الرمز يُعرَّف مرّةً واحدة"
