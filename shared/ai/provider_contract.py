"""العقد القانونيّ الموحَّد لمزوّد الذكاء الاصطناعيّ (V52 — Provider Snapshot Guard).

المنصّة تحمل **نسختين مستقلّتين** من منطق حلّ المزوّد لأنّ الخدمات مُعبَّأة بمعزل
(لا استيراد متبادل وقت التشغيل — "الكود معزول لكلّ خدمة، التهيئة مشتركة"):

- المونوليث:   ``services/sahool-platform/api/ai_provider_config.py``
- الـruntime:  ``services/ai_agronomist/ai_generation.py``

هذا الملفّ هو **المصدر القانونيّ الواحد** للعقد (أسماء المزوّدات، متغيّرات البيئة،
عناوين الأساس، صيغ السلك، مستويات مشاركة البيانات). يفرض الحارس
``tests_v9/test_ai_provider_contract_guard.py`` تطابق النسختين معه — فيُغلِق خطر
«انحراف تهيئة المزوّد» (drift) الذي رصده تدقيق V51.

القاعدة: أيّ تغيير في منطق المزوّد يجب أن يُحدِّث هذا العقد ونسختَي الخدمة معاً، وإلّا
يفشل الحارس في CI.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────
# أسماء المزوّدات: مرادف (lower) ⇒ المعرّف القانونيّ.
# ──────────────────────────────────────────────────────────────────────────
PROVIDER_ALIASES: dict[str, str] = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "cloud": "anthropic",
    "openrouter": "openrouter",
    "router": "openrouter",
    "or": "openrouter",
    "ollama": "local",
    "local": "local",
    "vllm": "vllm",
    "jais": "vllm",
    "jais-natural-farmer": "vllm",
}

# المعرّفات القانونيّة الأربعة. المجهول/الفارغ ⇒ المحلّيّ الآمن (بلا مفاتيح سحابيّة).
CANONICAL_PROVIDERS: tuple[str, ...] = ("local", "vllm", "anthropic", "openrouter")
DEFAULT_PROVIDER = "local"

# المزوّدات «الخارجيّة» (سحابيّة) — تُطبَّق عليها سياسة مشاركة البيانات/التنقيح قبل
# إرسال أيّ سياق حقل. ``local`` (Ollama داخليّ) ليس خارجيّاً.
EXTERNAL_PROVIDERS: tuple[str, ...] = ("anthropic", "openrouter")


def normalize_provider(raw: str | None) -> str:
    """يطبّع اسم المزوّد إلى معرّف قانونيّ. fail-safe ⇒ ``local``.

    مطابق منطقيّاً لـ``_normalize_provider`` في نسختَي الخدمة (يفرضه الحارس)."""
    return PROVIDER_ALIASES.get((raw or "").strip().lower(), DEFAULT_PROVIDER)


# ──────────────────────────────────────────────────────────────────────────
# ثوابت عقد الشبكة المشتركة (يجب أن تطابق نسختَي الخدمة حرفيّاً).
# ──────────────────────────────────────────────────────────────────────────
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_OLLAMA_BASE_URL = "http://ollama:11434"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_VLLM_BASE_URL = "http://sahool-vllm-jais:8000/v1"
DEFAULT_VLLM_MODEL = "jais-natural-farmer"

# صيغة السلك ولاحقة نقطة النهاية لكلّ مزوّد قانونيّ.
WIRE_FORMAT: dict[str, str] = {
    "local": "messages",
    "vllm": "openai_chat",
    "anthropic": "messages",
    "openrouter": "openai_chat",
}
ENDPOINT_SUFFIX: dict[str, str] = {
    "messages": "/v1/messages",
    "openai_chat": "/chat/completions",
}

# ──────────────────────────────────────────────────────────────────────────
# أسماء متغيّرات البيئة (التهيئة مشتركة عبر ‎.env‎ بين الخدمات المعزولة).
# ──────────────────────────────────────────────────────────────────────────
ENV_PROVIDER = "AI_PROVIDER"
ENV_MODEL = "AI_MODEL"
ENV_MODELS_CATALOG = "AI_MODELS"
ENV_GENERATION_ENABLED = "AI_GENERATION_ENABLED"
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_VLLM_BASE_URL = "VLLM_BASE_URL"
ENV_VLLM_API_KEY = "VLLM_API_KEY"
ENV_VLLM_MODEL = "VLLM_MODEL"
# المفاتيح السرّيّة تُقرأ من البيئة خادميّاً فقط — لا تصل الكود العميل ولا الواجهة.
SECRET_ENV_NAMES: tuple[str, ...] = (
    ENV_OPENROUTER_API_KEY,
    ENV_ANTHROPIC_API_KEY,
    ENV_VLLM_API_KEY,
)

# ──────────────────────────────────────────────────────────────────────────
# مستويات مشاركة البيانات (حوكمة V52) — كم من سياق الحقل يجوز أن يغادر حدّ المستأجِر.
# ──────────────────────────────────────────────────────────────────────────
DATA_SHARING_LOCAL_ONLY = "local_only"
DATA_SHARING_REDACTED_EXTERNAL = "redacted_external"
DATA_SHARING_FULL_EXTERNAL = "full_external"
DATA_SHARING_LEVELS: tuple[str, ...] = (
    DATA_SHARING_LOCAL_ONLY,
    DATA_SHARING_REDACTED_EXTERNAL,
    DATA_SHARING_FULL_EXTERNAL,
)
# الأكثر تحفّظاً افتراضيّاً: لا تُشارَك بيانات الحقل خارجيّاً حتى يختار المستأجِر صراحةً.
DEFAULT_DATA_SHARING_LEVEL = DATA_SHARING_LOCAL_ONLY

# ──────────────────────────────────────────────────────────────────────────
# كتالوج النماذج الافتراضيّ لكلّ مزوّد حين لا يُضبَط ``AI_MODELS`` في البيئة.
# هذا هو **المصدر القانونيّ الواحد** للكتالوج الافتراضيّ — يفرض الحارس تطابُقه مع
# نسختَي الخدمة (يُغلِق خطر انحراف كتالوج النماذج بين الواجهة والـruntime).
# ──────────────────────────────────────────────────────────────────────────
DEFAULT_CATALOG: dict[str, list[tuple[str, str]]] = {
    "openrouter": [
        ("deepseek/deepseek-chat", "DeepSeek"),
        ("anthropic/claude-sonnet-4.6", "Claude Sonnet"),
        ("google/gemini-3-pro", "Gemini 3 Pro"),
    ],
    "local": [
        ("qwen3", "Qwen3 (محلّيّ)"),
        ("qwen3:32b", "Qwen3 32B (محلّيّ)"),
    ],
    "vllm": [("jais-natural-farmer", "Jais Natural Farmer (Solshine / vLLM)")],
}
