"""G13 — المشهد يُعلَّم «معالَجاً» بعد حفظ مؤشّراته، لا قبله.

قبل الإصلاح كان ``_scan_one`` يضبط ``last_image_id`` ثمّ يُطلق المؤشّرات (التي تبتلع كلّ
فشل) ثمّ يحفظ الحقل بالمعرّف الجديد. فعطلٌ عابر بين التعليم والحفظ (هنا: فشل كتابة NDVI
في القاعدة) يجعل الدورة التالية ترى المعرّف نفسه فتتخطّاه ⇒ لا NDVI حتّى المشهد التالي
(~٥ أيّام). الاختبار يحقن الفشل مرّةً واحدة ويقيس أنّ الدورة الثانية تحفظ القيمة.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")

SCENE = {
    "item_id": "S2-scene-1",
    "datetime": "2026-10-12T08:00:00Z",
    "raster_url": "https://example.invalid/seven-band.tif",
}


@pytest.fixture(scope="module")
def core_on_path():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")


class _FakeConn:
    def __init__(self, db):
        self._db = db

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        if sql.startswith("SELECT set_config"):
            return
        if "last_ndvi_mean = $2" in sql:
            if self._db.fail_ndvi_writes > 0:
                self._db.fail_ndvi_writes -= 1
                raise ConnectionError("transient: connection reset during NDVI write")
            self._db.row["last_ndvi_mean"] = args[1]
            return
        if sql.startswith("INSERT INTO imagery_automation_fields"):
            # إدامة الحقل: last_image_id هو علامة «معالَج» الدائمة.
            self._db.row["last_image_id"] = args[6]
            self._db.persisted_image_ids.append(args[6])
            return


class _FakeDb:
    """قاعدة مُقلَّدة: صفّ واحد، وفشل كتابة NDVI قابل للحقن."""

    def __init__(self, *, fail_ndvi_writes: int):
        self.fail_ndvi_writes = fail_ndvi_writes
        self.row: dict = {"last_image_id": None, "last_ndvi_mean": None}
        self.persisted_image_ids: list = []

    @asynccontextmanager
    async def acquire(self):
        yield _FakeConn(self)


def _wire(monkeypatch, db):
    from api import imagery_automation as mod

    async def search(**_kw):
        return {"items": [SCENE]}

    async def batch(*, tenant_id, payload, **_kw):
        return {"job_id": "batch-1", "status": "completed"}

    async def result(job_id, *, tenant_id):
        values = {"batch-1_ndvi": 0.61, "batch-1_ndmi": 0.2, "batch-1_msi": 0.9}
        return {"stats": {"mean": values[job_id], "valid_pixels": 100}}

    monkeypatch.setattr(mod, "search_imagery_scenes", search)
    monkeypatch.setattr(mod, "process_indicator_batch", batch)
    monkeypatch.setattr(mod, "get_job_result", result)
    ia = mod.ImageryAutomation()
    ia.set_pool(db)
    tf = mod.TrackedField(field_id="f1", bbox=[44.0, 15.0, 44.1, 15.1], tenant_id="t1")
    ia._fields["f1"] = tf
    return ia, tf


def _scan(ia, tf):
    return asyncio.run(ia._scan_one("f1", tf, "2026-10-01", "2026-10-14", asyncio.Semaphore(1)))


def test_transient_ndvi_write_failure_does_not_mark_the_scene_processed(core_on_path, monkeypatch):
    db = _FakeDb(fail_ndvi_writes=1)
    ia, tf = _wire(monkeypatch, db)

    first = _scan(ia, tf)
    assert first == (False, "IndicatorsNotPersisted"), "الفشل العابر يجب أن يُعَدّ فشلاً"
    assert tf.last_image_id is None, "عُلِّم المشهد معالَجاً قبل حفظ NDVI"
    assert db.row["last_image_id"] is None, "المعرّف وصل القاعدة بلا NDVI ⇒ لن يُعاد"
    assert db.row["last_ndvi_mean"] is None
    assert tf.check_errors == 1

    # الدورة التالية: العطل زال ⇒ القيمة تُحفَظ ثمّ يُعلَّم المشهد.
    second = _scan(ia, tf)
    assert second == (True, None)
    assert db.row["last_ndvi_mean"] == 0.61, "NDVI ضاع حتّى المشهد التالي (~٥ أيّام)"
    assert db.row["last_image_id"] == "S2-scene-1"
    assert tf.last_image_id == "S2-scene-1"
    assert tf.pending_scene_id is None and tf.pending_scene_attempts == 0

    # وبعدها لا إعادة معالجة.
    assert _scan(ia, tf) == (False, None)


def test_retries_are_bounded_then_the_scene_is_marked(core_on_path, monkeypatch):
    """مشهد معطوب دائماً لا يُعاد بلا نهاية: بعد السقف يُعلَّم معالَجاً بلا قيم."""
    monkeypatch.setenv("IMAGERY_SCENE_MAX_ATTEMPTS", "2")
    db = _FakeDb(fail_ndvi_writes=99)
    ia, tf = _wire(monkeypatch, db)

    assert _scan(ia, tf) == (False, "IndicatorsNotPersisted")
    assert tf.last_image_id is None
    assert _scan(ia, tf) == (True, "IndicatorsNotPersisted")
    assert tf.last_image_id == "S2-scene-1"
    assert db.row["last_image_id"] == "S2-scene-1"
    assert db.row["last_ndvi_mean"] is None, "لا قيمة مُختلَقة عند الاستسلام"
    assert tf.check_errors == 2
    assert _scan(ia, tf) == (False, None)


def test_batch_timeout_leaves_the_scene_retryable(core_on_path, monkeypatch):
    """دفعة لم تكتمل ضمن الميزانيّة: التعليق يَعِد «تُعاد المحاولة في الدورة التالية»."""
    from api import imagery_automation as mod

    db = _FakeDb(fail_ndvi_writes=0)
    ia, tf = _wire(monkeypatch, db)

    async def pending_batch(*, tenant_id, payload, **_kw):
        return {"job_id": "batch-1", "status": "pending"}

    async def still_running(job_id, *, tenant_id=None, **_kw):
        return {"job_id": job_id, "status": "processing"}

    monkeypatch.setattr(mod, "process_indicator_batch", pending_batch)
    monkeypatch.setattr(mod, "get_job_status", still_running)
    monkeypatch.setenv("IMAGERY_BATCH_WAIT_BUDGET_S", "0.001")
    monkeypatch.setenv("IMAGERY_BATCH_POLL_INTERVAL_S", "0.05")

    assert _scan(ia, tf) == (False, "IndicatorsNotPersisted")
    assert tf.last_image_id is None and db.row["last_image_id"] is None
