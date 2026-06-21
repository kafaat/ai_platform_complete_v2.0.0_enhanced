"""مخزن مهامّ raster-service — تعاقُد الارتداد للذاكرة (بلا Redis).

السياق: نُقِلت حالة المهامّ من dict في الذاكرة (`_jobs`) إلى JobStore بطبقتين
(Redis مشترك إن توفّر، وإلّا الذاكرة). هذا الاختبار يتحقّق من تعاقُد الارتداد
للذاكرة وحده — بلا أيّ Redis (يعمل في CI/التطوير):

  ١) round-trip: نتيجة مهمّة تُكتب ثمّ تُقرأ كما هي (نفس الشكل).
  ٢) معرّف مفقود ⇒ None (نفس سلوك .get() القديم ⇒ 404 في نقطة /jobs/{id}).

نستورد job_store مباشرةً (لا fastapi/heavy deps) — لكن نلتزم نمط حارس التخطّي
في tests_v9/test_raster_field_tenant_authz.py: نضيف مسار raster لـsys.path ثمّ
نستورد، ونتخطّى بصدق إن غابت تبعيّة (لا فشل زائف في بيئة خفيفة).
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

pytestmark = [pytest.mark.unit]  # CI يشغّل -m unit

ROOT = os.path.join(os.path.dirname(__file__), "..")
RASTER = os.path.join(ROOT, "services/raster-service")


@pytest.fixture
def store():
    """يستورد job_store من مسار raster ويُنشئ مخزناً ذاكريّاً (بلا REDIS_URL)."""
    if RASTER not in sys.path:
        sys.path.insert(0, RASTER)
    try:
        sys.modules.pop("job_store", None)
        job_store = importlib.import_module("job_store")
    except ImportError as e:  # صدق: غياب تبعيّة في بيئة خفيفة ⇒ تخطٍّ لا فشل
        pytest.skip(f"job_store غير متاح في هذه البيئة: {e}")
    # بلا REDIS_URL ⇒ ارتداد للذاكرة (لا حاجة لخادم Redis).
    s = job_store.JobStore(redis_url=None)
    assert s.backend == "memory", "بلا REDIS_URL يجب أن يكون الباطن ذاكرة (fallback)"
    return s


def test_job_result_round_trips_via_memory(store):
    """نتيجة المهمّة تُكتب وتُقرأ كما هي عبر الارتداد للذاكرة (بلا Redis)."""
    job_id = "job_test123"
    payload = {
        "job_id": job_id,
        "status": "completed",
        "progress_pct": 100,
        "created_at": "2026-06-21T00:00:00+00:00",
        "result": {
            "job_id": job_id,
            "layer_id": "layer_abc",
            "indicator": "ndvi",
            "stats": {"min": 0.0, "max": 1.0, "mean": 0.5, "std": 0.1},
            "bounds_4326": [0.0, 0.0, 1.0, 1.0],
        },
    }
    store.set(job_id, payload)

    got = store.get(job_id)
    assert got is not None
    assert got["status"] == "completed"
    assert got["result"]["layer_id"] == "layer_abc"
    assert got["result"]["indicator"] == "ndvi"
    assert got["result"]["stats"]["mean"] == 0.5
    # round-trip كامل لشكل النتيجة (نفس استجابة /jobs/{id}/result).
    assert got["result"] == payload["result"]


def test_missing_job_returns_none(store):
    """معرّف غير موجود ⇒ None (نفس سلوك .get() ⇒ 404 'مهمّة غير موجودة')."""
    assert store.get("does_not_exist") is None


def test_update_read_modify_write(store):
    """update يطفّر حقلاً على مهمّة قائمة ويثبّته (يحاكي مطفرة dict القديمة)."""
    store.set("j1", {"job_id": "j1", "status": "pending", "progress_pct": 0})
    updated = store.update("j1", status="processing", progress_pct=10)
    assert updated is not None
    again = store.get("j1")
    assert again["status"] == "processing"
    assert again["progress_pct"] == 10
    # update على مهمّة مفقودة ⇒ None (لا إنشاء ضمنيّ).
    assert store.update("nope", status="x") is None


def test_values_lists_all_jobs(store):
    """values() يُرجِع كلّ المهامّ (للمقاييس)."""
    store.set("a", {"job_id": "a", "status": "completed"})
    store.set("b", {"job_id": "b", "status": "failed"})
    statuses = sorted(j["status"] for j in store.values())
    assert statuses == ["completed", "failed"]
