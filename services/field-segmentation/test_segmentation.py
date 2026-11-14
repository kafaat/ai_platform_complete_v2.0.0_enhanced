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
        "/v1/segment",
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
    r = client.post("/v1/segment", json={"mode": "manual", "user_polygon": gj}, headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "manual"


# ── ٢. auto/hybrid بلا نموذج → 503 صادق ──
def test_auto_without_model_returns_503(client):
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "model_not_configured"
    assert "SEGMENTATION_INFERENCE_URL" in detail["note_ar"]


def test_hybrid_without_model_returns_503(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/v1/segment",
        json={"mode": "hybrid", "user_polygon": poly},
        headers=_hdr(),
    )
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "model_not_configured"


# ── ٣. تحقّق المضلّع (مسار حقيقيّ يرفض القمامة) ──
def test_manual_rejects_out_of_range(client):
    poly = [[999.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/v1/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_rejects_too_few_points(client):
    poly = [[46.0, 24.0], [46.1, 24.0]]
    r = client.post("/v1/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert r.status_code == 422, r.text


def test_manual_requires_polygon(client):
    r = client.post("/v1/segment", json={"mode": "manual"}, headers=_hdr())
    assert r.status_code == 422, r.text


# ── ٤. مصادقة توكن الخدمة ──
def test_missing_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post("/v1/segment", json={"mode": "manual", "user_polygon": poly})
    assert r.status_code == 401, r.text


def test_wrong_token_rejected(client):
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1]]
    r = client.post(
        "/v1/segment",
        json={"mode": "manual", "user_polygon": poly},
        headers={"X-Agent-Token": "wrong"},
    )
    assert r.status_code == 401, r.text


# ── ٥. صحّة/جاهزيّة ──
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["service"] == "field-segmentation"


# ── API-VERSIONING-GUARD-IS-A-MIRROR-01: العقد مُصدَّر، لا القديم ──
def test_segment_route_is_versioned_not_legacy(client):
    """يُثبِّت شريحة API-VERSIONING-GUARD-IS-A-MIRROR-01: /segment رُحِّل إلى
    /v1/segment (services/field-segmentation/main.py:390). برهان بالتكذيب: لو
    عاد الديكوريتر إلى @app.post("/segment") يفشل هذا الاختبار بـ404 على
    /v1/segment ويُنجَح المسار القديم — الاختبار يُثبِّت الاتّجاه الصحيح فقط."""
    poly = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    versioned = client.post(
        "/v1/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr()
    )
    assert versioned.status_code == 200, versioned.text

    legacy = client.post("/segment", json={"mode": "manual", "user_polygon": poly}, headers=_hdr())
    assert legacy.status_code == 404, (
        "المسار القديم /segment يجب ألّا يبقى حيّاً — لا alias توافق، تحويل كامل فقط"
    )


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
    import httpx

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        mod.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, json={"status": "degraded"})
            ),
            **kwargs,
        ),
    )
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
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
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
    body = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr()).json()
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
    body = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr()).json()
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
    body = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr()).json()
    assert body["confidence"] is None


def test_manual_confidence_is_none(monkeypatch):
    """المسار اليدويّ (رسم المستخدم) بلا درجة نموذج ⇒ confidence=None."""
    mod, client = _configured(monkeypatch, backend="sam2")
    ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1], [46.0, 24.0]]
    body = client.post(
        "/v1/segment", json={"mode": "manual", "user_polygon": ring}, headers=_hdr()
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
        "/v1/segment",
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
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "inference_unreachable"


def test_inference_timeout_returns_503(monkeypatch):
    mod, client = _configured(monkeypatch)
    import httpx

    def _slow(payload):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(mod, "_post_inference", _slow)
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 503, r.text
    assert r.json()["detail"]["error"] == "inference_unreachable"


def test_inference_non_2xx_returns_502(monkeypatch):
    mod, client = _configured(monkeypatch)
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(mod, status_code=500, json_body={"err": "boom"}),
    )
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
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
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
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
    r = client.post("/v1/segment", json={"mode": "auto"}, headers=_hdr())
    assert r.status_code == 502, r.text
    assert r.json()["detail"]["error"] == "inference_bad_geometry"


# ── ٩. ExG قبل SAM2: صورة محسّنة + prompts لا هندسة مُفبركة ──
def _png_b64_rgb_square() -> str:
    import base64
    import io

    import numpy as np
    from PIL import Image

    img = np.zeros((96, 96, 3), dtype=np.uint8)
    img[:, :] = [135, 112, 80]  # تربة/رمل
    img[24:72, 28:76] = [25, 178, 45]  # غطاء نباتي واضح
    out = io.BytesIO()
    Image.fromarray(img, "RGB").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def test_custom_backend_exg_preprocesses_image(monkeypatch):
    mod, client = _configured(monkeypatch, backend="geosam")
    seen: dict = {}
    open_ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]

    def fake_post(payload):
        seen.update(payload)
        return _fake_response(
            mod,
            status_code=200,
            json_body={
                "geometry": {"type": "Polygon", "coordinates": [open_ring]},
                "confidence": 0.91,
            },
        )

    monkeypatch.setattr(mod, "_post_inference", fake_post)
    raw = _png_b64_rgb_square()
    r = client.post(
        "/v1/segment",
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


def test_custom_backend_exg_without_image_is_explicitly_skipped(monkeypatch):
    mod, client = _configured(monkeypatch, backend="geosam")
    seen: dict = {}
    open_ring = [[46.0, 24.0], [46.1, 24.0], [46.1, 24.1], [46.0, 24.1]]
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: (
            seen.update(payload)
            or _fake_response(
                mod,
                status_code=200,
                json_body={"geometry": {"type": "Polygon", "coordinates": [open_ring]}},
            )
        ),
    )
    r = client.post("/v1/segment", json={"mode": "auto", "preprocessing": "exg"}, headers=_hdr())
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["preprocessing"] == "exg_skipped_no_image"
    assert seen["preprocessing"] == "exg_skipped_no_image"


@pytest.mark.parametrize(
    "ring",
    [
        [[44, 15]] * 4,
        [[44, 15], [45, 15], [46, 15], [44, 15]],
        [[44, 15], [45, 16], [44, 16], [45, 15], [44, 15]],
        [[0, 0], [3, 0], [0, 2], [2, 2], [0, 0]],
    ],
)
@pytest.mark.parametrize("upstream", [False, True])
def test_invalid_topology_is_rejected(monkeypatch, ring, upstream):
    mod, client = _configured(monkeypatch, backend="sam2")
    if upstream:
        monkeypatch.setattr(
            mod,
            "_post_inference",
            lambda payload: _fake_response(
                mod,
                status_code=200,
                json_body={"geometry": {"type": "Polygon", "coordinates": [ring]}},
            ),
        )
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "auto" if upstream else "manual", "user_polygon": ring},
    )
    assert response.status_code == (502 if upstream else 422)


def test_holes_are_not_silently_removed(client):
    outer = [[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]
    inner = [[1, 1], [2, 1], [2, 2], [1, 1]]
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": {"type": "Polygon", "coordinates": [outer, inner]}},
    )
    assert response.status_code == 422


def test_topology_work_is_bounded(client):
    import math

    ring = [
        [44 + math.cos(i * 2 * math.pi / 2049), 15 + math.sin(i * 2 * math.pi / 2049)]
        for i in range(2049)
    ]
    response = client.post(
        "/v1/segment", headers=_hdr(), json={"mode": "manual", "user_polygon": ring}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("reverse", [False, True])
def test_valid_concave_ring_accepts_both_windings(client, reverse):
    ring = [[44, 15], [46, 15], [45, 16], [46, 17], [44, 17]]
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": ring[::-1] if reverse else ring},
    )
    assert response.status_code == 200


_SAM2_OK = {
    "geometry": {"type": "Polygon", "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]]},
    "metadata": {"preprocessing": "exg", "vegetation_ratio": 0.3, "candidate_count": 1},
}


@pytest.mark.parametrize("mode", ["auto", "hybrid"])
@pytest.mark.parametrize("with_image", [True, False])
def test_sam2_accepts_web_ui_payload_and_never_forwards_client_image(monkeypatch, mode, with_image):
    """GEO-01 BLOCKER: the exact AddFieldWithMap payload must not 422 under SAM2.

    Older web clients attach an un-georeferenced viewport screenshot; SAM2 builds its
    own georeferenced ExG image, so the screenshot is dropped, never forwarded, and
    the drop is reported (not silent).
    """
    mod, client = _configured(monkeypatch, backend="sam2")
    seen: list[dict] = []

    def post(payload):
        seen.append(payload)
        return _fake_response(mod, status_code=200, json_body=_SAM2_OK)

    monkeypatch.setattr(mod, "_post_inference", post)
    bbox = [44.1, 15.3, 44.3, 15.4]
    body = {
        "mode": mode,
        "bbox": bbox,
        "preprocessing": "exg",
        "fallback_to_original_on_low_exg": True,
    }
    if with_image:
        body["image_base64"] = _png_b64_rgb_square()
    if mode == "hybrid":
        body["hints"] = [[44.2, 15.35]]
    response = client.post("/v1/segment", headers=_hdr(), json=body)
    assert response.status_code == 200, response.text
    (payload,) = seen
    assert not {"image_base64", "boxes", "positive_points", "multimask_output"} & set(payload)
    assert payload["field_bbox"] == bbox
    assert payload["preprocessing"] == "exg"
    assert payload["user_polygon"] == ([[44.2, 15.35]] if mode == "hybrid" else None)
    metadata = response.json()["metadata"]
    assert metadata["preprocessing"] == "exg"
    if with_image:
        assert metadata["client_image"] == "ignored_not_georeferenced"
    else:
        assert "client_image" not in metadata


def test_sam2_requires_backend_preprocessing_confirmation(monkeypatch):
    mod, client = _configured(monkeypatch, backend="sam2")
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod,
            status_code=200,
            json_body={
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[44, 15], [45, 15], [45, 16], [44, 15]]],
                }
            },
        ),
    )
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "auto", "bbox": [44, 15, 45, 16], "preprocessing": "exg"},
    )
    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "inference_preprocessing_unconfirmed"


def test_inference_keeps_event_loop_available(monkeypatch):
    import asyncio
    import threading

    mod, _ = _configured(monkeypatch, backend="sam2")
    gate = threading.Event()

    def blocked(**kwargs):
        assert gate.wait(1), "event-loop coroutine could not release inference"
        return {"type": "Polygon", "coordinates": []}, None, {}

    monkeypatch.setattr(mod, "run_segmentation_model", blocked)

    async def run():
        async def release():
            await asyncio.sleep(0.01)
            gate.set()

        await asyncio.gather(mod.segment(mod.SegmentRequest(mode="auto"), _TOKEN), release())

    asyncio.run(run())


def test_manual_validation_keeps_event_loop_available(monkeypatch):
    """Manual validation runs off the event loop (deterministic gate, no timing race)."""
    import asyncio
    import threading

    mod = _load_app(monkeypatch)
    gate = threading.Event()
    real = mod.normalize_polygon

    def gated(polygon):
        assert gate.wait(1), "manual topology validation blocked the event loop"
        return real(polygon)

    monkeypatch.setattr(mod, "normalize_polygon", gated)
    ring = [[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.01]]

    async def run():
        async def release():
            await asyncio.sleep(0.01)
            gate.set()

        response, _ = await asyncio.gather(
            mod.segment(mod.SegmentRequest(mode="manual", user_polygon=ring), _TOKEN), release()
        )
        assert response["source"] == "manual"

    asyncio.run(run())


def _scalar_edges_intersect(ring):
    """Reference oracle: the former pure-Python O(n²) predicate, verbatim."""
    vertices = ring[:-1]

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a, b, p):
        return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(
            a[1], b[1]
        )

    for i in range(len(vertices)):
        a, b = ring[i], ring[i + 1]
        for j in range(i + 2, len(vertices)):
            if i == 0 and j == len(vertices) - 1:
                continue
            c, d = ring[j], ring[j + 1]
            ac, ad, ca, cb = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
            if (
                (ac * ad < 0 and ca * cb < 0)
                or (ac == 0 and on_segment(a, b, c))
                or (ad == 0 and on_segment(a, b, d))
                or (ca == 0 and on_segment(c, d, a))
                or (cb == 0 and on_segment(c, d, b))
            ):
                return True
    return False


def test_vectorised_intersection_matches_scalar_oracle(monkeypatch):
    """The fast predicate is bit-equivalent to the O(n²) loop on random grid/float rings."""
    import random

    mod = _load_app(monkeypatch)
    rnd = random.Random(20261111)
    for _ in range(4000):
        n = rnd.randint(3, 12)
        if rnd.random() < 0.7:
            g = rnd.choice([3, 4, 6])
            v = [[float(rnd.randint(0, g)), float(rnd.randint(0, g))] for _ in range(n)]
        else:
            v = [[44 + rnd.uniform(0, 1e-3), 15 + rnd.uniform(0, 1e-3)] for _ in range(n)]
        ring = v + [list(v[0])]
        assert mod._ring_edges_intersect(ring) == _scalar_edges_intersect(ring), ring


def test_maximum_manual_polygon_validation_is_cheap(client):
    """GEO-03 MINOR: 2048-vertex validation held the GIL ~1.25 s; now it is vectorised."""
    import math
    import time

    ring = [
        [44 + math.cos(i * 2 * math.pi / 2048), 15 + math.sin(i * 2 * math.pi / 2048)]
        for i in range(2048)
    ]
    started = time.perf_counter()
    response = client.post(
        "/v1/segment", headers=_hdr(), json={"mode": "manual", "user_polygon": ring}
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    assert len(response.json()["geometry"]["coordinates"][0]) == 2049
    assert elapsed < 0.4, f"2048-vertex validation took {elapsed:.3f}s"


@pytest.mark.parametrize(
    "ring, expected",
    [
        # Double click in the middle and a re-clicked closing vertex: normalised.
        ([[44, 15], [45, 15], [45, 15], [45, 16], [44, 16]], 5),
        ([[44, 15], [45, 15], [45, 16], [44, 15], [44, 15]], 4),
    ],
)
@pytest.mark.parametrize("upstream", [False, True])
def test_consecutive_duplicate_vertices_are_normalised(monkeypatch, ring, expected, upstream):
    mod, client = _configured(monkeypatch, backend="geosam")
    monkeypatch.setattr(
        mod,
        "_post_inference",
        lambda payload: _fake_response(
            mod, status_code=200, json_body={"type": "Polygon", "coordinates": [ring]}
        ),
    )
    body = {"mode": "auto"} if upstream else {"mode": "manual", "user_polygon": ring}
    response = client.post("/v1/segment", headers=_hdr(), json=body)
    assert response.status_code == 200, response.text
    out = response.json()["geometry"]["coordinates"][0]
    assert len(out) == expected and out[0] == out[-1]
    assert all(a != b for a, b in zip(out, out[1:], strict=False))


def test_non_consecutive_repeated_vertex_is_still_rejected(client):
    pinch = [[0, 0], [2, 0], [1, 1], [2, 2], [0, 2], [1, 1]]
    response = client.post(
        "/v1/segment", headers=_hdr(), json={"mode": "manual", "user_polygon": pinch}
    )
    assert response.status_code == 422
    assert "repeated" in response.text


def _square(lon: float, lat: float, side_deg: float) -> list[list[float]]:
    return [
        [lon, lat],
        [lon + side_deg, lat],
        [lon + side_deg, lat + side_deg],
        [lon, lat + side_deg],
    ]


@pytest.mark.parametrize(
    "ring",
    [
        _square(44.0, 15.0, 1e-5),  # ~1.2 m²
        [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3000000000000001]],  # float-noise collinear sliver
    ],
)
def test_sliver_and_sub_minimum_area_rings_are_rejected(client, ring):
    response = client.post(
        "/v1/segment", headers=_hdr(), json={"mode": "manual", "user_polygon": ring}
    )
    assert response.status_code == 422, response.text
    assert "minimum" in response.text


def test_minimum_area_is_measured_in_square_metres_not_degrees(client):
    """Same degree footprint: ~20 m² at the equator passes, ~6.8 m² at 70°N fails."""
    side = (20.0**0.5) / 111_195.0
    ok = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": _square(44.0, 0.0, side)},
    )
    assert ok.status_code == 200, ok.text
    north = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": _square(44.0, 70.0, side)},
    )
    assert north.status_code == 422, north.text


def test_minimum_area_is_configurable_by_env(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SEGMENTATION_MIN_AREA_M2", "100")
    client = TestClient(_load_app(monkeypatch).app)
    side = (25.0**0.5) / 111_195.0  # ~25 m²: above the default 10, below 100
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": _square(44.0, 0.0, side)},
    )
    assert response.status_code == 422
    monkeypatch.setenv("SEGMENTATION_MIN_AREA_M2", "10")
    client = TestClient(_load_app(monkeypatch).app)
    response = client.post(
        "/v1/segment",
        headers=_hdr(),
        json={"mode": "manual", "user_polygon": _square(44.0, 0.0, side)},
    )
    assert response.status_code == 200, response.text
