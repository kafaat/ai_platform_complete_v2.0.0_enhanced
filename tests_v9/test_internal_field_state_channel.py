"""قناة خدمة-لخدمة للحالة القانونيّة (supervisor → المنصّة → guardrails).

يثبّت: (أ) المنصّة تحمي /internal/fields/{id}/state بـX-Agent-Token (fail-closed)
وتُسجّلها؛ (ب) supervisor._fetch_field_state يستدعي القناة الداخليّة بالرؤوس/المعاملات
الصحيحة ويفشل بأمان (اختبار سلوكيّ بعميل مُزيّف)؛ (ج) كلا مساري التحقّق يحقنان
field_state في farm_context — فتمرّ الحَوكمة عبر مصدر الحقيقة الواحد.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
SUPERVISOR = os.path.join(ROOT, "services/supervisor-agent")
SUPERVISOR_MAIN = os.path.join(SUPERVISOR, "main.py")


@pytest.fixture(scope="module")
def app_mod():
    pytest.importorskip("fastapi")
    added = CORE not in sys.path
    if added:
        sys.path.insert(0, CORE)
    import api.main as m

    yield m
    if added and CORE in sys.path:  # عزل: أزِل المسار في التفكيك
        sys.path.remove(CORE)


@pytest.fixture(scope="module")
def sup_mod():
    # تحميل main.py الخاصّ بـsupervisor تحت اسم فريد عبر importlib — اسم الوحدة
    # «main» شائع عبر الخدمات فـ`import main` قد يعيد وحدة خدمة أخرى مُخبّأة (تضارب
    # ترتيب الاختبارات). التحميل من المسار باسم فريد يعزله.
    import importlib.util

    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    added = SUPERVISOR not in sys.path
    if added:
        sys.path.insert(0, SUPERVISOR)  # لازم لاستيرادات أخواته (circuit_breaker…)
    try:
        spec = importlib.util.spec_from_file_location(
            "sahool_supervisor_main_under_test", SUPERVISOR_MAIN
        )
        sup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sup)
        yield sup
    finally:
        if added and SUPERVISOR in sys.path:
            sys.path.remove(SUPERVISOR)


# ── المنصّة: حماية + تسجيل النقطة الداخليّة ──
def test_internal_state_route_registered(app_mod):
    paths = {getattr(r, "path", None) for r in app_mod.app.routes}
    assert "/internal/fields/{field_id}/state" in paths


def test_require_service_token_fail_closed(app_mod, monkeypatch):
    # P1 decomposition: النقطة الداخليّة وحارسها انتقلا إلى api/routers/internal_service.py
    # (الحارس نفسه في api/service_token_auth.py) — نفحصه حيث تستهلكه النقطة.
    from api.routers.internal_service import _require_service_token
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e1:  # سرّ غير مضبوط ⇒ يُرفض دائماً
        _require_service_token("anything")
    assert e1.value.status_code == 403

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t-token-value")
    with pytest.raises(HTTPException) as e2:  # سرّ مختلف ⇒ يُرفض
        _require_service_token("wrong")
    assert e2.value.status_code == 403
    assert _require_service_token("s3cr3t-token-value") is None  # مطابق ⇒ يمرّ


# ── supervisor: اختبار سلوكيّ لـ_fetch_field_state بعميل مُزيّف ──
class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        return self._resp


@pytest.mark.asyncio
async def test_fetch_field_state_calls_internal_channel(sup_mod, monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "tkn")
    client = _FakeClient(_Resp(200, {"validity": "valid", "execution_mode": "auto"}))
    out = await sup_mod._fetch_field_state(client, "fld_1", "t1")
    assert out == {"validity": "valid", "execution_mode": "auto"}
    url, params, headers = client.calls[0]
    assert url.endswith("/internal/fields/fld_1/state")
    assert params == {"tenant_id": "t1"}
    assert headers["X-Agent-Token"] == "tkn"


@pytest.mark.asyncio
async def test_fetch_field_state_none_without_ids(sup_mod):
    client = _FakeClient(_Resp(200, {}))
    assert await sup_mod._fetch_field_state(client, None, "t1") is None
    assert await sup_mod._fetch_field_state(client, "f", None) is None
    assert client.calls == []  # لا نداء بلا معرّفات (fail-safe)


@pytest.mark.asyncio
async def test_fetch_field_state_none_on_non_200(sup_mod):
    client = _FakeClient(_Resp(404, {"detail": "غير موجود"}))
    assert await sup_mod._fetch_field_state(client, "f", "t") is None


# ── supervisor: تعاقُد المصدر لحقن field_state في كلا مساري التحقّق ──
def test_both_guardrails_paths_inject_field_state():
    with open(SUPERVISOR_MAIN, encoding="utf-8") as f:
        src = f.read()
    for fn in ("_validate_actions_via_guardrails", "_validate_via_guardrails"):
        start = src.index(f"async def {fn}(")
        nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
        body = src[start : (start + 1 + nxt.start()) if nxt else len(src)]
        assert "_fetch_field_state" in body, f"{fn} لا يجلب الحالة القانونيّة"
        assert 'farm_context"]["field_state"]' in body, f"{fn} لا يحقن field_state"
