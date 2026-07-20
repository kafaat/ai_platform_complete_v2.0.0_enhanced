"""حارس صارم: healthcheck على erp-bridge ← /healthz فقط، لا ربط بمسار قدراتيّ.

ERR-BRIDGE-001 (مغلق بالالتزام 36e8656): الحاوية كانت تنهار في lifespan بسبب
CREATE TABLE تحت sahool_app الذي لا يملك CREATE على schema public.
هذا الحارس يمنع فئة أخرى (مستقلة): healthcheck يضرب مساراً يشترط قدرة خارجية
اختيارية ⇒ ERP غير مهيّأ يُدين الحاوية كلّها.

القواعد الثلاث المفروضة (ساكنة — لا خدمات مطلوبة):
  1. compose: healthcheck على erp-bridge يستخدم /healthz — لا /readyz، لا /capabilities.
  2. /healthz: كود النقطة لا يستدعي get_active_erp_provider() ولا أيّ I/O خارجيّ.
  3. /readyz/capabilities: كود النقطة لا يرفع HTTPException ولا يُجري probe شبكيّ.

البرهان السلبيّ: اختبار منفصل يُثبت أنّ الحارس نفسه يفشل عند انتهاك القاعدة
(healthcheck يُضبَط على /readyz/capabilities) ⇒ الحارس ليس فارغاً.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.v9.yml"
HEALTH_ROUTER = ROOT / "services" / "odoo-bridge" / "routers" / "health.py"

# المسارات المحظورة في healthcheck (قدراتيّة أو جاهزية تفصيلية تشترط I/O خارجيّ)
_FORBIDDEN_HC_PATHS = (
    "readyz",
    "capabilities",
)


# ══════════════════════════════════════════════════════════════════
# ① Compose: healthcheck يستخدم /healthz لا مساراً قدراتيّاً
# ══════════════════════════════════════════════════════════════════
def _erp_bridge_healthcheck_line(compose_text: str) -> str:
    """يستخرج سطر healthcheck test الخاصّ بـsahool-erp-bridge من compose."""
    in_bridge = False
    in_hc = False
    for line in compose_text.splitlines():
        stripped = line.strip()
        if "sahool-erp-bridge:" in stripped:
            in_bridge = True
            in_hc = False
            continue
        # نقطة خدمة جديدة (لا مسافة بادئة أو مسافتان)
        if in_bridge and re.match(r"^  \S", line) and "sahool-erp-bridge:" not in line:
            if not stripped.startswith("-") and ":" in stripped:
                in_bridge = False
        if in_bridge and "healthcheck:" in stripped:
            in_hc = True
        if in_bridge and in_hc and "localhost" in stripped:
            return stripped
    return ""


def test_erp_bridge_compose_healthcheck_uses_healthz():
    """Compose healthcheck لـerp-bridge يضرب /healthz — لا /readyz ولا /capabilities."""
    compose = COMPOSE.read_text(encoding="utf-8")
    hc_line = _erp_bridge_healthcheck_line(compose)
    assert hc_line, "لم يُعثَر على سطر healthcheck في تعريف sahool-erp-bridge"
    assert "/healthz" in hc_line, (
        f"healthcheck لا يستخدم /healthz: {hc_line!r}"
    )
    for forbidden in _FORBIDDEN_HC_PATHS:
        assert forbidden not in hc_line, (
            f"healthcheck يحتوي مساراً محظوراً ({forbidden!r}): {hc_line!r}"
        )


# ══════════════════════════════════════════════════════════════════
# ② /healthz: كود النقطة لا يستدعي I/O خارجيّ
# ══════════════════════════════════════════════════════════════════
def _healthz_function_source(router_text: str) -> str:
    """يستخرج جسم دالة healthz من ملفّ الراوتر."""
    tree = ast.parse(router_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "healthz":
            lines = router_text.splitlines()
            start = node.body[0].lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    return ""


_FORBIDDEN_HEALTHZ_CALLS = (
    "get_active_erp_provider",
    "get_odoo",
    "authenticate",
    "asyncpg",
    "httpx",
    "_pool",
    "acquire",
    "fetchval",
)


def test_healthz_contains_no_external_io():
    """/healthz لا يستدعي ERP ولا DB ولا أيّ I/O — نقطة خالصة."""
    src = HEALTH_ROUTER.read_text(encoding="utf-8")
    body = _healthz_function_source(src)
    assert body, "لم يُعثَر على دالة healthz في الراوتر"
    for forbidden in _FORBIDDEN_HEALTHZ_CALLS:
        assert forbidden not in body, (
            f"/healthz تستدعي {forbidden!r} — انتهاك نقاء مسار الحياة"
        )


# ══════════════════════════════════════════════════════════════════
# ③ /readyz/capabilities: لا HTTPException، لا probe شبكيّ
# ══════════════════════════════════════════════════════════════════
_FORBIDDEN_CAPABILITIES_CALLS = (
    "HTTPException",
    "raise",
    "authenticate",
    "asyncpg",
    "httpx",
    "_pool",
    "acquire",
    "fetchval",
)


def _capabilities_function_source(router_text: str) -> str:
    tree = ast.parse(router_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "readyz_capabilities":
            lines = router_text.splitlines()
            start = node.body[0].lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])
    return ""


def test_capabilities_endpoint_never_raises_http_exception():
    """/readyz/capabilities لا يرفع HTTPException ولا يُجري probe شبكيّ — HTTP 200 دائماً."""
    src = HEALTH_ROUTER.read_text(encoding="utf-8")
    body = _capabilities_function_source(src)
    assert body, "لم يُعثَر على دالة readyz_capabilities في الراوتر"
    for forbidden in _FORBIDDEN_CAPABILITIES_CALLS:
        assert forbidden not in body, (
            f"/readyz/capabilities تحتوي {forbidden!r} — قد تُعيد HTTP ≠ 200"
        )


# ══════════════════════════════════════════════════════════════════
# ④ البرهان السلبيّ — الحارس يفشل عند انتهاك القاعدة
# ══════════════════════════════════════════════════════════════════
def test_guard_negative_proof_detects_forbidden_healthcheck_path():
    """البرهان السلبيّ: إذا أُضيف 'readyz' لسطر healthcheck يفشل الحارس.

    يُثبت أنّ test_erp_bridge_compose_healthcheck_uses_healthz ليس اختباراً فارغاً:
    نُزيّف compose مع مسار محظور ونتحقّق أنّ الدالة المساعِدة ترصده.
    """
    fake_compose = """
  sahool-erp-bridge:
    healthcheck:
      test:
      - CMD
      - curl
      - -f
      - http://localhost:8126/readyz/capabilities
"""
    hc_line = _erp_bridge_healthcheck_line(fake_compose)
    # يجب أن يكون الخطّ مرصوداً
    assert hc_line, "الدالة المساعِدة لم تعثر على سطر healthcheck في النصّ المزيَّف"
    # ويجب أن يحتوي على مسار محظور
    has_forbidden = any(f in hc_line for f in _FORBIDDEN_HC_PATHS)
    assert has_forbidden, (
        "الدالة المساعِدة لم ترصد المسار المحظور في النصّ المزيَّف — "
        "الحارس الرئيسيّ قد يكون فارغاً"
    )
