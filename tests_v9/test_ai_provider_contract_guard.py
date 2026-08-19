"""حارس عقد مزوّد الذكاء (V52 — Provider Snapshot Guard).

يفرض أنّ النسختين المعزولتين من منطق حلّ المزوّد تبقيان متطابقتين مع العقد القانونيّ
الواحد ``shared/ai/provider_contract.py``:

- المونوليث:  ``services/sahool-platform/api/ai_provider_config.py``
- الـruntime: ``services/ai_agronomist/ai_generation.py``

إن انحرفت أيّ نسخة (اسم مزوّد، عنوان أساس، إصدار ترويسة) يفشل هذا الحارس في CI —
يُغلِق خطر «drift تهيئة المزوّد» الذي رصده تدقيق V51 دون فرض استيراد متبادل وقت التشغيل.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load(rel_path: str, mod_name: str):
    """تحميل وحدة بالمسار المطلق بمعزل (يتجنّب تضارب جذور الاستيراد بين الخدمتين)."""
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    # التسجيل في sys.modules قبل التنفيذ كي يحلّ ``@dataclass`` وحدته بشكل صحيح.
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


CONTRACT = _load("shared/ai/provider_contract.py", "sahool_provider_contract")
GEN = _load("services/ai_agronomist/ai_generation.py", "sahool_ai_generation_under_test")
CFG = _load(
    "services/sahool-platform/api/ai_provider_config.py", "sahool_ai_provider_config_under_test"
)

# عيّنة مدخلات تمثيليّة تغطّي كلّ المرادفات + حالات الحافّة (فراغ/مجهول/أحرف كبيرة).
_INPUTS = [
    "anthropic",
    "claude",
    "cloud",
    "Anthropic",
    "  CLAUDE  ",
    "openrouter",
    "router",
    "vllm",
    "jais",
    "jais-natural-farmer",
    "or",
    "OpenRouter",
    "ollama",
    "local",
    "",
    "none",
    "gpt-4",
    "unknown-provider",
    None,
]


def test_both_resolvers_agree_with_contract():
    """كلّ مدخل يُطبَّع إلى المعرّف نفسه عبر النسختين والعقد."""
    for raw in _INPUTS:
        a = GEN._normalize_provider(raw)
        b = CFG._normalize_provider(raw)
        c = CONTRACT.normalize_provider(raw)
        assert a == b == c, f"provider drift for {raw!r}: gen={a!r} cfg={b!r} contract={c!r}"


def test_network_contract_constants_match():
    """ثوابت عقد الشبكة (الإصدار + عناوين الأساس) متطابقة في النسختين والعقد."""
    for mod in (GEN, CFG):
        assert mod.ANTHROPIC_VERSION == CONTRACT.ANTHROPIC_VERSION
        assert mod.DEFAULT_ANTHROPIC_BASE_URL == CONTRACT.DEFAULT_ANTHROPIC_BASE_URL
        assert mod.DEFAULT_OPENROUTER_BASE_URL == CONTRACT.DEFAULT_OPENROUTER_BASE_URL
        assert mod.DEFAULT_OLLAMA_BASE_URL == CONTRACT.DEFAULT_OLLAMA_BASE_URL
        assert mod.DEFAULT_VLLM_BASE_URL == CONTRACT.DEFAULT_VLLM_BASE_URL
        assert mod.DEFAULT_VLLM_MODEL == CONTRACT.DEFAULT_VLLM_MODEL


def test_canonical_providers_closed_set():
    """مجموعة المزوّدات القانونيّة مغلقة: لا يُنتِج أيّ مدخل معرّفاً خارجها."""
    allowed = set(CONTRACT.CANONICAL_PROVIDERS)
    assert allowed == {"local", "vllm", "anthropic", "openrouter"}
    for raw in _INPUTS:
        assert CONTRACT.normalize_provider(raw) in allowed


def test_data_sharing_levels_contract():
    """مستويات مشاركة البيانات الثلاثة معرَّفة، والافتراضيّ هو الأكثر تحفّظاً."""
    assert CONTRACT.DATA_SHARING_LEVELS == ("local_only", "redacted_external", "full_external")
    assert CONTRACT.DEFAULT_DATA_SHARING_LEVEL == "local_only"


def test_secret_env_names_are_key_suffixed():
    """أسماء المتغيّرات السرّيّة للمزوّد تُقرأ من البيئة فقط (عقد، لا قيَم)."""
    assert CONTRACT.ENV_OPENROUTER_API_KEY == "OPENROUTER_API_KEY"
    assert CONTRACT.ENV_ANTHROPIC_API_KEY == "ANTHROPIC_API_KEY"
    assert CONTRACT.ENV_VLLM_API_KEY == "VLLM_API_KEY"
    assert all(name.endswith("_API_KEY") for name in CONTRACT.SECRET_ENV_NAMES)


def test_default_model_catalog_no_drift():
    """كتالوج النماذج الافتراضيّ متطابق بين العقد ونسختَي الخدمة (يُغلِق خطر انحراف
    كتالوج النماذج بين الواجهة والـruntime)."""
    assert GEN._DEFAULT_CATALOG == CONTRACT.DEFAULT_CATALOG
    assert CFG._DEFAULT_CATALOG == CONTRACT.DEFAULT_CATALOG


def test_external_providers_no_drift():
    """مجموعة المزوّدات الخارجيّة (الخاضعة لسياسة مشاركة البيانات) متطابقة."""
    assert tuple(GEN._EXTERNAL_PROVIDERS) == CONTRACT.EXTERNAL_PROVIDERS
    assert set(CONTRACT.EXTERNAL_PROVIDERS) == {"anthropic", "openrouter"}
    # المحلّيّ ليس خارجيّاً (لا تُطبَّق عليه قيود المشاركة).
    assert "local" not in CONTRACT.EXTERNAL_PROVIDERS
    assert "vllm" not in CONTRACT.EXTERNAL_PROVIDERS
    assert GEN.provider_is_external("anthropic") and not GEN.provider_is_external("local")
