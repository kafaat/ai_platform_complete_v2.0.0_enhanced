"""قناة خدمة-لخدمة للحالة القانونيّة (supervisor → المنصّة → guardrails).

يثبّت: (أ) المنصّة تحمي /internal/fields/{id}/state بـX-Agent-Token (fail-closed)
وتُسجّلها؛ (ب) supervisor يجلب الحالة عبر القناة الداخليّة ويُرفِقها بـfarm_context
في كلا مساري التحقّق — فتمرّ الحَوكمة عبر مصدر الحقيقة الواحد.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")
SUPERVISOR_MAIN = os.path.join(ROOT, "services/supervisor-agent", "main.py")


@pytest.fixture(scope="module")
def app_mod():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as m

    return m


def test_internal_state_route_registered(app_mod):
    paths = {getattr(r, "path", None) for r in app_mod.app.routes}
    assert "/internal/fields/{field_id}/state" in paths


def test_require_service_token_fail_closed(app_mod, monkeypatch):
    from fastapi import HTTPException

    # سرّ غير مضبوط ⇒ يُرفض دائماً (fail-closed)
    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e1:
        app_mod._require_service_token("anything")
    assert e1.value.status_code == 403

    # سرّ مضبوط ⇒ يُرفض المختلف، ويُقبل المطابق
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cr3t-token-value")
    with pytest.raises(HTTPException) as e2:
        app_mod._require_service_token("wrong")
    assert e2.value.status_code == 403
    assert app_mod._require_service_token("s3cr3t-token-value") is None  # يمرّ


def _supervisor_src() -> str:
    with open(SUPERVISOR_MAIN, encoding="utf-8") as f:
        return f.read()


def _func_src(src: str, name: str) -> str:
    start = src.index(f"async def {name}(")
    nxt = re.search(r"\n(?:@\w|async def |def |class )", src[start + 1 :])
    end = (start + 1 + nxt.start()) if nxt else len(src)
    return src[start:end]


def test_supervisor_fetches_state_via_internal_channel():
    src = _supervisor_src()
    fetch = _func_src(src, "_fetch_field_state")
    assert "/internal/fields/" in fetch
    assert "X-Agent-Token" in fetch
    assert "tenant_id" in fetch
    # fail-safe: يُرجِع None عند غياب المعرّفات أو التعذّر
    assert "return None" in fetch


def test_supervisor_injects_field_state_into_farm_context():
    src = _supervisor_src()
    for fn in ("_validate_actions_via_guardrails", "_validate_via_guardrails"):
        body = _func_src(src, fn)
        assert "_fetch_field_state" in body, f"{fn} لا يجلب الحالة القانونيّة"
        assert 'farm_context"]["field_state"]' in body, f"{fn} لا يُرفِق field_state"
