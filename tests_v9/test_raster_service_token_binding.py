"""حارسُ توكن الخدمة في الراستر يُربَط بكلّ نداء فعلاً — لا TypeError قبل التحقّق (P0).

التدقيق الموحَّد 2026-09-13: ``require_service_token(x_agent_token, agent_token)`` كان
بوسيطين إلزاميّين بينما 14 نداءً في خمسة راوترات (storage · processing · jobs ·
timeseries_routes · imagery_search) تمرّر الترويسة وحدَها، فكان كلُّ طلب على تلك النقاط
يسقط بـ``TypeError`` (500) **قبل** أيّ مقارنة توكن — منذ `3b77847b` وبلا اختبار يستورد
تلك الراوترات. ``fields.py`` نجا لأنّه يستعمل غلافاً محلّيّاً.

الحارس هنا وجهان: (١) AST — كلُّ نداء في الراوترات يُربَط بتوقيع الدالّة الحقيقيّ عبر
``inspect.signature().bind``؛ (٢) سلوك — النداء بوسيط واحد يقرأ التوكن المضبوط عند النداء
ويرفض/يقبل كما النداء بوسيطين.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = Path(__file__).resolve().parents[1]
RASTER = ROOT / "services" / "raster-service"
ROUTERS = RASTER / "routers"


def _load_security_context():
    for path in (str(ROOT), str(RASTER)):
        if path not in sys.path:
            sys.path.insert(0, path)
    importlib.import_module("raster_settings")  # ما يقرؤه الحارس عند النداء بوسيط واحد
    spec = importlib.util.spec_from_file_location(
        "_raster_security_context_under_test", RASTER / "raster_security_context.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _guard_calls():
    """كلّ نداء ``require_service_token(...)`` (مجرّداً أو عبر الوحدة) في راوترات الراستر."""
    for path in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "require_service_token":
                yield path.name, node


def test_every_router_call_binds_to_the_real_guard_signature():
    module = _load_security_context()
    sig = inspect.signature(module.require_service_token)
    calls = list(_guard_calls())
    assert len(calls) >= 14, "النداءات المقيسة في التدقيق اختفت — تحقّق من الراوترات"
    unbound = []
    for fname, call in calls:
        args = [object()] * len(call.args)
        kwargs = {kw.arg: object() for kw in call.keywords if kw.arg}
        try:
            sig.bind(*args, **kwargs)
        except TypeError as exc:
            unbound.append(f"{fname}:{call.lineno} {exc}")
    assert not unbound, "نداءات لا تُربَط بتوقيع الحارس (500 قبل التحقّق): " + "; ".join(unbound)


def test_one_argument_call_reads_the_configured_token_at_call_time(monkeypatch):
    module = _load_security_context()
    from fastapi import HTTPException

    settings = sys.modules["raster_settings"]
    monkeypatch.setattr(settings, "AGENT_TOKEN", "configured-token-for-test")
    module.require_service_token("configured-token-for-test")  # صالح ⇒ لا استثناء
    with pytest.raises(HTTPException) as wrong:
        module.require_service_token("wrong-token")
    assert wrong.value.status_code == 401
    with pytest.raises(HTTPException) as missing:
        module.require_service_token(None)
    assert missing.value.status_code == 401


def test_unconfigured_token_fails_closed_for_both_call_shapes(monkeypatch):
    module = _load_security_context()
    from fastapi import HTTPException

    settings = sys.modules["raster_settings"]
    monkeypatch.setattr(settings, "AGENT_TOKEN", "")
    for call in (
        lambda: module.require_service_token("anything"),
        lambda: module.require_service_token("anything", ""),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 503


def test_two_argument_call_still_uses_the_explicit_token(monkeypatch):
    module = _load_security_context()
    from fastapi import HTTPException

    settings = sys.modules["raster_settings"]
    monkeypatch.setattr(settings, "AGENT_TOKEN", "configured")
    module.require_service_token("explicit", "explicit")
    with pytest.raises(HTTPException) as exc:
        module.require_service_token("configured", "explicit")
    assert exc.value.status_code == 401
