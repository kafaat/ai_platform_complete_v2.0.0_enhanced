"""sensing_adapter يجب أن يُرسل توكن الخدمة (X-Agent-Token) لـraster /indices.

الفجوة (نفس صنف imagery_automation): raster `GET /indices` محميّ بـ_require_service_token،
لكنّ sensing_adapter كان ينادي عبر _get_json بلا توكن ⇒ 503/401 يُبتلَع ⇒ تغذية
الاستشعار الحيّة (ndvi/ndre…) لخطّ field-intelligence ميتة صامتاً.

اختبار تعاقُد مصدريّ + سلوكيّ نقيّ (بلا شبكة) — يعمل في وظيفة الوحدات بـCI.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.join(os.path.dirname(__file__), "..")
ADAPTERS = os.path.join(ROOT, "services/sahool-platform/core/field_intelligence_adapters.py")


def test_sensing_adapter_passes_agent_token_source():
    """تعاقُد مصدريّ: sensing_adapter يقرأ /indices عبر واجهة raster التي تحمل X-Agent-Token.

    P2 raster facade: توكن الخدمة انتقل من _get_json المحلّيّ إلى raster_service_client
    (raster_service_headers تبني X-Agent-Token من SAHOOL_AGENT_TOKEN). النيّة محفوظة:
    نداء /indices ما زال يحمل توكن الخدمة — عبر الواجهة.
    """
    src = open(ADAPTERS, encoding="utf-8").read()
    sa = src[src.index("def sensing_adapter") : src.index("def sensing_adapter") + 500]
    assert "get_indices_sync" in sa, "sensing_adapter لا يقرأ /indices عبر واجهة raster"
    client = open(
        os.path.join(ROOT, "services/sahool-platform/api/raster_service_client.py"),
        encoding="utf-8",
    ).read()
    assert 'os.getenv("SAHOOL_AGENT_TOKEN"' in client, "الواجهة لا تقرأ توكن الخدمة"
    assert '"X-Agent-Token"' in client, "الواجهة لا تبني رأس X-Agent-Token"


@pytest.mark.skipif(
    importlib.util.find_spec("httpx") is None, reason="httpx غير متاح في بيئة الوحدات الخفيفة"
)
def test_get_json_sends_agent_token_header(monkeypatch):
    """سلوكيّ: _get_json(agent_token=…) يُرسل الرأس فعليّاً (نلتقطه عبر transport وهميّ).

    _get_json يستورد httpx داخليّاً ثمّ يُنشئ httpx.Client؛ فنرقّع httpx.Client على
    وحدة httpx نفسها لتُعيد عميلاً بـMockTransport يلتقط الرؤوس."""
    import sys

    d = os.path.join(ROOT, "services/sahool-platform")
    if d not in sys.path:
        sys.path.insert(0, d)
    import httpx
    from core import field_intelligence_adapters as fia

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["X-Agent-Token"] = request.headers.get("X-Agent-Token")
        return httpx.Response(200, json={"ndvi": 0.5})

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    )
    out = fia._get_json("http://raster/indices", {"field_id": "f1"}, agent_token="secret-token")
    assert out == {"ndvi": 0.5}
    assert captured["X-Agent-Token"] == "secret-token"
