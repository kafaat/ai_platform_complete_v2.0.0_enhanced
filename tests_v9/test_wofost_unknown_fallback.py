"""WOFOST-UNKNOWN-FALLBACK-01: unknown crop → unsupported + BLOCK, never perennial_tree.

Before this contract, ``crop_model_type`` silently classified any unknown crop as
``perennial_tree`` and guidance borrowed that framework's change ranges and key
parameters — fabricated specificity. Unknown must be explicit and fail-closed.
"""

import pytest

pytestmark = pytest.mark.unit


def test_wf01_unknown_crop_model_type_is_unsupported_not_perennial_tree():
    from api.wofost_crop_params import crop_model_type

    assert crop_model_type("dragonfruit") == "unsupported"
    assert crop_model_type("") == "unsupported"
    assert crop_model_type("محصول-غير-موجود") == "unsupported"


def test_wf02_known_crops_keep_their_explicit_classification():
    from api.wofost_crop_params import crop_model_type

    assert crop_model_type("wheat") == "annual_cereal"
    assert crop_model_type("citrus") == "perennial_tree"
    assert crop_model_type("نخيل") == "perennial_tree"
    assert crop_model_type("potato") == "tuber"


def test_wf03_unknown_guidance_is_blocked_without_borrowed_framework_values():
    from api.wofost_crop_params import wofost_adaptation_guidance

    out = wofost_adaptation_guidance("dragonfruit")
    assert out["status"] == "blocked"
    assert out["reason"] == "crop_model_type_unknown"
    assert out["model_type"] == "unsupported"
    assert out["crop_recognized"] is False
    # No perennial_tree framework values may leak into the blocked payload.
    for leaked in (
        "expected_change_pct",
        "key_parameters",
        "typical_validation_r2",
        "data_requirement_gb",
    ):
        assert leaked not in out, leaked
    assert "معايرة ميدانيّة" in out["disclaimer_ar"]


def test_wf04_known_guidance_shape_is_unchanged_and_not_blocked():
    from api.wofost_crop_params import wofost_adaptation_guidance

    out = wofost_adaptation_guidance("citrus")
    assert out["crop_recognized"] is True
    assert out["model_type"] == "perennial_tree"
    assert "status" not in out
    assert out["expected_change_pct"] == "40–60%"
