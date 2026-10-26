"""video-processor ⇒ edge-inference: الإطار يحمل حقل البثّ ومحصوله، لا قيماً ثابتة.

كان `run_inference` يُرسِل `field_id="stream"` و`crop="wheat"` لكلّ بثّ، فتُزامِن الحافة
نتيجةً لحقلٍ غير موجود تردّ عليه المنصّة 404 وتُعاد محاولتها بلا نهاية. هنا يُقاس
ما يصل الحافة فعلاً: field_id البثّ إن رُبط بحقل (وإلّا لا field_id فلا مزامنة)،
والمحصول إن عُرف (وإلّا لا يُرسَل — لا «wheat» مُفترَض).
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.unit

VIDEO = Path(__file__).resolve().parents[1] / "services" / "video-processor"


@pytest.fixture
def vp(monkeypatch):
    monkeypatch.syspath_prepend(str(VIDEO))
    for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    # cv2 ثقيل وغير مثبّت في طبقة الاختبار؛ run_inference يستورده داخل الدالّة.
    cv2 = types.ModuleType("cv2")
    cv2.imencode = lambda ext, frame: (True, np.frombuffer(b"\xff\xd8jpeg", dtype=np.uint8))
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    module = importlib.import_module("main")
    assert hasattr(module, "run_inference") and hasattr(module, "StreamConfig")
    try:
        yield module
    finally:
        for name in ("main", "router_registry", "routers", "routers.streams", "routers.health"):
            sys.modules.pop(name, None)


@pytest.fixture
def posted(vp, monkeypatch):
    calls: list[dict] = []

    class _Resp:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {"detections": []}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return _Resp()

    monkeypatch.setattr(vp.httpx, "AsyncClient", _Client)
    return calls


FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


async def test_bound_stream_sends_its_own_field_id_and_crop(vp, posted):
    cfg = vp.StreamConfig(stream_id="s1", field_id="field-42", crop="maize")
    await vp.run_inference(FRAME, cfg)
    assert len(posted) == 1
    data = posted[0]["data"]
    assert posted[0]["url"].endswith("/v1/inference/pest-detect")
    assert data["field_id"] == "field-42"
    assert data["crop"] == "maize"


async def test_unknown_crop_is_not_invented_as_wheat(vp, posted):
    cfg = vp.StreamConfig(stream_id="s1", field_id="field-42")
    await vp.run_inference(FRAME, cfg)
    data = posted[0]["data"]
    assert data["field_id"] == "field-42"
    assert "crop" not in data


@pytest.mark.parametrize("field_id", ["unknown", "", "  ", "stream"])
async def test_unbound_stream_sends_no_field_id_so_the_edge_does_not_sync(vp, posted, field_id):
    cfg = vp.StreamConfig(stream_id="s1", field_id=field_id)
    await vp.run_inference(FRAME, cfg)
    data = posted[0]["data"]
    assert "field_id" not in data
    assert "crop" not in data


def test_create_stream_request_accepts_only_known_crops(vp):
    assert vp.CreateStreamRequest(field_id="f1", crop="coffee").crop == "coffee"
    assert vp.CreateStreamRequest(field_id="f1").crop is None
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        vp.CreateStreamRequest(field_id="f1", crop="banana")
