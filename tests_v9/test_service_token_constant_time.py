"""حارس التوكن الخدميّ (_require_service_token) — fail-closed + مقارنة زمن ثابت.

النقاط الداخليّة (/internal/...) محميّة بـSAHOOL_AGENT_TOKEN. هذه الاختبارات تثبّت:
السرّ الغائب يُرفض (fail-closed)، التوكن الخاطئ/الغائب يُرفض (403)، والصحيح يمرّ —
والمقارنة تمرّ عبر hmac.compare_digest (زمن ثابت) لا == (تسريب توقيت).
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit  # CI يشغّل -m unit؛ بلا الوسم لا يُنفَّذ

ROOT = os.path.join(os.path.dirname(__file__), "..")
CORE = os.path.join(ROOT, "services/sahool-platform")


@pytest.fixture(scope="module")
def m():
    if CORE not in sys.path:
        sys.path.insert(0, CORE)
    pytest.importorskip("fastapi")
    import api.main as main_mod

    return main_mod


def test_missing_secret_is_fail_closed(m, monkeypatch):
    """لا SAHOOL_AGENT_TOKEN في البيئة ⇒ تُرفض كلّ المحاولات (لا تُفتح النقطة)."""
    from fastapi import HTTPException

    monkeypatch.delenv("SAHOOL_AGENT_TOKEN", raising=False)
    with pytest.raises(HTTPException) as e:
        m._require_service_token(x_agent_token="anything")
    assert e.value.status_code == 403


def test_wrong_and_missing_token_rejected(m, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cret-agent-token")
    for bad in ("wrong", "", None):
        with pytest.raises(HTTPException) as e:
            m._require_service_token(x_agent_token=bad)
        assert e.value.status_code == 403


def test_correct_token_passes(m, monkeypatch):
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "s3cret-agent-token")
    # لا استثناء ⇒ مقبول (الدالّة تُعيد None ضمنيّاً)
    assert m._require_service_token(x_agent_token="s3cret-agent-token") is None


def test_uses_constant_time_compare(m):
    """تأكيد بنيويّ: الحارس يستخدم hmac.compare_digest لا == (منع تسريب التوقيت)."""
    import inspect

    src = inspect.getsource(m._require_service_token)
    assert "compare_digest" in src, "يجب أن تكون المقارنة بزمن ثابت (hmac.compare_digest)"
