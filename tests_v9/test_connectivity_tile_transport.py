"""Exercise the real COG transport and default deployment edges; no live services."""

from __future__ import annotations

import base64
import graphlib
import importlib.util
import re
import struct
import sys
import types
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from shared.gis import cog_tile_proxy

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4P8AAAAASUVORK5CYII="
)


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setenv("COG_TILE_ALLOWED_HOSTS", "cogs.example.test")
    original = httpx.AsyncClient
    requests = []

    def install(status=200, content=PNG, content_type="image/png", error=None):
        def handle(request):
            requests.append(request)
            if error:
                raise error
            return httpx.Response(status, content=content, headers={"Content-Type": content_type})

        monkeypatch.setattr(
            cog_tile_proxy.httpx,
            "AsyncClient",
            lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
        )

    install()
    return requests, install


async def test_backend_receives_encoded_source_and_returns_png(transport):
    requests, _ = transport
    source = "https://cogs.example.test/a.tif?signature=a&expires=42"
    result = await cog_tile_proxy.fetch_registered_cog_tile(
        source, 2, 1, 1, base_url="http://raster-tiler-service:8088", colormap="viridis"
    )
    assert result == PNG
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/cog/tiles/WebMercatorQuad/2/1/1.png"
    assert request.url.params["url"] == source
    assert "expires" not in request.url.params
    assert "authorization" not in request.headers


@pytest.mark.parametrize(
    "source",
    [
        "file:///etc/passwd",
        "s3://private/another-tenant.tif",
        "https://127.0.0.1/private.tif",
        "https://cogs.example.test.evil.test/a.tif",
        "https://user:password@cogs.example.test/a.tif",
        "https://cogs.example.test:9000/a.tif",
    ],
)
async def test_untrusted_source_is_rejected_before_transport(source, transport):
    requests, _ = transport
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            source, 2, 1, 1, base_url="http://raster-tiler-service:8088"
        )
    assert exc.value.status_code == 422
    assert requests == []


@pytest.mark.parametrize("coordinates", [(-1, 0, 0), (23, 0, 0), (2, 4, 0), (2, 0, -1)])
async def test_invalid_coordinates_do_not_reach_backend(coordinates, transport):
    requests, _ = transport
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", *coordinates, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 422
    assert not requests


async def test_unconfigured_allowlist_fails_closed(monkeypatch, transport):
    monkeypatch.delenv("COG_TILE_ALLOWED_HOSTS")
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 503
    assert transport[0] == []


@pytest.mark.parametrize(
    "status,content,content_type",
    [
        (302, b"", "image/png"),
        (500, b"", "image/png"),
        (200, b"<html/>", "text/html"),
        (200, b"not a png", "image/png"),
        (200, PNG + b"x" * (2 * 1024 * 1024), "image/png"),
    ],
)
async def test_bad_backend_response_is_not_a_successful_tile(
    status, content, content_type, transport
):
    transport[1](status, content, content_type)
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.status_code == 502


async def test_backend_timeout_has_named_failure(transport):
    transport[1](error=httpx.ReadTimeout("private transport details"))
    with pytest.raises(HTTPException) as exc:
        await cog_tile_proxy.fetch_registered_cog_tile(
            "https://cogs.example.test/a.tif", 2, 1, 1, base_url="http://tiler:8088"
        )
    assert exc.value.detail == "cog_tile_backend_unavailable"


def test_canonical_tiler_is_reachable_and_gateway_waits_for_its_upstreams():
    services = yaml.safe_load((ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8"))[
        "services"
    ]
    list(
        graphlib.TopologicalSorter(
            {k: set(v.get("depends_on", {})) for k, v in services.items()}
        ).static_order()
    )
    for name in ("sahool-platform", "sahool-raster-service"):
        caller = services[name]
        assert "raster-tiler-service:8088" in caller["environment"]["TITILER_URL"]
        assert set(caller["networks"]) & set(services["raster-tiler-service"]["networks"])
        assert caller["depends_on"]["raster-tiler-service"]["condition"] == "service_healthy"
    conf = "\n".join(
        line.split("#", 1)[0]
        for line in (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8").splitlines()
    )
    hosts = re.findall(r"upstream\s+\w+\s*\{\s*server\s+([\w-]+):\d+", conf)
    assert hosts
    for host in hosts:
        assert services["sahool-nginx"]["depends_on"][host]["condition"] == "service_healthy"
    assert services["sahool-titiler"]["profiles"] == ["legacy-tiler"]


def test_erp_credentials_without_explicit_target_do_not_invent_a_host(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "connectivity_erp_provider", ROOT / "services/odoo-bridge/erp_provider.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("ERP_PROVIDER", "erpnext")
    monkeypatch.setenv("ERPNEXT_API_KEY", "test-key")
    monkeypatch.setenv("ERPNEXT_API_SECRET", "test-secret")
    monkeypatch.delenv("ERPNEXT_URL", raising=False)
    assert module.get_erp_provider().name == "none"
    monkeypatch.setenv("ERPNEXT_URL", "https://erp.example.test")
    assert module.get_erp_provider().name == "erpnext"


def test_registry_tile_route_authorizes_before_contacting_backend(monkeypatch, transport):
    """Actual router + actual transport; identity and tenant DB are explicit test adapters."""

    class User(BaseModel):
        tenant_id: str

    class Permissions:
        def __getattr__(self, name):
            return name

    def require_permission(_permission):
        def authenticate(authorization: str | None = Header(None)):
            if authorization not in {"tenant-a", "tenant-b"}:
                raise HTTPException(401, "authentication_required")
            return User(tenant_id=authorization)

        return authenticate

    record = {
        "id": "raster-1",
        "tenant_id": "tenant-a",
        "field_id": "field-1",
        "product_date": "2026-09-10",
        "index_type": "ndvi",
        "cog_url": "https://cogs.example.test/a.tif",
        "cloud_pct": 0,
        "quality_score": 100,
        "scene_id": None,
        "resolution_m": 10,
        "bbox": None,
        "bands": None,
        "metadata": None,
    }

    @asynccontextmanager
    async def tenant_connection(user):
        class Connection:
            async def fetchrow(self, _sql, raster_id):
                return (
                    record if user.tenant_id == "tenant-a" and raster_id == record["id"] else None
                )

        yield Connection()

    stub = types.ModuleType("api.main")
    stub.UserSchema = User
    stub.Permission = Permissions()
    stub.require_permission = require_permission
    stub.tenant_connection = tenant_connection
    stub._db_unavailable = lambda *_: HTTPException(503, "database_unavailable")
    monkeypatch.setitem(sys.modules, "api.main", stub)
    name = "connectivity_gis_router"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "services/sahool-platform/api/routers/gis_cloud_native.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router)
    monkeypatch.setenv("TITILER_URL", "http://raster-tiler-service:8088")
    client = TestClient(app)
    base = "/api/v1/gis/cloud-native/rasters/raster-1"
    tilejson = client.get(base + "/tilejson.json", headers={"Authorization": "tenant-a"})
    assert tilejson.status_code == 200
    tile = tilejson.json()["tiles"][0].format(z=2, x=1, y=1)
    assert client.get(tile).status_code == 401
    assert client.get(tile, headers={"Authorization": "tenant-b"}).status_code == 404
    assert transport[0] == []
    response = client.get(tile, headers={"Authorization": "tenant-a"})
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["cache-control"] == "private, no-store"
    assert len(transport[0]) == 1


def _load_public_cog_url(monkeypatch):
    """Load the advertiser's predicate from its own file, without installing the service dir."""
    name = "connectivity_raster_security_context"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "services/raster-service/raster_security_context.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module.public_cog_url


#: كلُّ رابطٍ هنا يُعرَض على **الحاكمين معاً**: `public_cog_url` الذي يقرّر الإعلان،
#: و`fetch_registered_cog_tile` الذي يقرّر الجلب. والقائمةُ تشمل الأشكالَ التي كان
#: الحاكمان يختلفان عليها (http · منفذٌ غيرُ قياسيّ · اعتمادٌ مضمَّن · شُذاذة).
_SOURCE_CORPUS = [
    "https://cogs.example.test/a.tif",
    "https://cogs.example.test/a.tif?signature=s",
    "https://cogs.example.test:443/a.tif",
    "http://cogs.example.test/a.tif",
    "https://cogs.example.test:8443/a.tif",
    "https://user:password@cogs.example.test/a.tif",
    "https://cogs.example.test/a.tif#fragment",
    "http://sahool-minio:9000/cogs/a.tif",
    "file:///srv/cogs/a.tif",
    "s3://private/a.tif",
    "",
]


async def test_every_advertised_source_is_one_the_transport_will_fetch(monkeypatch, transport):
    """مجموعةُ قبول المُعلِن ⊆ مجموعة قبول الناقل — مقيسةٌ لا مُعادة صياغة.

    العطلُ المقيس: `public_cog_url` كان يقبل `http://` وأيَّ منفذ، والناقلُ يشترط
    `https` على المنفذ القياسيّ. فطبقةٌ بمصدرٍ كهذا تمرّ المُعلِنَ، فيُصدِر TileJSON
    قالبَ بلاطاتٍ، ثمّ تعود **كلُّ** بلاطةٍ بـ422 `cog_tile_source_not_allowed` —
    قالبٌ مُعلَنٌ لا يُنتِج بكسلاً واحداً. والخاصّيّةُ تُقاس بعرض كلّ رابطٍ على
    الحاكمين، لا بتكرار شرطِ أحدهما في تأكيد.
    """
    public_cog_url = _load_public_cog_url(monkeypatch)
    requests, _ = transport
    advertised = []
    for source in _SOURCE_CORPUS:
        if public_cog_url(source) is None:
            continue
        advertised.append(source)
        host = httpx.URL(source).host
        monkeypatch.setenv("COG_TILE_ALLOWED_HOSTS", host)
        before = len(requests)
        await cog_tile_proxy.fetch_registered_cog_tile(
            source, 2, 1, 1, base_url="http://raster-tiler-service:8088"
        )
        assert len(requests) == before + 1, f"مصدرٌ مُعلَنٌ لم يبلغ الخلفيّة: {source}"
    # أرضيّةُ صدق: خاصّيّةٌ على مجموعةٍ فارغة تمرّ بلا معنى.
    assert len(advertised) >= 3, f"انهار المُعلِن فصارت الخاصّيّةُ فارغة: {advertised}"


@pytest.mark.parametrize(
    "source",
    [
        "http://cogs.example.test/a.tif",
        "https://cogs.example.test:8443/a.tif",
        "https://user:password@cogs.example.test/a.tif",
        "https://cogs.example.test/a.tif#fragment",
    ],
)
def test_sources_the_transport_refuses_are_never_advertised(monkeypatch, source):
    """الأشكالُ الأربعةُ التي كان الانفصالُ يقع عليها بعينها."""
    assert _load_public_cog_url(monkeypatch)(source) is None


def _load_service_module(monkeypatch, bare_name: str, relative_path: str):
    """Load one raster-service module from its own file, registered under its bare name.

    **ولا يُوضَع دليلُ الخدمة على `sys.path` ولا يُستورَد باسمٍ عامّ.** العطلُ المقيس:
    التجهيزةُ كانت تقول `from routers import tiles`، فمرّت منفردةً وسقطت في الجناح
    الكامل بـ`ImportError: cannot import name 'tiles' from 'routers'` — و`routers`
    المُقيَّدة في `sys.modules` كانت
    `services/video-processor/routers/__init__.py`: **خدمةٌ أخرى تماماً** سبقت إلى
    اسمٍ عامّ. وهو نفسُ صنفِ التصادم الذي أسقط `agronomic_context` في هذه الجلسة.
    فيُحمَّل كلُّ ملفٍّ بمساره، ويُقيَّد باسمه المجرّد عبر `monkeypatch` وحدَه —
    فيُستعاد ما كان، ولا يبقى اسمٌ عامٌّ يُظلِّل خدمةً أخرى بعد الاختبار.
    """
    spec = importlib.util.spec_from_file_location(bare_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    # قبل التنفيذ: `dataclass` يقرأ `sys.modules[cls.__module__]` فيموت على وحدةٍ غير مُقيَّدة.
    monkeypatch.setitem(sys.modules, bare_name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def layer_tile_router(monkeypatch):
    """Load the real layer-tile route; DB ownership and request tenant are explicit adapters.

    **`TITILER_URL` يُربَط وقت التحميل** في `routers/tiles.py` (عبر `raster_settings`).
    أوّلُ صياغةٍ ضبطته بمتغيّر بيئة فمرّت منفردةً وأخفقت في الجناح الكامل بـ503
    (`tiles.TITILER_URL == ""` ⇒ `cog_tile_backend_not_configured`) لأنّ اختباراً أسبق
    يُحمّل الوحدةَ قبلها. فيُضبَط **سمةُ الوحدة** — مُكافئٌ لتحميلها والبيئةُ مضبوطة،
    ومستقلٌّ عن ترتيب الجناح.
    """
    db = types.ModuleType("db_persist")

    class OwnerLookupUnavailable(Exception):
        pass

    db.OwnerLookupUnavailable = OwnerLookupUnavailable
    db.owner = "tenant-a"

    async def layer_owner_tenant(_layer_id):
        return db.owner

    db.layer_owner_tenant = layer_owner_tenant
    monkeypatch.setitem(sys.modules, "db_persist", db)

    service = "services/raster-service"
    # بالترتيب: كلُّ وحدةٍ تُقيَّد قبل التي تستوردها باسمها المجرّد.
    _load_service_module(monkeypatch, "job_store", f"{service}/job_store.py")
    _load_service_module(monkeypatch, "raster_settings", f"{service}/raster_settings.py")
    runtime_state = _load_service_module(
        monkeypatch, "raster_runtime_state", f"{service}/raster_runtime_state.py"
    )
    security = _load_service_module(
        monkeypatch, "raster_security_context", f"{service}/raster_security_context.py"
    )
    tiles_router = _load_service_module(
        monkeypatch, "connectivity_layer_tiles", f"{service}/routers/tiles.py"
    )

    # هويّةُ الطلب: متغيّرُ سياقٍ يُقرأ داخل الحارس، فيُستبدَل بواحدٍ ذي افتراضٍ مُعلَن —
    # أصدقُ من محاولة تمريرِ سياقٍ عبر خيط TestClient.
    monkeypatch.setattr(security, "REQ_TENANT", ContextVar("req_tenant", default="tenant-a"))
    monkeypatch.setattr(tiles_router, "TITILER_URL", "http://raster-tiler-service:8088")
    # نُسَخٌ طازجة ⇒ `LAYERS` خاصٌّ بهذا الاختبار، فلا لقطةَ حالةٍ مشتركةٍ تُستعاد.
    layers = runtime_state.LAYERS
    app = FastAPI()
    app.include_router(tiles_router.router)
    yield TestClient(app), layers, db


def test_layer_tile_endpoint_serves_a_public_cog_through_the_bounded_transport(
    layer_tile_router, transport
):
    """المسارُ المنشور نفسُه: ملكيّةٌ أوّلاً، ثمّ نقلٌ محدود، ثمّ PNG."""
    client, layers, db = layer_tile_router
    requests, _ = transport
    layers["layer-1"] = {
        "tenant_id": "tenant-a",
        "cog_url": "https://cogs.example.test/a.tif",
    }

    response = client.get("/v1/tiles/layer-1/2/1/1.png?colormap=viridis")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    # **حالةُ القبول تُقاس مفكوكةً لا بمقارنة بايتات:** الشاهدُ الذي يُثبت أنّ الرفض
    # يعمل لا يُثبت أنّ القبول يعمل. فتُفكّ الصورةُ فعلاً — توقيعُ PNG ثمّ أبعادُ IHDR.
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert response.content[12:16] == b"IHDR"
    width, height = struct.unpack(">II", response.content[16:24])
    assert (width, height) == (1, 1), (width, height)
    assert response.content == PNG
    assert len(requests) == 1
    assert requests[0].url.host == "raster-tiler-service"
    assert requests[0].url.params["url"] == "https://cogs.example.test/a.tif"
    assert requests[0].url.params["colormap_name"] == "viridis"


def test_layer_tile_endpoint_checks_ownership_before_contacting_the_backend(
    layer_tile_router, transport
):
    client, layers, db = layer_tile_router
    layers["layer-1"] = {"tenant_id": "tenant-b", "cog_url": "https://cogs.example.test/a.tif"}
    db.owner = "tenant-b"
    assert client.get("/v1/tiles/layer-1/2/1/1.png").status_code == 403
    assert transport[0] == []


def test_a_stale_ownership_cache_does_not_serve_another_tenants_tile(layer_tile_router, transport):
    """القاعدةُ هي مصدرُ الحقيقة — والذاكرةُ وحدَها لا تكفي، وهذا مقيسٌ بطفرةٍ نجت أوّلاً.

    أوّلُ صياغةٍ لهذا الشاهد ضبطت `tenant_id` في الذاكرة مخالفاً لمستأجِر الطلب، فكان
    الفحصُ السريعُ في الذاكرة (`require_layer_tenant`) يُنتِج 403 وحدَه: نزعُ الفحص
    المدعوم بالقاعدة تركَ الاختبارَ **أخضر** — ناجٍ مُسجَّل. فالحالةُ هنا هي الحالةُ
    التي لا يكشفها إلّا الفحصُ المدعوم بالقاعدة: **ذاكرةٌ بائتة** تقول إنّ الطبقة
    لمستأجِر الطلب، والقاعدةُ تقول إنّها لغيره (نقلُ ملكيّةٍ بعد تعبئة المخزن المؤقّت).
    """
    client, layers, db = layer_tile_router
    layers["layer-1"] = {"tenant_id": "tenant-a", "cog_url": "https://cogs.example.test/a.tif"}
    db.owner = "tenant-b"  # القاعدة: الطبقةُ لمستأجِرٍ آخر
    assert client.get("/v1/tiles/layer-1/2/1/1.png").status_code == 403
    assert transport[0] == []


def test_layer_tile_endpoint_does_not_turn_a_non_servable_source_into_a_422_storm(
    layer_tile_router, transport
):
    """مصدرٌ لا يجلبه الناقل ⇒ بلاطةٌ شفّافةٌ صادقة، لا 422 على كلّ بلاطة."""
    client, layers, _ = layer_tile_router
    layers["layer-1"] = {"tenant_id": "tenant-a", "cog_url": "http://cogs.example.test/a.tif"}
    response = client.get("/v1/tiles/layer-1/2/1/1.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content != PNG  # البلاطةُ الشفّافة، لا حمولةُ الخلفيّة
    assert transport[0] == []


def _gateway_location_for(path: str, conf: str):
    """Resolve which nginx location serves `path`, by nginx's own precedence.

    التعبيرُ النمطيّ يسبق مطابقةَ البادئة في nginx، وبين البوادئ تفوز الأطول. فيُحتسَب
    الفائزُ هنا بالقاعدتين بدل افتراض أنّ موقعاً بعينه هو الفائز.
    """
    blocks = []
    for match in re.finditer(r"^\s*location\s+(=|~\*|~|\^~)?\s*([^\s{]+)\s*\{", conf, re.M):
        modifier, pattern = match.group(1), match.group(2)
        depth, i = 0, match.end() - 1
        while i < len(conf):
            if conf[i] == "{":
                depth += 1
            elif conf[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        blocks.append((modifier, pattern, conf[match.end() : i]))
    for modifier, pattern, body in blocks:
        if modifier == "=" and pattern == path:
            return pattern, body
    for modifier, pattern, body in blocks:  # regex, in file order
        if modifier in {"~", "~*"} and re.search(pattern, path, re.I if modifier == "~*" else 0):
            return pattern, body
    prefix = [b for b in blocks if b[0] in (None, "^~") and path.startswith(b[1])]
    if not prefix:
        return None, None
    modifier, pattern, body = max(prefix, key=lambda b: len(b[1]))
    return pattern, body


def test_the_advertised_tile_path_reaches_a_gateway_location_that_bridges_the_cookie():
    """القالبُ المُعلَن يجب أن يمرّ بموقعٍ يشتقّ التوكنَ من الكوكي — مشتقٌّ من المُنتِجَين.

    العطلُ المقيس: تبعيّةُ المنصّة تقرأ `Authorization: Bearer` فقط، و`<img>`/MapLibre
    لا يحمل ترويسة (ولا `transformRequest` في الواجهة). فبلا اشتقاقِ التوكن من كوكي
    `sahool_at` في البوّابة — كما في `/api/raster/` — تعود **كلُّ** بلاطةٍ 401.
    والمسارُ هنا يُحتسَب من `tilejson_for_cog` نفسِه لا من نصٍّ مثبَّت: تغييرُ شكلِ
    الرابط يُعيد حسابَ الفائز ويُحمِّر هذا الشاهد.
    """
    from shared.gis.cloud_native_runtime import RasterRegistryRecord, tilejson_for_cog

    record = RasterRegistryRecord(
        id="raster-1",
        tenant_id="tenant-a",
        field_id="field-1",
        product_date="2026-09-10",
        index_type="ndvi",
        cog_url="https://cogs.example.test/a.tif",
    )
    template = tilejson_for_cog(record)["tiles"][0]
    path = template.format(z=2, x=1, y=1)
    assert path.startswith("/api/v1/"), path
    conf = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    pattern, body = _gateway_location_for(path, conf)
    assert body is not None, f"لا موقعَ في البوّابة يخدم {path}"
    assert "$cookie_sahool_at" in body, (
        f"الموقعُ {pattern!r} يخدم البلاطات بلا اشتقاقِ التوكن من الكوكي ⇒ 401 لكلّ <img>"
    )
    assert "auth_request" in body, f"الموقعُ {pattern!r} يمرّر بلا تحقّقٍ فرعيّ من JWT"
    # والتوكنُ لا يُقبَل في الاستعلام على هذا المسار الجديد (يُسجَّل في السجلّات).
    assert "$arg_access_token" not in body


def test_the_resolver_is_not_a_restatement_of_the_location_we_expect():
    """أرضيّةُ صدقٍ للمُحتسِب: يجب أن يُميّز فعلاً، لا أن يُعيد نصّاً متوقَّعاً."""
    conf = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
    # مسارٌ آخرُ تحت `/api/v1/` يفوز بمطابقة البادئة العامّة، لا بموقع البلاطات.
    pattern, body = _gateway_location_for("/api/v1/fields", conf)
    assert pattern == "/api/v1/"
    assert "$cookie_sahool_at" not in body


def _directives(block, name):
    return [d for d in block if d.get("directive") == name]


def _walk(block):
    for directive in block:
        yield directive
        yield from _walk(directive.get("block") or [])


def test_the_gateway_configuration_parses_and_the_tile_location_is_well_formed():
    """صياغةُ nginx وبنيةُ موقع البلاطات — مقيسةٌ بمُحلّلٍ لا مقروءةٌ بالعين.

    لا nginx ولا Docker في عدّاء الوحدة، وقولُ «الصياغةُ تُشبه كتلاً مُجرَّبة» قراءةٌ
    لا تحقّق. `crossplane` (مُحلّل F5 الرسميّ) يُعطي نتيجةً نحويّة؛ وفوقها يُفحَص
    قيدٌ **دلاليٌّ لا يراه المُحلّل**: `proxy_pass` داخل موقعٍ بتعبيرٍ نمطيّ لا يجوز
    أن يحمل مقطعَ URI — يرفضه nginx وقتَ التحميل، فيسقط المكدّسُ كلُّه لا هذا المسار.
    """
    import crossplane

    payload = crossplane.parse(str(ROOT / "nginx/nginx.v9.conf"), single=True)
    assert payload["status"] == "ok", payload["errors"]
    parsed = payload["config"][0]["parsed"]

    servers = [d for d in _walk(parsed) if d.get("directive") == "server"]
    assert servers, "لا كتلةَ server في التهيئة"
    tile_locations = [
        (server, location)
        for server in servers
        for location in _directives(server.get("block") or [], "location")
        if location["args"][:1] == ["~"] and "gis/cloud-native/rasters" in location["args"][-1]
    ]
    assert len(tile_locations) == 1, f"موقعُ البلاطات ليس واحداً: {len(tile_locations)}"
    server, location = tile_locations[0]

    # الخادمُ الحاضن هو خادمُ TLS لا خادمُ إعادة التوجيه على 80.
    listens = [" ".join(d["args"]) for d in _directives(server.get("block") or [], "listen")]
    assert any("443" in value and "ssl" in value for value in listens), listens

    body = location.get("block") or []
    proxy = _directives(body, "proxy_pass")
    assert len(proxy) == 1, proxy
    # `http://upstream` وحدَه: أيُّ شرطةٍ مائلةٍ بعد المضيف مقطعُ URI ⇒ رفضٌ وقت التحميل.
    target = proxy[0]["args"][0]
    assert re.fullmatch(r"https?://[A-Za-z0-9_.-]+(?::\d+)?", target), (
        f"proxy_pass داخل موقعٍ نمطيّ يحمل مقطعَ URI: {target}"
    )
    assert any(d["args"] == ["/_auth_verify"] for d in _directives(body, "auth_request"))
    cookie_derivations = [
        d
        for d in _walk(body)
        if d.get("directive") == "set" and "$cookie_sahool_at" in " ".join(d["args"])
    ]
    assert cookie_derivations, "لا اشتقاقَ للتوكن من الكوكي في موقع البلاطات"

    # والموقعُ الذي يتحقّق من الهُويّة يبقى داخليّاً بحتاً.
    verify = [
        d
        for d in _walk(parsed)
        if d.get("directive") == "location" and d["args"][-1] == "/_auth_verify"
    ]
    assert len(verify) == 1
    assert _directives(verify[0].get("block") or [], "internal")
