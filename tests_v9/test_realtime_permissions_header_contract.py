"""Media remains denied until a separate realtime document is implemented.

The nginx runtime suite verifies actual responses after SPA internal redirects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "frontend" / "nginx.conf"


def test_nginx_media_policy_stays_fail_closed_before_realtime_feature():
    raw = CONFIG.read_text(encoding="utf-8")
    # One server declaration, plus the cache-header-declaring SPA shell, where
    # nginx does not inherit server add_header directives.
    denied = 'add_header Permissions-Policy "geolocation=(self), camera=(), microphone=()" always;'
    assert raw.count(denied) == 2
    assert "camera=(self)" not in raw, (
        "Camera capture must remain denied until an isolated realtime document and trusted session exist"
    )
    assert "microphone=(self)" not in raw, (
        "Microphone capture must remain denied until an isolated realtime document and trusted session exist"
    )
    assert "$sahool_media_permissions_policy" not in raw, (
        "The former raw-URI media grant survives SPA fallback and navigation into ordinary pages"
    )
