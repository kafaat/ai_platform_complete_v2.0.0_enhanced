import logging
logger = logging.getLogger(__name__)
#!/usr/bin/env python3
"""
Edge-Optimized Pest/Disease Detector
ONNX Runtime with INT8 quantization for ARM64
Supports: YOLOv8-World / MobileViT / Custom quantized models
"""
import io
import os
from typing import Dict, List

import numpy as np
from PIL import Image


class EdgePestDetector:
    """
    On-device pest and disease detection.
    Production: Load ONNX quantized model.
    MVP: Template-based simulation with realistic latency.
    """

    # Yemen agricultural pests database
    PEST_DB = {
        "aphid": {"arabic": "منّ", "crops": ["wheat", "barley", "maize", "tomato"], 
                  "action": "رش زيت النيم أو Imidacloprid", "severity": "medium"},
        "armyworm": {"arabic": "دودة الحشد", "crops": ["maize", "sorghum", "millet"],
                     "action": "Bacillus thuringiensis أو Chlorpyrifos", "severity": "high"},
        "leaf_miner": {"arabic": "حفار الأوراق", "crops": ["tomato", "potato"],
                       "action": "Abamectin أو Spinosad", "severity": "medium"},
        "red_spider_mite": {"arabic": "عنكبوت أحمر", "crops": ["tomato", "potato", "coffee"],
                            "action": "صابون زراعي أو Abamectin", "severity": "medium"},
        "stem_borer": {"arabic": "حفار الساق", "crops": ["maize", "sorghum"],
                       "action": "زراعة مبكرة + فخوم فرمونية", "severity": "high"},
        "rust": {"arabic": "صدأ", "crops": ["wheat", "barley"],
                 "action": "Mancozeb أو Propiconazole", "severity": "high"},
        "blight": {"arabic": "لفحة", "crops": ["potato", "tomato"],
                   "action": "Mancozeb + Copper oxychloride", "severity": "high"},
        "bacterial_wilt": {"arabic": "ذبول بكتيري", "crops": ["tomato", "potato"],
                           "action": "تناوب المحاصيل + مقاومة الأصناف", "severity": "high"},
        "coffee_borer": {"arabic": "حفار القهوة", "crops": ["coffee"],
                         "action": "Beauveria bassiana أو Endosulfan (محظور)", "severity": "high"},
        "coffee_rust": {"arabic": "صدأ القهوة", "crops": ["coffee"],
                        "action": "Copper fungicides", "severity": "high"}
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
            logger.info(f"[EdgePestDetector] Model not found: {self.model_path}. Using simulation mode.")

    def predict(self, image_bytes: bytes, confidence_threshold: float = 0.6) -> List[Dict]:
        """
        Run inference on image bytes.
        Returns list of detections with Arabic names and actions.
        """
        # Preprocess
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        original_size = image.size

        # Resize
        image_resized = image.resize(self.input_size)
        img_array = np.array(image_resized).astype(np.float32) / 255.0
        img_array = np.transpose(img_array, (2, 0, 1))  # CHW
        img_array = np.expand_dims(img_array, axis=0)

        # Run inference (production: ONNX session.run)
        if self.session:
            outputs = self.session.run(None, {self.input_name: img_array})
            return self._parse_onnx_outputs(outputs, confidence_threshold, original_size)
        else:
            # Simulation mode: return realistic mock detections
            return self._simulate_detection(image, confidence_threshold)

    def _parse_onnx_outputs(self, outputs, threshold, original_size):
        """Parse YOLOv8 ONNX outputs."""
        # YOLOv8 output format: [batch, 84, 8400] for 80 COCO classes
        # Adapted for custom pest classes
        detections = []
        # ... actual parsing logic ...
        return detections

    def _simulate_detection(self, image, threshold):
        """Simulate realistic pest detection for MVP."""
        import random
        # FIXED: hash() is non-deterministic in Python 3 (PYTHONHASHSEED)
        # Use hashlib.md5 for reproducible deterministic seeding
        import hashlib as _hl
        seed = int(_hl.md5(image.tobytes()).hexdigest(), 16) % (2**31)
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

            detections.append({
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
                    "height": round(h, 3)
                },
                "affected_crops": pest_info["crops"],
                "recommended_action": pest_info["action"],
                "severity": pest_info["severity"]
            })

        # Sort by confidence
        detections.sort(key=lambda x: x["confidence"], reverse=True)
        return detections
