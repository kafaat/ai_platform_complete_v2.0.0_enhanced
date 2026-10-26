"""صور الإدخال على الحافة تُرفض فوق سقف البكسلات قبل فكّها.

كان كاشف الآفات ومقدّر الغلّة يفكّان أيّ صورة بإعدادات Pillow الافتراضيّة: ملفّ PNG
من ~٥٣١ ك.ب يُعلن 13000×13000 يُفكّ إلى ~١٫٣ غ.ب (Pillow يكتفي بتحذير تحت ضعف
``MAX_IMAGE_PIXELS``). هنا يُقاس أنّ الأبعاد المُعلنة فوق السقف تُرفض قبل ``load``،
وأنّ ``DecompressionBombWarning`` رفضٌ لا تحذير.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageFile

pytestmark = [pytest.mark.unit]

_EDGE = Path(__file__).resolve().parents[1] / "services" / "edge-inference"


def _load(name: str, relative: str):
    if str(_EDGE) not in sys.path:
        sys.path.insert(0, str(_EDGE))
    spec = importlib.util.spec_from_file_location(name, _EDGE / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pest_detector():
    return _load("eipc_pest_detector", "models/pest_detector.py")


@pytest.fixture(scope="module")
def yield_estimator():
    return _load("eipc_yield_estimator", "models/yield_estimator.py")


@pytest.fixture
def detector(pest_detector, tmp_path, monkeypatch):
    monkeypatch.delenv("PEST_MODEL_PATH", raising=False)
    return pest_detector.EdgePestDetector(str(tmp_path / "absent.onnx"))


@pytest.fixture
def estimator(yield_estimator, tmp_path, monkeypatch):
    monkeypatch.delenv("YIELD_MODEL_PATH", raising=False)
    return yield_estimator.EdgeYieldEstimator(str(tmp_path / "absent.onnx"))


def _png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("1", (width, height), 0).save(buffer, "PNG")  # 1-bit: ترويسة كبيرة، ملفّ صغير
    return buffer.getvalue()


@pytest.fixture
def load_calls(monkeypatch):
    calls: list[tuple[int, int]] = []
    original = ImageFile.ImageFile.load

    def _counting_load(self):
        calls.append(self.size)
        return original(self)

    monkeypatch.setattr(ImageFile.ImageFile, "load", _counting_load)
    return calls


def _image_too_large(module):
    # الصنف كما يراه الكاشف نفسه (لا ما قد يكون في sys.modules من حزمة models أخرى).
    return module.decode_rgb.__globals__["ImageTooLarge"]


def test_pest_detector_rejects_an_image_above_the_pixel_cap_before_decoding(
    detector, pest_detector, monkeypatch, load_calls
):
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", "10000")
    with pytest.raises(_image_too_large(pest_detector)):
        detector.predict(_png(200, 100))  # 20 000 px > 10 000
    assert load_calls == []


def test_yield_estimator_rejects_an_image_above_the_pixel_cap_before_decoding(
    estimator, yield_estimator, monkeypatch, load_calls
):
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", "10000")
    with pytest.raises(_image_too_large(yield_estimator)):
        estimator.extract_features(_png(200, 100))
    assert load_calls == []


def test_default_cap_rejects_a_48_megapixel_png_that_pillow_would_decode(
    estimator, yield_estimator, monkeypatch, load_calls
):
    monkeypatch.delenv("EDGE_MAX_IMAGE_PIXELS", raising=False)
    data = _png(8000, 6000)  # 48 MP: تحت عتبة تحذير Pillow (~89 MP)، فوق السقف (40 MP)
    assert len(data) < 200_000
    with pytest.raises(_image_too_large(yield_estimator)):
        estimator.extract_features(data)
    assert load_calls == []


@pytest.mark.parametrize("raw", ["not-a-number", "0", "-5"])
def test_invalid_cap_falls_back_to_the_default_not_to_no_cap(yield_estimator, monkeypatch, raw):
    decode = sys.modules[yield_estimator.decode_rgb.__module__]
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", raw)
    assert decode.max_image_pixels() == decode.DEFAULT_MAX_IMAGE_PIXELS


def test_decompression_bomb_warning_is_a_rejection(estimator, yield_estimator, monkeypatch):
    # سقفنا مرفوع، وعتبة Pillow منخفضة: 40×40 = 1600 > 1000 ⇒ تحذير (لا خطأ) عند Pillow.
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", str(10**9))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(_image_too_large(yield_estimator)):
        estimator.extract_features(_png(40, 40))


def test_an_image_under_the_cap_is_still_decoded(estimator, monkeypatch):
    monkeypatch.setenv("EDGE_MAX_IMAGE_PIXELS", "10000")
    features = estimator.extract_features(_png(64, 64))
    assert set(features) >= {"greenness", "brightness", "texture"}
