"""اختبار تعاقُد توصيل نواة GIS (api/routers/gis_kernel.py) + سلوك العلم.

يثبت — بلا قاعدة:
  ١) النقاط الأربع (buffer/union/split/validate) مُسجَّلة POST على app.routes.
  ٢) العلم مُطفأ افتراضاً ⇒ `_gis_kernel_enabled()` False و`_require_enabled()` يرفع 404.
  ٣) العلم مُفعَّل ⇒ لا يرفع.
  ٤) كلّ نقطة محروسة بصلاحيّة RECOMMENDATION_VIEW (شجرة التبعيّات تحوي get_current_user).

مُعلَّم unit؛ يُشغَّل من services/sahool-platform بـPYTHONPATH=.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

import api.main as m  # noqa: E402
from api.routers import gis_kernel as gk  # noqa: E402

_EXPECTED = {
    ("POST", "/api/v1/gis/buffer"),
    ("POST", "/api/v1/gis/union"),
    ("POST", "/api/v1/gis/split"),
    ("POST", "/api/v1/gis/validate"),
}


def _routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for route in m.app.routes:
        path = getattr(route, "path", "")
        for meth in getattr(route, "methods", None) or set():
            out.add((meth, path))
    return out


def test_four_gis_endpoints_registered():
    routes = _routes()
    missing = _EXPECTED - routes
    assert not missing, f"نقاط GIS غير موصولة: {sorted(missing)}"


def test_flag_off_by_default_and_require_enabled_raises_404(monkeypatch):
    monkeypatch.delenv("FEATURE_GIS_KERNEL", raising=False)
    assert gk._gis_kernel_enabled() is False
    with pytest.raises(HTTPException) as exc:
        gk._require_enabled()
    assert exc.value.status_code == 404


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_flag_on_variants_enable(monkeypatch, val):
    monkeypatch.setenv("FEATURE_GIS_KERNEL", val)
    assert gk._gis_kernel_enabled() is True
    gk._require_enabled()  # لا يرفع


@pytest.mark.parametrize("val", ["0", "false", "off", "", "maybe"])
def test_flag_falsey_variants_disable(monkeypatch, val):
    monkeypatch.setenv("FEATURE_GIS_KERNEL", val)
    assert gk._gis_kernel_enabled() is False


def _auth_in_tree(dep) -> bool:
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", "") == "get_current_user":
        return True
    return any(_auth_in_tree(sub) for sub in getattr(dep, "dependencies", []))


def test_all_gis_endpoints_require_auth():
    guarded = {
        getattr(r, "path", "")
        for r in m.app.routes
        if getattr(r, "path", "").startswith("/api/v1/gis/")
        and getattr(r, "dependant", None) is not None
        and _auth_in_tree(r.dependant)
    }
    expected_paths = {p for _, p in _EXPECTED}
    assert expected_paths <= guarded, f"نقاط GIS بلا مصادقة: {sorted(expected_paths - guarded)}"
