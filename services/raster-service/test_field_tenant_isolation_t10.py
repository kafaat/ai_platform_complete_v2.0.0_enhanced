"""T10 (تدقيق 2026-11-01): عزل المستأجرين في مسارات الحقل الخدميّة.

العطل: ``process-cdse`` و``prescription`` و``change`` كانت تكتفي بتوكن الخدمة المشترك —
وهو يُثبت أنّ المُنادي خدمة SAHOOL لا أيّ مستأجر يعمل له — فمستأجر B يعالج حقل A باسمه
أو يقرأ وصفته/تغيّره. و``process-cdse`` كانت تقصّ وتحفظ بهندسة الجسم لا هندسة الحقل
المخزّنة، وسجلّ الطبقات في الذاكرة مفهرس بـ``field_id`` وحده فيُعيد طبقة مستأجر آخر.

العقد بعد الإصلاح:
  * الثلاثة تستدعي ``_require_field_tenant`` ⇒ حقل مستأجر آخر = 403 قبل أيّ قراءة/جدولة.
  * ``process-cdse`` مع قاعدة: الهندسة وbbox **ومراجعتها** من جدول ``fields``/سجلّ
    ``field_geometry_history``، والمستأجر من السياق؛ هندسة الجسم تُتجاهَل، وغياب الهندسة
    المخزّنة ⇒ 400 بلا مهمّة، ومراجعة الجسم المخالفة للمخزّنة ⇒ 409 بلا مهمّة.
  * ``resolve_field_layer`` لا يُرجِع طبقة ذاكرة مالكها غير مستأجر الطلب.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import db_persist  # noqa: E402
import layer_lookup  # noqa: E402
import raster_security_context  # noqa: E402
import routers.fields as fields  # noqa: E402
from raster_api_models import (  # noqa: E402
    FieldChangeRequest,
    PrescriptionRequest,
    ProcessCdseRequest,
)

pytestmark = pytest.mark.unit

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
FIELD = "fld-t10-owned-by-a"

STORED = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.02, 15.0], [44.02, 15.03], [44.0, 15.03], [44.0, 15.0]]],
}
FOREIGN = {
    "type": "Polygon",
    "coordinates": [[[10.0, 50.0], [10.5, 50.0], [10.5, 50.5], [10.0, 50.5], [10.0, 50.0]]],
}


@pytest.fixture()
def as_tenant(monkeypatch):
    """يضبط مستأجر الطلب ومالك الحقل (A) بلا قاعدة حقيقيّة."""

    async def owner_is_a(field_id: str) -> str | None:
        return TENANT_A if field_id == FIELD else None

    monkeypatch.setattr(raster_security_context, "field_owner", owner_is_a)
    if "main" in sys.modules:  # _require_field_tenant يفضّل main._field_owner إن وُجد
        monkeypatch.setattr(sys.modules["main"], "_field_owner", owner_is_a, raising=False)
    monkeypatch.setattr(fields, "_require_service_token", lambda token: None)
    # يُضبط داخل الاختبار غير المتزامن: سياقه نسخةٌ خاصّة بمهمّته فلا يتسرّب لاختبار آخر.
    return raster_security_context.REQ_TENANT.set


def _fail_if_read(*_a, **_k):
    raise AssertionError("route read/queued data before proving field ownership")


@pytest.mark.asyncio
async def test_prescription_rejects_cross_tenant_field(as_tenant, monkeypatch):
    as_tenant(TENANT_B)
    monkeypatch.setattr(fields, "_resolve_field_layer", _fail_if_read)
    with pytest.raises(HTTPException) as exc:
        await fields.field_prescription(FIELD, PrescriptionRequest(), x_agent_token="ok")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_change_rejects_cross_tenant_field(as_tenant, monkeypatch):
    as_tenant(TENANT_B)
    monkeypatch.setattr(fields, "_real_field_grid", _fail_if_read)
    req = FieldChangeRequest(index="ndvi", date_a="2026-01-01", date_b="2026-02-01")
    with pytest.raises(HTTPException) as exc:
        await fields.field_change(FIELD, req, x_agent_token="ok")
    assert exc.value.status_code == 403


def _cdse_ready(monkeypatch) -> None:
    import cdse_client
    import imagery_source_gate

    monkeypatch.setattr(cdse_client, "is_configured", lambda: True)
    monkeypatch.setattr(imagery_source_gate, "enforce_enabled", lambda: False)


@pytest.mark.asyncio
async def test_process_cdse_rejects_cross_tenant_field(as_tenant, monkeypatch):
    as_tenant(TENANT_B)
    _cdse_ready(monkeypatch)
    tasks = BackgroundTasks()
    req = ProcessCdseRequest(bbox=[44.0, 15.0, 44.02, 15.03], indicators=["ndvi"])
    with pytest.raises(HTTPException) as exc:
        await fields.process_cdse(FIELD, req, tasks, x_agent_token="ok")
    assert exc.value.status_code == 403
    assert tasks.tasks == []


@pytest.mark.asyncio
async def test_process_cdse_uses_stored_geometry_not_body(as_tenant, monkeypatch):
    as_tenant(TENANT_A)
    _cdse_ready(monkeypatch)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://t10.invalid/db")
    seen: list[tuple] = []

    async def stored_geometry(field_id, tenant_id=None):
        seen.append((field_id, tenant_id))
        return {"geometry": STORED, "revision": 4}

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", stored_geometry)
    tasks = BackgroundTasks()
    req = ProcessCdseRequest(bbox=[10.0, 50.0, 10.5, 50.5], geometry=FOREIGN, indicators=["ndvi"])
    out = await fields.process_cdse(FIELD, req, tasks, x_agent_token="ok")
    assert out["queued"] is True
    assert seen == [(FIELD, TENANT_A)]
    (task,) = tasks.tasks
    queued_req = task.args[2]
    assert queued_req.geometry == STORED
    assert queued_req.bbox == [44.0, 15.0, 44.02, 15.03]
    # الطبقات تُنسَب لمستأجر السياق حتى لو غاب من الجسم (كانت تُحفَظ بمستأجر "").
    assert queued_req.tenant_id == TENANT_A


@pytest.mark.asyncio
async def test_process_cdse_without_stored_geometry_queues_nothing(as_tenant, monkeypatch):
    as_tenant(TENANT_A)
    _cdse_ready(monkeypatch)
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://t10.invalid/db")

    async def no_geometry(field_id, tenant_id=None):
        return None

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", no_geometry)
    tasks = BackgroundTasks()
    req = ProcessCdseRequest(bbox=[10.0, 50.0, 10.5, 50.5], geometry=FOREIGN, indicators=["ndvi"])
    with pytest.raises(HTTPException) as exc:
        await fields.process_cdse(FIELD, req, tasks, x_agent_token="ok")
    assert exc.value.status_code == 400
    assert tasks.tasks == []


# ── مراجعة PR #1324: نَسَب الهندسة يُقرأ مع الهندسة نفسها ─────────────────────
# كانت الهندسة تُستبدَل بالمخزّنة الحاليّة ويبقى ``geometry_revision`` من الجسم، فتُحفَظ
# المراجعة N نَسَباً (raster_cdse_processing → raster_asset_persistence) لأصلٍ قُصّ بهندسة
# N+1. العقد: الهندسة ومراجعتها من القاعدة معاً؛ مراجعةٌ في الجسم تخالف المخزّنة ⇒ 409 بلا
# مهمّة؛ مطابقةٌ أو غائبة ⇒ تُختَم المراجعة المخزّنة.


def _stored_revision(monkeypatch, revision):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://t10.invalid/db")

    async def stored(field_id, tenant_id=None):
        return {"geometry": STORED, "revision": revision}

    monkeypatch.setattr(db_persist, "fetch_field_geometry_with_revision", stored)


@pytest.mark.asyncio
@pytest.mark.parametrize(("stored_rev", "body_rev"), [(5, 4), (4, 5), (None, 4)])
async def test_process_cdse_stale_geometry_revision_is_409_and_queues_nothing(
    as_tenant, monkeypatch, stored_rev, body_rev
):
    as_tenant(TENANT_A)
    _cdse_ready(monkeypatch)
    _stored_revision(monkeypatch, stored_rev)
    tasks = BackgroundTasks()
    monkeypatch.setattr(fields._jobs, "set", _fail_if_read)  # لا سجلّ مهمّة قبل الرفض
    req = ProcessCdseRequest(
        bbox=[44.0, 15.0, 44.02, 15.03], indicators=["ndvi"], geometry_revision=body_rev
    )
    with pytest.raises(HTTPException) as exc:
        await fields.process_cdse(FIELD, req, tasks, x_agent_token="ok")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "stale_geometry_revision"
    assert exc.value.detail["requested_revision"] == body_rev
    assert exc.value.detail["current_revision"] == stored_rev
    assert tasks.tasks == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("stored_rev", "body_rev"), [(5, 5), (5, None), (None, None)])
async def test_process_cdse_stamps_the_stored_geometry_revision(
    as_tenant, monkeypatch, stored_rev, body_rev
):
    as_tenant(TENANT_A)
    _cdse_ready(monkeypatch)
    _stored_revision(monkeypatch, stored_rev)
    tasks = BackgroundTasks()
    req = ProcessCdseRequest(
        bbox=[10.0, 50.0, 10.5, 50.5],
        geometry=FOREIGN,
        indicators=["ndvi"],
        geometry_revision=body_rev,
    )
    out = await fields.process_cdse(FIELD, req, tasks, x_agent_token="ok")
    assert out["queued"] is True
    (task,) = tasks.tasks
    queued_req = task.args[2]
    assert queued_req.geometry == STORED
    assert queued_req.geometry_revision == stored_rev


def _layer(layer_id: str, tenant: str, acquired: str) -> dict:
    return {
        "layer_id": layer_id,
        "field_id": FIELD,
        "tenant_id": tenant,
        "index": "ndvi",
        "cog_url": f"file:///tmp/{layer_id}.tif",
        "acquisition_date": acquired,
        "created_at": acquired,
    }


async def _resolve(layers, field_layers, tenant: str | None, date: str = "latest"):
    return await layer_lookup.resolve_field_layer(
        FIELD,
        "ndvi",
        date,
        layers=layers,
        field_layers=field_layers,
        tenant_getter=lambda: tenant,
        logger=None,
        object_store_module=None,
    )


@pytest.mark.asyncio
async def test_in_memory_layer_of_another_tenant_is_not_returned(monkeypatch):
    async def no_db(*_a, **_k):
        return None

    monkeypatch.setattr(layer_lookup, "rehydrate_field_layer_from_db", no_db)
    layers = {
        "a_old": _layer("a_old", TENANT_A, "2026-05-01T08:00:00Z"),
        "b_new": _layer("b_new", TENANT_B, "2026-06-01T08:00:00Z"),
    }
    field_layers = {FIELD: ["a_old", "b_new"]}

    # B يرى طبقته فقط؛ A لا يرى طبقة B الأحدث ولا تحجب طبقته الأقدم.
    assert (await _resolve(layers, field_layers, TENANT_B))["layer_id"] == "b_new"
    assert (await _resolve(layers, field_layers, TENANT_A))["layer_id"] == "a_old"
    assert await _resolve(layers, field_layers, TENANT_A, "2026-06-01") is None
    # بلا سياق مستأجر لا تُقرأ طبقة مملوكة.
    assert await _resolve(layers, field_layers, None) is None
