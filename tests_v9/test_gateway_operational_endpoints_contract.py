from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_frontend_gateway_exact_operational_routes_precede_spa() -> None:
    text = _text("frontend/nginx.conf")
    ready = text.index("location = /readyz {")
    identity = text.index("location = /runtime-identity {")
    spa = text.index("location / {", identity)
    assert ready < spa and identity < spa
    assert "sahool-platform:8000/readyz" in text
    assert "sahool-platform:8000/runtime-identity" in text


def test_production_gateway_is_private_and_never_spa_fallback() -> None:
    text = _text("nginx/nginx.v9.conf")
    ready = text.index("location = /readyz {")
    identity = text.index("location = /runtime-identity {")
    spa = text.index("location / {", identity)
    assert ready < spa and identity < spa
    for segment in (text[ready:identity], text[identity:spa]):
        assert "deny all;" in segment
        assert "proxy_intercept_errors off;" in segment
    assert "platform_backend/readyz" in text
    assert "platform_backend/runtime-identity" in text


def test_contract_forbids_html_fallback() -> None:
    text = _text("docs/architecture/GATEWAY_OPERATIONAL_ENDPOINT_CONTRACT.md")
    assert "`200 text/html` is forbidden" in text
    assert "private/operator-only" in text
