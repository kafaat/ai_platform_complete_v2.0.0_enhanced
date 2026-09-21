"""D1 — the platform no longer writes raster-owned tables; it sends write commands.

``raster_registry`` and ``raster_cache_invalidations`` are owned by raster-service
(docs/architecture/db_ownership.yml). The platform used to INSERT into both directly
(``POST /cog-registry`` and ``spatial_sync.mark_raster_cache_stale``). This file measures
the HTTP boundary of the platform side after the cutover:

  • ``/cog-registry`` builds the STAC item from the row raster-service persisted, keeps
    its response shape, and surfaces raster-service failures as 502 without leaking the
    internal host or the raw exception;
  • the platform source carries no direct SQL against either table any more, and the
    invalidation call sites no longer pass a DB connection (the write is not theirs).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

PLATFORM = Path(__file__).resolve().parents[1]
TENANT = "11111111-1111-1111-1111-111111111111"


def _client(monkeypatch, register_cog_asset):
    from api.main import UserSchema, get_current_user
    from api.routers import gis_cloud_native
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(gis_cloud_native, "register_cog_asset", register_cog_asset)
    app = FastAPI()
    app.include_router(gis_cloud_native.router)
    app.dependency_overrides[get_current_user] = lambda: UserSchema(
        user_id="42", tenant_id=TENANT, role="owner", name_ar="اختبار"
    )
    return TestClient(app, raise_server_exceptions=False)


_BODY = {
    "field_id": "fld_d1",
    "scene_id": "S2A_X",
    "product_date": "2026-09-08",
    "index_type": "ndvi",
    "cog_url": "https://cdn.example/ndvi.tif",
    "cloud_pct": 3.5,
    "bbox": [44.3, 16.7, 44.4, 16.8],
}


@pytest.mark.unit
def test_cog_registry_sends_a_write_command_and_builds_stac_from_the_persisted_row(monkeypatch):
    seen: dict = {}

    async def _register(*, tenant_id, payload, timeout_s=15.0):
        seen["tenant_id"] = tenant_id
        seen["payload"] = payload
        return {
            "registered": True,
            "entry": {
                "id": "row-1",
                "tenant_id": tenant_id,
                "field_id": payload["field_id"],
                "scene_id": payload["scene_id"],
                "product_date": payload["product_date"],
                "index_type": payload["index_type"],
                "cog_url": payload["cog_url"],
                "cloud_pct": payload["cloud_pct"],
                "quality_score": payload["quality_score"],
                "resolution_m": payload["resolution_m"],
                "bbox": "[44.3, 16.7, 44.4, 16.8]",
                "bands": "{}",
                "metadata": '{"quality": {"score": 1}}',
            },
        }

    with _client(monkeypatch, _register) as client:
        response = client.post("/api/v1/gis/cloud-native/cog-registry", json=_BODY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["registered"] is True and "quality" in body
    assert body["stac_item"]["id"] == "S2A_X"
    assert seen["tenant_id"] == TENANT
    assert seen["payload"]["field_id"] == "fld_d1"
    assert seen["payload"]["quality_score"] == body["quality"]["score"]
    assert seen["payload"]["metadata"]["quality"]["score"] == body["quality"]["score"]


@pytest.mark.unit
def test_cog_registry_requires_a_field_id_because_the_owner_key_includes_it(monkeypatch):
    async def _never(**_kwargs):
        raise AssertionError("no command without a field_id")

    with _client(monkeypatch, _never) as client:
        response = client.post(
            "/api/v1/gis/cloud-native/cog-registry", json={**_BODY, "field_id": None}
        )
    assert response.status_code == 422, response.text


@pytest.mark.unit
def test_cog_registry_surfaces_raster_service_refusals_verbatim(monkeypatch):
    async def _refuse(**_kwargs):
        raise HTTPException(status_code=403, detail="الحقل لا يخصّ مستأجِرك")

    with _client(monkeypatch, _refuse) as client:
        response = client.post("/api/v1/gis/cloud-native/cog-registry", json=_BODY)
    assert response.status_code == 403
    assert response.json()["detail"] == "الحقل لا يخصّ مستأجِرك"


@pytest.mark.unit
def test_cog_registry_hides_transport_internals_behind_a_502(monkeypatch):
    async def _blow_up(**_kwargs):
        raise ConnectionError("private-raster-host:8001 refused")

    with _client(monkeypatch, _blow_up) as client:
        response = client.post("/api/v1/gis/cloud-native/cog-registry", json=_BODY)
    assert response.status_code == 502, response.text
    assert "private-raster-host" not in response.text
    assert "تعذّر" in response.json()["detail"]


@pytest.mark.unit
def test_cog_registry_refuses_an_acknowledgement_without_a_row(monkeypatch):
    async def _empty(**_kwargs):
        return {"registered": True}

    with _client(monkeypatch, _empty) as client:
        response = client.post("/api/v1/gis/cloud-native/cog-registry", json=_BODY)
    assert response.status_code == 502


@pytest.mark.unit
def test_platform_source_has_no_direct_sql_against_the_raster_owned_tables():
    gis = (PLATFORM / "api" / "routers" / "gis_cloud_native.py").read_text(encoding="utf-8")
    spatial = (PLATFORM / "api" / "spatial_sync.py").read_text(encoding="utf-8")
    assert "INSERT INTO raster_registry" not in gis
    assert "INSERT INTO raster_cache_invalidations" not in spatial
    assert "register_cog_asset(" in gis
    assert "INSERT INTO processing_jobs" in spatial  # the platform-owned intent
    assert "enqueue_raster_cache_invalidation" in spatial  # المُوصِّل بعد الالتزام، استيرادٌ كسول


@pytest.mark.unit
def test_invalidation_call_sites_still_write_the_intent_on_the_transaction_connection():
    """The intent is the platform's own row and must live in the field transaction: every
    call site hands over ``conn``, and no HTTP client is reachable from the helper."""
    import re

    src = (PLATFORM / "api" / "routers" / "fields.py").read_text(encoding="utf-8")
    calls = re.findall(r"mark_raster_cache_stale\(\s*([^,\n]+)", src)
    assert len(calls) >= 3, calls
    assert all(arg.strip() == "conn" for arg in calls), calls
    import ast

    tree = ast.parse((PLATFORM / "api" / "spatial_sync.py").read_text(encoding="utf-8"))
    helper = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "mark_raster_cache_stale"
    )
    reached = {n.id for n in ast.walk(helper) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(helper) if isinstance(n, ast.Attribute)
    }
    assert not reached & {"enqueue_raster_cache_invalidation", "raster_service_client", "httpx"}
    # العميلُ يُستورَد كسولاً داخل المُوصِّل فقط، لا على مستوى الوحدة.
    assert not any(
        "raster_service_client" in (getattr(n, "module", "") or "")
        for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
    )
