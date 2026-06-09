#!/usr/bin/env python3
"""
Edge-Optimized Yield Estimator
MobileViT / EfficientNet-Lite quantized for ARM64
Extracts phenotypic features from field images
"""

import io
import logging
import os

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class EdgeYieldEstimator:
    """
    On-device yield estimation from field sample images.
    Uses plant counting + canopy coverage + growth stage analysis.
    """

    def __init__(self, model_path: str, device: str = "rpi5"):
        self.model_path = model_path
        self.device = device
        self.version = "2026.1-edge"
        self.input_size = (224, 224)

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

        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                import onnxruntime as ort

                providers = ["CPUExecutionProvider"]
                if self.device == "jetson_orin":
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

                self.session = ort.InferenceSession(self.model_path, providers=providers)
                self.input_name = self.session.get_inputs()[0].name
            except ImportError:
                self.session = None
        else:
            self.session = None
            logger.info(
                f"[EdgeYieldEstimator] Model not found: {self.model_path}. Using simulation mode."
            )

    def extract_features(self, image_bytes: bytes) -> dict[str, float]:
        """Extract visual features from a single image."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
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

    def predict_yield(self, features: list[dict], crop: str, growth_stage: str) -> dict[str, float]:
        """
        Predict yield from multiple sample images.
        """
        if not features:
            return {"yield_kg_ha": 0, "biomass_proxy": 0, "plant_count": 0}

        # Aggregate features
        avg_greenness = np.mean([f["greenness"] for f in features])
        avg_texture = np.mean([f["texture"] for f in features])
        total_plant_proxy = sum([f["plant_count_proxy"] for f in features])

        # Growth stage multiplier
        stage_multipliers = {
            "seedling": 0.3,
            "vegetative": 0.6,
            "flowering": 0.85,
            "grain_filling": 0.95,
            "maturity": 1.0,
        }
        stage_mult = stage_multipliers.get(growth_stage, 0.7)

        # Baseline yield
        baseline = self.yield_baselines.get(crop, 2000)

        # Adjust based on visual features
        # Greenness factor: 0.8 to 1.2
        greenness_factor = 0.8 + (avg_greenness * 0.4)

        # Density factor: based on texture variance (plant density proxy)
        density_factor = 0.7 + min(avg_texture * 2, 0.5)

        # Calculate yield
        estimated_yield = baseline * stage_mult * greenness_factor * density_factor

        # Biomass proxy (higher than yield, before harvest index)
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
            "greenness_factor": round(greenness_factor, 3),
            "density_factor": round(density_factor, 3),
            "stage_multiplier": stage_mult,
        }
