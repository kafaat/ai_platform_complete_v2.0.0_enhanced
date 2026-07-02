from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# توحيد main↔cert: نُقِل التمرير التوافقيّ لـ/api/raster/* من api/main.py إلى راوتر
# مستقلّ (api/routers/compat_gateway.py) عند تفكيك الخدمة؛ يقرأ الحارس المصدرَ حيث
# يعيش المنطق الآن كي يبقى عقد التمرير (حفظ الاستعلام + tid→X-Tenant-Id) محروساً.
PLATFORM = (ROOT / "services/sahool-platform/api/routers/compat_gateway.py").read_text(
    encoding="utf-8"
)
COMPOSE = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
REQ = (ROOT / "services/raster-service/requirements.txt").read_text(encoding="utf-8")


def test_platform_raster_proxy_preserves_query_and_tid():
    assert "request: Request" in PLATFORM
    assert "request.url.query" in PLATFORM
    assert 'request.query_params.get("tid")' in PLATFORM
    assert 'headers["X-Tenant-Id"] = effective_tenant' in PLATFORM
    assert '+ (f"?{query}" if query else "")' in PLATFORM


def test_platform_raster_proxy_default_service_name_matches_compose():
    assert "http://sahool-raster-service:8001" in PLATFORM
    assert "http://raster-service:8001" not in PLATFORM


def test_raster_service_has_db_and_redis_runtime_env():
    assert "sahool-raster-service:" in COMPOSE
    marker = "  sahool-raster-service:\n"
    assert marker in COMPOSE
    block = COMPOSE.split(marker, 1)[1].split("\n\n  #", 1)[0]
    assert "DATABASE_URL:" in block
    assert "REDIS_URL:" in block


def test_raster_service_has_asyncpg_dependency():
    assert "asyncpg" in REQ
