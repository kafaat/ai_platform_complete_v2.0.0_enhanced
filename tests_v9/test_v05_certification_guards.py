"""حُرّاس انحدار مستمدّة من شهادة الإنتاج الحقيقيّة v05 (evidence_pack/CERTIFICATION_REPORT).

شهادة بيئة حقيقيّة (28 حاوية، الحكم FAIL) كشفت فجوات نشر/أمان عُولِجت كلّها لاحقاً في
الكود. بعض الإصلاحات الحرجة محروسة سلفاً (حارس دور القاعدة F-001 ⇒ test_db_role_guard،
test_rls_role_hardening_v66)، لكنّ إصلاحات **النشر/الإعداد** (ترويسات nginx الأمنيّة، ربط
المنافذ الحسّاسة بـlocalhost، نشر sahool-platform، توكن الحوكمة، توجيه auth، دور القاعدة
في .env المثال) لم تكن محروسة — فتنحدر بصمت في إعادة هيكلة لاحقة.

هذه حُرّاس ساكنة (فحص ملفّات الإعداد نصّيّاً، بلا قاعدة) — نفس فلسفة test_event_bus_invariants/
sahool_inspector: تُثبّت إصلاحات الشهادة كبوّابة CI كي لا يعود أيّ FINDING صامتاً.
"""

from __future__ import annotations

import os
import re

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ── F-001 (طبقة الإعداد): التطبيق يتّصل بدور مقيّد لا superuser ──
# (الحارس وقت التشغيل role_can_bypass_rls محروس في test_db_role_guard؛ هنا نحرس
#  افتراض .env المثال كي لا يعود sahool_user — الذي يتجاوز RLS — قيمةً افتراضيّة.)
def test_env_example_database_url_uses_restricted_role():
    """F-001: سطر DATABASE_URL في .env.example يستعمل sahool_app (NOBYPASSRLS) لا sahool_user."""
    line = next(ln for ln in _read(".env.example").splitlines() if ln.startswith("DATABASE_URL="))
    assert "sahool_app" in line, "DATABASE_URL يجب أن يتّصل بـsahool_app المقيّد (يبقى RLS فعّالاً)"
    assert "sahool_user" not in line, (
        "DATABASE_URL يتّصل بـsahool_user (superuser يتجاوز كلّ RLS) — انحدار F-001"
    )


# ── F-002: خدمة منطق الأعمال الأساسيّة منشورة ──
def test_sahool_platform_service_deployed_in_fixed_compose():
    """F-002: docker-compose.fixed.yml يعرّف خدمة sahool-platform (لا تُنسى كما في v05)."""
    assert "\n  sahool-platform:" in _read("docker-compose.fixed.yml"), (
        "خدمة sahool-platform غير منشورة في fixed.yml — انحدار F-002 (المنطق الأساسيّ غائب)"
    )


# ── F-003: حوكمة الذكاء الاصطناعيّ تتطلّب توكناً ──
def test_agent_token_required_in_fixed_compose():
    """F-003: SAHOOL_AGENT_TOKEN مطلوب (:?required) في fixed.yml — لا تعمل الحوكمة بلا توكن."""
    compose = _read("docker-compose.fixed.yml")
    assert "SAHOOL_AGENT_TOKEN: ${SAHOOL_AGENT_TOKEN:?" in compose, (
        "SAHOOL_AGENT_TOKEN ليس مطلوباً بصرامة — انحدار F-003 (تعمل إجراءات AI بلا تحقّق أمان)"
    )


# ── F-005: المنافذ الحسّاسة (MinIO/raster) مربوطة بـlocalhost لا 0.0.0.0 ──
def test_sensitive_ports_bound_to_localhost():
    """F-005: منافذ MinIO (9000/9001) وraster (8001) مربوطة بـ127.0.0.1 لا مكشوفة للعالم."""
    compose = _read("docker-compose.fixed.yml")
    for port in ("9000", "9001", "8001"):
        assert f'"127.0.0.1:{port}:{port}"' in compose, f"المنفذ {port} ليس مربوطاً بـ127.0.0.1"
        # لا كشف على كلّ الواجهات (0.0.0.0 أو ربط عارٍ بلا مضيف).
        assert f"0.0.0.0:{port}" not in compose, f"المنفذ {port} مكشوف على 0.0.0.0 — انحدار F-005"
        assert not re.search(rf'^\s*-\s*"{port}:{port}"\s*$', compose, re.M), (
            f"المنفذ {port} مربوط عارياً (كلّ الواجهات) — انحدار F-005"
        )


# ── F-006: ترويسات أمان nginx ──
def test_nginx_security_headers_present():
    """F-006: nginx.fixed.conf يحوي ترويسات الأمان الأساسيّة (X-Frame-Options, nosniff)."""
    conf = _read("nginx/nginx.fixed.conf")
    assert "X-Frame-Options" in conf, "X-Frame-Options مفقود — انحدار F-006"
    assert "X-Content-Type-Options" in conf and "nosniff" in conf, (
        "X-Content-Type-Options: nosniff مفقود — انحدار F-006"
    )


# ── توجيه auth (خطأ v05: /auth/ يُجرّد البادئة ⇒ 404) ──
def test_nginx_auth_routing_rewrite_present():
    """يحرس إصلاح توجيه auth: rewrite يمنع /auth/auth/* ⇒ 404 (خطأ توجيه v05)."""
    conf = _read("nginx/nginx.fixed.conf")
    assert "rewrite ^/auth/auth/" in conf, (
        "إصلاح توجيه auth (rewrite ^/auth/auth/) مفقود — يعود خطأ التوجيه (login ⇒ 404)"
    )
