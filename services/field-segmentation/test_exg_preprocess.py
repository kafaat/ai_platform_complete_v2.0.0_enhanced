from __future__ import annotations

import base64
import io

import numpy as np
from exg_preprocess import apply_exg_for_sam2
from PIL import Image


def _img_to_b64(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8), "RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_exg_highlights_green_region_and_extracts_candidate():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = [125, 100, 70]
    img[25:75, 25:75] = [30, 185, 45]

    result = apply_exg_for_sam2(_img_to_b64(img))

    assert result.image_base64
    assert 0.05 < result.vegetation_ratio < 0.8
    assert result.low_confidence is False
    assert result.candidates
    best = result.candidates[0]
    assert 20 <= best.centroid[0] <= 80
    assert 20 <= best.centroid[1] <= 80


def test_exg_marks_flat_image_low_confidence():
    img = np.full((80, 80, 3), [120, 120, 120], dtype=np.uint8)

    result = apply_exg_for_sam2(_img_to_b64(img))

    assert result.image_base64
    assert result.low_confidence is True
    assert result.vegetation_ratio < 0.02 or result.vegetation_ratio > 0.95


def test_exg_accepts_data_url_and_reports_processed_size():
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    img[:, :] = [130, 105, 75]
    img[30:90, 45:115] = [20, 180, 40]

    result = apply_exg_for_sam2("data:image/png;base64," + _img_to_b64(img))

    assert result.original_size == (160, 120)
    assert result.processed_size == (160, 120)
    assert result.scale == 1.0
    assert result.candidates


def test_exg_downscales_large_viewport_and_keeps_prompt_inside_image(monkeypatch):
    import exg_preprocess

    monkeypatch.setattr(exg_preprocess, "EXG_MAX_SIDE", 96)
    img = np.zeros((180, 240, 3), dtype=np.uint8)
    img[:, :] = [130, 105, 75]
    img[50:130, 80:170] = [20, 190, 45]

    result = apply_exg_for_sam2(_img_to_b64(img))

    assert result.original_size == (240, 180)
    assert max(result.processed_size) == 96
    assert 0 < result.scale < 1
    assert result.candidates
    w, h = result.processed_size
    x1, y1, x2, y2 = result.candidates[0].bbox
    assert 0 <= x1 < x2 <= w
    assert 0 <= y1 < y2 <= h
