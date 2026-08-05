#!/usr/bin/env python3
"""عقد WOFOST Runtime Closure — يمنع عودة التحميل الديناميكي في الإنتاج.

الواقعة المُغلقة: المحرّك كان في ``wofost_real/`` خارج سياق Docker
(يُنسَخ ``shared/`` و``services/sahool-platform/`` فقط)، فحمّله
``routers/simulate.py`` بـ``spec_from_file_location`` وعاد
``available: False`` صامتاً في الإنتاج — تدهور خفيّ لا يرصده أحد.
الإغلاق: حزمة مملوكة ``shared/wofost/`` + استيراد نظاميّ + هذا العقد.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SIMULATE = ROOT / "services" / "sahool-platform" / "api" / "routers" / "simulate.py"


def _production_router_sources() -> dict[str, str]:
    """مصادر موجّهات الإنتاج كلّها — الممنوع عامّ لا خاصّ بـsimulate."""
    out = {}
    for p in sorted(ROOT.glob("services/**/routers/*.py")):
        out[str(p.relative_to(ROOT))] = p.read_text(encoding="utf-8")
    assert out, "لا موجّهات مُكتشَفة — حارس بلا عين (نجاح كاذب ممنوع)"
    return out


def test_no_dynamic_file_loading_in_production_routers() -> None:
    for rel, src in _production_router_sources().items():
        assert "spec_from_file_location" not in src, f"تحميل ديناميكيّ عاد في {rel}"
        assert "module_from_spec" not in src, f"تحميل ديناميكيّ عاد في {rel}"


def test_simulate_imports_owned_package_not_a_file_path() -> None:
    src = SIMULATE.read_text(encoding="utf-8")
    assert "from shared.wofost import simulate_wofost" in src
    assert "wofost_real" not in src, "مسار الحزمة القديمة باقٍ في الموجِّه"


def test_engine_lives_inside_docker_context() -> None:
    # عقد سياق Docker: المحرّك يجب أن يسكن حزمةً ينسخها Dockerfile فعلاً.
    engine = ROOT / "shared" / "wofost" / "engine.py"
    assert engine.is_file(), "المحرّك ليس في shared/wofost/engine.py"
    dockerfile = (ROOT / "services" / "sahool-platform" / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^COPY\s+shared/", dockerfile, re.M), (
        "Dockerfile لا ينسخ shared/ — العقدة مكسورة من جهة الصورة"
    )


def test_old_isolated_package_is_gone() -> None:
    assert not (ROOT / "wofost_real").exists(), "wofost_real عادت — نسختان = انحراف"


def test_no_python_file_imports_the_old_package_anywhere() -> None:
    # أُضيف بعد أن فات مستهلك (vegetation_real) بحثاً مقطوعاً بـhead في الجولة
    # الأولى — الفحص هنا شامل بلا اقتطاع، والحارس لا يعتمد على ذاكرة أحد.
    offenders = []
    for p in sorted(ROOT.rglob("*.py")):
        if ".git" in p.parts or p.name == "test_wofost_runtime_closure.py":
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "from wofost_real" in src or "import wofost_real" in src:
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"استيرادات من الحزمة المحذوفة: {offenders}"


def test_normal_import_works() -> None:
    import inspect
    import sys

    sys.path.insert(0, str(ROOT))
    try:
        from shared.wofost import simulate_wofost
    finally:
        sys.path.remove(str(ROOT))
    assert inspect.iscoroutinefunction(simulate_wofost), "توقيع الواجهة تغيّر بصمت"
