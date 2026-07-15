from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The runtime /api/raster/* proxy now lives in nginx (frontend + gateway), not the
# platform compat router — the gateway verifies JWT via auth_request, injects the
# authenticated tenant, and forwards the token source so <img> tile loads work.
# These guards read nginx (where the contract actually lives) so the raster proxy
# contract stays guarded: tenant injection + correct service + token forwarding.
NGINX = (ROOT / "nginx/nginx.v9.conf").read_text(encoding="utf-8")
FRONTEND_NGINX = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.v9.yml").read_text(encoding="utf-8")
REQ = (ROOT / "services/raster-service/requirements.txt").read_text(encoding="utf-8")


def test_nginx_raster_proxy_injects_authenticated_tenant_and_forwards_token():
    # JWT verified before proxy, tenant taken from the verified response (not client),
    # and the cookie/query token forwarded downstream (the tile 401 fix path).
    assert "location /api/raster/" in NGINX
    assert "auth_request /_auth_verify;" in NGINX
    assert "auth_request_set $tenant $upstream_http_x_tenant_id;" in NGINX
    assert "proxy_set_header X-Tenant-Id $tenant;" in NGINX
    assert "$cookie_sahool_at" in NGINX
    assert "proxy_set_header Authorization $fwd_auth;" in NGINX


def test_nginx_raster_proxy_points_at_correct_service():
    assert "server sahool-raster-service:8001;" in NGINX
    assert "http://sahool-raster-service:8001/" in FRONTEND_NGINX
    assert "raster-service:8001" not in NGINX.replace("sahool-raster-service:8001", "")


def test_raster_service_has_db_and_redis_runtime_env():
    assert "sahool-raster-service:" in COMPOSE
    marker = "  sahool-raster-service:\n"
    assert marker in COMPOSE
    block = COMPOSE.split(marker, 1)[1].split("\n\n  #", 1)[0]
    assert "DATABASE_URL:" in block
    assert "REDIS_URL:" in block


def test_raster_service_has_asyncpg_dependency():
    assert "asyncpg" in REQ
