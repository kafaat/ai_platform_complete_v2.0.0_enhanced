"""G-H1: عزل بلاطات CDSE — حقلٌ مجهول يُرفَض، وهندسة العميل لا تتجاوز حدود الحقل.

العطلان (مراجعة خارجيّة):
  * ``require_field_tenant`` كان يمرّر الطلب حين لا يُعرَف للحقل مالك في ``fields``
    (فرع «field not known»)، فأيّ مستخدم مُصادَق يسمّي ``field_id`` غير موجود يصيّر
    بلاطات CDSE على الحصّة المشتركة.
  * ``poly``/``bbox`` العميل كانا يحلّان محلّ حدود الحقل بلا سقف مساحة — حتّى الكرة كلّها.

العقد: حقلٌ بلا مالك والقاعدة مُهيّأة (أو الإنتاج) ⇒ 403/404؛ ``poly`` خارج حدود الحقل
المخزّنة ⇒ تُستعمَل الهندسة المخزّنة؛ ``bbox`` يُقصّ إلى حدود الحقل؛ وبلا حدود مخزّنة
تُرفَض الهندسة فوق السقف بـ422 قبل أيّ نداء CDSE.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import cdse_client  # noqa: E402
import db_persist  # noqa: E402
import imagery_source_gate  # noqa: E402
import raster_cdse_tile_runtime as rt  # noqa: E402
import raster_security_context as rsc  # noqa: E402

pytestmark = pytest.mark.unit

TENANT_A = "11111111-1111-1111-1111-111111111111"
LOG = logging.getLogger("test-g-h1")

FIELD_GEOM = {
    "type": "Polygon",
    "coordinates": [[[44.0, 15.0], [44.02, 15.0], [44.02, 15.03], [44.0, 15.03], [44.0, 15.0]]],
}
GLOBE_POLY = "-180,-85;180,-85;180,85;-180,85"


async def _no_owner(_field_id: str) -> str | None:
    return None


async def _check(field_id: str, *, hide: bool = False) -> None:
    await rsc.require_field_tenant(
        field_id,
        hide_existence=hide,
        layers={},
        field_layers={},
        logger=LOG,
        owner_lookup=_no_owner,
    )


@pytest.mark.asyncio
async def test_unknown_field_is_refused_when_db_configured(monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "postgresql://g-h1.invalid/db")
    rsc.REQ_TENANT.set(TENANT_A)
    with pytest.raises(HTTPException) as exc:
        await _check("fld-does-not-exist")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await _check("fld-does-not-exist", hide=True)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_field_is_refused_in_production_without_db(monkeypatch):
    monkeypatch.setattr(db_persist, "DATABASE_URL", "")
    monkeypatch.setenv("SAHOOL_ENV", "production")
    rsc.REQ_TENANT.set(TENANT_A)
    with pytest.raises(HTTPException) as exc:
        await _check("fld-does-not-exist")
    assert exc.value.status_code == 403


def _cdse_on(monkeypatch, stored):
    monkeypatch.setattr(cdse_client, "is_configured", lambda: True)
    monkeypatch.setattr(imagery_source_gate, "enforce_enabled", lambda: False)

    async def stored_geometry(field_id, tenant_id=None):
        return stored

    monkeypatch.setattr(db_persist, "fetch_field_geometry", stored_geometry)


def _inside(bbox, outer, tol=1e-9):
    return (
        bbox[0] >= outer[0] - tol
        and bbox[1] >= outer[1] - tol
        and bbox[2] <= outer[2] + tol
        and bbox[3] <= outer[3] + tol
    )


@pytest.mark.asyncio
async def test_client_globe_poly_cannot_replace_field_bounds(monkeypatch):
    _cdse_on(monkeypatch, FIELD_GEOM)
    params = await rt.normalize_cdse_request(
        "fld-a", "ndvi", "latest", (None, None, None, None), GLOBE_POLY
    )
    assert params is not None
    assert _inside(params["field_bbox"], [44.0, 15.0, 44.02, 15.03])
    assert params["field_geom"] == FIELD_GEOM


@pytest.mark.asyncio
async def test_client_globe_bbox_is_clipped_to_field_bounds(monkeypatch):
    _cdse_on(monkeypatch, FIELD_GEOM)
    params = await rt.normalize_cdse_request(
        "fld-a", "ndvi", "latest", (-180.0, -85.0, 180.0, 85.0), None
    )
    assert params is not None
    assert params["field_bbox"] == [44.0, 15.0, 44.02, 15.03]


@pytest.mark.asyncio
async def test_client_poly_inside_field_is_kept(monkeypatch):
    _cdse_on(monkeypatch, FIELD_GEOM)
    inner = "44.001,15.001;44.019,15.001;44.019,15.029;44.001,15.029"
    params = await rt.normalize_cdse_request(
        "fld-a", "ndvi", "latest", (None, None, None, None), inner
    )
    assert params["field_geom"] == rt.parse_poly(inner)


@pytest.mark.asyncio
async def test_without_stored_bounds_large_client_geometry_is_refused(monkeypatch):
    _cdse_on(monkeypatch, None)
    with pytest.raises(HTTPException) as exc:
        await rt.normalize_cdse_request(
            "fld-a", "ndvi", "latest", (None, None, None, None), GLOBE_POLY
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "client_geometry_too_large"


@pytest.mark.asyncio
async def test_without_stored_bounds_field_sized_geometry_is_accepted(monkeypatch):
    _cdse_on(monkeypatch, None)
    small = "44.0,15.0;44.02,15.0;44.02,15.03;44.0,15.03"
    params = await rt.normalize_cdse_request(
        "fld-a", "ndvi", "latest", (None, None, None, None), small
    )
    assert params["field_bbox"] == [44.0, 15.0, 44.02, 15.03]


def test_bbox_outside_field_is_refused():
    with pytest.raises(HTTPException) as exc:
        rt.bound_client_geometry(None, [10.0, 50.0, 10.5, 50.5], FIELD_GEOM)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "bbox_outside_field"
