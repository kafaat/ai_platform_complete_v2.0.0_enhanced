"""ExG preprocessing for vegetation-assisted SAM2 field segmentation.

This module intentionally stays lighter than OpenCV: Pillow + NumPy only.
It enhances vegetation contrast and extracts conservative box/point prompts that
can guide SAM2 without fabricating final field geometry.
"""

from __future__ import annotations

import base64
import io
import os
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageFilter

# Guard against accidental very large images from map screenshots.
Image.MAX_IMAGE_PIXELS = int(os.getenv("EXG_MAX_IMAGE_PIXELS", "12000000"))
EXG_MAX_SIDE = int(os.getenv("EXG_MAX_SIDE", "1280"))


@dataclass(frozen=True)
class VegetationCandidate:
    """A vegetation component candidate to use as a SAM2 prompt."""

    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    area_px: int
    circularity: float
    rectangularity: float
    confidence: float

    def to_dict(self) -> dict:
        data = asdict(self)
        data["bbox"] = list(self.bbox)
        data["centroid"] = list(self.centroid)
        return data


@dataclass(frozen=True)
class ExGResult:
    """Vegetation-enhanced image + prompt candidates for SAM2."""

    image_base64: str
    vegetation_ratio: float
    low_confidence: bool
    candidates: list[VegetationCandidate]
    original_size: tuple[int, int]
    processed_size: tuple[int, int]
    scale: float

    def metadata(self) -> dict:
        return {
            "preprocessing": "exg",
            "vegetation_ratio": self.vegetation_ratio,
            "low_confidence": self.low_confidence,
            "candidate_count": len(self.candidates),
            "candidates": [c.to_dict() for c in self.candidates],
            "original_size": list(self.original_size),
            "processed_size": list(self.processed_size),
            "scale": self.scale,
        }


def _strip_data_url(value: str) -> str:
    return (
        value.split(",", 1)[1] if "," in value and value[:32].lower().startswith("data:") else value
    )


def decode_image_base64(image_base64: str) -> np.ndarray:
    raw = base64.b64decode(_strip_data_url(image_base64), validate=False)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.asarray(image, dtype=np.uint8)


def encode_png_base64(rgb: np.ndarray) -> str:
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    out = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(out, format="PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


def _resize_for_exg(
    rgb: np.ndarray, max_side: int | None = None
) -> tuple[np.ndarray, tuple[int, int], tuple[int, int], float]:
    """Resize oversized map screenshots before Python-side connected components.

    SAM2 receives the processed image, so prompt coordinates remain in the same
    coordinate space as the image. The size metadata is returned for provenance.
    """
    if max_side is None:
        max_side = EXG_MAX_SIDE
    h, w = rgb.shape[:2]
    original_size = (int(w), int(h))
    longest = max(w, h)
    if max_side <= 0 or longest <= max_side:
        return rgb, original_size, original_size, 1.0
    scale = float(max_side / longest)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = Image.fromarray(rgb, mode="RGB").resize((new_w, new_h), Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.uint8), original_size, (int(new_w), int(new_h)), scale


def _morphology_open_close(mask: np.ndarray, size: int = 3) -> np.ndarray:
    """Small binary opening then closing using Pillow filters.

    This removes isolated bright pixels and seals small holes without adding an
    OpenCV/SciPy dependency to the service image.
    """
    if size < 3 or size % 2 == 0:
        size = 3
    img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    opened = img.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))
    closed = opened.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
    return np.asarray(closed, dtype=np.uint8) > 0


def _otsu_threshold(gray: np.ndarray) -> int:
    """Small NumPy implementation of Otsu threshold for uint8 images."""
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = float(gray.size)
    if total <= 0:
        return 0
    prob = hist / total
    omega = np.cumsum(prob)
    mu = np.cumsum(prob * np.arange(256, dtype=np.float64))
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom == 0] = np.nan
    sigma = ((mu_t * omega - mu) ** 2) / denom
    if np.all(np.isnan(sigma)):
        return 0
    return int(np.nanargmax(sigma))


def _remove_small_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    """8-connected component filter without scipy/opencv."""
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    keep = np.zeros((h, w), dtype=bool)
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist(), strict=False):
        if visited[sy, sx]:
            continue
        stack = [(sy, sx)]
        visited[sy, sx] = True
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for ny in range(max(0, y - 1), min(h, y + 2)):
                for nx in range(max(0, x - 1), min(w, x + 2)):
                    if (ny == y and nx == x) or visited[ny, nx] or not mask[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if len(pixels) >= min_area:
            py, px = zip(*pixels, strict=False)
            keep[np.array(py), np.array(px)] = True
    return keep


def _component_candidates(mask: np.ndarray, max_candidates: int = 8) -> list[VegetationCandidate]:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    candidates: list[VegetationCandidate] = []
    img_area = max(1, h * w)
    min_area = max(80, int(img_area * 0.0002))
    ys, xs = np.nonzero(mask)

    for sy, sx in zip(ys.tolist(), xs.tolist(), strict=False):
        if visited[sy, sx]:
            continue
        stack = [(sy, sx)]
        visited[sy, sx] = True
        pixels: list[tuple[int, int]] = []
        edge_count = 0
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            local_boundary = False
            for ny in range(max(0, y - 1), min(h, y + 2)):
                for nx in range(max(0, x - 1), min(w, x + 2)):
                    if ny == y and nx == x:
                        continue
                    if not mask[ny, nx]:
                        local_boundary = True
                        continue
                    if not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            if local_boundary:
                edge_count += 1

        area = len(pixels)
        if area < min_area:
            continue
        arr = np.asarray(pixels, dtype=np.int32)
        min_y, min_x = arr.min(axis=0)
        max_y, max_x = arr.max(axis=0)
        bbox_w = int(max_x - min_x + 1)
        bbox_h = int(max_y - min_y + 1)
        # Give SAM2 a little context around the ExG component. Tight boxes can
        # cut pivot/rectangle edges after thresholding.
        pad = max(3, int(round(max(bbox_w, bbox_h) * 0.04)))
        prompt_min_x = max(0, int(min_x) - pad)
        prompt_min_y = max(0, int(min_y) - pad)
        prompt_max_x = min(w, int(max_x + 1) + pad)
        prompt_max_y = min(h, int(max_y + 1) + pad)
        bbox_area = max(1, bbox_w * bbox_h)
        rectangularity = float(area / bbox_area)
        perimeter = max(1, edge_count)
        circularity = float(min(1.0, (4.0 * np.pi * area) / (perimeter * perimeter)))
        cy = int(round(float(arr[:, 0].mean())))
        cx = int(round(float(arr[:, 1].mean())))
        confidence = float(min(1.0, max(0.0, rectangularity * 0.55 + circularity * 0.45)))
        candidates.append(
            VegetationCandidate(
                bbox=(prompt_min_x, prompt_min_y, prompt_max_x, prompt_max_y),
                centroid=(cx, cy),
                area_px=int(area),
                circularity=circularity,
                rectangularity=rectangularity,
                confidence=confidence,
            )
        )

    candidates.sort(key=lambda c: (c.area_px, c.confidence), reverse=True)
    return candidates[:max_candidates]


def apply_exg_for_sam2(image_base64: str) -> ExGResult:
    """Enhance green vegetation contrast before SAM2.

    ExG = 2G - R - B. The returned image is still RGB so SAM2 keeps context, while
    green vegetation becomes a high-contrast object. Candidate boxes/points are
    derived from the ExG mask and are optional prompts for SAM2.
    """
    rgb_raw = decode_image_base64(image_base64)
    rgb, original_size, processed_size, scale = _resize_for_exg(rgb_raw)
    arr = rgb.astype(np.float32) / 255.0
    exg = (2.0 * arr[:, :, 1]) - arr[:, :, 0] - arr[:, :, 2]
    p2, p98 = np.percentile(exg, [2, 98])
    if abs(float(p98 - p2)) < 1e-8:
        exg_norm = np.zeros_like(exg, dtype=np.float32)
    else:
        exg_norm = np.clip((exg - p2) / (p98 - p2), 0.0, 1.0)
    exg_u8 = (exg_norm * 255.0).astype(np.uint8)
    threshold = _otsu_threshold(exg_u8)
    mask = exg_u8 > max(8, threshold)
    mask = _morphology_open_close(mask, size=3)
    min_area = max(80, int(mask.size * 0.0002))
    mask = _remove_small_components(mask, min_area=min_area)
    vegetation_ratio = float(mask.sum() / max(1, mask.size))
    candidates = _component_candidates(mask)
    low_confidence = vegetation_ratio < 0.02 or vegetation_ratio > 0.95 or not candidates

    exg_rgb = np.repeat(exg_u8[:, :, None], 3, axis=2)
    enhanced = np.clip(
        (rgb.astype(np.float32) * 0.35) + (exg_rgb.astype(np.float32) * 0.65), 0, 255
    )
    return ExGResult(
        image_base64=encode_png_base64(enhanced.astype(np.uint8)),
        vegetation_ratio=vegetation_ratio,
        low_confidence=low_confidence,
        candidates=candidates,
        original_size=original_size,
        processed_size=processed_size,
        scale=scale,
    )
