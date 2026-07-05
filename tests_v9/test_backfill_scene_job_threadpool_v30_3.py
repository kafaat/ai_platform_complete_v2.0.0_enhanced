"""حارس: مهمّة معالجة مشهد backfill متزامنة (threadpool) لا تحجب حلقة الأحداث.

v6-audit F3: كان `_run_scene_job` مُعرَّفاً `async def` ويستدعي `_run_processing`
المتزامن الثقيل (build_band_vrt + معالجة COG) مباشرةً ⇒ FastAPI يُنفّذ مهامّ الخلفيّة
`async` على حلقة الأحداث فتُحجب باقي طلبات raster. الإصلاح: تعريفها `def` عاديّة كي
يُشغّلها FastAPI في threadpool.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
FIELDS = REPO / "services" / "raster-service" / "routers" / "fields.py"


def test_run_scene_job_is_sync_for_threadpool() -> None:
    src = FIELDS.read_text(encoding="utf-8")
    # مُعرَّفة def لا async def.
    assert re.search(r"^\s*def _run_scene_job\(", src, re.M), (
        "_run_scene_job يجب أن تكون def متزامنة (threadpool)، لا async def (تحجب الحلقة)"
    )
    assert "async def _run_scene_job(" not in src, "بقيت async def — ستُنفَّذ على حلقة الأحداث"
    # ما زالت تُجدوَل كمهمّة خلفيّة وتستدعي المعالجة المتزامنة.
    assert "background_tasks.add_task(_run_scene_job)" in src
    assert "main._run_processing(jid, preq)" in src
