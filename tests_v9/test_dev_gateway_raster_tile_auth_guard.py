"""Dev Gateway guard — frontend/nginx.conf /api/raster/ mirrors the production
identity contract so a *production* Vite build's Leaflet <img> tiles authenticate
on the dev host (:3003) over HTTP via the sahool_at cookie.

خلفيّة (بلاغ 403 مُكرَّر): بوّابة الواجهة التطويريّة كانت تشتقّ المستأجِر من query
(tid/tenant_id) أو ترويسة X-Tenant-Id من العميل. حزمة الإنتاج تُجرّد tid (import.meta.env.PROD)
وبلاطة <img> لا تحمل ترويسات ⇒ مستأجِر فارغ ⇒ خدمة الراستر 403 (وAUTH_COOKIE_SECURE=0 لا
يُصلحه لأنّ هذا المسار لم يكن يقرأ الكوكي أصلاً). الإصلاح: نفس عقد الإنتاج —
كوكي sahool_at ⇒ auth_request ⇒ /v1/auth/verify ⇒ حقن X-Tenant-Id الموثّق فقط.

هذا الحارس يمنع انحدار البوّابة إلى الاشتقاق غير الموثّق من العميل.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
NGINX = ROOT / "frontend" / "nginx.conf"
API_TS = ROOT / "frontend" / "src" / "services" / "api.ts"


def _read(rel_or_path) -> str:
    p = rel_or_path if isinstance(rel_or_path, Path) else ROOT / rel_or_path
    return p.read_text(encoding="utf-8")


def _block(conf: str, header: str) -> str:
    """Extract a single `location ... {` block body by brace matching."""
    start = conf.index(header)
    i = conf.index("{", start)
    depth = 0
    for j in range(i, len(conf)):
        if conf[j] == "{":
            depth += 1
        elif conf[j] == "}":
            depth -= 1
            if depth == 0:
                return conf[i : j + 1]
    raise AssertionError(f"unbalanced braces after {header!r}")


def test_auth_verify_subrequest_forwards_only_token() -> None:
    block = _block(_read(NGINX), "location = /_auth_verify")
    assert "internal;" in block  # لا يصله العميل مباشرةً
    assert "http://sahool-auth:8000/v1/auth/verify" in block  # نفس نقطة تحقّق الإنتاج
    assert "Authorization" in block and "$fwd_auth" in block  # التوكن فقط
    # لا ثقة برؤوس هويّة من العميل في طلب التحقّق.
    assert 'proxy_set_header   X-Tenant-Id     "";' in block or 'X-Tenant-Id     ""' in block


def test_raster_location_uses_cookie_auth_request() -> None:
    block = _block(_read(NGINX), "location ^~ /api/raster/")
    # كوكي sahool_at مصدر توكن (بلاطات <img> للحزمة الإنتاجية على HTTP).
    assert 'set $fwd_auth "Bearer $cookie_sahool_at"' in block
    # التحقّق قبل التمرير (فشله ⇒ رفض).
    assert "auth_request /_auth_verify;" in block


def test_raster_tenant_is_jwt_verified_only_not_client_supplied() -> None:
    block = _block(_read(NGINX), "location ^~ /api/raster/")
    # المستأجِر يُلتقَط من ردّ التحقّق الموثّق ويُحقَن.
    assert "auth_request_set $raster_tenant $upstream_http_x_tenant_id;" in block
    assert "proxy_set_header   X-Tenant-Id       $raster_tenant;" in block
    # حرِّيّة صارمة: لا يُشتقّ المستأجِر من رأس/query العميل في مسار البلاطات.
    assert "$http_x_tenant_id" not in block, "raster tenant must NOT come from client header"
    assert "$arg_tenant_id" not in block, "raster tenant must NOT come from client query"


def test_prod_build_keeps_tile_urls_without_tid_or_access_token() -> None:
    # الإصلاح لا يُعيد إدخال tid/access_token في حزمة الإنتاج — الهويّة عبر الكوكي/البوّابة.
    api = _read(API_TS)
    assert "if (import.meta.env.PROD) return;" in api  # appendTileAccessToken: dev-only
    assert "if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);" in api
