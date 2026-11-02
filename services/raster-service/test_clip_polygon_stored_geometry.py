"""قاعدة T10 لمضلّع القصّ في process-date و imagery/backfill و process-from-stac.

العطل (تدقيق 2026-11-01): الثلاثة تفحص ملكيّة الحقل ثمّ تقصّ وتحفظ باسم الحقل بمضلّع
``clip_polygon_geojson`` يختاره المُنادي — فيُعالَج أيّ مضلّع (أرض آخرين) تحت معرّف حقل
مملوك. العقد بعد الإصلاح (مثل process-cdse في T10):
  * مع قاعدة وغياب مضلّع الجسم ⇒ الهندسة المخزّنة في ``fields``.
  * مضلّع جسمٍ داخل الهندسة المخزّنة ⇒ مقبول كما هو؛ خارجها ⇒ 400 بلا جدولة.
  * بلا قاعدة ⇒ السلوك القديم (مضلّع الجسم) دون تغيير.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import db_persist  # noqa: E402
import raster_date_geo  # noqa: E402
import raster_security_context  # noqa: E402
import routers.fields as fields  # noqa: E402
from raster_api_models import (  # noqa: E402
    HistoricalBackfillRequest,
    ProcessDateRequest,
    ProcessFromStacRequest,
)

pytestmark = pytest.mark.unit

TENANT_A = "11111111-1111-1111-1111-111111111111"
FIELD = "fld-clip-owned-by-a"

STORED = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.02, 15.0], [44.02, 15.03], [44.0, 15.03], [44.0, 15.0]]],
}
INSIDE = {
    "type": "Polygon",
    "coordinates": [
        [[44.005, 15.005], [44.01, 15.005], [44.01, 15.01], [44.005, 15.01], [44.005, 15.005]]
    ],
}
FOREIGN = {
    "type": "Polygon",
    "coordinates": [[[10.0, 50.0], [10.5, 50.0], [10.5, 50.5], [10.0, 50.5], [10.0, 50.0]]],
}
#: مراجعة الهندسة المخزّنة الحاليّة (field_geometry_history) — تُقرأ مع الهندسة في جملة واحدة.
STORED_REVISION = 7
# يتجاوز الحقل قليلاً (~1 كم شرقاً): ليس «داخل» الحقل وإن تداخل معه.
OVERLAPPING = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.03, 15.0], [44.03, 15.03], [44.0, 15.03], [44.0, 15.0]]],
}


@pytest.fixture()
def owned_field(monkeypatch):
    """الحقل مملوك لـA، والطلب بسياق A، وقاعدة «موجودة» تُرجِع STORED."""

    async def owner_is_a(field_id: str) -> str | None:
        return TENANT_A if field_id == FIELD else None

    async def stored_geometry(field_id, tenant_id=None):
        assert (field_id, tenant_id) == (FIELD, TENANT_A)
        return STORED

    async def stored_with_revision(field_id, tenant_id=None):
        assert (field_id, tenant_id) == (FIELD, TENANT_A)
        return {"geometry": STORED, "revision": STORED_REVISION}

    monkeypatch.setattr(raster_security_context, "field_owner", owner_is_a)
    if "main" in sys.modules:  # _require_field_tenant يفضّل main._field_owner إن وُجد
        monkeypatch.setattr(sys.modules["main"], "_field_owner", owner_is_a, raising=False)
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://clip.invalid/db")
    monkeypatch.setattr(db_persist, "fetch_field_geometry", stored_geometry)
    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", stored_with_revision)
    return raster_security_context.REQ_TENANT.set


def _capture_process_date(monkeypatch) -> list[dict]:
    seen: list[dict] = []

    async def enqueue(**kwargs):
        seen.append(kwargs)
        return {"status": "planned", "run_id": "r1", "item_id": "i1"}

    monkeypatch.setattr(db_persist, "enqueue_single_scene_process", enqueue)
    return seen


def _date_req(clip: dict | None) -> ProcessDateRequest:
    return ProcessDateRequest(
        date="2026-10-01", index="ndvi", scene_id="S2A_X", clip_polygon_geojson=clip
    )


# ── process-date ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_date_rejects_body_polygon_outside_field(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)
    for outside in (FOREIGN, OVERLAPPING):
        with pytest.raises(HTTPException) as exc:
            await fields.field_process_date(FIELD, _date_req(outside), x_agent_token="ok")
        assert exc.value.status_code == 400
    assert seen == [], "a polygon outside the field must not be scheduled"


@pytest.mark.asyncio
async def test_process_date_accepts_body_polygon_inside_field(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)
    await fields.field_process_date(FIELD, _date_req(INSIDE), x_agent_token="ok")
    assert seen[-1]["clip_polygon_geojson"] == INSIDE
    assert seen[-1]["tenant_id"] == TENANT_A


@pytest.mark.asyncio
async def test_process_date_absent_polygon_uses_stored_geometry(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)
    await fields.field_process_date(FIELD, _date_req(None), x_agent_token="ok")
    assert seen[-1]["clip_polygon_geojson"] == STORED


@pytest.mark.asyncio
async def test_process_date_without_stored_geometry_rejects_body_polygon(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)

    async def no_geometry(field_id, tenant_id=None):
        return None

    monkeypatch.setattr(db_persist, "fetch_field_geometry", no_geometry)
    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", no_geometry)
    with pytest.raises(HTTPException) as exc:
        await fields.field_process_date(FIELD, _date_req(INSIDE), x_agent_token="ok")
    assert exc.value.status_code == 400
    assert seen == []


@pytest.mark.asyncio
async def test_process_date_db_less_keeps_body_polygon(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    await fields.field_process_date(FIELD, _date_req(FOREIGN), x_agent_token="ok")
    assert seen[-1]["clip_polygon_geojson"] == FOREIGN


# ── imagery/backfill ─────────────────────────────────────────────────────────


def _capture_backfill_run(monkeypatch) -> list[dict]:
    seen: list[dict] = []

    async def insert_run(**kwargs):
        seen.append(kwargs)
        return "run-1"

    monkeypatch.setattr(fields, "_async_backfill_enabled", lambda: True)
    monkeypatch.setattr(db_persist, "insert_backfill_run", insert_run)
    return seen


@pytest.mark.asyncio
async def test_backfill_rejects_body_polygon_outside_field(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_backfill_run(monkeypatch)
    req = HistoricalBackfillRequest(indices=["ndvi"], clip_polygon_geojson=FOREIGN)
    with pytest.raises(HTTPException) as exc:
        await fields.field_historical_backfill(FIELD, req, BackgroundTasks(), x_agent_token="ok")
    assert exc.value.status_code == 400
    assert seen == []


@pytest.mark.asyncio
async def test_backfill_accepts_inside_and_defaults_to_stored(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_backfill_run(monkeypatch)
    for body, expected in ((INSIDE, INSIDE), (None, STORED)):
        req = HistoricalBackfillRequest(indices=["ndvi"], clip_polygon_geojson=body)
        out = await fields.field_historical_backfill(
            FIELD, req, BackgroundTasks(), x_agent_token="ok"
        )
        assert out["run_id"] == "run-1"
        assert seen[-1]["clip_polygon_geojson"] == expected


# ── process-from-stac ────────────────────────────────────────────────────────


class _StacReached(Exception):
    pass


@pytest.mark.asyncio
async def test_process_from_stac_rejects_body_polygon_outside_field(owned_field, monkeypatch):
    owned_field(TENANT_A)
    import stac_search

    reached: list[dict] = []

    async def stac_query(body):
        reached.append(body)
        raise _StacReached

    monkeypatch.setattr(stac_search, "stac_query", stac_query)

    def req(clip):
        return ProcessFromStacRequest(
            band_hrefs={"B04": "https://x/B04.tif"}, scene_id="S2A_X", clip_polygon_geojson=clip
        )

    with pytest.raises(HTTPException) as exc:
        await fields.process_from_stac(FIELD, req(FOREIGN), BackgroundTasks(), x_agent_token="ok")
    assert exc.value.status_code == 400
    assert reached == [], "catalogue was queried before the polygon was checked"

    with pytest.raises(_StacReached):  # داخل الحقل ⇒ يمضي إلى الكتالوج
        await fields.process_from_stac(FIELD, req(INSIDE), BackgroundTasks(), x_agent_token="ok")


# ── المحمول الصرف ───────────────────────────────────────────────────────────


def test_clip_within_field_predicate():
    assert raster_date_geo.clip_within_field(STORED, STORED)
    assert raster_date_geo.clip_within_field(INSIDE, STORED)
    assert raster_date_geo.clip_within_field({"type": "Feature", "geometry": INSIDE}, STORED)
    assert not raster_date_geo.clip_within_field(FOREIGN, STORED)
    assert not raster_date_geo.clip_within_field(OVERLAPPING, STORED)
    assert not raster_date_geo.clip_within_field(
        {"type": "Point", "coordinates": [44.01, 15.01]}, STORED
    )
    assert not raster_date_geo.clip_within_field({"type": "Polygon", "coordinates": "bad"}, STORED)
    assert not raster_date_geo.clip_within_field(INSIDE, None)


def test_clip_within_field_fails_closed_on_malformed_feature_collection():
    """``features`` ليس قائمة عنصرٍ واحدٍ قاموسيّ بهندسة قاموسيّة ⇒ False (400)، لا استثناء (500)."""
    for features in ([None], ["x"], [{"geometry": None}], [{"geometry": "x"}], "a", {"k": 1}, 7):
        bad = {"type": "FeatureCollection", "features": features}
        assert not raster_date_geo.clip_within_field(bad, STORED), features
    one = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": INSIDE}]}
    assert raster_date_geo.clip_within_field(one, STORED)


@pytest.mark.asyncio
async def test_process_date_malformed_feature_collection_is_400(owned_field, monkeypatch):
    owned_field(TENANT_A)
    seen = _capture_process_date(monkeypatch)
    bad = {"type": "FeatureCollection", "features": [None]}
    with pytest.raises(HTTPException) as exc:
        await fields.field_process_date(FIELD, _date_req(bad), x_agent_token="ok")
    assert exc.value.status_code == 400
    assert seen == []


# ── مراجعة الهندسة: تُختَم مع القصّ لا من الجسم (مراجعة PR #1330) ─────────────
#
# العطل: ``_clip_on_stored_field`` كان يُرجِع الهندسة المخزّنة الحاليّة (N+1) بينما تُجدوِل
# النقاط الثلاث مراجعة الجسم (N) — فيُختَم أصلٌ قُصّ بـN+1 نَسَباً N، ويُعاد استعمال أصلٍ
# جاهزٍ بمفتاح المراجعة الخاطئة. العقد (كـprocess-cdse): مراجعة مخالِفة ⇒ 409
# ``stale_geometry_revision`` بلا جدولة؛ غيابها ⇒ تُختَم المراجعة المخزّنة.


def _assert_stale_409(exc: pytest.ExceptionInfo) -> None:
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "stale_geometry_revision"
    assert exc.value.detail["requested_revision"] == STORED_REVISION - 1
    assert exc.value.detail["current_revision"] == STORED_REVISION


def _stac_req(clip: dict | None, revision: int | None = None) -> ProcessFromStacRequest:
    return ProcessFromStacRequest(
        band_hrefs={"B04": "https://x/B04.tif"},
        scene_id="S2A_X",
        clip_polygon_geojson=clip,
        geometry_revision=revision,
    )


def _c1_pipeline(monkeypatch) -> list[tuple]:
    """كتالوج C1 يُرجِع المشهد المطلوب بالضبط؛ ``process_c1_scene`` يُلتقَط بلا GDAL."""
    import stac_c1_processing
    import stac_search

    async def stac_query(body):
        return {"features": [{"id": "S2A_X", "properties": {"datetime": None}, "assets": {}}]}

    monkeypatch.setattr(stac_search, "stac_query", stac_query)
    monkeypatch.setattr(
        stac_search, "band_urls_from_assets", lambda _a: {"B04": "https://x/B04.tif"}
    )
    monkeypatch.setattr(stac_search, "radiometry_context_from_item", lambda _i: {})
    monkeypatch.setattr(stac_c1_processing, "validate_c1_scene", lambda *_a, **_k: {})
    seen: list[tuple] = []
    monkeypatch.setattr(stac_c1_processing, "process_c1_scene", lambda *a, **_k: seen.append(a))
    return seen


@pytest.mark.asyncio
async def test_stale_body_revision_is_409_on_all_three_without_scheduling(owned_field, monkeypatch):
    owned_field(TENANT_A)
    stale = STORED_REVISION - 1
    dates = _capture_process_date(monkeypatch)
    for clip in (None, INSIDE):
        req = ProcessDateRequest(
            date="2026-10-01",
            index="ndvi",
            scene_id="S2A_X",
            clip_polygon_geojson=clip,
            geometry_revision=stale,
        )
        with pytest.raises(HTTPException) as exc:
            await fields.field_process_date(FIELD, req, x_agent_token="ok")
        _assert_stale_409(exc)
    assert dates == []

    runs = _capture_backfill_run(monkeypatch)
    req = HistoricalBackfillRequest(indices=["ndvi"], geometry_revision=stale)
    with pytest.raises(HTTPException) as exc:
        await fields.field_historical_backfill(FIELD, req, BackgroundTasks(), x_agent_token="ok")
    _assert_stale_409(exc)
    assert runs == []

    c1 = _c1_pipeline(monkeypatch)
    tasks = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await fields.process_from_stac(FIELD, _stac_req(None, stale), tasks, x_agent_token="ok")
    _assert_stale_409(exc)
    await tasks()
    assert c1 == []


@pytest.mark.asyncio
async def test_stored_revision_is_stamped_with_the_stored_clip(owned_field, monkeypatch):
    """بلا مراجعة في الجسم (أو بالمطابقة) تُختَم المراجعة المخزّنة التي قُصّ بها، لا None."""
    owned_field(TENANT_A)
    dates = _capture_process_date(monkeypatch)
    for revision in (None, STORED_REVISION):
        req = ProcessDateRequest(
            date="2026-10-01", index="ndvi", scene_id="S2A_X", geometry_revision=revision
        )
        await fields.field_process_date(FIELD, req, x_agent_token="ok")
        assert dates[-1]["geometry_revision"] == STORED_REVISION
        assert dates[-1]["clip_polygon_geojson"] == STORED

    runs = _capture_backfill_run(monkeypatch)
    req = HistoricalBackfillRequest(indices=["ndvi"])
    await fields.field_historical_backfill(FIELD, req, BackgroundTasks(), x_agent_token="ok")
    assert runs[-1]["geometry_revision"] == STORED_REVISION


@pytest.mark.asyncio
async def test_sync_backfill_scene_jobs_carry_the_stored_revision(owned_field, monkeypatch):
    owned_field(TENANT_A)
    c1 = _c1_pipeline(monkeypatch)
    scene = {"item_id": "S2A_X", "datetime": None, "bands_urls": {"B04": "https://x/B04.tif"}}

    async def stac_search(*_a, **_k):
        return {"items": [scene], "count": 1}

    async def no_persist(*_a, **_k):
        return None

    monkeypatch.setattr(fields, "_async_backfill_enabled", lambda: False)
    monkeypatch.setattr(fields, "_stac_search", stac_search)
    monkeypatch.setattr(fields, "_select_backfill_scenes_by_policy", lambda items, **_k: items)
    monkeypatch.setattr(fields, "_persist_selected_stac_scenes", no_persist)
    tasks = BackgroundTasks()
    req = HistoricalBackfillRequest(
        indices=["ndvi"], preset="custom", from_date="2026-09-01", to_date="2026-09-20"
    )
    await fields.field_historical_backfill(FIELD, req, tasks, x_agent_token="ok")
    await tasks()
    assert c1, "scene job did not reach the C1 core"
    _scene, _index, _field, _tenant, revision, clip = c1[-1][:6]
    assert (revision, clip) == (STORED_REVISION, STORED)


@pytest.mark.asyncio
async def test_process_from_stac_without_body_polygon_uses_stored_geometry(
    owned_field, monkeypatch
):
    """غياب ``clip_polygon_geojson`` ⇒ الهندسة المخزّنة (قاعدة T10) — لا 422 radiometry_unresolved
    من حارسٍ يسبق حلّ القصّ."""
    owned_field(TENANT_A)
    c1 = _c1_pipeline(monkeypatch)
    tasks = BackgroundTasks()
    out = await fields.process_from_stac(FIELD, _stac_req(None), tasks, x_agent_token="ok")
    assert out["status"] == "pending"
    await tasks()
    _scene, _index, _field, tenant, revision, clip = c1[-1][:6]
    assert (tenant, revision, clip) == (TENANT_A, STORED_REVISION, STORED)


@pytest.mark.asyncio
async def test_process_from_stac_db_less_without_polygon_stays_contained(owned_field, monkeypatch):
    """بلا قاعدة لا هندسة مخزّنة تُحلّ: القصّ يبقى غائباً فيبقى الرفض 422 كما كان."""
    owned_field(TENANT_A)
    c1 = _c1_pipeline(monkeypatch)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    with pytest.raises(HTTPException) as exc:
        await fields.process_from_stac(
            FIELD, _stac_req(None), BackgroundTasks(), x_agent_token="ok"
        )
    assert exc.value.status_code == 422
    assert c1 == []
