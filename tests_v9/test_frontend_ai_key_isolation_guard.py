"""حارس عزل مفاتيح مزوّدي الذكاء عن حزمة الواجهة (frontend/src).

السبب (مبدأ أمنيّ من مراجعة 1.3، وأساس إضافة OpenRouter): مفاتيح المزوّدات
(OpenRouter/Anthropic) تبقى خادميّة حصراً — تُحلّ في api/ai_provider_config وتُستعمَل
في الـproxy. أيّ تسريب لها إلى كود الواجهة (أو متغيّرات Vite العامّة `import.meta.env`)
يكشفها في المتصفّح (DevTools → Network/Source). منتقي النموذج يرسل **معرّف النموذج
فقط** لا المفتاح.

هذا الحارس مسح ساكن لـ`frontend/src` يمنع:
  • ذكر أسماء أسرار المفاتيح (OPENROUTER_API_KEY / ANTHROPIC_API_KEY).
  • قراءة أيّ `import.meta.env.*API_KEY*` (سرّ مُجمَّع في الحزمة).
  • ترويسة سرّ مزوّد ثابتة (`x-api-key` أو `Bearer sk-...`).
لا تشغيل بناء — مسح نصّيّ صرف.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_SRC = os.path.join(_ROOT, "frontend", "src")

# أنماط محظورة في كود الواجهة (الأسرار خادميّة فقط).
_FORBIDDEN = [
    re.compile(r"OPENROUTER_API_KEY"),
    re.compile(r"ANTHROPIC_API_KEY"),
    re.compile(r"import\.meta\.env\.[A-Za-z0-9_]*API_KEY"),
    re.compile(r"""['"]x-api-key['"]""", re.IGNORECASE),
    re.compile(r"Bearer\s+sk-"),
]


def _iter_source_files():
    for base, _dirs, files in os.walk(_SRC):
        for name in files:
            if name.endswith((".ts", ".tsx", ".js", ".jsx")):
                yield os.path.join(base, name)


def test_no_provider_secret_referenced_in_frontend():
    assert os.path.isdir(_SRC), "frontend/src غير موجود"
    violations: list[str] = []
    for path in _iter_source_files():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for pat in _FORBIDDEN:
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                rel = os.path.relpath(path, _ROOT)
                violations.append(f"{rel}:{line} ⇒ {pat.pattern}")
    assert not violations, "تسريب محتمل لسرّ مزوّد في الواجهة:\n" + "\n".join(violations)


def test_model_picker_sends_model_id_only():
    """منتقي النموذج يرسل معرّف النموذج (model) لا أيّ مفتاح — تثبيت العقد الآمن."""
    chatbot = os.path.join(_SRC, "sections", "ChatbotPage.tsx")
    assert os.path.isfile(chatbot), "ChatbotPage.tsx غير موجود"
    with open(chatbot, encoding="utf-8") as fh:
        text = fh.read()
    # يجلب الكتالوج من نقطة الخادم (لا أسرار) ويرسل model فقط.
    assert "/api/v1/ai/models" in text, "المنتقي لا يجلب كتالوج النماذج من الخادم"
    assert "model: selectedModel" in text, "المنتقي لا يرسل معرّف النموذج المختار"
