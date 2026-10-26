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
