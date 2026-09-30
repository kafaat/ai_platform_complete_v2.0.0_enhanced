"""حارس مسار NDVI عبر Leaflet/MapLibre — المستأجِر من الترويسة الموثوقة وحدَها.

TileLayer يحمّل البلاطات كصور ولا يمرّر ترويسات axios؛ فكانت الواجهة تضيف ``tid`` إلى
رابط البلاطة والخدمة تقرؤه. لكنّ ``?tid=`` لا يسأل مَن يُنادي: التدقيق الحيّ
(2026-09-29) قرأ صور مستأجِرٍ آخر بكتابة معرّفه في الاستعلام (RASTER-TENANT-TRUST-01).
اليوم تمرّ بلاطات ``<img>`` بالبوّابة التي تتحقّق من الكوكي عبر auth_request وتحقن
``X-Tenant-Id`` الموثَّق مع توكن الخدمة، فالعقد هنا: الترويسة تصل إلى
``db_persist.fetch_latest_asset`` بعد إعادة التشغيل، و``tid`` لا يصل أبداً ولا يُصدَر.
"""

import db_persist
import main
from fastapi.testclient import TestClient


def _capture_fetch(monkeypatch, calls):
    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append((field_id, index_name, date, tenant_id))
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)


def _reset():
    main._layers.clear()
    main._field_layers.clear()
    main._field_owner_cache.clear()


def test_tilejson_header_tenant_rehydrates_db_with_tenant(monkeypatch):
    _reset()
    calls = []
    _capture_fetch(monkeypatch, calls)
    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tilejson?index=ndvi&date=latest", headers={"X-Tenant-Id": "T-1"}
    )
    assert resp.status_code == 200
    assert calls, "expected DB rehydrate attempt"
    assert calls[-1][-1] == "T-1"


def test_tile_header_tenant_is_used_when_rendering_after_restart(monkeypatch):
    _reset()
    calls = []
    _capture_fetch(monkeypatch, calls)
    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tiles/14/100/100.png?index=ndvi&v=123", headers={"X-Tenant-Id": "T-1"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert calls[-1][-1] == "T-1"


def test_query_tid_never_reaches_the_db_layer(monkeypatch):
    """``?tid=``/``?tenant_id=`` بلا ترويسة ⇒ لا مستأجِر (كان: مستأجِر الاستعلام يصل للقاعدة)."""
    for param in ("tid", "tenant_id"):
        _reset()
        calls = []
        _capture_fetch(monkeypatch, calls)
        client = TestClient(main.app)
        client.get(f"/v1/fields/F-123/tilejson?index=ndvi&{param}=victim-tenant")
        client.get(f"/v1/fields/F-123/tiles/14/100/100.png?index=ndvi&{param}=victim-tenant")
        assert all(c[-1] != "victim-tenant" for c in calls), (param, calls)


def test_header_tenant_wins_and_query_tid_is_not_echoed(monkeypatch):
    _reset()
    calls = []
    _capture_fetch(monkeypatch, calls)
    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tilejson?index=ndvi&tid=query-tenant&v=999",
        headers={"X-Tenant-Id": "header-tenant"},
    )
    assert resp.status_code == 200
    assert calls[-1][-1] == "header-tenant"
    tile_url = resp.json()["tiles"][0]
    assert "tid=" not in tile_url and "tenant" not in tile_url
    assert "v=999" in tile_url


def test_tilejson_hides_cross_tenant_field(monkeypatch):
    """tilejson لا يكشف وجود حقل tenant آخر، ويرجع 404 عام."""
    _reset()

    async def fake_field_owner(field_id):
        assert field_id == "OTHER-TENANT-FIELD"
        return "tenant-2"

    monkeypatch.setattr(main, "_field_owner", fake_field_owner)
    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/OTHER-TENANT-FIELD/tilejson?index=ndvi", headers={"X-Tenant-Id": "tenant-1"}
    )
    assert resp.status_code == 404


def test_tilejson_contract_chain_keeps_the_version_and_the_header(monkeypatch):
    """السلسلة tilejson→tiles: الرابط الراجع يحفظ v، والبلاطة تُقرأ بمستأجِر الترويسة."""
    _reset()
    calls = []

    async def fake_field_owner(field_id):
        return "tenant-1"

    monkeypatch.setattr(main, "_field_owner", fake_field_owner)
    _capture_fetch(monkeypatch, calls)
    client = TestClient(main.app)
    headers = {"X-Tenant-Id": "tenant-1"}
    tj = client.get("/v1/fields/F-123/tilejson?index=ndvi&v=abc", headers=headers)
    assert tj.status_code == 200
    tile_url = tj.json()["tiles"][0]
    assert "v=abc" in tile_url and "tid=" not in tile_url

    concrete_url = tile_url.replace("{z}", "14").replace("{x}", "123").replace("{y}", "456")
    tile = client.get(concrete_url, headers=headers)
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"
    assert calls[-1][-1] == "tenant-1"
    # والرابط نفسه بلا الترويسة لا يحمل مستأجِراً: الحقل مملوك ⇒ 403 لا بلاطة.
    assert client.get(concrete_url).status_code == 403
