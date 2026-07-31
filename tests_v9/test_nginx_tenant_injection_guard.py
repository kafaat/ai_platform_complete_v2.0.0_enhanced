"""حارس ثابت (R6) لنموذج ثقة X-Tenant-Id في بوّابة nginx.

يثبّت الثوابت الأمنيّة دون تشغيل nginx (تحليل نصّيّ للكونف فقط):
  • proxy_params.conf يمسح X-Tenant-Id الذي قد يحقنه العميل (الافتراض الآمن: فارغ).
  • مواقع الخدمات المصغّرة (raster/vegetation) تحقّق JWT عبر auth_request،
    وتلتقط المستأجِر الموثّق من ردّ التحقّق، وتعيد حقنه — بهذا الترتيب الصحيح.
  • موقع تحقّق داخليّ (internal) يُمرّر /v1/auth/verify ولا يصله العميل مباشرةً.

منع انتحال المستأجِر = شرط لعزل RLS. أيّ انحدار هنا يكسر الحارس."""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))
NGINX_CONF = os.path.join(BASE, "nginx", "nginx.v9.conf")
PROXY_PARAMS = os.path.join(BASE, "nginx", "proxy_params.conf")

# مواقع الخدمات المصغّرة التي تثق برأس X-Tenant-Id وتُخدَّم فعليّاً (لا 503).
PROTECTED_LOCATIONS = ("/api/raster/", "/api/vegetation/")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _location_block(conf: str, prefix: str) -> str:
    """يستخرج جسم كتلة `location <prefix> { ... }` (توازن أقواس بسيط)."""
    marker = f"location {prefix}"
    start = conf.index(marker)
    brace = conf.index("{", start)
    depth = 0
    for i in range(brace, len(conf)):
        if conf[i] == "{":
            depth += 1
        elif conf[i] == "}":
            depth -= 1
            if depth == 0:
                return conf[brace : i + 1]
    raise AssertionError(f"كتلة location {prefix} غير متوازنة الأقواس")


def test_proxy_params_blanks_client_trust_headers():
    """الافتراض الآمن: proxy_params يمسح X-Tenant-Id (وX-User-Id/X-Agent-Token)."""
    pp = _read(PROXY_PARAMS)
    assert re.search(r'proxy_set_header\s+X-Tenant-Id\s+""\s*;', pp), (
        "proxy_params.conf يجب أن يمسح X-Tenant-Id الذي يرسله العميل"
    )
    assert re.search(r'proxy_set_header\s+X-User-Id\s+""\s*;', pp)
    assert re.search(r'proxy_set_header\s+X-Agent-Token\s+""\s*;', pp)


def test_internal_auth_verify_location_exists():
    """موقع تحقّق داخليّ (internal) يُمرّر /v1/auth/verify — هدف الطلب الفرعيّ."""
    conf = _read(NGINX_CONF)
    block = _location_block(conf, "= /_auth_verify")
    assert "internal;" in block, "موقع التحقّق يجب أن يكون internal (لا يصله العميل)"
    assert "/v1/auth/verify" in block, "الطلب الفرعيّ يجب أن يُمرَّر إلى /v1/auth/verify"


@pytest.mark.parametrize("prefix", PROTECTED_LOCATIONS)
def test_microservice_location_verifies_and_injects_tenant(prefix):
    """كلّ موقع خدمة مصغّرة: auth_request للتحقّق، ثمّ التقاط المستأجِر الموثّق وحقنه."""
    conf = _read(NGINX_CONF)
    block = _location_block(conf, prefix)

    # (1) تحقّق JWT عبر طلب فرعيّ — فشله يرفض الطلب الأصليّ (لا تمرير رأس غير موثّق).
    assert "auth_request /_auth_verify;" in block, (
        f"{prefix} يجب أن يتحقّق عبر auth_request /_auth_verify"
    )
    # (2) الافتراض الآمن: مسح رؤوس الثقة يبقى عبر تضمين proxy_params.
    assert "/etc/nginx/proxy_params.conf" in block, (
        f"{prefix} يجب أن يُضمّن proxy_params (مسح X-Tenant-Id العميل)"
    )
    # (3) التقاط المستأجِر الموثّق من ردّ التحقّق.
    assert "auth_request_set $tenant $upstream_http_x_tenant_id;" in block, (
        f"{prefix} يجب أن يلتقط $tenant من ردّ /v1/auth/verify"
    )
    # (4) إعادة حقن القيمة الموثّقة.
    assert "proxy_set_header X-Tenant-Id $tenant;" in block, (
        f"{prefix} يجب أن يعيد حقن X-Tenant-Id $tenant الموثّق"
    )


@pytest.mark.parametrize("prefix", PROTECTED_LOCATIONS)
def test_blank_precedes_verified_injection(prefix):
    """الترتيب حاسم: المسح (proxy_params) قبل إعادة حقن $tenant الموثّق كي يتجاوزه."""
    conf = _read(NGINX_CONF)
    block = _location_block(conf, prefix)
    blank_at = block.index("/etc/nginx/proxy_params.conf")
    inject_at = block.index("proxy_set_header X-Tenant-Id $tenant;")
    assert blank_at < inject_at, f"{prefix}: يجب مسح رأس العميل أوّلاً ثمّ حقن المستأجِر الموثّق بعده"
