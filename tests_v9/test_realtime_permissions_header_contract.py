"""Restrict browser microphone/camera permissions to the future realtime SPA route.

This is a source contract only: the nginx runtime suite must separately prove that
the compiled config sends the expected headers, and the feature must secure sessions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "frontend" / "nginx.conf"


def test_nginx_media_policy_defaults_to_denial():
    raw = CONFIG.read_text(encoding="utf-8")
    match = re.search(
        r"map\s+\$request_uri\s+\$sahool_media_permissions_policy\s*\{([^}]+)\}",
        raw,
    )
    assert match, "Scoped permission map must be present in http context"
    body = match.group(1)
    assert 'default "geolocation=(self), camera=(), microphone=()";' in body
    assert r'~^/realtime(?:/|\?|$) "geolocation=(self), camera=(self), microphone=(self)";' in body
    assert (
        raw.count("add_header Permissions-Policy $sahool_media_permissions_policy always;")
        == 1
    )


@pytest.mark.parametrize(
    ("uri", "should_allow"),
    [
        ("/", False),
        ("/chat", False),
        ("/api/ai-agronomist/chat", False),
        ("/tts/stream", False),
        ("/realtime", True),
        ("/realtime/field", True),
        ("/realtime?session=123", True),
        ("/realtime/field?session=123", True),
        ("/realtime-unsafe", False),
        ("/other/realtime", False),
    ],
)
def test_eligible_realtime_route_is_explicit(uri, should_allow):
    # Mirrors the one PCRE location condition in frontend/nginx.conf.
    assert bool(re.search(r"^/realtime(?:/|\?|$)", uri)) is should_allow
