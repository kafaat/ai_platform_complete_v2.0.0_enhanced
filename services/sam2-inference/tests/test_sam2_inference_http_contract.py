"""عقد HTTP لخدمة sam2-inference — السلوك عبر TestClient، لا نصّ المصدر.

الخدمة تُعلن أربعة مسارات (`POST /v1/predict` · `GET /healthz` · `GET /health` ·
`GET /readyz`) وخطّاف إقلاع يحمّل النموذج. هذه الاختبارات تُثبّت ما يراه المستدعي:

* **المصادقة** على `/v1/predict`: توكن غير مضبوط ⇒ 503 فشلٌ آمن؛ ترويسة غائبة/خاطئة
  ⇒ 401؛ والمصادقة تسبق كشف حالة النموذج **وتسبق التحقّق من الجسم** (المجهول لا يرى
  422 بتفاصيل المخطّط) ولا يبلغ أيّ طلب مرفوض المُتنبِّئ.
* **التحقّق من المدخلات** (`mode` ∈ {auto, hybrid} · `field_bbox` أرقام · `user_polygon`
  قائمة أو GeoJSON) ⇒ 422.
* **المسار السعيد** بمُتنبِّئ وهميّ: أعلى درجة تختار القناع، والثقة والبيانات الوصفيّة
  تُشتقّ منه، والبادرة تصل المُتنبِّئ كما بناها وقت التشغيل.
* **مسارات الخطأ الصادقة**: نموذج غير محمّل 503 · صورة صغيرة 503 · فشل استدلال 500 ·
  لا قناع 500 · لا صورة ولا bbox 422 — ولا مضلّع مُلفَّق في أيٍّ منها.
* **الحياة والجاهزيّة**: `/healthz` و`/health` حيّان مستقلّان عن النموذج؛ `/readyz`
  يعكس حالة الإقلاع الحقيقيّة (503 متدهور بسببٍ مصنَّف، 200 جاهز).

لماذا لا تخطّي: `torch`/`sam2` (CUDA) غائبان عن طبقة الاختبار، فيُستبدَل `torch` بوحدة
وهميّة في `sys.modules` داخل الاختبار نفسه (يستوردها `main.predict` و`_load_model` داخل
الدوالّ)، والمُتنبِّئ بكائن وهميّ. أمّا `fastapi`/`numpy`/`rasterio`/`shapely` فمثبّتة في
`tests_v9/requirements-test.txt` التي تُثبّتها وظيفة *Unit Tests* المُشغِّلة لهذا الملفّ.

التحميل: كلّ اختبار يُحمِّل `sam2_runtime.py` و`main.py` **طازجين** بالمسار تحت
`monkeypatch.setitem(sys.modules, …)` — فالإعداد المقروء عند الاستيراد (`SAHOOL_AGENT_TOKEN`
· `SAM2_CHECKPOINT` · `SAM2_CHECKPOINT_SHA256`) يُضبط لكلّ اختبار، والحالة العالميّة
(`_PREDICTOR` …) لا تتسرّب بين الاختبارات، واسم `main` لا يصطدم بخدمة أخرى.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

SVC_DIR = Path(__file__).resolve().parents[1]


def test_exg_thin_vegetation_uses_point_without_degenerate_box(svc):
    rgb = np.full((24, 32, 3), [135, 112, 80], dtype=np.uint8)
    rgb[:, 3] = [25, 178, 45]
    image, prompt, meta = svc.rt._preprocess_georeferenced_rgb(rgb, "exg", True)
    assert image.shape == rgb.shape and not np.array_equal(image, rgb)
    assert prompt[2] is None
    assert prompt[0][0][0] == 3
    assert meta["candidate_count"] == 1


@pytest.mark.parametrize("preprocessing", ["none", "exg", "auto_exg"])
def test_adapter_to_sam2_applies_exg_on_georeferenced_image(
    svc, client, monkeypatch, preprocessing
):
    """Both real ASGI boundaries; only imagery fetch and CUDA model are stand-ins."""
    rgb = np.full((24, 32, 3), [135, 112, 80], dtype=np.uint8)
    rgb[2:10, 3:12] = [25, 178, 45]
    calls = _arm(svc, monkeypatch, rgb=rgb)
    directory = SVC_DIR.parent / "field-segmentation"
    monkeypatch.syspath_prepend(str(directory))
    adapter = _load("_segmentation_contract_adapter", directory / "main.py", monkeypatch)
    monkeypatch.setattr(adapter, "AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(adapter, "SEGMENTATION_BACKEND", "sam2")
    monkeypatch.setattr(adapter, "SEGMENTATION_INFERENCE_URL", "http://offline/v1/predict")
    monkeypatch.setattr(
        adapter,
        "_post_inference",
        lambda payload: client.post("/v1/predict", headers={"X-Agent-Token": TOKEN}, json=payload),
    )
    response = TestClient(adapter.app).post(
        "/v1/segment",
        headers={"X-Agent-Token": TOKEN},
        json={
            "mode": "auto",
            "field_bbox": BBOX,
            "image_ref": IMAGE_REF,
            "preprocessing": preprocessing,
        },
    )
    assert response.status_code == 200, response.text
    actual = calls.predictor.images[0]
    assert actual.shape == rgb.shape
    _, transform, crs = calls.polygon[0]
    assert transform is calls.transform and crs is calls.crs
    prompt = calls.predictor.prompts[0]["point_coords"][0]
    if preprocessing == "none":
        assert np.array_equal(actual, rgb)
        assert list(prompt) == [16, 12]
        assert response.json()["metadata"]["preprocessing"] == "none"
    else:
        assert not np.array_equal(actual, rgb)
        assert 3 <= prompt[0] < 12 and 2 <= prompt[1] < 10
        assert list(calls.predictor.prompts[0]["box"]) == [3, 2, 11, 9]
        assert response.json()["metadata"]["preprocessing"] == "exg"
        assert response.json()["metadata"]["candidate_count"] == 1


@pytest.mark.parametrize("fallback", [True, False])
def test_exg_low_confidence_policy_is_explicit(svc, client, monkeypatch, fallback):
    rgb = np.full((6, 8, 3), [135, 112, 80], dtype=np.uint8)
    calls = _arm(svc, monkeypatch, rgb=rgb)
    response = _predict(
        client,
        {
            "mode": "auto",
            "image_ref": IMAGE_REF,
            "preprocessing": "exg",
            "fallback_to_original_on_low_exg": fallback,
        },
    )
    assert response.status_code == 200
    meta = response.json()["metadata"]
    assert meta["preprocessing"] == ("exg_low_confidence_fallback_original" if fallback else "exg")
    assert meta["low_confidence"] is True and meta["candidate_count"] == 0
    assert np.array_equal(calls.predictor.images[0], rgb) == fallback


def test_exg_preserves_hybrid_user_prompt(svc, client, monkeypatch):
    rgb = np.full((24, 32, 3), [135, 112, 80], dtype=np.uint8)
    rgb[2:10, 3:12] = [25, 178, 45]
    calls = _arm(svc, monkeypatch, rgb=rgb)
    point = np.array([[25, 20]], dtype=np.float32)
    monkeypatch.setattr(svc.rt, "_build_prompt", lambda *args: (point, np.array([1]), None))
    response = _predict(client, {"mode": "hybrid", "image_ref": IMAGE_REF, "preprocessing": "exg"})
    assert response.status_code == 200
    assert calls.predictor.prompts[0]["point_coords"] is point
    assert not np.array_equal(calls.predictor.images[0], rgb)


@pytest.mark.parametrize(
    "extra",
    [
        {"preprocessing": "unknown"},
        {"preprocessing": "exg", "image_url_override": "file:///etc/passwd"},
        {"prompt_boxes": [[0, 0, 1, 1]]},
    ],
)
def test_sam2_does_not_silently_ignore_unsupported_imagery(svc, client, monkeypatch, extra):
    calls = _arm(svc, monkeypatch)
    response = _predict(client, {"mode": "auto", **extra})
    assert response.status_code == 422
    assert not calls.predictor.images


def _two_fields_with_strays() -> np.ndarray:
    """100×100 bare soil, a large field top-left, a small one bottom-right, 2 stray trees."""
    rgb = np.full((100, 100, 3), [135, 112, 80], dtype=np.uint8)
    rgb[5:35, 5:40] = [25, 178, 45]  # field A: 30×35 = 1050 px
    rgb[70:90, 75:95] = [25, 178, 45]  # field B: 20×20 = 400 px
    rgb[0, 99] = rgb[99, 0] = [25, 178, 45]  # isolated vegetation pixels
    return rgb


def test_exg_prompt_box_covers_one_component_not_every_green_pixel(svc):
    """GEO-01 MAJOR: two fields + strays used to give box [0,0,99,99] (the whole window)."""
    image, prompt, meta = svc.rt._preprocess_georeferenced_rgb(
        _two_fields_with_strays(), "exg", True
    )
    points, labels, box = prompt
    assert list(box) == [5, 5, 39, 34], "box must bound field A only"
    col, row = points[0]
    assert 5 <= col <= 39 and 5 <= row <= 34, "the positive point lies inside field A"
    assert labels.tolist() == [1]
    assert meta["candidate_count"] == 2, "stray pixels are not prompt candidates"
    assert meta["preprocessing"] == "exg"


def test_exg_hybrid_click_selects_the_component_under_the_click(svc):
    rgb = _two_fields_with_strays()
    _, prompt, _ = svc.rt._preprocess_georeferenced_rgb(rgb, "exg", True, (80, 75))
    points, _, box = prompt
    assert points.tolist() == [[80.0, 75.0]], "the user's click stays the positive point"
    assert list(box) == [75, 70, 94, 89], "box bounds field B, the one under the click"
    _, miss, _ = svc.rt._preprocess_georeferenced_rgb(rgb, "exg", True, (60, 50))
    assert miss is None, "a click on bare soil keeps the plain user prompt"


def test_exg_components_below_threshold_give_no_prompt(svc, monkeypatch):
    rgb = np.full((40, 40, 3), [135, 112, 80], dtype=np.uint8)
    rgb[::4, ::4] = [25, 178, 45]  # 100 isolated pixels: 6 % vegetation, no field
    _, prompt, meta = svc.rt._preprocess_georeferenced_rgb(rgb, "exg", True)
    assert prompt is None and meta["candidate_count"] == 0
    monkeypatch.setattr(svc.rt, "EXG_MIN_COMPONENT_PX", 1)
    _, prompt, meta = svc.rt._preprocess_georeferenced_rgb(rgb, "exg", True)
    assert prompt is not None and meta["candidate_count"] == 100


def test_hybrid_single_point_hint_is_used_not_discarded(svc, client, monkeypatch):
    """The web UI sends hints=[[lon, lat]]; it used to fall back to the image centre."""
    calls = _arm(svc, monkeypatch, rgb=_two_fields_with_strays())
    monkeypatch.setattr(svc.rt, "_lonlat_to_pixel", lambda lon, lat, t, c: (int(lon), int(lat)))
    response = _predict(
        client, {"mode": "hybrid", "image_ref": IMAGE_REF, "user_polygon": [[80.0, 75.0]]}
    )
    assert response.status_code == 200, response.text
    (prompt,) = calls.predictor.prompts
    assert prompt["point_coords"].tolist() == [[80.0, 75.0]]
    assert prompt["box"] is None, "no preprocessing: a plain point prompt"

    calls = _arm(svc, monkeypatch, rgb=_two_fields_with_strays())
    response = _predict(
        client,
        {
            "mode": "hybrid",
            "image_ref": IMAGE_REF,
            "user_polygon": [[80.0, 75.0]],
            "preprocessing": "exg",
        },
    )
    assert response.status_code == 200, response.text
    (prompt,) = calls.predictor.prompts
    assert prompt["point_coords"].tolist() == [[80.0, 75.0]]
    assert list(prompt["box"]) == [75, 70, 94, 89]


def test_previous_client_shape_is_tolerated_but_never_reaches_the_predictor(
    svc, client, monkeypatch
):
    """Rolling deploy: the old field-segmentation payload must not 422 auto segmentation."""
    rgb = np.full((24, 32, 3), [135, 112, 80], dtype=np.uint8)
    rgb[2:10, 3:12] = [25, 178, 45]
    calls = _arm(svc, monkeypatch, rgb=rgb)
    response = _predict(
        client,
        {
            "mode": "auto",
            "image_ref": IMAGE_REF,
            "image_base64": "c2NyZWVuc2hvdA==",
            "boxes": [[20, 20, 31, 23]],
            "positive_points": [[30, 22]],
            "multimask_output": True,
            "preprocessing": "exg",
            "request_hash": "0123456789abcdef",
        },
    )
    assert response.status_code == 200, response.text
    assert np.array_equal(calls.predictor.images[0].shape, rgb.shape)
    prompt = calls.predictor.prompts[0]
    assert list(prompt["box"]) == [3, 2, 11, 9], "server ExG box, not the client's pixel box"
    meta = response.json()["metadata"]
    assert meta["ignored_client_fields"] == [
        "boxes",
        "image_base64",
        "multimask_output",
        "positive_points",
    ]
    assert meta["preprocessing"] == "exg"


@pytest.mark.parametrize("label", ["exg_skipped_no_image", "exg_low_confidence_fallback_original"])
def test_previous_client_preprocessing_labels_map_to_none(svc, client, monkeypatch, label):
    calls = _arm(svc, monkeypatch)
    response = _predict(client, {"mode": "auto", "image_ref": IMAGE_REF, "preprocessing": label})
    assert response.status_code == 200, response.text
    assert response.json()["metadata"]["preprocessing"] == "none"
    assert response.json()["metadata"]["ignored_client_fields"] == []
    assert calls.predictor.prompts[0]["point_coords"].tolist() == [[4.0, 3.0]]


@pytest.mark.parametrize("with_image", [True, False])
@pytest.mark.parametrize("mode", ["auto", "hybrid"])
def test_web_ui_payload_through_adapter_and_sam2_is_200(svc, client, monkeypatch, mode, with_image):
    """GEO-01 BLOCKER: exactly what AddFieldWithMap posts, through both real ASGI apps."""
    calls = _arm(svc, monkeypatch, rgb=_two_fields_with_strays())
    monkeypatch.setattr(svc.rt, "_lonlat_to_pixel", lambda lon, lat, t, c: (80, 75))
    directory = SVC_DIR.parent / "field-segmentation"
    monkeypatch.syspath_prepend(str(directory))
    adapter = _load("_segmentation_contract_adapter", directory / "main.py", monkeypatch)
    monkeypatch.setattr(adapter, "AGENT_TOKEN", TOKEN)
    monkeypatch.setattr(adapter, "SEGMENTATION_BACKEND", "sam2")
    monkeypatch.setattr(adapter, "SEGMENTATION_INFERENCE_URL", "http://offline/v1/predict")
    monkeypatch.setattr(
        adapter,
        "_post_inference",
        lambda payload: client.post("/v1/predict", headers={"X-Agent-Token": TOKEN}, json=payload),
    )
    body = {
        "mode": mode,
        "bbox": [44.1, 15.3, 44.3, 15.4],
        "preprocessing": "exg",
        "fallback_to_original_on_low_exg": True,
    }
    if with_image:
        body["image_base64"] = "iVBORw0KGgo="
    if mode == "hybrid":
        body["hints"] = [[44.2, 15.35]]
    response = TestClient(adapter.app).post(
        "/v1/segment", headers={"X-Agent-Token": TOKEN}, json=body
    )
    assert response.status_code == 200, response.text
    meta = response.json()["metadata"]
    assert meta["preprocessing"] == "exg"
    assert ("client_image" in meta) is with_image
    prompt = calls.predictor.prompts[0]
    expected_box = [5, 5, 39, 34] if mode == "auto" else [75, 70, 94, 89]
    assert list(prompt["box"]) == expected_box


TOKEN = "sam2-contract-test-token"
DIGEST = "ab" * 32
IMAGE_REF = "https://example.invalid/scene/visual.tif"
BBOX = [44.0, 15.0, 44.01, 15.01]


# ─── التحميل الطازج ───────────────────────────────────────────────────────
def _load(name: str, path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def make_svc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """يُحمّل الخدمة بإعداد بيئة صريح؛ `main` يستورد `sam2_runtime` من `sys.modules`."""

    def _make(*, token: str = TOKEN, digest: str | None = None) -> SimpleNamespace:
        checkpoint = tmp_path / "sam2_hiera_large.pt"
        monkeypatch.setenv("SAHOOL_AGENT_TOKEN", token)
        monkeypatch.setenv("SAM2_CHECKPOINT", str(checkpoint))
        monkeypatch.delenv("SAM2_MODEL_CFG", raising=False)
        if digest is None:
            monkeypatch.delenv("SAM2_CHECKPOINT_SHA256", raising=False)
        else:
            monkeypatch.setenv("SAM2_CHECKPOINT_SHA256", digest)
        rt = _load("sam2_runtime", SVC_DIR / "sam2_runtime.py", monkeypatch)
        main = _load("_sam2_inference_main_under_test", SVC_DIR / "main.py", monkeypatch)
        assert main.rt is rt, "main يجب أن يربط وقت التشغيل المُحمَّل لهذا الاختبار"
        return SimpleNamespace(main=main, rt=rt, checkpoint=checkpoint)

    return _make


@pytest.fixture
def svc(make_svc) -> SimpleNamespace:
    return make_svc()


@pytest.fixture
def client(svc):
    # `with` يُشغّل خطّاف الإقلاع الحقيقيّ (rt._load_model): بلا بصمة ⇒ يرفض قبل torch.
    with TestClient(svc.main.app) as c:
        yield c


# ─── بدائل torch والمُتنبِّئ ────────────────────────────────────────────────
class _TorchState:
    def __init__(self) -> None:
        self.active: list[str] = []
        self.autocast_args: list[tuple] = []


def _fake_torch(monkeypatch: pytest.MonkeyPatch, *, cuda_available: bool = True) -> _TorchState:
    state = _TorchState()

    @contextlib.contextmanager
    def _ctx(label: str):
        state.active.append(label)
        try:
            yield
        finally:
            state.active.remove(label)

    def inference_mode():
        return _ctx("inference_mode")

    def autocast(device_type, dtype=None):
        state.autocast_args.append((device_type, dtype))
        return _ctx("autocast")

    torch = types.ModuleType("torch")
    torch.bfloat16 = "bfloat16"
    torch.inference_mode = inference_mode
    torch.autocast = autocast
    torch.cuda = SimpleNamespace(is_available=lambda: cuda_available)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return state


class FakePredictor:
    def __init__(self, masks, scores, *, exc: Exception | None = None, torch_state=None):
        self.masks = masks
        self.scores = scores
        self.exc = exc
        self.torch_state = torch_state
        self.images: list = []
        self.prompts: list[dict] = []
        self.contexts_at_predict: list[list[str]] = []

    def set_image(self, image) -> None:
        self.images.append(image)

    def predict(self, **kwargs):
        self.prompts.append(kwargs)
        if self.torch_state is not None:
            self.contexts_at_predict.append(list(self.torch_state.active))
        if self.exc is not None:
            raise self.exc
        return self.masks, self.scores, None


def _rect_mask(h: int, w: int, rows: slice, cols: slice) -> np.ndarray:
    m = np.zeros((h, w), dtype=bool)
    m[rows, cols] = True
    return m


_DEFAULT = object()
RING = [[44.0, 15.0], [44.001, 15.0], [44.001, 15.001], [44.0, 15.001], [44.0, 15.0]]


def _arm(
    svc,
    monkeypatch: pytest.MonkeyPatch,
    *,
    masks=_DEFAULT,
    scores=None,
    exc: Exception | None = None,
    rgb: np.ndarray | None = None,
    stub_polygon: bool = True,
) -> SimpleNamespace:
    """نموذج «محمّل» بمُتنبِّئ وهميّ + جلب صورة مُستبدَل (لا شبكة ولا COG)."""
    rt = svc.rt
    torch_state = _fake_torch(monkeypatch)
    rgb = np.zeros((6, 8, 3), dtype=np.uint8) if rgb is None else rgb
    if masks is _DEFAULT:
        masks = np.stack([_rect_mask(6, 8, slice(0, 1), slice(0, 1))])
        scores = np.array([0.5], dtype=np.float32)
    predictor = FakePredictor(masks, scores, exc=exc, torch_state=torch_state)
    calls = SimpleNamespace(resolve=[], read=[], polygon=[], predictor=predictor, torch=torch_state)
    transform, crs = object(), object()

    def resolve(image_ref, field_bbox):
        calls.resolve.append((image_ref, field_bbox))
        return "resolved://" + str(image_ref)

    def read_rgb(image_url, bbox):
        calls.read.append((image_url, bbox))
        return rgb, transform, crs

    def mask_to_polygon(mask, tr, cr):
        calls.polygon.append((np.array(mask), tr, cr))
        return {"type": "Polygon", "coordinates": [RING]}

    monkeypatch.setattr(rt, "_PREDICTOR", predictor)
    monkeypatch.setattr(rt, "_MODEL_LOAD_ERROR", None)
    monkeypatch.setattr(rt, "_MODEL_LOAD_REASON_CODE", None)
    monkeypatch.setattr(rt, "_MODEL_ARTIFACT_DIGEST", DIGEST)
    monkeypatch.setattr(rt, "_resolve_image_url", resolve)
    monkeypatch.setattr(rt, "_read_rgb", read_rgb)
    if stub_polygon:
        monkeypatch.setattr(rt, "_mask_to_polygon", mask_to_polygon)
    calls.transform, calls.crs = transform, crs
    return calls


def _predict(client, body: dict | None = None, *, token: str | None = TOKEN):
    headers = {} if token is None else {"X-Agent-Token": token}
    payload = {"mode": "auto", "image_ref": IMAGE_REF, "field_bbox": BBOX}
    if body is not None:
        payload = body
    return client.post("/v1/predict", json=payload, headers=headers)


# ═══ المصادقة ═══════════════════════════════════════════════════════════════
@pytest.mark.parametrize("token", [None, "", "wrong-token", TOKEN + "x"])
def test_predict_rejects_missing_or_wrong_agent_token_with_401(svc, client, monkeypatch, token):
    calls = _arm(svc, monkeypatch)

    r = _predict(client, token=token)

    assert r.status_code == 401
    assert calls.predictor.images == [] and calls.predictor.prompts == []
    assert calls.resolve == [], "طلبٌ مرفوض لا يجلب صورة"


def test_predict_authenticates_before_revealing_model_state(client):
    # النموذج غير محمّل بعد الإقلاع الحقيقيّ: المجهول يرى 401 لا «model_not_loaded».
    r = _predict(client, token=None)

    assert r.status_code == 401


@pytest.mark.parametrize("header", [None, "", "anything"])
def test_predict_fails_closed_with_503_when_service_token_is_unset(make_svc, monkeypatch, header):
    svc = make_svc(token="")
    calls = _arm(svc, monkeypatch)
    with TestClient(svc.main.app) as c:
        r = _predict(c, token=header)

    assert r.status_code == 503
    assert "SAHOOL_AGENT_TOKEN" in r.json()["detail"]
    assert calls.predictor.prompts == [], "خدمةٌ بلا توكن لا تقبل مجهولاً ولا تستدلّ"


# ═══ ترتيب المصادقة والتحقّق ═══════════════════════════════════════════════════
# المصادقة تبعيّة FastAPI تُحَلّ قبل التحقّق من الجسم: المجهول لا يرى 422 بتفاصيل
# المخطّط (نمط `mode` ونوع الحقول)؛ يرى 401 (أو 503 إن لم يُضبط التوكن) أيّاً كان جسمه.
_INVALID_BODIES = [
    {"mode": "manual"},  # خارج ^(auto|hybrid)$
    {},  # mode مطلوب
    {"mode": "auto", "field_bbox": ["west", 15.0, 44.01, 15.01]},
    {"mode": "hybrid", "user_polygon": "not-a-polygon"},
]


@pytest.mark.parametrize("token", [None, "wrong-token"])
@pytest.mark.parametrize("body", _INVALID_BODIES)
def test_unauthenticated_invalid_body_gets_401_not_422(svc, client, monkeypatch, token, body):
    calls = _arm(svc, monkeypatch)

    r = _predict(client, body, token=token)

    assert r.status_code == 401, r.text
    assert r.json() == {"detail": "توكن خدمة غير صالح"}
    assert "auto|hybrid" not in r.text, "المجهول لا يرى نمط mode"
    assert calls.resolve == [] and calls.predictor.prompts == []


def test_unset_service_token_with_invalid_body_fails_closed_503_not_422(make_svc, monkeypatch):
    svc = make_svc(token="")
    with TestClient(svc.main.app) as c:
        r = _predict(c, {"mode": "manual"}, token=None)

    assert r.status_code == 503, r.text
    assert "SAHOOL_AGENT_TOKEN" in r.json()["detail"]


def test_authenticated_invalid_body_still_gets_422_with_schema_detail(svc, client, monkeypatch):
    calls = _arm(svc, monkeypatch)

    r = _predict(client, {"mode": "manual"})

    assert r.status_code == 422, r.text
    (err,) = r.json()["detail"]
    assert err["loc"] == ["body", "mode"]
    assert err["ctx"]["pattern"] == "^(auto|hybrid)$"
    assert calls.predictor.prompts == []


def test_predict_still_documents_the_agent_token_header_in_openapi(client):
    params = client.app.openapi()["paths"]["/v1/predict"]["post"]["parameters"]

    assert [(p["name"], p["in"]) for p in params] == [("x-agent-token", "header")]


# ═══ التحقّق من المدخلات ═══════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "body",
    [
        {"image_ref": IMAGE_REF},  # mode مطلوب
        {"mode": "manual", "image_ref": IMAGE_REF},  # خارج auto|hybrid
        {"mode": "AUTO", "image_ref": IMAGE_REF},  # النمط حسّاس لحالة الأحرف
        {"mode": "auto", "field_bbox": ["west", 15.0, 44.01, 15.01]},
        {"mode": "hybrid", "user_polygon": "not-a-polygon"},
    ],
)
def test_predict_rejects_malformed_request_with_422(svc, client, monkeypatch, body):
    calls = _arm(svc, monkeypatch)

    r = _predict(client, body)

    assert r.status_code == 422
    assert calls.predictor.prompts == []


# ═══ المسار السعيد ═══════════════════════════════════════════════════════════
def test_predict_happy_path_selects_highest_scoring_mask_and_reports_metadata(
    svc, client, monkeypatch
):
    low = _rect_mask(6, 8, slice(0, 1), slice(0, 1))  # 1 بكسل
    best = _rect_mask(6, 8, slice(1, 3), slice(2, 5))  # 6 بكسلات
    other = _rect_mask(6, 8, slice(0, 6), slice(0, 8))  # 48 بكسلاً
    calls = _arm(
        svc,
        monkeypatch,
        masks=np.stack([low, best, other]),
        scores=np.array([0.2, 0.85, 0.4], dtype=np.float32),
    )

    r = _predict(client)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"geometry", "confidence", "metadata"}
    assert body["geometry"] == {"type": "Polygon", "coordinates": [RING]}
    assert body["confidence"] == pytest.approx(0.85, abs=1e-6)

    # القناع المُمرَّر للتحويل هو صاحب أعلى درجة، بإطار الصورة نفسه.
    (mask, tr, cr) = calls.polygon[0]
    assert np.array_equal(mask, best.astype(np.uint8))
    assert tr is calls.transform and cr is calls.crs

    meta = body["metadata"]
    assert meta["source"] == "sam2" and meta["model"] == "sam2"
    assert meta["mode"] == "auto"
    assert meta["model_version"] == svc.rt.VERSION == "1.0.0"
    assert meta["checkpoint"] == "sam2_hiera_large.pt"
    assert meta["model_cfg"] == "sam2_hiera_l.yaml"
    assert meta["artifact_digest"] == DIGEST
    assert meta["post_processing"] == {
        "simplify_tolerance_m": 3.0,
        "dedup_tolerance_m": 0.5,
        "preserve_topology": True,
    }
    assert meta["vertices_after"] == len(RING)
    assert meta["mask_area_px"] == 6
    assert isinstance(meta["inference_ms"], float) and meta["inference_ms"] >= 0.0

    # الصورة تُجلَب من الطلب نفسه، والمُتنبِّئ يرى ما قُرِئ.
    assert calls.resolve == [(IMAGE_REF, BBOX)]
    assert calls.read == [("resolved://" + IMAGE_REF, BBOX)]
    assert len(calls.predictor.images) == 1
    assert calls.predictor.images[0].shape == (6, 8, 3)


def test_predict_auto_mode_prompts_image_centre_under_inference_autocast(svc, client, monkeypatch):
    calls = _arm(svc, monkeypatch)

    r = _predict(client)

    assert r.status_code == 200, r.text
    (prompt,) = calls.predictor.prompts
    # الصورة 6×8 ⇒ نقطة موجبة واحدة عند (col=4, row=3)، بلا مربّع، وأقنعة متعدّدة.
    assert prompt["point_coords"].tolist() == [[4.0, 3.0]]
    assert prompt["point_labels"].tolist() == [1]
    assert prompt["box"] is None
    assert prompt["multimask_output"] is True
    # الاستدلال بلا تدرّج وتحت autocast على CUDA بدقّة bfloat16.
    assert calls.predictor.contexts_at_predict == [["inference_mode", "autocast"]]
    assert calls.torch.autocast_args == [("cuda", "bfloat16")]


def test_predict_hybrid_forwards_request_polygon_and_built_prompt(svc, client, monkeypatch):
    calls = _arm(svc, monkeypatch)
    built = []
    point = np.array([[2.0, 1.0]], dtype=np.float32)
    label = np.array([1], dtype=np.int32)
    box = np.array([1.0, 0.0, 6.0, 5.0], dtype=np.float32)

    def build_prompt(mode, user_polygon, transform, crs, img_h, img_w):
        built.append((mode, user_polygon, transform, crs, img_h, img_w))
        return point, label, box

    monkeypatch.setattr(svc.rt, "_build_prompt", build_prompt)
    polygon = {"type": "Polygon", "coordinates": [RING]}

    r = _predict(client, {"mode": "hybrid", "image_ref": IMAGE_REF, "user_polygon": polygon})

    assert r.status_code == 200, r.text
    assert built == [("hybrid", polygon, calls.transform, calls.crs, 6, 8)]
    (prompt,) = calls.predictor.prompts
    assert prompt["point_coords"] is point
    assert prompt["point_labels"] is label
    assert prompt["box"] is box
    assert r.json()["metadata"]["mode"] == "hybrid"


def test_predict_without_scores_uses_first_mask_and_reports_no_confidence(svc, client, monkeypatch):
    first = _rect_mask(6, 8, slice(0, 2), slice(0, 2))  # 4 بكسلات
    second = _rect_mask(6, 8, slice(0, 6), slice(0, 8))
    calls = _arm(svc, monkeypatch, masks=[first, second], scores=None)

    r = _predict(client)

    assert r.status_code == 200, r.text
    assert r.json()["confidence"] is None
    assert r.json()["metadata"]["mask_area_px"] == 4
    assert np.array_equal(calls.polygon[0][0], first.astype(np.uint8))


def test_predict_returns_a_closed_wgs84_ring_through_the_real_post_processing(
    svc, client, monkeypatch
):
    """القناع ⇒ مضلّع عبر `_mask_to_polygon` الحقيقيّ: الحلقة التي يتحقّق منها
    field-segmentation (`normalize_polygon`): مغلقة، ≥٤ رؤوس، داخل نطاق الصورة."""
    from rasterio.crs import CRS
    from rasterio.transform import Affine

    h, w = 40, 40
    mask = _rect_mask(h, w, slice(10, 30), slice(5, 25))
    calls = _arm(
        svc,
        monkeypatch,
        masks=np.stack([mask]),
        scores=np.array([0.9], dtype=np.float32),
        rgb=np.zeros((h, w, 3), dtype=np.uint8),
        stub_polygon=False,
    )
    transform = Affine(0.0001, 0.0, 44.0, 0.0, -0.0001, 15.004)
    crs = CRS.from_epsg(4326)
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    monkeypatch.setattr(svc.rt, "_read_rgb", lambda url, bbox: (rgb, transform, crs))

    r = _predict(client)

    assert r.status_code == 200, r.text
    geom = r.json()["geometry"]
    assert geom["type"] == "Polygon"
    ring = geom["coordinates"][0]
    assert len(ring) >= 4 and ring[0] == ring[-1]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    assert min(lons) == pytest.approx(44.0005) and max(lons) == pytest.approx(44.0025)
    assert min(lats) == pytest.approx(15.001) and max(lats) == pytest.approx(15.003)
    assert r.json()["metadata"]["vertices_after"] == len(ring)
    assert r.json()["metadata"]["mask_area_px"] == 400
    assert calls.predictor.prompts[0]["point_coords"].tolist() == [[20.0, 20.0]]


# ═══ مسارات الخطأ الصادقة ═══════════════════════════════════════════════════
def test_predict_returns_503_model_not_loaded_after_failed_startup(svc, client):
    r = _predict(client)

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "model_not_loaded"
    assert detail["load_error_present"] is True


def test_predict_returns_503_when_image_window_is_too_small(svc, client, monkeypatch):
    calls = _arm(svc, monkeypatch, rgb=np.zeros((1, 8, 3), dtype=np.uint8))

    r = _predict(client)

    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "image_too_small"
    assert calls.predictor.images == [], "لا استدلال على نافذة أصغر من 2×2"


def test_predict_maps_inference_exception_to_500_with_its_type(svc, client, monkeypatch):
    _arm(svc, monkeypatch, exc=RuntimeError("CUDA out of memory"))

    r = _predict(client)

    assert r.status_code == 500
    assert r.json()["detail"] == {
        "error": "inference_error",
        "detail": "RuntimeError: CUDA out of memory",
    }


@pytest.mark.parametrize("masks", [None, [], np.zeros((0, 6, 8), dtype=bool)])
def test_predict_returns_500_no_mask_instead_of_inventing_geometry(svc, client, monkeypatch, masks):
    calls = _arm(svc, monkeypatch, masks=masks, scores=np.array([], dtype=np.float32))

    r = _predict(client)

    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "no_mask"
    assert calls.polygon == []


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "auto"},  # لا image_ref ولا bbox
        {"mode": "auto", "image_ref": "S2A_MSIL2A_20260101"},  # مرجع مشهد بلا bbox للبحث
        {"mode": "auto", "field_bbox": [44.0, 15.0, 44.01]},  # bbox ناقص
    ],
)
def test_predict_returns_422_when_there_is_no_image_and_no_bbox(svc, client, monkeypatch, body):
    real_resolve = svc.rt._resolve_image_url
    calls = _arm(svc, monkeypatch)
    # `_resolve_image_url` الحقيقيّ هنا (هذه المسارات ترفض قبل أيّ شبكة/STAC).
    monkeypatch.setattr(svc.rt, "_resolve_image_url", real_resolve)

    r = _predict(client, body)

    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "no_image_and_no_bbox"
    assert calls.read == [] and calls.predictor.prompts == []


# ═══ image_ref: لا يبلغ GDAL إلّا https إلى مضيف COG مسموح ═══════════════════
ALLOWED_COG = (
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/38/P/LB/2026/9/"
    "S2B_38PLB_20260901_0_L2A/TCI.tif"
)
HOSTILE_REFS = [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://127.0.0.1:8080/internal",
    "http://sentinel-cogs.s3.us-west-2.amazonaws.com/x/TCI.tif",  # http لا https
    "https://169.254.169.254/latest/meta-data/",
    "https://attacker.example.com/TCI.tif",
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com.attacker.example/TCI.tif",
    "https://user@sentinel-cogs.s3.us-west-2.amazonaws.com/TCI.tif",
    "https://sentinel-cogs.s3.us-west-2.amazonaws.com:8443/TCI.tif",
    "/etc/passwd",
    "/vsizip//tmp/x.zip/a.tif",
    "/vsicurl/http://127.0.0.1:8080/x",
    "/vsis3/bucket/key.tif",
    "s3://bucket/key.tif",
    "file:///etc/passwd",
    "ftp://example.com/a.tif",
]


@pytest.mark.parametrize("ref", HOSTILE_REFS)
def test_resolve_image_url_rejects_local_vsi_and_non_allowlisted_refs_with_422(svc, ref):
    # field_bbox=None: الرفض يجب أن يأتي من الحارس، لا من غياب bbox ولا من STAC.
    with pytest.raises(svc.rt.HTTPException) as exc:
        svc.rt._resolve_image_url(ref, None)
    assert exc.value.status_code == 422
    assert exc.value.detail["error"] == "image_ref_not_allowed"


@pytest.mark.parametrize("ref", HOSTILE_REFS)
def test_read_rgb_never_hands_a_disallowed_ref_to_gdal(svc, monkeypatch, ref):
    import rasterio

    opened: list[str] = []
    monkeypatch.setattr(rasterio, "open", lambda path, *a, **k: opened.append(path))
    with pytest.raises(svc.rt.HTTPException) as exc:
        svc.rt._read_rgb(ref, BBOX)
    assert exc.value.status_code == 422
    assert opened == []


def test_stac_href_outside_the_allowlist_is_refused_before_gdal(svc, client, monkeypatch):
    """مرجع مشهد يسقط إلى STAC؛ href غير مسموح منه لا يُفتح أيضاً."""
    import rasterio

    opened: list[str] = []
    monkeypatch.setattr(rasterio, "open", lambda path, *a, **k: opened.append(path))
    real_resolve, real_read = svc.rt._resolve_image_url, svc.rt._read_rgb
    calls = _arm(svc, monkeypatch)
    monkeypatch.setattr(svc.rt, "_resolve_image_url", real_resolve)
    monkeypatch.setattr(svc.rt, "_read_rgb", real_read)
    monkeypatch.setattr(
        svc.rt, "_stac_latest_visual", lambda bbox: "http://169.254.169.254/latest/meta-data/"
    )

    r = _predict(client, {"mode": "auto", "image_ref": "S2B_38PLB_20260901", "field_bbox": BBOX})

    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "image_ref_not_allowed"
    assert opened == [] and calls.predictor.prompts == []


def test_allowlisted_https_cog_is_read_through_vsicurl(svc, monkeypatch):
    import rasterio

    opened: list[str] = []

    def _open(path, *a, **k):
        opened.append(path)
        raise rasterio.errors.RasterioIOError("no network in tests")

    monkeypatch.setattr(rasterio, "open", _open)
    assert svc.rt._resolve_image_url(ALLOWED_COG, None) == ALLOWED_COG
    with pytest.raises(svc.rt.HTTPException):
        svc.rt._read_rgb(ALLOWED_COG, BBOX)
    assert opened == [f"/vsicurl/{ALLOWED_COG}"]


def test_image_host_allowlist_is_env_overridable(make_svc, monkeypatch):
    monkeypatch.setenv("SAM2_IMAGE_HOST_ALLOWLIST", "cogs.example.org, Other.Example.org")
    rt = make_svc().rt
    assert rt._resolve_image_url("https://cogs.example.org/a.tif", None) == (
        "https://cogs.example.org/a.tif"
    )
    assert rt._resolve_image_url("https://other.example.org/b.tif", None)
    with pytest.raises(rt.HTTPException) as exc:
        rt._resolve_image_url(ALLOWED_COG, None)
    assert exc.value.status_code == 422


def test_gdal_http_timeouts_are_set_at_import_unless_the_operator_set_them(make_svc, monkeypatch):
    import os

    for key in ("GDAL_HTTP_TIMEOUT", "GDAL_HTTP_CONNECTTIMEOUT"):
        monkeypatch.setenv(key, "placeholder")  # يُسجَّل للاستعادة ثمّ يُحذف
        monkeypatch.delenv(key)
    make_svc()
    assert int(os.environ["GDAL_HTTP_TIMEOUT"]) > 0
    assert int(os.environ["GDAL_HTTP_CONNECTTIMEOUT"]) > 0

    monkeypatch.setenv("GDAL_HTTP_TIMEOUT", "7")
    make_svc()
    assert os.environ["GDAL_HTTP_TIMEOUT"] == "7"


def test_dockerfile_pins_gdal_http_timeouts():
    dockerfile = (SVC_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "GDAL_HTTP_TIMEOUT=" in dockerfile
    assert "GDAL_HTTP_CONNECTTIMEOUT=" in dockerfile


# ═══ الحياة والجاهزيّة ════════════════════════════════════════════════════════
def test_healthz_is_alive_even_while_the_model_is_not_loaded(svc, client):
    assert client.get("/readyz").status_code == 503  # متدهور فعلاً

    r = client.get("/healthz")

    assert r.status_code == 200
    assert r.json() == {"status": "alive", "service": "sam2-inference", "version": "1.0.0"}


def test_legacy_health_mirrors_healthz_and_stays_out_of_the_schema(client):
    assert client.get("/health").json() == client.get("/healthz").json()
    assert client.get("/health").status_code == 200

    paths = client.app.openapi()["paths"]
    assert "/healthz" in paths and "/readyz" in paths and "/v1/predict" in paths
    assert "/health" not in paths, "المسار القديم مخفيّ عن المخطّط (include_in_schema=False)"


def test_readyz_reports_degraded_503_with_the_startup_reason(svc, client):
    r = client.get("/readyz")

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["service"] == "sam2-inference"
    assert body["model_loaded"] is False and body["implemented_runtime"] is False
    # خطّاف الإقلاع شُغِّل فعلاً: بلا SAM2_CHECKPOINT_SHA256 ⇒ رفضٌ مُصنَّف قبل torch.
    assert body["reason_code"] == "checkpoint_digest_missing_or_invalid"
    assert body["load_error_present"] is True
    assert "checkpoint_digest_missing_or_invalid" in body["reason"]
    assert body["checkpoint_expected"] == str(svc.checkpoint)
    assert body["artifact_digest"] is None and body["artifact_digest_verified"] is False


def test_readyz_reports_verified_digest_but_cuda_unavailable(make_svc, monkeypatch, tmp_path):
    """بصمة صحيحة على أوزان حقيقيّة البايتات، بلا CUDA ⇒ متدهور بسبب cuda_unavailable،
    والبصمة المُتحقَّق منها تُعلَن (الهويّة ثابتة، التشغيل لا)."""
    payload = b"approved-sam2-checkpoint-bytes"
    digest = hashlib.sha256(payload).hexdigest()
    svc = make_svc(digest=digest)
    svc.checkpoint.write_bytes(payload)
    _fake_torch(monkeypatch, cuda_available=False)

    with TestClient(svc.main.app) as c:
        r = c.get("/readyz")

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["reason_code"] == "cuda_unavailable"
    assert body["artifact_digest"] == digest
    assert body["artifact_digest_verified"] is True
    assert body["model_loaded"] is False


def test_readyz_is_200_ready_when_the_model_is_loaded(svc, client, monkeypatch):
    _arm(svc, monkeypatch)

    r = client.get("/readyz")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["model_loaded"] is True and body["implemented_runtime"] is True
    assert body["reason_code"] is None and body["reason"] is None
    assert body["load_error_present"] is False
    assert body["artifact_digest"] == DIGEST and body["artifact_digest_verified"] is True


# ═══ التزامن: العمل الحاجب خارج حلقة الأحداث، و set_image+predict لا يتداخلان ══════════
# العطلُ الذي وُجدت هذه لأجله (2026-11-02): المسار ``async`` كان يستدعي المُتنبِّئ المشترك
# وقراءة الصورة البعيدة مباشرةً، فيحجز حلقة الأحداث طوال الاستدلال (``/healthz`` لا يجيب).
class _GatedPredictor(FakePredictor):
    """يسجّل تسلسل set_image/predict، وينتظر بوّابةً بين النداءين ليكشف التداخل والحجز."""

    def __init__(self, masks, scores, gate, *, wait_s: float = 2.0):
        super().__init__(masks, scores)
        import threading as _th

        self.gate = gate
        self.wait_s = wait_s
        self.order: list[tuple[str, int]] = []
        self.gate_opened_in_time: list[bool] = []
        self._lock = _th.Lock()

    def set_image(self, image) -> None:
        with self._lock:
            self.order.append(("set", int(image[0, 0, 0])))
        self.gate_opened_in_time.append(self.gate.wait(self.wait_s))

    def predict(self, **kwargs):
        with self._lock:
            self.order.append(("predict", len(self.order)))
        return self.masks, self.scores, None


def _arm_gated(svc, monkeypatch, gate, images, *, wait_s: float = 2.0):
    rt = svc.rt
    _fake_torch(monkeypatch)
    masks = np.stack([_rect_mask(6, 8, slice(0, 2), slice(0, 2))])
    predictor = _GatedPredictor(masks, np.array([0.9], dtype=np.float32), gate, wait_s=wait_s)
    monkeypatch.setattr(rt, "_PREDICTOR", predictor)
    monkeypatch.setattr(rt, "_MODEL_LOAD_ERROR", None)
    monkeypatch.setattr(rt, "_MODEL_ARTIFACT_DIGEST", DIGEST)
    monkeypatch.setattr(rt, "_resolve_image_url", lambda ref, bbox: str(ref))
    it = iter(images)
    monkeypatch.setattr(rt, "_read_rgb", lambda url, bbox: (next(it), object(), object()))
    monkeypatch.setattr(
        rt, "_mask_to_polygon", lambda m, t, c: {"type": "Polygon", "coordinates": [RING]}
    )
    return predictor


def test_predict_does_not_block_the_event_loop_while_inferring(svc, monkeypatch):
    import asyncio
    import threading

    gate = threading.Event()
    predictor = _arm_gated(svc, monkeypatch, gate, [np.full((6, 8, 3), 7, dtype=np.uint8)])
    req = svc.rt.PredictRequest(mode="auto", image_ref=IMAGE_REF, field_bbox=BBOX)

    async def scenario():
        task = asyncio.create_task(svc.main.predict(req))
        # حلقة الأحداث حرّة أثناء الاستدلال: healthz يجيب قبل أن تُفتح البوّابة.
        health = await asyncio.wait_for(svc.main.healthz(), timeout=1.0)
        await asyncio.sleep(0.05)
        gate.set()
        return health, await asyncio.wait_for(task, timeout=5.0)

    health, out = asyncio.run(scenario())
    assert health["status"] == "alive"
    assert out["geometry"]["type"] == "Polygon"
    assert predictor.gate_opened_in_time == [True], "الاستدلال حجز حلقة الأحداث حتّى انتهاء المهلة"


def test_concurrent_predicts_never_interleave_set_image_and_predict(svc, monkeypatch):
    import asyncio
    import threading

    gate = threading.Event()  # لا تُفتح: كلّ set_image يتوقّف 50مث فتظهر أيّ نافذة تداخل
    images = [np.full((6, 8, 3), v, dtype=np.uint8) for v in (1, 2, 3, 4)]
    predictor = _arm_gated(svc, monkeypatch, gate, images, wait_s=0.05)
    req = svc.rt.PredictRequest(mode="auto", image_ref=IMAGE_REF, field_bbox=BBOX)

    async def scenario():
        return await asyncio.gather(*(svc.main.predict(req) for _ in images))

    outs = asyncio.run(scenario())
    assert len(outs) == 4
    kinds = [k for k, _ in predictor.order]
    # كلّ set_image يتبعه predict مباشرةً — لا set ثانٍ قبل predict الأوّل.
    assert kinds == ["set", "predict"] * 4, predictor.order
