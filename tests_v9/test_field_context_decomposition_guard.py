"""حارس تفكيك: عنقود السياق الزراعيّ للحقل في api/field_context.py (لا في main.py).

استُخرِج عنقود اشتقاق سياق الحقل (طقس/تربة/موسم/سياسة محرّكات التوصيات) من الوحدة
الضخمة ``api/main.py`` إلى وحدة ``api/field_context.py`` (تفكيك B1)، ويُعاد تصديره من
``api.main`` كي تبقى نقاط الاستدعاء ``from api.main import …`` في الموجِّهات صحيحة.

هذا الحارس يثبّت العقد:
  • الدوالّ الثمانية مُعرَّفة في ``field_context.py`` (مصدر) لا inline في ``main.py``.
  • ``api.main`` يُعيد تصديرها بنفس هويّة الكائن (re-export سليم لا نسخة منفصلة).
فيمنع انحدارَين: إعادة دمج العنقود في main، أو كسر سطر إعادة التصدير صامتاً.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit

_CORE = os.path.join(os.path.dirname(__file__), "..", "services/sahool-platform")
_MAIN = os.path.join(_CORE, "api", "main.py")
_FIELD_CONTEXT = os.path.join(_CORE, "api", "field_context.py")

# الأسماء المُستخرَجة (٧ دوالّ + ثابت مراحل النموّ).
_EXPORTS = (
    "_growth_stage",
    "_field_weather_context",
    "_latest_soil_moisture",
    "_field_season_context",
    "_historical_rain_3d_mm",
    "_resolve_recommendation_policy",
    "_load_recommendation_policy",
    "_STAGE_DAY_BOUNDS",
)


def test_field_context_module_exists():
    assert os.path.isfile(_FIELD_CONTEXT), "وحدة api/field_context.py مفقودة"


def test_helpers_defined_in_field_context_not_main():
    """الدوالّ مُعرَّفة في field_context.py لا inline في main.py (لا انحدار دمج)."""
    with open(_FIELD_CONTEXT, encoding="utf-8") as f:
        fc_src = f.read()
    with open(_MAIN, encoding="utf-8") as f:
        main_src = f.read()
    for name in _EXPORTS:
        if name == "_STAGE_DAY_BOUNDS":
            assert f"{name} =" in fc_src, f"{name} غير مُعرَّف في field_context.py"
            assert f"{name} =" not in main_src, f"{name} ما زال مُعرَّفاً في main.py (لم يُنقَل)"
        else:
            assert f"def {name}(" in fc_src, f"{name} غير مُعرَّف في field_context.py"
            assert f"def {name}(" not in main_src, f"{name} ما زال مُعرَّفاً في main.py (لم يُنقَل)"


def test_main_reexports_with_same_identity():
    """api.main يُعيد تصدير كلّ اسم بنفس هويّة الكائن (re-export سليم)."""
    if _CORE not in sys.path:
        sys.path.insert(0, _CORE)
    pytest.importorskip("fastapi")
    try:
        import api.field_context as fc
        import api.main as m
    except ModuleNotFoundError as e:  # تبعيّات المنصّة غائبة محليّاً (asyncpg…)
        pytest.skip(f"platform deps missing: {e}")
    for name in _EXPORTS:
        assert hasattr(m, name), f"api.main لا يُعيد تصدير {name}"
        assert getattr(m, name) is getattr(fc, name), f"{name}: إعادة التصدير ليست نفس الكائن"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
