"""عقد HTTP لبلاطات الحقل ومصغّراته (MAP-02 + P3-LIM).

* **MAP-02** — بلاطات/مصغّرات الحقل بيانات **مستأجِر** تُفوَّض بالجلسة، ورابطها لا يحمل
  المستأجِر دائماً (الواجهة تُسقط ``tid`` في الإنتاج). ``Cache-Control: public`` كان يأذن
  لأيّ مخزن مشترك (CDN/وسيط) بإعادة تقديم بايتات مستأجِر لجلسة أخرى بالرابط نفسه. العقد:
  ``private`` + ``Vary`` على ترويسات الهويّة (Authorization · Cookie · X-Tenant-Id).
* **P3-LIM (XYZ)** — ``z/x/y`` تُفحَص في مساعد واحد **قبل** التفويض وقراءة الذاكرة
  المؤقّتة وأيّ عمل CDSE/تصيير: ``0 ≤ z ≤ 22`` و``0 ≤ x,y < 2**z`` وإلّا 422.
* **P3-LIM (fanout)** — ``/timeseries?dates=`` الصريحة تُزال تكراراتها وتُحدّ بسقف؛
  تجاوزه 422 برسالة صريحة بدل N قراءة شبكة.

تكذيب: إرجاع ``public`` في أيّ فرع، أو حذف ``validate_xyz`` من أحد المسارين، أو حذف
السقف — يُسقط اختباراً مسمّى هنا.
"""

from __future__ import annotations

import main
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_IDENTITY_HEADERS = {"authorization", "cookie", "x-tenant-id"}


def _assert_tenant_private(resp) -> None:
    cc = resp.headers.get("cache-control", "")
    assert "public" not in cc, f"بلاطة مستأجِر قابلة للتخزين المشترك: {cc!r}"
    assert "private" in cc, f"متوقّع private، وُجد {cc!r}"
    vary = {v.strip().lower() for v in resp.headers.get("vary", "").split(",") if v.strip()}
    assert _IDENTITY_HEADERS <= vary, f"Vary لا يغطّي ترويسات الهويّة: {vary!r}"


async def _noop_async(*_args, **_kwargs):
    return None


@pytest.fixture
def client():
    return TestClient(main.app)


# ── MAP-02: field tile (miss ثمّ hit) ──────────────────────────────────────────


def test_field_tile_render_and_cache_hit_are_tenant_private(monkeypatch, tmp_path, client):
    import tile_render
    from routers import fields

    monkeypatch.setattr(fields, "_require_field_tenant", _noop_async)

    async def _layer(*_a, **_k):
        return {"cog_url": f"file://{tmp_path}/x.tif"}

    monkeypatch.setattr(fields, "_resolve_field_layer", _layer)
    monkeypatch.setattr(tile_render, "render_tile_png", lambda *_a, **_k: _PNG)
    store: dict[str, bytes] = {}
    monkeypatch.setattr(fields, "_read_tile_cache", lambda p: store.get(p))
    monkeypatch.setattr(fields, "_write_tile_cache", lambda p, b: store.__setitem__(p, b))

    miss = client.get("/v1/fields/F-map02/tiles/14/100/100.png", params={"index": "ndvi"})
    assert miss.status_code == 200
    assert miss.headers["X-Sahool-Tile-Cache"] == "miss"
    _assert_tenant_private(miss)

    hit = client.get("/v1/fields/F-map02/tiles/14/100/100.png", params={"index": "ndvi"})
    assert hit.headers["X-Sahool-Tile-Cache"] == "hit"
    _assert_tenant_private(hit)


# ── MAP-02: CDSE tile + thumbnails (live و persisted) ─────────────────────────


@pytest.fixture
def cdse_stubbed(monkeypatch):
    import tile_render
    from routers import cdse_tiles

    monkeypatch.setattr(cdse_tiles, "_require_field", _noop_async)

    async def _normalize(*_a, **_k):
        return {
            "internal": "ndvi",
            "field_bbox": None,
            "today": "2026-06-18",
            "date_from": "2026-06-18",
            "date_to": "2026-06-18",
            "field_geom": None,
            "has_poly": False,
        }

    async def _cog(*_a, **_k):
        return "/tmp/fake.tif"

    monkeypatch.setattr(cdse_tiles, "_normalize_cdse_request", _normalize)
    monkeypatch.setattr(cdse_tiles, "_ensure_field_cog", _cog)
    monkeypatch.setattr(tile_render, "render_tile_png", lambda *_a, **_k: _PNG)
    monkeypatch.setattr(tile_render, "render_cog_thumbnail_png", lambda *_a, **_k: _PNG)
    return cdse_tiles


def test_cdse_tile_is_tenant_private(cdse_stubbed, client):
    resp = client.get("/v1/fields/F-map02/cdse-tiles/14/100/100.png")
    assert resp.status_code == 200 and resp.content == _PNG
    _assert_tenant_private(resp)


def test_cdse_live_thumbnail_is_tenant_private(cdse_stubbed, client):
    resp = client.get("/v1/fields/F-map02/cdse-thumbnail.png", params={"source": "auto"})
    assert resp.status_code == 200 and resp.content == _PNG
    _assert_tenant_private(resp)


def test_cdse_persisted_thumbnail_is_tenant_private(monkeypatch, cdse_stubbed, client):
    import object_store

    async def _asset(*_a, **_k):
        return {"cog_url": "/data/a.tif", "acquisition_date": "2026-06-18"}

    monkeypatch.setattr(cdse_stubbed._db, "fetch_latest_asset", _asset)
    monkeypatch.setattr(object_store, "exists_locally", lambda _u: True)
    resp = client.get(
        "/v1/fields/F-map02/cdse-thumbnail.png",
        params={"source": "persisted", "date": "2026-06-18"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Imagery-State"] == "ready"
    _assert_tenant_private(resp)


# ── P3-LIM: XYZ validated early (422) on both tile routes ─────────────────────

_INVALID_XYZ = [
    (-1, 0, 0),  # zoom سالب
    (23, 0, 0),  # فوق سقف 22 (نفس عقد shared/gis/cog_tile_proxy)
    (1, 2, 0),  # x ≥ 2**z
    (1, 0, 2),  # y ≥ 2**z
    (3, -1, 0),  # x سالب
    (3, 0, -1),  # y سالب
    (10_000, 0, 0),  # 2**z ضخم — يُرفَض قبل أيّ حساب
]


def _forbid_work(monkeypatch):
    """أيّ وصول إلى التفويض/الذاكرة/CDSE لإحداثيّ باطل خرقٌ لترتيب الفحص."""
    from routers import cdse_tiles, fields

    def _boom(*_a, **_k):
        raise AssertionError("عمل نُفِّذ قبل فحص XYZ")

    async def _aboom(*_a, **_k):
        raise AssertionError("عمل نُفِّذ قبل فحص XYZ")

    monkeypatch.setattr(fields, "_require_field_tenant", _aboom)
    monkeypatch.setattr(fields, "_tile_cache_key", _boom)
    monkeypatch.setattr(cdse_tiles, "_require_field", _aboom)
    monkeypatch.setattr(cdse_tiles, "_normalize_cdse_request", _aboom)


@pytest.mark.parametrize(("z", "x", "y"), _INVALID_XYZ)
def test_field_tile_rejects_invalid_xyz_before_any_work(monkeypatch, client, z, x, y):
    _forbid_work(monkeypatch)
    resp = client.get(f"/v1/fields/F-xyz/tiles/{z}/{x}/{y}.png")
    assert resp.status_code == 422, (resp.status_code, resp.text)
    assert "invalid_tile_coordinates" in resp.text


@pytest.mark.parametrize(("z", "x", "y"), _INVALID_XYZ)
def test_cdse_tile_rejects_invalid_xyz_before_any_work(monkeypatch, client, z, x, y):
    _forbid_work(monkeypatch)
    resp = client.get(f"/v1/fields/F-xyz/cdse-tiles/{z}/{x}/{y}.png")
    assert resp.status_code == 422, (resp.status_code, resp.text)
    assert "invalid_tile_coordinates" in resp.text


@pytest.mark.parametrize(("z", "x", "y"), [(0, 0, 0), (22, 2**22 - 1, 2**22 - 1), (14, 100, 100)])
def test_valid_xyz_edges_pass_validation(z, x, y):
    from raster_http_policy import validate_xyz

    validate_xyz(z, x, y)  # لا استثناء


# ── P3-LIM: timeseries explicit-date fanout is deduplicated and capped ────────


def _stub_timeseries(monkeypatch) -> list[str]:
    from routers import fields

    calls: list[str] = []

    async def _grid(_fid, _index, date, _grid):
        calls.append(date)
        return None

    monkeypatch.setattr(fields, "_require_field_tenant", _noop_async)
    monkeypatch.setattr(fields, "_real_field_grid", _grid)
    return calls


def test_timeseries_duplicate_dates_are_read_once(monkeypatch, client):
    calls = _stub_timeseries(monkeypatch)
    dup = ",".join(["2026-06-18"] * 50 + ["2026-06-23"])
    resp = client.get("/v1/fields/F-ts/timeseries", params={"dates": dup})
    assert resp.status_code == 200
    assert calls == ["2026-06-18", "2026-06-23"], calls


def test_timeseries_rejects_explicit_dates_over_cap(monkeypatch, client):
    from raster_http_policy import TIMESERIES_MAX_DATES

    calls = _stub_timeseries(monkeypatch)
    many = ",".join(f"d{i:05d}" for i in range(TIMESERIES_MAX_DATES + 1))
    resp = client.get("/v1/fields/F-ts/timeseries", params={"dates": many})
    assert resp.status_code == 422, (resp.status_code, resp.text[:200])
    assert "too_many_dates" in resp.text
    assert calls == [], "لا قراءة شبكة واحدة قبل رفض الطلب"


def test_timeseries_accepts_exactly_cap_dates(monkeypatch, client):
    from raster_http_policy import TIMESERIES_MAX_DATES

    calls = _stub_timeseries(monkeypatch)
    at_cap = ",".join(f"d{i:05d}" for i in range(TIMESERIES_MAX_DATES))
    resp = client.get("/v1/fields/F-ts/timeseries", params={"dates": at_cap})
    assert resp.status_code == 200
    assert len(calls) == TIMESERIES_MAX_DATES
