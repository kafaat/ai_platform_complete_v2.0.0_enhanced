"""Exercise activation and the detector with input-dependent ONNX output batches."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize(("declared", "actual"), [(1, 1), (2, 2), ("batch", 1), ("batch", 2)])
def test_pest_output_batch_contract(monkeypatch, declared, actual):
    ort = pytest.importorskip("onnxruntime")
    tests = Path(__file__).resolve().parent
    monkeypatch.syspath_prepend(str(tests.parent))
    from models.errors import ModelOutputContractError
    from models.model_bundle import ModelBundleStore
    from models.pest_detector import DEFAULT_PEST_LABELS_PATH, EdgePestDetector

    path = tests / "fixtures" / f"pest_batch_{declared}.onnx"
    monkeypatch.delenv("PEST_MODEL_BUNDLE_MANIFEST", raising=False)
    monkeypatch.delenv("PEST_LABELS_PATH", raising=False)
    monkeypatch.setenv("PEST_MODEL_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())

    # Each graph flattens the input, casts NonZero indices to float, then
    # reshapes to [-1, width, 1]. Thus one symbolic graph emits both sizes.
    width = 4 + len(json.loads(DEFAULT_PEST_LABELS_PATH.read_bytes())["labels"])
    image = np.zeros((1, 3, 640, 640), dtype=np.float32)
    image.flat[:actual * width] = 1
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    assert session.get_outputs()[0].shape == [declared, width, 1]
    outputs = session.run(None, {"image": image})
    assert outputs[0].shape == (actual, width, 1)
    detector = EdgePestDetector(str(path))
    if actual == 2:
        with pytest.raises(ModelOutputContractError, match="pest_model_batch_not_one"):
            detector._parse_onnx_outputs(outputs, 1e6, (640, 640))
    else:
        assert detector._parse_onnx_outputs(outputs, 1e6, (640, 640)) == []

    capability, bundle = ModelBundleStore().resolve(
        path=str(path), sha_env="PEST_MODEL_SHA256", runtime_available=True, device="rpi5"
    )
    assert capability["active"] is (declared == 1)
    assert (bundle is not None) is (declared == 1)
    if declared != 1:
        assert capability["reason"] == "pest_model_label_contract_violation"
