"""Only the isolated call document may request a microphone."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def _block(raw: str, declaration: str) -> str:
    assert raw.count(declaration) == 1
    start = raw.index(declaration) + len(declaration)
    depth = 1
    for index in range(start, len(raw)):
        if raw[index] == "{":
            depth += 1
        elif raw[index] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:index]
    raise AssertionError("Unclosed configuration block")


def test_nginx_media_policy_grants_microphone_only_to_isolated_document():
    raw = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    denied = 'add_header Permissions-Policy "geolocation=(self), camera=(), microphone=()" always;'
    assert raw.count(denied) == 2
    assert denied in _block(raw, "location = /index.html {")
    assert "camera=(self)" not in raw
    assert "$sahool_media_permissions_policy" not in raw
    policy = _block(raw, "map $request_uri $realtime_call_permissions {")
    assert [line.strip() for line in policy.splitlines() if line.strip()] == [
        'default "geolocation=(), camera=(), microphone=()";',
        '"/realtime-call/" "geolocation=(), camera=(), microphone=(self)";',
    ]
    assert raw.count("microphone=(self)") == 1
    call = _block(raw, "location = /realtime-call/ {")
    assert 'if ($request_uri != "/realtime-call/") { return 404; }' in call
    assert "try_files /realtime-call/index.html =404;" in call
    header = "add_header Permissions-Policy $realtime_call_permissions always;"
    assert header in call and raw.count(header) == 1
    assert "add_header X-Frame-Options DENY always;" in call
    assert "frame-ancestors 'none'" in call
    assert 'add_header Cache-Control "no-store" always;' in call
    assert _block(raw, "location ^~ /realtime-call/ {").strip() == "return 404;"
    assert _block(raw, "location ^~ /api/v1/realtime/internal/ {").strip() == "return 404;"
    assert "try_files $uri $uri/ /index.html;" in _block(raw, "location / {")
