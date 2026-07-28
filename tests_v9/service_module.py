"""تحميل ``main.py`` لخدمة بعينها رغم عموميّة الاسم عبر ٢٤ خدمة (نمط #570).

كلّ خدمة تحمل ``main.py`` في جذرها، و``sys.modules`` مفتاحه الاسم لا المسار — فاستيراد
``main`` بعد استيراد خدمة أخرى يُعيد الوحدة البائتة بصمت. الخطر ليس فشلاً بل **نجاحاً
كاذباً**: اختبار يفحص مسارات خدمة (أ) بينما يقرأ فعليّاً وحدة الخدمة (ب).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# أسماء وحدات عامّة تتكرّر عبر الخدمات؛ تُنظَّف بالبادئة لا بالاسم المضبوط، لأنّ
# `routers` وحدها لا تُزيل `routers.equipment` المُحمَّلة من خدمة أخرى.
_GENERIC_ROOTS = {"main", "router_registry", "routers"}


def purge_generic_modules() -> None:
    """يُزيل كلّ وحدة اسمها الجذريّ عامّ، مع فروعها."""
    for name in list(sys.modules):
        if name.split(".")[0] in _GENERIC_ROOTS:
            sys.modules.pop(name, None)


def load_service_main(service_dir: str, *, required_attrs: tuple[str, ...]):
    """يُحمّل main.py لخدمة بعينها رغم عموميّة الاسم عبر الخدمات (نمط #570)."""
    root = Path(service_dir).resolve()
    while service_dir in sys.path:
        sys.path.remove(service_dir)
    sys.path.insert(0, service_dir)
    purge_generic_modules()
    try:
        mod = importlib.import_module("main")
    except ImportError as e:
        pytest.skip(f"تبعيّة ناقصة: {e}", allow_module_level=True)

    # هويّة الوحدة تُثبَت بمسارها، لا تُستدَلّ من سماتها: خدمتان تحملان `app` و`router`
    # معاً تمرّان فحص السمات وهما وحدتان مختلفتان.
    loaded = Path(mod.__file__ or "").resolve()
    if not loaded.is_relative_to(root):
        raise AssertionError(f"استُورد main خاطئ (تصادم أسماء): {loaded} خارج {root}")
    missing = [a for a in required_attrs if not hasattr(mod, a)]
    if missing:
        raise AssertionError(f"استُورد main خاطئ (تصادم أسماء) — ينقصه {missing}")
    return mod
