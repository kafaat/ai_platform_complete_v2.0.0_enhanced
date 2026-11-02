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

    monkeypatch.setattr(raster_security_context, "field_owner", owner_is_a)
    if "main" in sys.modules:  # _require_field_tenant يفضّل main._field_owner إن وُجد
        monkeypatch.setattr(sys.modules["main"], "_field_owner", owner_is_a, raising=False)
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://clip.invalid/db")
    monkeypatch.setattr(db_persist, "fetch_field_geometry", stored_geometry)
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
