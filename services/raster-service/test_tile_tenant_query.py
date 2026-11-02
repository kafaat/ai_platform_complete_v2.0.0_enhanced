"""حارس مهم لمسار NDVI عبر Leaflet/MapLibre.

TileLayer يحمّل البلاطات كصور ولا يمرّر ترويسات axios. الواجهة تضيف `tid` إلى
رابط البلاطة؛ يجب أن يمرّ هذا tenant hint إلى db_persist.fetch_latest_asset
كي لا ترجع الخدمة بلاطات شفافة بعد إعادة التشغيل عندما تكون _field_layers فارغة.

عقد المصدر الموثَّق (تدقيق 2026-11-01): `tid`/`tenant_id` تلميحٌ فقط — يُقبَل حين يطابق
مستأجراً موثَّقاً (رأس X-Tenant-Id من البوّابة، أو JWT مُتحقَّق في `access_token`/`Authorization`
للتطوير بلا بوّابة)، وإلّا 403. كان `tid` وحده يختار المستأجر لأيّ مُنادٍ يبلغ الخدمة مباشرةً.
"""

import secrets
from datetime import UTC, datetime, timedelta

import db_persist
import jwt
import main
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def sign(monkeypatch):
    """يوقّع JWT صالحاً بمفتاح اختبار (نفس المُتحقِّق المشترك الذي تستعمله الخدمة)."""
    key = secrets.token_urlsafe(48)
    monkeypatch.setenv("JWT_SECRET", key)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")

    def _sign(tenant: str, *, signing_key: str = key) -> str:
        claims = {
            "sub": "tile-witness",
            "tenant_id": tenant,
            "iss": "sahool-auth",
            "aud": "sahool",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        }
        return jwt.encode(claims, signing_key, algorithm="HS256")

    return _sign


def test_tilejson_query_tid_rehydrates_db_with_tenant(monkeypatch, sign):
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
    resp = client.get(
        f"/v1/fields/F-123/tilejson?index=ndvi&date=latest&tid=T-1&access_token={sign('T-1')}"
    )

    assert resp.status_code == 200
    assert calls, "expected DB rehydrate attempt"
    assert calls[-1]["tenant_id"] == "T-1"


def test_tile_query_tid_is_used_when_rendering_after_restart(monkeypatch, sign):
    main._layers.clear()
    main._field_layers.clear()
    calls = []

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append((field_id, index_name, date, tenant_id))
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tiles/14/100/100.png?index=ndvi&tid=T-1&v=123",
        headers={"Authorization": f"Bearer {sign('T-1')}"},
    )

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
    resp = client.get(
        "/v1/fields/F-123/tilejson?index=ndvi&date=latest&tid=T-1&v=999",
        headers={"X-Tenant-Id": "T-1"},
    )

    assert resp.status_code == 200
    tile_url = resp.json()["tiles"][0]
    assert "tid=T-1" in tile_url
    assert "v=999" in tile_url


def test_header_tenant_has_priority_over_token_and_matching_tid(monkeypatch, sign):
    """رأس البوّابة هو المصدر الموثَّق الأوّل: يسبق JWT آخر، و`tid` المطابق له يُقبَل."""
    main._layers.clear()
    main._field_layers.clear()
    calls = []

    async def fake_fetch_latest_asset(field_id, index_name, date=None, tenant_id=None):
        calls.append(tenant_id)
        return None

    monkeypatch.setattr(db_persist, "fetch_latest_asset", fake_fetch_latest_asset)

    client = TestClient(main.app)
    resp = client.get(
        "/v1/fields/F-123/tilejson?index=ndvi&tid=header-tenant",
        headers={
            "X-Tenant-Id": "header-tenant",
            "Authorization": f"Bearer {sign('token-tenant')}",
        },
    )

    assert resp.status_code == 200
    assert calls[-1] == "header-tenant"
    assert "tid=header-tenant" in resp.json()["tiles"][0]


def _no_db_read(monkeypatch):
    async def must_not_read(*_a, **_k):
        raise AssertionError("tenant data read before the tenant hint was verified")

    monkeypatch.setattr(db_persist, "fetch_latest_asset", must_not_read)
    main._layers.clear()
    main._field_layers.clear()


def test_query_tid_that_differs_from_gateway_header_is_rejected(monkeypatch):
    _no_db_read(monkeypatch)
    client = TestClient(main.app)
    for hint in ("tid", "tenant_id"):
        resp = client.get(
            f"/v1/fields/F-123/tilejson?index=ndvi&{hint}=tenant-B",
            headers={"X-Tenant-Id": "tenant-A"},
        )
        assert resp.status_code == 403, hint


def test_query_tid_without_verified_source_is_rejected(monkeypatch, sign):
    """بلا بوّابة: `tid` وحده — أو مع JWT مزوَّر — لا يختار مستأجراً."""
    _no_db_read(monkeypatch)
    client = TestClient(main.app)
    forged = sign("tenant-B", signing_key=secrets.token_urlsafe(48))
    for url in (
        "/v1/fields/F-123/tilejson?index=ndvi&tid=tenant-B",
        "/v1/fields/F-123/tiles/14/100/100.png?index=ndvi&tenant_id=tenant-B",
        f"/v1/fields/F-123/tilejson?index=ndvi&tid=tenant-B&access_token={forged}",
    ):
        assert client.get(url).status_code == 403, url


def test_query_tid_that_differs_from_verified_token_is_rejected(monkeypatch, sign):
    _no_db_read(monkeypatch)
    client = TestClient(main.app)
    resp = client.get(
        f"/v1/fields/F-123/tilejson?index=ndvi&tid=tenant-B&access_token={sign('tenant-A')}"
    )
    assert resp.status_code == 403


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
    resp = client.get(
        "/v1/fields/OTHER-TENANT-FIELD/tilejson?index=ndvi&tid=tenant-1",
        headers={"X-Tenant-Id": "tenant-1"},
    )

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
    gateway = {"X-Tenant-Id": "tenant-1"}  # البوّابة تحقن المستأجر الموثَّق في كلّ قفزة
    tj = client.get("/v1/fields/F-123/tilejson?index=ndvi&tid=tenant-1&v=abc", headers=gateway)
    assert tj.status_code == 200
    tile_url = tj.json()["tiles"][0]
    assert "tid=tenant-1" in tile_url
    assert "v=abc" in tile_url

    concrete_url = tile_url.replace("{z}", "14").replace("{x}", "123").replace("{y}", "456")
    tile = client.get(concrete_url, headers=gateway)
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "image/png"
    assert calls[-1][-1] == "tenant-1"
