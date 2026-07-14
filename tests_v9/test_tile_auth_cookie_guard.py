"""حارس ساكن: مصادقة بلاطات الخريطة عبر كوكي HttpOnly بدل JWT في الرابط.

خلفيّة (تدقيق الواجهة F-UI — «JWT في روابط البلاطات»): بلاطات المؤشّر/الراستر تُحمَّل
كـ<img> بلا ترويسات، فكان الرابط يحمل JWT كـ`access_token` query — تسريب محتمل عبر
سجلّ المتصفّح/الـReferrer/التلمترة. الإصلاح (متوافق للخلف، بلا كسر إنتاج):

  1) خدمة auth تضبط كوكي HttpOnly `sahool_at` عند الدخول/التجديد/التسجيل/قبول الدعوة،
     وتمسحها عند الخروج.
  2) بوّابة nginx تقرأ `$cookie_sahool_at` كمصدر توكن لـauth_request في موقعَي البلاطات
     (`/api/raster/` و`/api/vegetation/`)، مع بقاء `$arg_access_token` fallback للتطوير.
  3) الواجهة لا تضع JWT ولا المستأجِر (tid/tenant_id) في رابط البلاطة في **الإنتاج**
     (`import.meta.env.PROD`)؛ التطوير فقط يبقيهما كـfallback مباشر لخدمة الراستر.

هذا الحارس يمنع انحدار أيّ من الطبقات الثلاث.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_auth_defines_httponly_tile_cookie_helpers() -> None:
    main = _read("services/auth/main.py")
    assert 'AUTH_TILE_COOKIE_NAME = os.getenv("AUTH_TILE_COOKIE_NAME", "sahool_at")' in main
    assert "def set_tile_auth_cookie(" in main
    assert "def clear_tile_auth_cookie(" in main
    # الكوكي HttpOnly (غير قابلة للقراءة من JS ⇒ لا تُوسِّع سطح XSS).
    assert "httponly=True" in main
    # تُبنى من اسم الكوكي القابل للضبط (لا سلسلة حرفيّة مبعثرة).
    assert "key=AUTH_TILE_COOKIE_NAME" in main


def test_session_sets_cookie_on_login_and_refresh_and_clears_on_logout() -> None:
    session = _read("services/auth/routers/session.py")
    # الدخول والتجديد يضبطان الكوكي؛ الخروج يمسحها.
    assert session.count("main.set_tile_auth_cookie(response, token)") >= 2
    assert "main.clear_tile_auth_cookie(response)" in session


def test_registration_and_invitation_set_cookie() -> None:
    assert "main.set_tile_auth_cookie(response, token)" in _read(
        "services/auth/routers/registration.py"
    )
    assert "main.set_tile_auth_cookie(response, token)" in _read(
        "services/auth/routers/invitations.py"
    )


def test_nginx_tile_locations_read_cookie_source() -> None:
    conf = _read("nginx/nginx.v9.conf")
    # كِلا موقعَي البلاطات يقرآن الكوكي كمصدر auth_request.
    assert conf.count("$cookie_sahool_at") >= 2
    assert 'set $fwd_auth "Bearer $cookie_sahool_at"' in conf
    # يبقى مسار query كـfallback (توافق للخلف/تطوير).
    assert 'set $fwd_auth "Bearer $arg_access_token"' in conf


def test_frontend_prod_gates_jwt_and_tenant_out_of_tile_urls() -> None:
    # المصدر المشترك في api.ts: لا JWT في الإنتاج.
    api = _read("frontend/src/services/api.ts")
    assert "const appendTileAccessToken" in api
    # أوّل سطر فعّال داخل الدالّة يقصر الإلحاق على غير‌الإنتاج.
    idx = api.index("const appendTileAccessToken")
    body = api[idx : idx + 600]
    assert "if (import.meta.env.PROD) return;" in body
    # tid مقصور على التطوير.
    assert "if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);" in api

    # باني رابط البلاطة استُخرِج إلى وحدة مُشترَكة قابلة للاختبار (indicatorTileUrl.ts):
    # نتحقّق من حارس الإنتاج فيها — access_token + tenant_id خلف `!import.meta.env.PROD`.
    tile_url = _read("frontend/src/components/maphub/indicatorTileUrl.ts")
    assert "if (!import.meta.env.PROD) {" in tile_url
    assert "params.set('access_token', tok)" in tile_url
    assert "if (!import.meta.env.PROD && tenantId) params.set('tenant_id', tenantId);" in tile_url

    # وكِلا المحرّكَين (HubMap/HubMapGL) يستعملان الباني المُشترَك ⇒ ينطبق الحارس عليهما.
    for rel in (
        "frontend/src/components/maphub/HubMap.tsx",
        "frontend/src/components/maphub/HubMapGL.tsx",
    ):
        assert "indicatorTileUrl(" in _read(rel)
