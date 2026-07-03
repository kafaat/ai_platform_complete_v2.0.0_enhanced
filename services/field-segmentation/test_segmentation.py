#!/usr/bin/env python3
"""
اختبارات وحدة لخدمة تقطيع الحقل (offline، pytest، @unit).

تغطّي عقد الصدق:
  • manual → هندسة Polygon مغلقة صالحة + source=manual (مسار حقيقيّ).
  • auto بلا خادم استدلال مُهيّأ → 503 صادق (model_not_configured) — لا تلفيق.
  • hybrid بلا خادم استدلال مُهيّأ → 503 صادق.
  • auto/hybrid مع خادم مُهيّأ + خلفيّة موهومة تُرجِع Polygon → 200 مُدقَّق (source=backend).
  • تعذّر اتصال/مهلة الخادم → 503 inference_unreachable.
  • الخادم يردّ غير 2xx → 502 inference_failed.
  • الخادم يردّ 2xx بهندسة ناقصة/فاسدة → 502 inference_bad_geometry (برهان: بلا تلفيق).
  • تحقّق المضلّع (NaN/خارج المدى/رؤوس ناقصة) → 422.
  • مصادقة توكن الخدمة (X-Agent-Token).

مَفصِل المحاكاة (seam): نُرقّع main._post_inference (الذي يلفّ httpx.Client.post)
بدالّة تُرجِع httpx.Response جاهزاً أو ترفع httpx.ConnectError — بلا أيّ شبكة.

التشغيل:
  cd services/field-segmentation && PYTHONPATH=. pytest -m unit -q
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

pytestmark = pytest.mark.unit

_TOKEN = "test-agent-token"


def _load_app(monkeypatch, *, model_path: str = "", backend: str = "", inference_url: str = ""):
    """يحمّل main بقيم بيئة محدّدة (الخدمة تقرأها وقت الاستيراد)."""
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", _TOKEN)
    if model_path:
        monkeypatch.setenv("SEGMENTATION_MODEL_PATH", model_path)
    else:
        monkeypatch.delenv("SEGMENTATION_MODEL_PATH", raising=False)
    if backend:
        monkeypatch.setenv("SEGMENTATION_BACKEND", backend)
    else:
        monkeypatch.delenv("SEGMENTATION_BACKEND", raising=False)
    if inference_url:
        monkeypatch.setenv("SEGMENTATION_INFERENCE_URL", inference_url)
    else:
        monkeypatch.delenv("SEGMENTATION_INFERENCE_URL", raising=False)
    sys.modules.pop("main", None)
    import main  # noqa: WPS433

    return importlib.reload(main)


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    mod = _load_app(monkeypatch)  # لا نموذج مُهيّأ افتراضاً
    return TestClient(mod.app)


def _hdr() -> dict:
    return {"X-Agent-Token": _TOKEN}


# ── ١. المسار اليدويّ حقيقيّ → هندسة + source=manual ──
def test_manual_returns_closed_geometry(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "manual", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "manual"
    assert body["source"] == "manual"
    ring = body["geometry"]["coordinates"][0]
    assert body["geometry"]["type"] == "Polygon"
    # الحلقة أُغلِقت (الرأس الأوّل = الأخير).
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_manual_accepts_geojson(client):
    gj = {
        "type": "Polygon",
        "coordinates": [[[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]],
    }
    r = client.post("/segment", json={"mode": "manual", "user_polygon": gj}, headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "manual"


# ── ٢. auto/hybrid بلا نموذج → 503 صادق ──
def test_auto_without_model_returns_503(client):
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "model_not_configured"
    assert "SEGMENTATION_INFERENCE_URL" in detail["note_ar"]


def test_hybrid_without_model_returns_503(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "hybrid", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "model_not_configured"


# ── ٣. تحقّق المضلّع (مسار حقيقيّ يرفض القمامة) ──
def test_manual_rejects_out_of_range(client):
    poly = [[999.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_rejects_too_few_points(client):
    poly = [[46.0, 24.0], [46.1, 24.0]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_requires_polygon(client):
    r = client.post("/segment", json={"mode": "manual"}, headers=_hdr())
    assert r.status_code == 422, r.text


# ── ٤. مصادقة توكن الخدمة ──
def test_missing_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/segment", json={"mode": "manual", "user_polygon": poly})
    assert r.status_code == 401, r.text


def test_wrong_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "manual", "user_polygon": poly},
        headers={"X-Agent-Token": "wrong"},
    )
    assert r.status_code == 401, r.text


# ── ٥. صحّة/جاهزيّة ──
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["service"] == "field-segmentation"


def test_readyz_reports_model_state(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["model_configured"] is False


# ── ٦. محوّل الاستدلال البعيد (auto/hybrid مع خادم مُهيّأ) ──
_INFERENCE_URL = "http://inference.internal/predict"


def _configured(monkeypatch, backend: str = "sam2"):
    """يحمّل main بخادم استدلال مُهيّأ + يُعيد (mod, TestClient)."""
    from fastapi.testclient import TestClient

    mod = _load_app(monkeypatch, backend=backend, inference_url=_INFERENCE_URL)
    return mod, TestClient(mod.app)


def _fake_response(mod, *, status_code: int, json_body):
    """يبني httpx.Response حقيقيّاً (لا شبكة) لترقيع _post_inference."""
    import httpx

    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("POST", _INFERENCE_URL),
    )


def test_configured_model_flag_true(monkeypatch):
    """خادم مُهيّأ (خلفيّة + عنوان استدلال) ⇒ _model_configured و/readyz يبلّغان True."""
    mod, client = _configured(monkeypatch)
    assert mod._model_configured() is True
    assert client.get("/readyz").json()["model_configured"] is True


def test_auto_configured_backend_polygon_returns_200(monkeypatch):
    mod, client = _configured(monkeypatch, backend="geosam")
    # حلقة غير مغلقة قصداً: نُثبت أنّ normalize_polygon فعلاً ركض (سيُغلِقها).
    open_ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={"geometry": {"type": "Polygon", "coordinates": [open_ring]}},
        ),
    )
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "auto"
    assert body["source"] == "geosam"
    ring = body["geometry"]["coordinates"][0]
    # برهان أنّ normalize_polygon ركض: الحلقة أُغلِقت (5 رؤوس، الأوّل=الأخير).
    assert body["geometry"]["type"] == "Polygon"
    assert ring[0] == ring[-1]
    assert len(ring) == 5


def test_auto_surfaces_backend_confidence(monkeypatch):
    """درجة ثقة الخادم (SAM2 IoU) تُمرَّر في استجابة /segment (سير اقتراح ثمّ قبول)."""
    mod, client = _configured(monkeypatch, backend="sam2")
    ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={"geometry": {"type": "Polygon", "coordinates": [ring]}, "confidence": 0.87},
        ),
    )
    body = client.post("/segment", json={"mode": "auto"}, headers=_hdr()).json()
    assert body["confidence"] == 0.87, "لم تُمرَّر درجة ثقة الخادم في الاستجابة"
    assert body["metadata"]["source"] == "sam2"
    assert body["metadata"]["confidence"] == 0.87


def test_auto_surfaces_upstream_metadata(monkeypatch):
    """شفافية: image/model/post-processing metadata من SAM2 تمر عبر field-segmentation."""
    mod, client = _configured(monkeypatch, backend="sam2")
    ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "confidence": 0.81,
                "metadata": {
                    "imagery_source": "sentinel_truecolor",
                    "imagery_date": "2026-07-03",
                    "model_version": "sam2-hiera-large",
                    "post_processing": {"simplify_tolerance_m": 3},
                },
            },
        ),
    )
    body = client.post("/segment", json={"mode": "auto"}, headers=_hdr()).json()
    assert body["metadata"]["imagery_source"] == "sentinel_truecolor"
    assert body["metadata"]["model_version"] == "sam2-hiera-large"
    assert body["metadata"]["post_processing"]["simplify_tolerance_m"] == 3


def test_auto_confidence_none_when_backend_omits_it(monkeypatch):
    """لا درجة من الخادم ⇒ confidence=None (صدق، لا اختراع درجة)."""
    mod, client = _configured(monkeypatch, backend="sam2")
    ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod, status_code=200, json_body={"geometry": {"type": "Polygon", "coordinates": [ring]}}
        ),
    )
    body = client.post("/segment", json={"mode": "auto"}, headers=_hdr()).json()
    assert body["confidence"] is None


def test_manual_confidence_is_none(monkeypatch):
    """المسار اليدويّ (رسم المستخدم) بلا درجة نموذج ⇒ confidence=None."""
    mod, client = _configured(monkeypatch, backend="sam2")
    ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1], [46.0, 24.0]]
    body = client.post(
        "/segment", json={"mode": "manual", "user_polygon": ring}, headers=_hdr()
    ).json()
    assert body["source"] == "manual"
    assert body["confidence"] is None


def test_hybrid_configured_bare_polygon_returns_200(monkeypatch):
    """الاستجابة قد تكون Polygon خاماً (بلا غلاف geometry) — استخراج دفاعيّ."""
    mod, client = _configured(monkeypatch, backend="sam2")
    closed = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.0]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={"type": "Polygon", "coordinates": [closed]},
        ),
    )
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/segment",
        json={"mode": "hybrid", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "sam2"


def test_inference_unreachable_returns_503(monkeypatch):
    mod, client = _configured(monkeypatch)
    import httpx

    def _boom(payload):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(mod, "_post_inference", _boom)
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "inference_unreachable"


def test_inference_timeout_returns_503(monkeypatch):
    mod, client = _configured(monkeypatch)
    import httpx

    def _slow(payload):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(mod, "_post_inference", _slow)
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "inference_unreachable"


def test_inference_non_2xx_returns_502(monkeypatch):
    mod, client = _configured(monkeypatch)
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(mod, status_code=500, json_body={"err": "boom"}),
    )
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 502, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "inference_failed"
    assert detail["status"] == 500


def test_inference_missing_geometry_returns_502(monkeypatch):
    """2xx لكن بلا هندسة — برهان أنّنا لا نُلفّق مضلّعاً."""
    mod, client = _configured(monkeypatch)
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(mod, status_code=200, json_body={"foo": "bar"}),
    )
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 502, r.text
    assert r.json()["detail"]["error"] == "inference_bad_geometry"


def test_inference_invalid_geometry_returns_502(monkeypatch):
    """2xx بهندسة فاسدة (خارج المدى) — normalize_polygon يرفضها ⇒ 502، بلا تمرير قمامة."""
    mod, client = _configured(monkeypatch)
    bad = [[999.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={"geometry": {"type": "Polygon", "coordinates": [bad]}},
        ),
    )
    r = client.post("/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 502, r.text
    assert r.json()["detail"]["error"] == "inference_bad_geometry"

# ── ٩. ExG قبل SAM2: صورة محسّنة + prompts لا هندسة مُفبركة ──
def _png_b64_rgb_square() -> str:
    import base64
    import io

    import numpy as np
    from PIL import Image

    img = np.zeros((96, 96, 3), dtype=np.uint8)
    img[:, :] = [135, 112, 80]       # تربة/رمل
    img[24:72, 28:76] = [25, 178, 45]  # غطاء نباتي واضح
    out = io.BytesIO()
    Image.fromarray(img, "RGB").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def test_auto_exg_preprocesses_image_before_sam2(monkeypatch):
    mod, client = _configured(monkeypatch, backend="sam2")
    seen: dict = {}
    open_ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]

    def fake_post(payload):
        seen.update(payload)
        return _fake_response(
            mod,
            status_code=200,
            json_body={"geometry": {"type": "Polygon", "coordinates": [open_ring]}, "confidence": 0.91},
        )

    monkeypatch.setattr(mod, "_post_inference", fake_post)
    raw = _png_b64_rgb_square()
    r = client.post(
        "/segment",
        json={"mode": "auto", "image_base64": raw, "preprocessing": "exg"},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metadata"]["preprocessing"] == "exg"
    assert body["metadata"]["vegetation_ratio"] > 0.02
    assert body["metadata"]["candidate_count"] >= 1
    assert seen["preprocessing"] == "exg"
    assert seen["image_base64"] != raw
    assert seen["boxes"]
    assert seen["positive_points"]


def test_auto_exg_without_image_is_explicitly_skipped(monkeypatch):
    mod, client = _configured(monkeypatch, backend="sam2")
    seen: dict = {}
    open_ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: seen.update(payload)
        or _fake_response(
            mod,
            status_code=200,
            json_body={"geometry": {"type": "Polygon", "coordinates": [open_ring]}},
        ),
    )
    r = client.post("/segment", json={"mode": "auto", "preprocessing": "exg"}, headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["preprocessing"] == "exg_skipped_no_image"
    assert seen["preprocessing"] == "exg_skipped_no_image"
