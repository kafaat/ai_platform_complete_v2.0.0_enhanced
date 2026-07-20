"""حارس ساكن لنقطة auth ``/auth/edge-sign`` (SEASON-RECORD-ENTRY-01 شريحة 3b).

النواة النقيّة (اشتقاق الأدوار + التوقيع مقيَّد الوجهة) مُثبَتة وحدةً في test_season_edge_attestation.
هذا الحارس يثبّت **أسلاك** النقطة الحسّاسة بلا تشغيل تطبيق auth الكامل (AST/نصّ):
  • التوقيع باشتقاق مُعلَن {owner, expert} (season_reviewer_roles_for)، لا الدور الخام.
  • مقيَّد بالوجهة: compute_edge_attestation على method/path/body (لا الهويّة فقط).
  • الوجهة القانونيّة من ترويسة nginx (X-Canonical-*) لا من هويّة العميل — والغياب fail-closed.
  • مفتاح غير مُهيّأ ⇒ 503 (لا توقيع صامت). هويّة JWT عبر get_current_user (لا ترويسة عارية).

وحدة صرفة — ``pytest -m unit`` (لا شبكة/تطبيق).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "services" / "auth" / "routers" / "season_edge_sign.py"


def _source() -> str:
    return _SRC.read_text(encoding="utf-8")


def test_endpoint_registered_get_edge_sign():
    """راوتر يُصدِّر router ونقطة GET /auth/edge-sign (auto-register في auth، بلا تضخيم main)."""
    src = _source()
    tree = ast.parse(src)
    assert "router = APIRouter()" in src
    routes = {
        (d.func.attr.upper(), d.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        for d in node.decorator_list
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "router"
        and d.args
        and isinstance(d.args[0], ast.Constant)
    }
    assert ("GET", "/auth/edge-sign") in routes
    assert len(routes) == 1  # نقطة واحدة فقط — لا توسّع صامت


def test_signs_with_declared_derivation_and_destination_bound():
    src = _source()
    # اشتقاق مُعلَن {owner, expert} لا الدور الخام
    assert "season_reviewer_roles_for(" in src
    assert 'user.get("role")' in src or "user.get('role')" in src
    # مقيَّد بالوجهة: التوقيع على method/path/body
    assert "compute_edge_attestation(" in src
    assert "edge_body_sha256(" in src
    # الهويّة من JWT (get_current_user) لا ترويسة عارية
    assert "get_current_user" in src
    assert 'user.get("sub"' in src or "user.get('sub'" in src


def test_canonical_from_nginx_header_and_fail_closed():
    src = _source()
    # الوجهة القانونيّة من ترويسة nginx (X-Canonical-*) — الموقِّع يثق بما تُعلنه البوّابة
    assert "X-Canonical-Method" in src
    assert "X-Canonical-Path" in src
    # fail-closed: وجهة ناقصة ⇒ 401 · مفتاح غير مُهيّأ ⇒ 503 (لا توقيع صامت)
    assert "canonical destination required" in src
    assert "SEASON_EDGE_HMAC_KEY" in src
    assert "edge signing not configured" in src
    assert "HTTP_401_UNAUTHORIZED" in src
    assert "HTTP_503_SERVICE_UNAVAILABLE" in src


def test_returns_edge_headers_for_gateway():
    """يضع ترويسات التصديق على الردّ ليرفعها nginx بـauth_request_set (لا تُعاد للعميل)."""
    src = _source()
    for h in (
        "X-User-Id",
        "X-Roles",
        "X-Edge-Timestamp",
        "X-Edge-Attestation",
        "X-Tenant-Id",
    ):
        assert f'response.headers["{h}"]' in src, h
