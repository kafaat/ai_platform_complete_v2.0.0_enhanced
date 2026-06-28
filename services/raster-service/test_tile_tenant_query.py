"""حارس مهم لمسار NDVI عبر Leaflet/MapLibre.

TileLayer يحمّل البلاطات كصور ولا يمرّر ترويسات axios. الواجهة تضيف `tid` إلى
رابط البلاطة؛ يجب أن يمرّ هذا tenant hint إلى db_persist.fetch_latest_asset
كي لا ترجع الخدمة بلاطات شفافة بعد إعادة التشغيل عندما تكون _field_layers فارغة.
"""

import db_persist
import main
from fastapi.testclient import TestClient


def test_tilejson_query_tid_rehydrates_db_with_tenant(monkeypatch):
    main._layers.clear()
    main._field_layers.clear()
    calls = []

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append(
            {
                "field_id": field_id,
                "index_name": index_name,
                "date": date,
                "tenant_id": tenant_id,
            }
        )
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get("/v1/fields/F-123/tilejson?index=ndvi&date=latest&tid=T-1")

    assert resp.status_code == 200
    assert calls, "expected DB rehydrate attempt"
    assert calls[-1]["tenant_id"] == "T-1"


def test_tile_query_tid_is_used_when_rendering_after_restart(monkeypatch):
    main._layers.clear()
    main._field_layers.clear()
    calls = []

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append((field_id, index_name, date, tenant_id))
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get("/v1/fields/F-123/tiles/14/100/100.png?index=ndvi&tid=T-1&v=123")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert calls[-1][-1] == "T-1"


def test_tilejson_tiles_propagate_tid_and_cache_version(monkeypatch):
    main._layers.clear()
    main._field_layers.clear()

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get("/v1/fields/F-123/tilejson?index=ndvi&date=latest&tid=T-1&v=999")

    assert resp.status_code == 200
    tile_url = resp.json()["tiles"][0]
    assert "tid=T-1" in tile_url
    assert "v=999" in tile_url


def test_header_tenant_has_priority_over_query_tid(monkeypatch):
    main._layers.clear()
    main._field_layers.clear()
    calls = []

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append(tenant_id)
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tilejson?index=ndvi&tid=query-tenant",
        headers={"X-Tenant-Id": "header-tenant"},
    )

    assert resp.status_code == 200
    assert calls[-1] == "header-tenant"
    assert "tid=header-tenant" in resp.json()["tiles"][0]


def test_tilejson_hides_cross_tenant_field(monkeypatch):
    """tilejson لا يكشف وجود حقل tenant آخر، ويرجع 404 عام."""
    main._layers.clear()
    main._field_layers.clear()
    main._field_owner_cache.clear()

    async def fake_field_owner(field_id):
        assert field_id == "OTHER-TENANT-FIELD"
        return "tenant-2"

    monkeypatch.setattr(main, "_field_owner", fake_field_owner)

    client = TestClient(main.app)
    resp = client.get("/v1/fields/OTHER-TENANT-FIELD/tilejson?index=ndvi&tid=tenant-1")

    assert resp.status_code == 404
    assert "not" not in resp.text.lower() or "found" in resp.text.lower()


def test_tilejson_contract_chain_uses_returned_tid_url(monkeypatch):
    """السلسلة tilejson→tiles تحفظ tid داخل URL البلاطة الراجع."""
    main._layers.clear()
    main._field_layers.clear()
    main._field_owner_cache.clear()
    calls = []

    async def fake_field_owner(field_id):
        return "tenant-1"

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append((field_id, index_name, date, tenant_id))
        return None

    monkeypatch.setattr(main, "_field_owner", fake_field_owner)
    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    tj = client.get("/v1/fields/F-123/tilejson?index=ndvi&tid=tenant-1&v=abc")
    assert tj.status_code == 200
    tile_url = tj.json()["tiles"][0]
    assert "tid=tenant-1" in tile_url
    assert "v=abc" in tile_url

    concrete_url = tile_url.replace("{z}", "14").replace("{x}", "123").replace("{y}", "456")
    tile = client.get(concrete_url)
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"
    assert calls[-1][-1] == "tenant-1"
