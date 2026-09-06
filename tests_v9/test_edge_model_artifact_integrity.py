"""اسمُ الملفّ لا يُفعِّل نموذجاً، والكاشفُ لا يصف علاجاً — `EDGE-MODEL-ARTIFACT-INTEGRITY-01`.

**ثلاثةُ أعطالٍ مقيسة على `ad4ac5cc`:**

1. **تفعيلٌ بالاسم.** `_model_capability` كانت تُعلن القدرةَ `active` بوجود ملفٍّ بالاسم
   المتوقَّع + `onnxruntime`. لا شيءَ يسأل ما البايتات. و`download_models.verify_sha256`
   كانت تُرجِع `True` على بصمةٍ **فارغة** — وهي القيمةُ المشحونة (`"sha256": ""`).
2. **كاشفٌ يصف مبيدات.** جدولٌ ثابت في `pest_detector.py` يحمل لكلّ صنفٍ «إجراءً»
   بأسماء مبيدات (Imidacloprid · Chlorpyrifos · Abamectin · وEndosulfan **مع كلمة
   «محظور» في السطر نفسه**)، ويُبثّ في تنبيه الواجهة. كاشفُ صورٍ صار يُصدِر توصيةَ علاج.
3. **لايقينٌ مُصطنَع.** `confidence_interval` كان `×0.85`/`×1.15` ثابتين على أيّ تنبّؤ،
   و`predict_yield([])` كان يُرجِع غلّةً **صفراً** عن مُدخَلٍ فارغ.

هذه الحالاتُ تقيس المنطقَ الصرف في `tests_v9` حيث بوّابةُ الدمج؛ ونقاطُ النهاية
تُقاس في `services/edge-inference/tests/` (تحتاج `python-multipart`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.unit]

_ROOT = Path(__file__).resolve().parents[1]
_EDGE = _ROOT / "services" / "edge-inference"


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
def gate():
    return _load("emai_gate", "model_artifact_gate.py")


@pytest.fixture(scope="module")
def downloader():
    return _load("emai_downloader", "download_models.py")


@pytest.fixture(scope="module")
def pest_detector():
    return _load("emai_pest_detector", "models/pest_detector.py")


@pytest.fixture(scope="module")
def yield_estimator():
    return _load("emai_yield_estimator", "models/yield_estimator.py")


# ─── (١) الهويّة: البصمةُ تُفعِّل، لا الاسم ──────────────────────────────


def test_a_same_named_file_without_an_approved_digest_is_not_active(gate, tmp_path, monkeypatch):
    """الشكلُ الذي شُحِن: ملفٌّ بالاسم الصحيح، لا بصمةَ في البيئة."""
    model = tmp_path / "pest_detector_int8.onnx"
    model.write_bytes(b"whatever-bytes-from-anywhere")
    monkeypatch.delenv("PEST_MODEL_SHA256", raising=False)
    cap = gate.model_capability(
        path=str(model), sha_env_name="PEST_MODEL_SHA256", runtime_available=True
    )
    assert cap["active"] is False
    assert cap["reason"] == "model_sha256_missing_or_invalid"
    assert cap["model_file_present"] is True


def test_a_mismatching_digest_is_not_active_and_names_the_reason(gate, tmp_path, monkeypatch):
    model = tmp_path / "pest_detector_int8.onnx"
    model.write_bytes(b"model-v1")
    monkeypatch.setenv("PEST_MODEL_SHA256", "0" * 64)
    cap = gate.model_capability(
        path=str(model), sha_env_name="PEST_MODEL_SHA256", runtime_available=True
    )
    assert cap["active"] is False
    assert cap["reason"] == "model_sha256_mismatch"
    assert cap["actual_sha256"] == hashlib.sha256(b"model-v1").hexdigest()


def test_a_matching_digest_with_runtime_is_active(gate, tmp_path, monkeypatch):
    model = tmp_path / "pest_detector_int8.onnx"
    model.write_bytes(b"model-v1")
    monkeypatch.setenv("PEST_MODEL_SHA256", hashlib.sha256(b"model-v1").hexdigest().upper())
    cap = gate.model_capability(
        path=str(model), sha_env_name="PEST_MODEL_SHA256", runtime_available=True
    )
    assert cap["active"] is True
    assert cap["reason"] is None
    assert cap["sha256_verified"] is True


def test_the_digest_cache_follows_the_bytes_not_the_name(gate, tmp_path):
    """ملفٌّ استُبدِل تحت الاسم نفسه يُعاد تجزئتُه — الذاكرةُ بمفتاح (mtime · size)."""
    model = tmp_path / "m.onnx"
    model.write_bytes(b"v1")
    first = gate.sha256_of_file(str(model))
    model.write_bytes(b"v2-longer")
    second = gate.sha256_of_file(str(model))
    assert first == hashlib.sha256(b"v1").hexdigest()
    assert second == hashlib.sha256(b"v2-longer").hexdigest()


@pytest.mark.parametrize("bad", ["", "   ", "bad", "0" * 63, "g" * 64])
def test_malformed_expected_digests_are_rejected_not_ignored(gate, monkeypatch, bad):
    monkeypatch.setenv("YIELD_MODEL_SHA256", bad)
    assert gate.expected_sha256("YIELD_MODEL_SHA256") is None


def test_the_downloader_no_longer_passes_an_empty_digest(downloader, tmp_path):
    """كان `if not expected: return True` — البصمةُ الفارغة تقبل أيّ بايتات."""
    model = tmp_path / "x.onnx"
    model.write_bytes(b"x")
    assert downloader.verify_sha256(str(model), "") is False
    assert downloader.verify_sha256(str(model), "not-a-digest") is False
    assert downloader.verify_sha256(str(model), "0" * 64) is False
    assert downloader.verify_sha256(str(model), hashlib.sha256(b"x").hexdigest()) is True


def test_nothing_is_downloaded_without_an_approved_digest(downloader, tmp_path, monkeypatch):
    """لا «نزِّل ثمّ ارفض»: بلا بصمةٍ لا يُلمَس المزوّدُ ولا يُكتَب بايتٌ على القرص."""
    monkeypatch.setattr(downloader, "MODELS_DIR", str(tmp_path))
    # يُسجَّل النداءُ بدل أن يُرفَع: `download_model` تلتقط أيّ استثناءٍ من التنزيل
    # وتُرجِع False، فالرفعُ كان سيجعل الطفرةَ «نزِّل ثمّ ارفض» تمرّ خضراء (قِيس).
    calls: list[str] = []
    monkeypatch.setattr(
        downloader.urllib.request, "urlretrieve", lambda url, dest: calls.append(url)
    )
    ok = downloader.download_model(
        "pest_detector_int8.onnx",
        # بالشكل الكامل لِما في `REQUIRED_MODELS` — مدخلٌ ناقص (`size_mb`) كان يُسقِط سطرَ
        # السجلّ قبل التنزيل فتمرّ الطفرةُ خلف KeyError لا خلف الفحص (قِيس).
        {"url": "https://x/pest.onnx", "size_mb": 18, "sha256": "", "fallback": "not_provisioned"},
    )
    assert ok is False
    assert calls == [], f"نُودي المزوّدُ بلا بصمة: {calls}"
    assert not (tmp_path / "pest_detector_int8.onnx").exists()


# ─── (٢) الكاشفُ ملاحظةٌ لا علاج ──────────────────────────────────────────


def test_the_detector_table_carries_no_treatment_and_no_pesticide_name(pest_detector):
    for key, info in pest_detector.EdgePestDetector.PEST_DB.items():
        assert "action" not in info, f"{key}: ما زال يحمل إجراءً"
    source = (_EDGE / "models" / "pest_detector.py").read_text(encoding="utf-8")
    for pesticide in ("Imidacloprid", "Chlorpyrifos", "Abamectin", "Endosulfan", "Mancozeb"):
        assert pesticide not in source, f"اسمُ مبيد ما زال في مصدر الكاشف: {pesticide}"


def test_a_real_shaped_detection_is_observation_only(pest_detector):
    """يُنتَج كشفٌ من رأس YOLOv8 تركيبيّ ويُفحَص شكلُه — لا مطابقةَ نصّ."""
    detector = pest_detector.EdgePestDetector(model_path="/nonexistent/pest.onnx")
    n_classes = len(detector.PEST_DB)
    # رأسُ YOLOv8: [batch, 4 + classes, anchors] — المراسي أكثر من الصفوف ليُوجَّه صحيحاً
    head = np.zeros((1, 4 + n_classes, 32), dtype=np.float32)
    head[0, :4, 0] = [0.5, 0.5, 0.2, 0.2]
    head[0, 4 + 1, 0] = 0.93  # صنفٌ واحد فوق العتبة
    detections = detector._parse_onnx_outputs([head], threshold=0.6, original_size=(640, 640))
    assert len(detections) == 1
    detection = detections[0]
    assert detection["action_policy"] == "observation_only"
    assert "recommended_action" not in detection
    assert {"class_name", "confidence", "bbox", "affected_crops", "severity"} <= set(detection)


def test_the_alert_names_the_pest_and_refuses_to_prescribe(gate):
    alert = gate.high_confidence_alert(
        [
            {
                "arabic_name": "منّ",
                "confidence": 0.93,
                "bbox": {"x1": 0.1},
                "action_policy": "observation_only",
            }
        ]
    )
    assert alert is not None and "منّ" in alert
    assert "الإجراء المقترح" not in alert
    assert "ملاحظةُ كشفٍ فقط" in alert
    assert gate.high_confidence_alert([{"arabic_name": "منّ", "confidence": 0.7}]) is None


# ─── (٣) الغلّة: لا صفرَ عن فراغ ولا فاصلَ مُصطنَع ──────────────────────────


def test_empty_features_are_rejected_not_reported_as_zero_yield(yield_estimator):
    estimator = yield_estimator.EdgeYieldEstimator(model_path="/nonexistent/yield.onnx")
    with pytest.raises(ValueError, match="yield_features_missing"):
        estimator.predict_yield([], crop="wheat", growth_stage="vegetative")


def test_a_model_without_an_interval_publishes_none_and_a_named_limitation(gate):
    shaped = gate.shape_yield_result(
        {"yield_kg_ha": 3210.456, "biomass_proxy": 1.2, "plant_count": 40}
    )
    assert shaped["estimated_yield_kg_ha"] == 3210.46
    assert shaped["confidence_interval"] is None
    assert shaped["limitations"] == ["yield_uncertainty_not_calibrated"]


def test_a_model_supplied_interval_passes_through_unchanged(gate):
    shaped = gate.shape_yield_result(
        {"yield_kg_ha": 3000, "confidence_interval": {"lower": 2500.004, "upper": 3400}}
    )
    assert shaped["confidence_interval"] == {"lower": 2500.0, "upper": 3400.0}
    assert shaped["limitations"] == []
    assert shaped["biomass_proxy"] is None and shaped["plant_count_estimate"] is None


def test_the_fabricated_multipliers_are_gone_from_the_endpoint(gate):
    """تكذيبٌ للشكل الذي شُحِن: لا `×0.85`/`×1.15` في أيّ مسار."""
    for value in (1000.0, 1.0, 12345.678):
        shaped = gate.shape_yield_result({"yield_kg_ha": value})
        assert shaped["confidence_interval"] != {
            "lower": round(value * 0.85, 2),
            "upper": round(value * 1.15, 2),
        }
    source = (_EDGE / "main.py").read_text(encoding="utf-8")
    assert "* 0.85" not in source and "* 1.15" not in source
