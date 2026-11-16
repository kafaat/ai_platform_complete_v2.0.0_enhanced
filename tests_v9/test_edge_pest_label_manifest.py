"""W1-19 (scout-9): the pest model's output width must equal its label manifest.

Before: ``_parse_onnx_outputs`` mapped class index i to the i-th key of the ``PEST_DB``
dict and used ``n_classes = min(output_classes, len(PEST_DB))``. A model trained on a
different class list was silently truncated or re-labelled: an 11-class model had its
last class dropped and every other index named by dict order, so a farmer was told
"aphid" for whatever the model's class 0 was.

Now ``models_manifest/pest_labels.json`` declares class index -> label -> taxonomy code,
and any output that is not ``4 + len(labels)`` wide is refused (ModelOutputContractError,
HTTP 503 at the endpoint).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.unit]

_EDGE = Path(__file__).resolve().parents[1] / "services" / "edge-inference"
_MANIFEST = _EDGE / "models_manifest" / "pest_labels.json"


@pytest.fixture(scope="module")
def pd():
    if str(_EDGE) not in sys.path:
        sys.path.insert(0, str(_EDGE))
    spec = importlib.util.spec_from_file_location(
        "eplm_pest_detector", _EDGE / "models/pest_detector.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, "pest_detector spec has no loader"
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def detector(pd, tmp_path, monkeypatch):
    monkeypatch.delenv("PEST_MODEL_PATH", raising=False)
    monkeypatch.delenv("PEST_LABELS_PATH", raising=False)
    return pd.EdgePestDetector(str(tmp_path / "absent.onnx"))


def _manifest_len() -> int:
    return len(json.loads(_MANIFEST.read_text(encoding="utf-8"))["labels"])


def _head(n_classes: int, cls: int = 0, score: float = 0.9, anchors: int = 64) -> list:
    out = np.zeros((1, 4 + n_classes, anchors), dtype=np.float32)
    out[0, :4, 0] = (320, 320, 40, 40)
    out[0, 4 + cls, 0] = score
    return [out]


def test_a_manifest_width_output_is_accepted_and_carries_the_taxonomy_code(detector):
    detections = detector._parse_onnx_outputs(_head(_manifest_len(), cls=1), 0.6, (640, 640))
    assert len(detections) == 1, f"expected one detection: {detections}"
    assert detections[0]["class_name"] == "armyworm", f"{detections[0]}"
    assert detections[0]["taxonomy_code"] == "fall_armyworm", f"{detections[0]}"


@pytest.mark.parametrize("delta", [1, -1, 5])
def test_an_output_wider_or_narrower_than_the_manifest_is_refused(pd, detector, delta):
    n = _manifest_len() + delta
    with pytest.raises(pd.ModelOutputContractError, match="width_mismatch"):
        detector._parse_onnx_outputs(_head(n, cls=0), 0.6, (640, 640))


def test_anchor_major_layout_is_accepted_by_width_not_guessed(detector):
    [head] = _head(_manifest_len(), cls=5)
    detections = detector._parse_onnx_outputs([head.transpose(0, 2, 1)], 0.6, (640, 640))
    assert [d["class_name"] for d in detections] == ["rust"], f"{detections}"


def test_a_batch_of_more_than_one_image_is_refused(pd, detector):
    [head] = _head(_manifest_len())
    with pytest.raises(pd.ModelOutputContractError, match="batch_not_one"):
        detector._parse_onnx_outputs([np.concatenate([head, head])], 0.6, (640, 640))


def test_no_output_is_refused_not_an_empty_list(pd, detector):
    with pytest.raises(pd.ModelOutputContractError, match="no_output"):
        detector._parse_onnx_outputs([], 0.6, (640, 640))


def test_class_index_follows_the_manifest_not_dict_order(pd, detector, tmp_path, monkeypatch):
    reordered = {
        "labels": [
            {"index": 0, "label": "coffee_rust", "taxonomy_code": "coffee_leaf_rust"},
            {"index": 1, "label": "aphid", "taxonomy_code": "aphid"},
        ]
    }
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(reordered), encoding="utf-8")
    monkeypatch.setenv("PEST_LABELS_PATH", str(path))
    detections = detector._parse_onnx_outputs(_head(2, cls=0), 0.6, (640, 640))
    assert detections[0]["class_name"] == "coffee_rust", f"{detections}"
    assert detections[0]["taxonomy_code"] == "coffee_leaf_rust", f"{detections}"
    # The default 10-class head is now the wrong width for this model's manifest.
    with pytest.raises(pd.ModelOutputContractError, match="width_mismatch"):
        detector._parse_onnx_outputs(_head(_manifest_len()), 0.6, (640, 640))


@pytest.mark.parametrize(
    ("labels", "reason"),
    [
        ([], "no_labels"),
        ([{"index": 1, "label": "aphid", "taxonomy_code": "aphid"}], "index_gap"),
        (
            [
                {"index": 0, "label": "aphid", "taxonomy_code": "aphid"},
                {"index": 1, "label": "aphid", "taxonomy_code": "aphid"},
            ],
            "duplicate_label",
        ),
        ([{"index": 0, "label": "locust", "taxonomy_code": "locust"}], "unknown_label"),
        ([{"index": 0, "label": "aphid", "taxonomy_code": ""}], "missing_taxonomy_code"),
    ],
)
def test_an_invalid_manifest_fails_closed(pd, tmp_path, labels, reason):
    path = tmp_path / "labels.json"
    path.write_text(json.dumps({"labels": labels}), encoding="utf-8")
    with pytest.raises(pd.ModelOutputContractError, match=reason):
        pd.load_label_manifest(path, pd.EdgePestDetector.PEST_DB)


def test_an_unreadable_manifest_fails_closed(pd, detector, tmp_path, monkeypatch):
    monkeypatch.setenv("PEST_LABELS_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(pd.ModelOutputContractError, match="unreadable"):
        detector._parse_onnx_outputs(_head(_manifest_len()), 0.6, (640, 640))


def test_the_shipped_manifest_is_valid_and_indexed(pd):
    labels = pd.load_label_manifest(_MANIFEST, pd.EdgePestDetector.PEST_DB)
    assert len(labels) == _manifest_len(), "loader dropped manifest entries"
    assert len({label for label, _ in labels}) == len(labels), "duplicate labels shipped"
