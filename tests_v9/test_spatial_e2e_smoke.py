"""غلاف integration لِ scripts/e2e/spatial_flows.py — يتخطّى بلا مكدّس حيّ.

لا يُشغَّل في بوّابة الوحدات (مُعلَّم integration؛ ``-m unit`` يُلغي اختياره). يتطلّب
مكدّساً حيّاً (postgis+redis+auth+sahool-platform خلف بوّابة) وضبط
``SAHOOL_E2E_BASE_URL``. عند غياب المتغيّر أو تعذّر الوصول للمكدّس يتخطّى بدل الفشل،
فيبقى آمناً في أيّ تشغيل offline/CI.

التشغيل (مع مكدّس حيّ):
  docker compose -f docker-compose.v9.yml up -d
  SAHOOL_E2E_BASE_URL=http://localhost python -m pytest -m integration \
      tests_v9/test_spatial_e2e_smoke.py
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _REPO_ROOT / "scripts" / "e2e" / "spatial_flows.py"


def _load_harness():
    """يحمّل وحدة الـ harness من مسارها مباشرةً (scripts/ ليست حزمة مستوردة)."""
    spec = importlib.util.spec_from_file_location("spatial_flows", _HARNESS)
    assert spec is not None and spec.loader is not None, f"تعذّر تحميل الـ harness: {_HARNESS}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
def test_spatial_flows_against_live_stack():
    base = os.getenv("SAHOOL_E2E_BASE_URL")
    if not base:
        pytest.skip("SAHOOL_E2E_BASE_URL غير مضبوط — لا مكدّس حيّ؛ تخطٍّ (لا يُشغَّل في -m unit).")

    assert _HARNESS.exists(), f"الـ harness مفقود: {_HARNESS}"
    harness = _load_harness()

    if not harness.stack_reachable(base.rstrip("/")):
        pytest.skip(f"الأساس {base} غير قابل للوصول — لا مكدّس حيّ؛ تخطٍّ.")

    # نوجّه الـ harness للأساس المضبوط، ثمّ نشغّل main() مباشرةً (بلا subprocess).
    os.environ.setdefault("BASE_URL", base)
    rc = harness.main()
    assert rc == 0, f"فشلت تدفّقات E2E المكانيّة (rc={rc}) — راجع PASS/FAIL أعلاه."
