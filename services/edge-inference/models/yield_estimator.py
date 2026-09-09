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
from models.errors import ModelNotProvisioned
from PIL import Image

logger = logging.getLogger(__name__)

# Gating mirrors services/sahool-platform/core/capabilities.py :: ml_yield_active()
# ("تنبّؤ الإنتاج بنموذج ML — يتطلّب ملفّ ONNX موجوداً"). The real ONNX path activates
# ONLY when YIELD_MODEL_PATH points at an existing file AND onnxruntime is importable
# (lazy — onnxruntime is NOT a hard dependency). Otherwise the service stays honestly
# dormant and falls back to the existing rule-based heuristic estimate, unchanged.
YIELD_MODEL_ENV = "YIELD_MODEL_PATH"

# Cache of loaded ONNX sessions keyed by resolved model path (one session per file).
_ONNX_SESSION_CACHE: dict[str, object] = {}


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

    onnxruntime is intentionally an OPTIONAL dependency: if the import fails the
    capability is treated as dormant and the caller falls back to the rule-based path.
    """
    cached = _ONNX_SESSION_CACHE.get(model_path)
    if cached is not None:
        return cached
    try:
        import onnxruntime as ort  # lazy: not in requirements, optional
    except ImportError:
        logger.info(
            "[EdgeYieldEstimator] onnxruntime not installed — ML yield path dormant, "
            "falling back to rule-based estimation."
        )
        return None
    providers = ["CPUExecutionProvider"]
    if device == "jetson_orin":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    # نموذج تالف / provider غير متاح ⇒ خامل بصدق (سقوط للمسار القاعديّ، لا كسر طلب)
    try:
        session = ort.InferenceSession(model_path, providers=providers)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[EdgeYieldEstimator] فشل تحميل نموذج ONNX (%s) — السقوط للمسار القاعديّ: %s",
            model_path,
            e,
        )
        return None
    _ONNX_SESSION_CACHE[model_path] = session
    return session


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
                f"[EdgeYieldEstimator] Model not found: {self.model_path}. Capability dormant."
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

    def predict_yield(self, features: list[dict], crop: str, growth_stage: str) -> dict:
        """
        Predict yield from multiple sample images.

        Gated on capabilities.ml_yield_active(): when YIELD_MODEL_PATH points at an
        existing ONNX file AND onnxruntime is importable, run REAL model inference over
        the already-computed band-stat features and tag the result "source": "ml_onnx".
        Otherwise fail closed with ModelNotProvisioned; no synthetic yield is returned.
        """
        if not features:
            # غيابُ القياسات البصريّة ليس غلّةً صفراً — كان يُرجِع `yield_kg_ha: 0`
            # فيقرؤه المستهلكُ محصولاً معدوماً. مُدخَلٌ غيرُ صالح يُرفَض، لا يُصفَّر.
            raise ValueError("yield_features_missing")

        # ── Conditional REAL ONNX path (dormant unless a model file is provisioned) ──
        model_path = _ml_yield_model_path(self.model_path)
        if model_path is not None:
            session = _load_onnx_session(model_path, self.device)
            if session is not None:
                return self._predict_yield_onnx(session, model_path, features, crop, growth_stage)

        # ── لا نموذج ONNX حقيقيّ ⇒ لا اختلاق ──
        # سابقاً كان يُرجِع تقدير غلّة تقريبيّاً (baseline × معاملات بصريّة) مُقدَّماً
        # للمزارع كـ"estimated_yield" بفاصل ثقة ±15% مُصطنَع. أمانةً نرفع استثناءً
        # تُترجمه طبقة الـAPI إلى 503 بدل رقمٍ مُختلَق يبني عليه المزارع قراراً.
        raise ModelNotProvisioned("نموذج تقدير الغلّة (ONNX) غير مُجهَّز — لا اختلاق أرقام")

    def _predict_yield_onnx(
        self,
        session,
        model_path: str,
        features: list[dict],
        crop: str,
        growth_stage: str,
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
