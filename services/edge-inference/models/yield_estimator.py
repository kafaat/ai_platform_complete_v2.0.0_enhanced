#!/usr/bin/env python3
"""
Edge-Optimized Yield Estimator
MobileViT / EfficientNet-Lite quantized for ARM64
Extracts phenotypic features from field images
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import numpy as np
from models import onnx_providers
from models.errors import ModelNotProvisioned
from models.image_decode import decode_rgb

if TYPE_CHECKING:
    from models.model_bundle import ModelBundle

logger = logging.getLogger(__name__)

YIELD_MODEL_ENV = "YIELD_MODEL_PATH"
YIELD_INPUT_SIZE = (224, 224)

# Cache model sessions separately for CPU and CUDA device selection.
_ONNX_SESSION_CACHE: dict[tuple[str, str], object] = {}


def _ml_yield_model_path(fallback_path: str | None = None) -> str | None:
    """Return the configured yield ONNX path if present on disk.

    Resolution order is explicit env first, then the service-level fallback path
    provided by main.py. This keeps the container usable with MODEL_CACHE only
    while still allowing operators to pin an exact model via YIELD_MODEL_PATH.
    """
    candidates = [os.getenv(YIELD_MODEL_ENV, ""), fallback_path or ""]
    if fallback_path:
        base = os.path.dirname(fallback_path)
        candidates.extend(
            [
                os.path.join(base, "yield_estimator_int8.onnx"),
                os.path.join(base, "yield_estimator_quantized.onnx"),
            ]
        )
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _load_onnx_session(model_path: str, device: str):
    """Lazily import onnxruntime and return a cached InferenceSession, or None.

    onnxruntime is an optional dependency for standalone callers.
    """
    providers = onnx_providers(device)
    key = model_path, providers[0]
    cached = _ONNX_SESSION_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import onnxruntime as ort  # lazy: not in requirements, optional
    except ImportError:
        logger.info("[EdgeYieldEstimator] onnxruntime not installed. ML yield path is dormant.")
        return None
    try:
        session = ort.InferenceSession(model_path, providers=providers)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[EdgeYieldEstimator] فشل تحميل نموذج ONNX (%s): %s",
            model_path,
            e,
        )
        return None
    _ONNX_SESSION_CACHE[key] = session
    return session


class EdgeYieldEstimator:
    """
    On-device yield estimation from field sample images.
    Uses plant counting + canopy coverage + growth stage analysis.
    """

    def __init__(self, model_path: str, device: str = "rpi5", *, bundle: ModelBundle | None = None):
        self._bundle = bundle
        self.model_path = bundle.weight_path if bundle is not None else model_path
        self.device = device
        self.version = "2026.1-edge"
        self.input_size = (
            bundle.preprocessing.input_size if bundle is not None else YIELD_INPUT_SIZE
        )

        # Crop-specific yield factors (kg/ha baseline)
        self.yield_baselines = {
            "wheat": 2500,
            "barley": 2200,
            "maize": 4500,
            "sorghum": 3000,
            "millet": 1800,
            "rice": 5000,
            "potato": 25000,  # kg/ha (high value crop)
            "tomato": 35000,
            "coffee": 1500,
        }

        if bundle is None:
            self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                import onnxruntime as ort

                self.session = ort.InferenceSession(
                    self.model_path, providers=onnx_providers(self.device)
                )
                self.input_name = self.session.get_inputs()[0].name
            except ImportError:
                self.session = None
        else:
            self.session = None
            logger.info(
                f"[EdgeYieldEstimator] Model not found: {self.model_path}. Capability dormant."
            )

    def extract_features(self, image_bytes: bytes) -> dict[str, float]:
        """Extract visual features from a single image."""
        image = decode_rgb(image_bytes)  # يرفض ما فوق سقف البكسلات قبل الفكّ
        image_resized = image.resize(self.input_size)
        img_array = np.array(image_resized).astype(np.float32) / 255.0

        # Production: Run ONNX feature extractor
        # MVP: Simulate features based on image statistics

        # Greenness index (proxy for canopy health)
        r, g, b = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2]
        greenness = np.mean(g) / (np.mean(r) + np.mean(b) + 1e-6)

        # Brightness (proxy for sunlight/exposure)
        brightness = np.mean(img_array)

        # Texture variance (proxy for plant density)
        texture = np.var(img_array)

        # Simulated plant count (from image complexity)
        plant_count_proxy = int(texture * 100)

        return {
            "greenness": round(float(greenness), 3),
            "brightness": round(float(brightness), 3),
            "texture": round(float(texture), 3),
            "plant_count_proxy": plant_count_proxy,
        }

    def predict_yield(self, features: list[dict], crop: str, growth_stage: str) -> dict:
        """Predict yield from visual features with a provisioned ONNX model."""
        if not features:
            # غيابُ القياسات البصريّة ليس غلّةً صفراً — كان يُرجِع `yield_kg_ha: 0`
            # فيقرؤه المستهلكُ محصولاً معدوماً. مُدخَلٌ غيرُ صالح يُرفَض، لا يُصفَّر.
            raise ValueError("yield_features_missing")

        if self._bundle is None:
            model_path = _ml_yield_model_path(self.model_path)
            session = _load_onnx_session(model_path, self.device) if model_path else None
        else:
            model_path = self._bundle.weight_path
            session = self._bundle.session
        if session is None:
            raise ModelNotProvisioned("نموذج تقدير الغلّة (ONNX) غير مُجهَّز — لا اختلاق أرقام")
        return self._predict_yield_onnx(
            session,
            model_path,
            features,
            crop,
            growth_stage,
            input_name=self._bundle.input_name if self._bundle is not None else None,
        )

    def _predict_yield_onnx(
        self,
        session,
        model_path: str,
        features: list[dict],
        crop: str,
        growth_stage: str,
        *,
        input_name: str | None = None,
    ) -> dict:
        """Run REAL ONNX inference over the already-computed band-stat features.

        Builds the model input vector from the aggregated visual features extracted in
        extract_features() (greenness, brightness, texture, plant-count proxy) plus the
        crop baseline and growth-stage multiplier, then maps the model's scalar output
        (predicted yield in kg/ha) to the existing result shape. No fabrication: the
        numbers come entirely from the provisioned model's output.
        """
        stage_multipliers = {
            "seedling": 0.3,
            "vegetative": 0.6,
            "flowering": 0.85,
            "grain_filling": 0.95,
            "maturity": 1.0,
        }
        stage_mult = stage_multipliers.get(growth_stage, 0.7)
        baseline = self.yield_baselines.get(crop, 2000)

        avg_greenness = float(np.mean([f["greenness"] for f in features]))
        avg_brightness = float(np.mean([f["brightness"] for f in features]))
        avg_texture = float(np.mean([f["texture"] for f in features]))
        total_plant_proxy = sum(f["plant_count_proxy"] for f in features)

        # Feature vector fed to the regressor (shape [1, 6], float32).
        input_vec = np.array(
            [
                [
                    avg_greenness,
                    avg_brightness,
                    avg_texture,
                    float(total_plant_proxy),
                    float(baseline),
                    stage_mult,
                ]
            ],
            dtype=np.float32,
        )
        if input_name is None:
            input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: input_vec})
        estimated_yield = float(np.asarray(outputs[0]).reshape(-1)[0])

        harvest_index = {
            "wheat": 0.45,
            "barley": 0.42,
            "maize": 0.50,
            "sorghum": 0.48,
            "millet": 0.35,
            "rice": 0.52,
            "potato": 0.75,
            "tomato": 0.60,
            "coffee": 0.30,
        }.get(crop, 0.45)
        biomass = estimated_yield / harvest_index if harvest_index > 0 else estimated_yield * 2

        return {
            "yield_kg_ha": round(estimated_yield, 2),
            "biomass_proxy": round(biomass, 2),
            "plant_count": int(total_plant_proxy * stage_mult),
            "stage_multiplier": stage_mult,
            "source": "ml_onnx",
            "model": os.path.basename(model_path),
        }
