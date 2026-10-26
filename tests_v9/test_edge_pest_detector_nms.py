"""كاشف الآفات: حشرةٌ واحدة = كشفٌ واحد (NMS لكلّ صنف بـIoU 0.45).

رأس YOLOv8 يُخرج مرشّحاً لكلّ مرساة، وحشرةٌ واحدة تُضيء مراسيَ متجاورة كثيرة. كان
``_parse_onnx_outputs`` يُحوّل كلّ مرساة فوق العتبة إلى كشف، فيرى المزارع عدّة مربّعات
متراكبة لآفةٍ واحدة (ويُضخَّم عدّها). هنا تُقاس المخرجات على مصفوفة YOLOv8 مُصطنعة.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.unit]

_EDGE = Path(__file__).resolve().parents[1] / "services" / "edge-inference"
N_CLASSES = 10  # PEST_DB


@pytest.fixture(scope="module")
def pest_detector():
    if str(_EDGE) not in sys.path:
        sys.path.insert(0, str(_EDGE))
    spec = importlib.util.spec_from_file_location(
        "epnms_pest_detector", _EDGE / "models/pest_detector.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def detector(pest_detector, tmp_path, monkeypatch):
    monkeypatch.delenv("PEST_MODEL_PATH", raising=False)
    return pest_detector.EdgePestDetector(str(tmp_path / "absent.onnx"))


def _yolo(anchors: list[tuple[float, float, float, float, int, float]]) -> list[np.ndarray]:
    """[(cx, cy, w, h, class_id, score)] ⇒ مخرج YOLOv8 بشكل (1, 4+C, A) بإحداثيّات بكسل.

    تُحشى مراسٍ صفريّة حتّى 64 (الحقيقيّ 8400) كي يبقى A > 4+C فيُستدلّ الاتّجاه صحيحاً."""
    out = np.zeros((1, 4 + N_CLASSES, max(64, len(anchors))), dtype=np.float32)
    for a, (cx, cy, w, h, cls, score) in enumerate(anchors):
        out[0, :4, a] = (cx, cy, w, h)
        out[0, 4 + cls, a] = score
    return [out]


def test_one_insect_lit_on_neighbouring_anchors_yields_one_detection(detector):
    outputs = _yolo(
        [
            (320, 320, 40, 40, 0, 0.91),
            (322, 321, 40, 40, 0, 0.88),
            (318, 319, 42, 38, 0, 0.84),
            (321, 318, 39, 41, 0, 0.79),
        ]
    )
    detections = detector._parse_onnx_outputs(outputs, 0.6, (640, 640))
    assert len(detections) == 1
    assert detections[0]["class_name"] == "aphid"
    assert detections[0]["confidence"] == pytest.approx(0.91, abs=1e-3)


def test_separate_insects_and_other_classes_are_not_suppressed(detector):
    outputs = _yolo(
        [
            (100, 100, 40, 40, 0, 0.90),  # منّ أ
            (102, 101, 40, 40, 0, 0.70),  # تكرار منّ أ ⇒ يُكبَت
            (500, 500, 40, 40, 0, 0.80),  # منّ ب بعيد ⇒ يبقى
            (101, 100, 40, 40, 5, 0.75),  # صدأ في الموضع نفسه ⇒ صنف آخر يبقى
            (300, 300, 40, 40, 1, 0.50),  # تحت العتبة ⇒ يُسقَط
        ]
    )
    detections = detector._parse_onnx_outputs(outputs, 0.6, (640, 640))
    assert [(d["class_name"], d["confidence"]) for d in detections] == [
        ("aphid", 0.9),
        ("aphid", 0.8),
        ("rust", 0.75),
    ]


def test_iou_threshold_is_0_45(pest_detector):
    assert pest_detector.NMS_IOU_THRESHOLD == 0.45
    boxes = np.array([[0, 0, 10, 10], [5, 0, 15, 10], [3, 0, 13, 10]], dtype=np.float64)
    scores = np.array([0.9, 0.8, 0.7])
    classes = np.zeros(3, dtype=int)
    # IoU(0,1) = 50/150 ≈ 0.33 ⇒ يبقى؛ IoU(0,2) = 70/130 ≈ 0.54 ⇒ يُكبَت.
    assert pest_detector._nms_per_class(boxes, scores, classes, 0.45) == [0, 1]


def test_no_candidate_above_threshold_is_an_empty_list(detector):
    outputs = _yolo([(320, 320, 40, 40, 0, 0.3)])
    assert detector._parse_onnx_outputs(outputs, 0.6, (640, 640)) == []
