"""حُرّاس شهادة الإنتاج: مصادقة تعمل تحت الدور المقيّد + توجيه nginx للمصادقة.

CRITICAL-001: جدول users عليه FORCE RLS بسياسة user_self (تسمح عبر current_user_id
أو current_tenant أو current_role='admin'). خدمة الهويّة تقرأ users بالبريد قبل معرفة
المستأجِر ⇒ تحتاج سياق admin على كلّ اتّصال؛ بلا ذلك register=500/login=401 (المنصّة معطّلة).

CRITICAL-002: توجيه nginx لـ/auth/ يجب ألّا يُجرّد البادئة فقط بشرطة لاحقة (يكسر العميل
المباشر /auth/login ⇒ /login ⇒ 404). يُطبَّع المزدوج بـrewrite ويُمرَّر الـURI كما هو.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = pytest.mark.unit

BASE = os.path.dirname(os.path.dirname(__file__))


def _read(p):
    with open(os.path.join(BASE, p), encoding="utf-8") as f:
        return f.read()


def test_auth_pool_sets_admin_role_context():
    """مسبح auth يضبط app.current_role='admin' على كلّ اتّصال (init) — وإلّا RLS
    على users تُرشّح كلّ الصفوف فتفشل المصادقة كلّها تحت sahool_app."""
    src = _read("services/auth/main.py")
    assert "init=" in src, "create_pool بلا init ⇒ لا سياق admin على اتّصالات المسبح"
    # يضبط الدور admin (session-level) في init.
    assert re.search(r"set_config\(\s*'app\.current_role'\s*,\s*'admin'\s*,\s*false\s*\)", src), (
        "auth لا يضبط app.current_role='admin' (session-level) ⇒ register=500/login=401"
    )


@pytest.mark.parametrize("conf", ["nginx/nginx.fixed.conf", "nginx/nginx.v9.conf"])
def test_nginx_auth_routing_preserves_prefix(conf):
    """توجيه /auth/ يطبّع المزدوج (/auth/auth/*) ويمرّر الـURI كما هو (لا تجريد يكسر
    العميل المباشر). أي: rewrite + proxy_pass بلا مسار لاحق على auth_backend."""
    src = _read(conf)
    # يوجد تطبيع المزدوج.
    assert re.search(r"rewrite\s+\^/auth/auth/", src), f"{conf}: لا تطبيع /auth/auth/ (rewrite)"
    # proxy_pass بلا مسار لاحق (يحفظ الـURI) — لا الشكل القديم http://auth_backend/ المُجرِّد.
    assert re.search(r"proxy_pass\s+http://auth_backend\s*;", src), (
        f"{conf}: proxy_pass يجب أن يكون http://auth_backend; (بلا مسار) ليحفظ /auth/login"
    )
    assert not re.search(r"proxy_pass\s+http://auth_backend/\s*;", src), (
        f"{conf}: proxy_pass http://auth_backend/; يُجرّد /auth/ ⇒ /auth/login يصير /login (404)"
    )
