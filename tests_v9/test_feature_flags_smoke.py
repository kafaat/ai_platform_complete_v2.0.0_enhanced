"""دخان أعلام الميزات: مطابقة المجموعة الفعليّة المستخرجة من الراوترات مع سجلّ موثّق.

كلّ راوتر محروس يقرأ علماً بنمط ``os.getenv("FEATURE_X", "").strip().lower() in _TRUTHY``
(مُطفأ افتراضاً ⇒ 404). نستخرج المجموعة الفعليّة بالمسح المباشر لـ``api/routers/`` (لا
قائمة ثابتة)، ونؤكّد أنّها تساوي مفاتيح ``feature_registry.FEATURE_FLAGS``. أيّ علم جديد
يحرس راوتراً دون مدخل في السجلّ ⇒ يفشل الاختبار (منع مسارات 404 صامتة/غير موثّقة).
كذلك نؤكّد أنّ المُسنِد الافتراضيّ (غياب البيئة) ⇒ مُعطَّل (اختبار الدالّة النقيّة، بلا HTTP/DB).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_DIR = _REPO_ROOT / "services" / "sahool-platform" / "api"
_ROUTERS_DIR = _API_DIR / "routers"

# نمط الحراسة الدقيق: os.getenv("FEATURE_X", "")...  — هذا هو ما يحوّل راوتراً إلى 404.
# نقصره على getenv بافتراض فارغ "" حتى نلتقط أعلام الحراسة فقط (لا أيّ ذكر نصّيّ للعلم).
_GATING_RE = re.compile(r"""getenv\(\s*["'](?P<flag>FEATURE_[A-Z0-9_]+)["']\s*,\s*["']["']""")


def _load_registry():
    """تحميل feature_registry بمسار الملفّ مباشرةً (تفادي استيراد حزمة api كاملة/DB)."""
    spec = importlib.util.spec_from_file_location(
        "sahool_feature_registry", _API_DIR / "feature_registry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flags_used_in_routers() -> set[str]:
    """استخراج أعلام الحراسة الفعليّة من كلّ ملفّات راوترات .py (لا cache، لا قائمة ثابتة)."""
    assert _ROUTERS_DIR.is_dir(), f"مجلّد الراوترات غير موجود: {_ROUTERS_DIR}"
    flags: set[str] = set()
    for path in _ROUTERS_DIR.glob("*.py"):
        flags.update(_GATING_RE.findall(path.read_text(encoding="utf-8")))
    return flags


@pytest.mark.unit
def test_router_flags_match_registry_exactly():
    """مجموعة أعلام الحراسة المستخرجة من الراوترات = مفاتيح السجلّ (تساوٍ في الاتّجاهين)."""
    actual = _flags_used_in_routers()
    assert actual, "لم يُستخرَج أيّ علم FEATURE_* من الراوترات — تغيّر نمط الحراسة؟"
    registry = set(_load_registry().FEATURE_FLAGS)

    undocumented = actual - registry
    stale = registry - actual
    assert not undocumented, (
        f"أعلام تحرس راوترات بلا مدخل في feature_registry.FEATURE_FLAGS (404 صامت): "
        f"{sorted(undocumented)}. أضِف وصفاً لكلّ علم في السجلّ."
    )
    assert not stale, f"مداخل في السجلّ لا تحرس أيّ راوتر (stale): {sorted(stale)}. أزِلها من السجلّ."


@pytest.mark.unit
def test_registry_entries_have_descriptions():
    """كلّ مدخل في السجلّ له اسم FEATURE_* ووصف غير فارغ."""
    flags = _load_registry().FEATURE_FLAGS
    for name, desc in flags.items():
        assert name.startswith("FEATURE_"), f"اسم علم غير صالح: {name}"
        assert isinstance(desc, str) and desc.strip(), f"وصف فارغ للعلم: {name}"


@pytest.mark.unit
def test_default_off_predicate_is_disabled():
    """المُسنِد النقيّ ``is_enabled`` مُعطَّل افتراضاً (None/فارغ/falsy) ومُفعَّل على truthy فقط."""
    reg = _load_registry()
    for name in reg.FEATURE_FLAGS:
        assert reg.is_enabled(name, None) is False
        assert reg.is_enabled(name, "") is False
        assert reg.is_enabled(name, "0") is False
        assert reg.is_enabled(name, "false") is False
        assert reg.is_enabled(name, "1") is True
        assert reg.is_enabled(name, " TRUE ") is True
        assert reg.is_enabled(name, "on") is True
