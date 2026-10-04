"""احتواءُ Element84→VRT سلوكيّاً: الرفضُ يقع **قبل** أيّ VRT أو معالجة أو COG أو حفظ.

كلّ نقطة دخول كانت تبني VRT من نطاقات Element84 تُشغَّل هنا بمكوّناتها الحقيقيّة، بينما
تُستبدَل المراحلُ اللاحقة بفخاخٍ ترمي إن لُمِست: بنّاءُ الـVRT (``stac_vrt.build_band_vrt``)،
ونواةُ المعالجة (``_run_processing``/``run_processing`` — هي التي تحسب المؤشّر وتكتب COG
وتحفظ ``raster_assets``)، ومسارُ CDSE (لا ارتداد صامت إليه). فنجاحُ الاختبار يعني أنّ
الرفض سبق كلّ ذلك، لا أنّ النتيجة صادف أن كانت فشلاً.

والفشلُ دائمٌ لنسخة المعالجة: عنصرُ backfill المحجوب لا يُعاد صفُّه في التشغيلة التالية،
بينما يُعاد صفُّ الفشل العابر كما كان (الشاهدُ الضابط).
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import radiometry_containment as rc  # noqa: E402

pytestmark = pytest.mark.unit

HREFS = {
    "red": "https://sentinel-cogs.example/B04.tif",
    "nir": "https://sentinel-cogs.example/B08.tif",
    "swir1": "https://sentinel-cogs.example/B11.tif",
    "scl": "https://sentinel-cogs.example/SCL.tif",
}
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
}
TENANT = "00000000-0000-0000-0000-000000000001"
ELEMENT84_SCENE = {
    "item_id": "S2A_38PLB_20250605_0_L2A",
    "datetime": "2025-06-05T07:40:00Z",
    "cloud_cover_pct": 3.0,
    "bands_urls": HREFS,
    "provider": "element84",
}


def _trap(name: str):
    def _fail(*_a, **_k):
        raise AssertionError(f"{name} استُدعي بعد الرفض — الاحتواء ليس قبل التنفيذ")

    return _fail


@pytest.fixture
def no_vrt(monkeypatch):
    """أيّ بناءٍ لـVRT يرمي — عبر الوحدة الحقيقيّة إن وُجدت، وإلّا وحدةٌ بديلة."""
    fake = types.ModuleType("stac_vrt")
    fake.build_band_vrt = _trap("stac_vrt.build_band_vrt")
    monkeypatch.setitem(sys.modules, "stac_vrt", fake)


# ── ١. process-from-stac ──


def test_process_from_stac_is_rejected_with_422_and_creates_no_job(monkeypatch, no_vrt):
    from fastapi import BackgroundTasks, HTTPException
    from raster_api_models import ProcessFromStacRequest
    from routers import fields

    monkeypatch.setattr(fields, "_require_service_token", lambda _t: None)
    monkeypatch.setattr(fields, "_run_processing", _trap("_run_processing"))
    created: list[str] = []
    monkeypatch.setattr(fields._jobs, "set", lambda jid, _v: created.append(jid))
    tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as info:
        asyncio.run(
            fields.process_from_stac(
                "fld", ProcessFromStacRequest(band_hrefs=HREFS), tasks, x_agent_token="t"
            )
        )

    assert info.value.status_code == 422
    assert info.value.detail["code"] == "radiometry_unresolved"
    assert info.value.detail["entry_point"] == "process_from_stac"
    assert info.value.detail["retryable"] is False
    assert {r["code"] for r in info.value.detail["reasons"]} == {
        "reflectance_scale_unresolved",
        "band_grid_misaligned",
        "nodata_not_propagated",
    }
    assert created == [] and tasks.tasks == [], "مهمّة أُنشئت لطلبٍ محجوب"


# ── ٢. backfill المتزامن (routers/fields) ──


def test_sync_backfill_marks_the_job_failed_permanently_without_processing(monkeypatch, no_vrt):
    from fastapi import BackgroundTasks
    from raster_api_models import HistoricalBackfillRequest, JobStatus
    from routers import fields

    async def _noop_async(*_a, **_k):
        return None

    async def _search(*_a, **_k):
        return {"count": 1, "items": [dict(ELEMENT84_SCENE)]}

    monkeypatch.setattr(fields, "_require_service_token", lambda _t: None)
    monkeypatch.setattr(fields, "_require_field_tenant", _noop_async)
    monkeypatch.setattr(fields, "_async_backfill_enabled", lambda: False)
    monkeypatch.setattr(fields, "_authenticated_tenant", lambda _t: TENANT)
    monkeypatch.setattr(fields, "_stac_search", _search)
    monkeypatch.setattr(
        fields, "_select_backfill_scenes_by_policy", lambda items, **_k: list(items)
    )
    monkeypatch.setattr(fields, "_run_processing", _trap("_run_processing"))
    monkeypatch.setattr(
        fields, "_process_backfill_scene_cdse", _trap("_process_backfill_scene_cdse")
    )
    store: dict[str, dict] = {}
    monkeypatch.setattr(fields._jobs, "set", lambda jid, v: store.__setitem__(jid, dict(v)))
    monkeypatch.setattr(fields._jobs, "get", lambda jid: store.get(jid))

    tasks = BackgroundTasks()
    req = HistoricalBackfillRequest(
        indices=["evi"],
        from_date="2025-06-01",
        to_date="2025-06-30",
        clip_polygon_geojson=POLYGON,
        preset="custom",
    )
    asyncio.run(fields.field_historical_backfill("fld", req, tasks, x_agent_token="t"))

    scene_jobs = [t for t in tasks.tasks if t.func.__name__ == "_run_scene_job"]
    assert scene_jobs, "لم تُجدوَل مهمّة مشهد — الشاهد بلا عين"
    for task in scene_jobs:
        task.func(*task.args, **task.kwargs)

    jobs = [v for v in store.values() if v.get("job_type") == "historical_backfill"]
    assert jobs
    for job in jobs:
        assert job["status"] == JobStatus.failed
        assert job["error_message"] == "radiometry_unresolved"
        assert job["error_detail"]["entry_point"] == "historical_backfill"
        assert job["retryable"] is False
        assert "result" not in job, "نتيجة/منتج سُجِّل لمسار محجوب"


# ── ٣. عامل الفحص اللاتزامنيّ ──


@pytest.fixture
def worker(monkeypatch, no_vrt):
    pytest.importorskip("asyncpg")
    import backfill_scan_worker as bsw

    monkeypatch.setattr(bsw.raster_processing_runtime, "run_processing", _trap("run_processing"))
    monkeypatch.setattr(bsw, "_process_backfill_scene_cdse", _trap("_process_backfill_scene_cdse"))
    return bsw


def test_worker_scene_is_rejected_before_vrt_processing_or_persist(worker):
    outcome = worker._process_scene_index(
        dict(ELEMENT84_SCENE), "evi", "fld", TENANT, None, POLYGON, True, "jid1"
    )
    assert outcome == worker.SceneOutcome(False, rc.ITEM_ERROR)


def test_worker_truecolor_keeps_its_existing_cdse_route(worker, monkeypatch):
    """خارج نطاق الاحتواء: truecolor كان يُوجَّه إلى CDSE قبل هذا التغيير ويبقى كذلك."""
    routed: list[str] = []
    monkeypatch.setattr(
        worker, "_process_backfill_scene_cdse", lambda scene, *_a: routed.append(scene["item_id"])
    )
    monkeypatch.setattr(worker, "_outcome_from_job", lambda _jid: worker.SceneOutcome(True))
    outcome = worker._process_scene_index(
        dict(ELEMENT84_SCENE), "truecolor", "fld", TENANT, None, POLYGON, True, "jid2"
    )
    assert outcome.ok and routed == [ELEMENT84_SCENE["item_id"]]


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Conn:
    """قاعدةٌ مصغّرة لعنصرٍ واحد قائم: تُطبّق شرط إعادة الصفّ كما تكتبه العبارة نفسها."""

    def __init__(self, db: dict):
        self.db = db

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        self.db["executed"].append((" ".join(sql.split()), args))
        return "OK"

    async def fetchval(self, sql, *args):
        flat = " ".join(sql.split())
        if flat.startswith("SELECT 1 FROM raster_assets"):
            return None  # لا أصل جاهز
        if "INSERT INTO backfill_run_items" in flat:
            return None  # العنصر قائمٌ من تشغيلة سابقة (تعارض المفتاح)
        if "SET run_id=$1, status='queued'" in flat:
            # يُطبَّق الشرط فقط إن حملته العبارة — فحذفُه يُعيد الصفَّ بلا قيد كما في القاعدة.
            error = self.db["item_error"]
            guarded = "AND (error IS NULL OR NOT starts_with(error, $4))" in flat
            if guarded and error is not None and error.startswith(args[3]):
                return None
            self.db["requeued"] = True
            return 77
        raise AssertionError(f"عبارة غير متوقَّعة: {flat}")


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_exc):
        return False


class _Pool:
    def __init__(self, db):
        self.conn = _Conn(db)

    def acquire(self):
        return _Acquire(self.conn)


def _run_with_prior_item_error(worker, monkeypatch, item_error):
    async def _search(*_a, **_k):
        return {"items": [dict(ELEMENT84_SCENE)]}

    monkeypatch.setattr(worker.stac_search_helpers, "stac_search", _search)
    monkeypatch.setattr(
        worker.scene_policy, "select_backfill_scenes_by_policy", lambda items, **_k: list(items)
    )
    processed: list[str] = []

    def _process(scene, index, *_a):
        processed.append(index)
        return worker.SceneOutcome(False, rc.ITEM_ERROR)

    monkeypatch.setattr(worker, "_process_scene_index", _process)
    db = {"executed": [], "item_error": item_error, "requeued": False}
    run = {
        "id": "run1",
        "tenant_id": TENANT,
        "field_id": "fld",
        "geometry_revision": None,
        "max_cloud_pct": 30,
        "limit_per_month": 2,
        "indices": ["evi"],
        "clip_polygon_geojson": POLYGON,
        "from_date": "2025-06-01",
        "to_date": "2025-06-30",
        "source": "sentinel-2",
        "run_kind": "backfill",
        "apply_cloud_mask": True,
    }
    asyncio.run(worker._process_run(_Pool(db), run))
    final = [
        args for sql, args in db["executed"] if sql.startswith("UPDATE backfill_runs SET status=$2")
    ]
    return db, processed, final[-1]


def test_a_permanently_rejected_item_is_not_requeued_by_the_next_run(worker, monkeypatch):
    db, processed, final = _run_with_prior_item_error(worker, monkeypatch, rc.ITEM_ERROR)
    assert db["requeued"] is False
    assert processed == [], "عنصرٌ محجوبٌ لهذه النسخة أُعيدت معالجته"
    assert final[1] == "completed_with_errors" and final[4] == 1  # items_failed


def test_a_transient_failure_is_still_requeued(worker, monkeypatch):
    """الشاهد الضابط: الاستثناءُ في الشرط خاصٌّ بالفشل الدائم؛ إعادةُ المحاولة العابرة باقية."""
    db, processed, _final = _run_with_prior_item_error(
        worker, monkeypatch, "exception:ConnectionError:abc123"
    )
    assert db["requeued"] is True
    assert processed == ["evi"]
