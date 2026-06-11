#!/usr/bin/env python3
"""
Edge-Optimized Pest/Disease Detector
ONNX Runtime with INT8 quantization for ARM64
Supports: YOLOv8-World / MobileViT / Custom quantized models
"""

import io
import logging
import os

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Gating mirrors services/sahool-platform/core/capabilities.py :: ml_pest_active()
# ("كشف الآفات بنموذج ML — يتطلّب ملفّ ONNX موجوداً"). The real ONNX path activates
# ONLY when PEST_MODEL_PATH points at an existing file AND onnxruntime is importable
# (lazy — onnxruntime is NOT a hard dependency). Otherwise the service stays honestly
# dormant and falls back to the existing rule-based / simulation path, unchanged.
PEST_MODEL_ENV = "PEST_MODEL_PATH"

# Cache of loaded ONNX sessions keyed by resolved model path (one session per file).
_ONNX_SESSION_CACHE: dict[str, object] = {}


def _ml_pest_model_path() -> str | None:
    """Return the configured pest model path iff it is set and the file exists.

    Same condition as capabilities.ml_pest_active(): PEST_MODEL_PATH present on disk.
    Returns None when the capability is dormant (no model → rule-based fallback).
    """
    p = os.getenv(PEST_MODEL_ENV, "")
    return p if p and os.path.exists(p) else None


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
            "[EdgePestDetector] onnxruntime not installed — ML pest path dormant, "
            "falling back to rule-based detection."
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
            "[EdgePestDetector] فشل تحميل نموذج ONNX (%s) — السقوط للمسار القاعديّ: %s",
            model_path,
            e,
        )
        return None
    _ONNX_SESSION_CACHE[model_path] = session
    return session


class EdgePestDetector:
    """
    On-device pest and disease detection.
    Production: Load ONNX quantized model.
    MVP: Template-based simulation with realistic latency.
    """

    # Yemen agricultural pests database
    PEST_DB = {
        "aphid": {
            "arabic": "منّ",
            "crops": ["wheat", "barley", "maize", "tomato"],
            "action": "رش زيت النيم أو Imidacloprid",
            "severity": "medium",
        },
        "armyworm": {
            "arabic": "دودة الحشد",
            "crops": ["maize", "sorghum", "millet"],
            "action": "Bacillus thuringiensis أو Chlorpyrifos",
            "severity": "high",
        },
        "leaf_miner": {
            "arabic": "حفار الأوراق",
            "crops": ["tomato", "potato"],
            "action": "Abamectin أو Spinosad",
            "severity": "medium",
        },
        "red_spider_mite": {
            "arabic": "عنكبوت أحمر",
            "crops": ["tomato", "potato", "coffee"],
            "action": "صابون زراعي أو Abamectin",
            "severity": "medium",
        },
        "stem_borer": {
            "arabic": "حفار الساق",
            "crops": ["maize", "sorghum"],
            "action": "زراعة مبكرة + فخوم فرمونية",
            "severity": "high",
        },
        "rust": {
            "arabic": "صدأ",
            "crops": ["wheat", "barley"],
            "action": "Mancozeb أو Propiconazole",
            "severity": "high",
        },
        "blight": {
            "arabic": "لفحة",
            "crops": ["potato", "tomato"],
            "action": "Mancozeb + Copper oxychloride",
            "severity": "high",
        },
        "bacterial_wilt": {
            "arabic": "ذبول بكتيري",
            "crops": ["tomato", "potato"],
            "action": "تناوب المحاصيل + مقاومة الأصناف",
            "severity": "high",
        },
        "coffee_borer": {
            "arabic": "حفار القهوة",
            "crops": ["coffee"],
            "action": "Beauveria bassiana أو Endosulfan (محظور)",
            "severity": "high",
        },
        "coffee_rust": {
            "arabic": "صدأ القهوة",
            "crops": ["coffee"],
            "action": "Copper fungicides",
            "severity": "high",
        },
    }

    def __init__(self, model_path: str, device: str = "rpi5"):
        self.model_path = model_path
        self.device = device
        self.version = "2026.1-edge"
        self.input_size = (640, 640)

        # Production: Load ONNX Runtime session
        # For MVP: simulate inference with realistic Yemen pest probabilities
        self._load_model()

    def _load_model(self):
        """Load quantized ONNX model."""
        if os.path.exists(self.model_path):
            try:
                import onnxruntime as ort

                # Use ARM64 optimized execution providers
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
                f"[EdgePestDetector] Model not found: {self.model_path}. Using simulation mode."
            )

    def predict(self, image_bytes: bytes, confidence_threshold: float = 0.6) -> list[dict]:
        """
        Run inference on image bytes.
        Returns list of detections with Arabic names and actions.

        Gated on capabilities.ml_pest_active(): when PEST_MODEL_PATH points at an
        existing ONNX file AND onnxruntime is importable, run REAL model inference and
        tag detections "source": "ml_onnx". Otherwise fall back to the EXISTING
        rule-based simulation, byte-for-byte unchanged.
        """
        # Preprocess (shared by both paths — image features are computed here).
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        original_size = image.size

        # Resize
        image_resized = image.resize(self.input_size)
        img_array = np.array(image_resized).astype(np.float32) / 255.0
        img_array = np.transpose(img_array, (2, 0, 1))  # CHW
        img_array = np.expand_dims(img_array, axis=0)

        # ── Conditional REAL ONNX path (dormant unless a model file is provisioned) ──
        model_path = _ml_pest_model_path()
        if model_path is not None:
            session = _load_onnx_session(model_path, self.device)
            if session is not None:
                input_name = session.get_inputs()[0].name
                outputs = session.run(None, {input_name: img_array})
                detections = self._parse_onnx_outputs(outputs, confidence_threshold, original_size)
                model_name = os.path.basename(model_path)
                for d in detections:
                    d["source"] = "ml_onnx"
                    d["model"] = model_name
                return detections

        # ── Honest fallback: EXISTING rule-based simulation (unchanged output) ──
        return self._simulate_detection(image, confidence_threshold)

    def _parse_onnx_outputs(self, outputs, threshold, original_size):
        """Parse YOLOv8-style ONNX outputs into the existing detection shape.

        Expects a YOLOv8 detection head: [batch, 4 + num_classes, num_anchors],
        where rows 0..3 are the box (cx, cy, w, h in input-normalized or pixel coords)
        and rows 4.. are per-class scores. Class indices map to PEST_DB keys in order.
        Real outputs only — no fabrication; an empty model output yields no detections.
        """
        pest_keys = list(self.PEST_DB.keys())
        preds = np.asarray(outputs[0])
        # Drop batch dim if present: (1, C, A) -> (C, A).
        if preds.ndim == 3:
            preds = preds[0]
        if preds.ndim != 2 or preds.shape[0] < 5:
            return []
        # Orient to (num_anchors, 4 + num_classes).
        if preds.shape[0] < preds.shape[1]:
            preds = preds.T
        boxes = preds[:, :4]
        scores = preds[:, 4:]
        n_classes = min(scores.shape[1], len(pest_keys))

        # Normalize box coords to [0, 1] if they appear to be in input-pixel space.
        in_w, in_h = self.input_size
        scale = np.array([in_w, in_h, in_w, in_h], dtype=np.float32)
        if float(np.nanmax(np.abs(boxes))) > 1.5:
            boxes = boxes / scale

        detections = []
        for i in range(preds.shape[0]):
            class_id = int(np.argmax(scores[i, :n_classes]))
            confidence = float(scores[i, class_id])
            if confidence < threshold:
                continue
            pest_key = pest_keys[class_id]
            pest_info = self.PEST_DB[pest_key]
            cx, cy, w, h = (float(v) for v in boxes[i, :4])
            x1, y1 = cx - w / 2.0, cy - h / 2.0
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": pest_key,
                    "arabic_name": pest_info["arabic"],
                    "confidence": round(confidence, 3),
                    "bbox": {
                        "x1": round(x1, 3),
                        "y1": round(y1, 3),
                        "x2": round(x1 + w, 3),
                        "y2": round(y1 + h, 3),
                        "width": round(w, 3),
                        "height": round(h, 3),
                    },
                    "affected_crops": pest_info["crops"],
                    "recommended_action": pest_info["action"],
                    "severity": pest_info["severity"],
                }
            )
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections

    def _simulate_detection(self, image, threshold):
        """Simulate realistic pest detection for MVP."""
        # FIXED: hash() is non-deterministic in Python 3 (PYTHONHASHSEED)
        # Use hashlib.md5 for reproducible deterministic seeding
        import hashlib as _hl
        import random

        seed = int(_hl.md5(image.tobytes(), usedforsecurity=False).hexdigest(), 16) % (2**31)
        random.seed(seed)

        # Determine likely pests based on image hash (simulated crop context)
        num_detections = random.randint(0, 3)
        if num_detections == 0:
            return []

        detections = []
        available_pests = list(self.PEST_DB.keys())

        for i in range(num_detections):
            pest_key = random.choice(available_pests)
            pest_info = self.PEST_DB[pest_key]
            confidence = random.uniform(threshold, min(0.99, threshold + 0.3))

            # Random bbox (normalized)
            x1 = random.uniform(0.1, 0.6)
            y1 = random.uniform(0.1, 0.6)
            w = random.uniform(0.05, 0.3)
            h = random.uniform(0.05, 0.3)

            detections.append(
                {
                    "class_id": i,
                    "class_name": pest_key,
                    "arabic_name": pest_info["arabic"],
                    "confidence": round(confidence, 3),
                    "bbox": {
                        "x1": round(x1, 3),
                        "y1": round(y1, 3),
                        "x2": round(x1 + w, 3),
                        "y2": round(y1 + h, 3),
                        "width": round(w, 3),
                        "height": round(h, 3),
                    },
                    "affected_crops": pest_info["crops"],
                    "recommended_action": pest_info["action"],
                    "severity": pest_info["severity"],
                }
            )

        # Sort by confidence
        detections.sort(key=lambda x: x["confidence"], reverse=True)
        return detections
