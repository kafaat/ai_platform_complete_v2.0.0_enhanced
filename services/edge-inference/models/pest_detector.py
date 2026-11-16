#!/usr/bin/env python3
"""
Edge-Optimized Pest/Disease Detector
ONNX Runtime with INT8 quantization for ARM64
Supports: YOLOv8-World / MobileViT / Custom quantized models
"""

import json
import logging
import os
from pathlib import Path

import numpy as np
from models import onnx_providers
from models.errors import ModelNotProvisioned, ModelOutputContractError
from models.image_decode import decode_rgb

logger = logging.getLogger(__name__)

# Gating mirrors services/sahool-platform/core/capabilities.py :: ml_pest_active()
# ("كشف الآفات بنموذج ML — يتطلّب ملفّ ONNX موجوداً"). The real ONNX path activates
# ONLY when PEST_MODEL_PATH points at an existing file AND onnxruntime is importable
# (lazy — onnxruntime is NOT a hard dependency). Otherwise the service stays honestly
# dormant: detect() raises ModelNotProvisioned (HTTP 503), with no simulated detections.
PEST_MODEL_ENV = "PEST_MODEL_PATH"

# Cache model sessions separately for CPU and CUDA device selection.
_ONNX_SESSION_CACHE: dict[tuple[str, str], object] = {}

# W1-19 (scout-9): class index -> label comes from a label manifest shipped with the model,
# not from the order of a Python dict. The output width must equal 4 + len(labels).
PEST_LABELS_ENV = "PEST_LABELS_PATH"
DEFAULT_PEST_LABELS_PATH = (
    Path(__file__).resolve().parent.parent / "models_manifest" / "pest_labels.json"
)
YOLO_BOX_ROWS = 4


def load_label_manifest(path: str | os.PathLike, known_labels) -> tuple[tuple[str, str], ...]:
    """Read and validate a label manifest -> ``((label, taxonomy_code), ...)`` by class index.

    Fails closed (ModelOutputContractError) on a missing/unreadable file, a gap or repeat in
    the indices, a duplicate label, a label the detector has no metadata for, or a missing
    taxonomy code.
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelOutputContractError(f"pest_label_manifest_unreadable: {path}") from exc
    entries = doc.get("labels") if isinstance(doc, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ModelOutputContractError("pest_label_manifest_has_no_labels")
    if doc.get("box_rows", YOLO_BOX_ROWS) != YOLO_BOX_ROWS:
        raise ModelOutputContractError("pest_label_manifest_box_rows_unsupported")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("index") != position:
            raise ModelOutputContractError(f"pest_label_manifest_index_gap_at_{position}")
        label = entry.get("label")
        code = entry.get("taxonomy_code")
        if not isinstance(label, str) or label not in known_labels:
            raise ModelOutputContractError(f"pest_label_manifest_unknown_label: {label!r}")
        if label in seen:
            raise ModelOutputContractError(f"pest_label_manifest_duplicate_label: {label}")
        if not isinstance(code, str) or not code.strip():
            raise ModelOutputContractError(f"pest_label_manifest_missing_taxonomy_code: {label}")
        seen.add(label)
        out.append((label, code))
    return tuple(out)


# YOLOv8 heads emit one candidate per anchor; a single insect lights up many
# neighbouring anchors. Overlapping boxes of the same class are collapsed to
# the highest-scoring one (standard YOLOv8 IoU threshold).
NMS_IOU_THRESHOLD = 0.45


def _box_area(boxes_xyxy: np.ndarray) -> np.ndarray:
    return np.clip(boxes_xyxy[..., 2] - boxes_xyxy[..., 0], 0, None) * np.clip(
        boxes_xyxy[..., 3] - boxes_xyxy[..., 1], 0, None
    )


def _nms_per_class(
    boxes_xyxy: np.ndarray, scores: np.ndarray, class_ids: np.ndarray, iou_threshold: float
) -> list[int]:
    """Greedy non-maximum suppression within each class. Returns kept indices,
    highest score first. Boxes of different classes never suppress each other."""
    keep: list[int] = []
    for cls in np.unique(class_ids):
        idx = np.flatnonzero(class_ids == cls)
        idx = idx[np.argsort(-scores[idx], kind="stable")]
        while idx.size:
            best, rest = idx[0], idx[1:]
            keep.append(int(best))
            if not rest.size:
                break
            x1 = np.maximum(boxes_xyxy[best, 0], boxes_xyxy[rest, 0])
            y1 = np.maximum(boxes_xyxy[best, 1], boxes_xyxy[rest, 1])
            x2 = np.minimum(boxes_xyxy[best, 2], boxes_xyxy[rest, 2])
            y2 = np.minimum(boxes_xyxy[best, 3], boxes_xyxy[rest, 3])
            inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
            union = _box_area(boxes_xyxy[best]) + _box_area(boxes_xyxy[rest]) - inter
            iou = np.where(union > 0, inter / np.where(union > 0, union, 1), 0.0)
            idx = rest[iou <= iou_threshold]
    keep.sort(key=lambda i: -float(scores[i]))
    return keep


def _ml_pest_model_path(fallback_path: str | None = None) -> str | None:
    """Return the configured pest ONNX path if present on disk.

    Resolution order is explicit env first, then the service-level fallback path
    provided by main.py. This keeps the container usable with MODEL_CACHE only
    while still allowing operators to pin an exact model via PEST_MODEL_PATH.
    """
    candidates = [os.getenv(PEST_MODEL_ENV, ""), fallback_path or ""]
    # Backward-compatible names seen across earlier packages/downloaders.
    if fallback_path:
        base = os.path.dirname(fallback_path)
        candidates.extend(
            [
                os.path.join(base, "pest_detector_int8.onnx"),
                os.path.join(base, "pest_detector_quantized.onnx"),
            ]
        )
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _load_onnx_session(model_path: str, device: str):
    """Lazily import onnxruntime and return a cached InferenceSession, or None.

    onnxruntime is intentionally an OPTIONAL dependency: if the import fails the
    capability is treated as dormant and detect() refuses with ModelNotProvisioned (503).
    """
    providers = onnx_providers(device)
    key = model_path, providers[0]
    cached = _ONNX_SESSION_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        import onnxruntime as ort  # lazy: not in requirements, optional
    except ImportError:
        logger.info(
            "[EdgePestDetector] onnxruntime not installed — ML pest path dormant, "
            "detection refused until a model is provisioned."
        )
        return None
    # نموذج تالف / provider غير متاح ⇒ خامل بصدق (رفض ModelNotProvisioned ⇒ 503، لا كشوف مُختلَقة)
    try:
        session = ort.InferenceSession(model_path, providers=providers)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[EdgePestDetector] فشل تحميل نموذج ONNX (%s) — الكشف مرفوض حتى تجهيز النموذج: %s",
            model_path,
            e,
        )
        return None
    _ONNX_SESSION_CACHE[key] = session
    return session


class EdgePestDetector:
    """
    On-device pest and disease detection.
    Production: Load ONNX quantized model.
    Without a provisioned model detect() raises ModelNotProvisioned (503); the simulation
    helper is kept for tests only and never answers a request.
    """

    # Yemen agricultural pests database
    PEST_DB = {
        "aphid": {
            "arabic": "منّ",
            "crops": ["wheat", "barley", "maize", "tomato"],
            "severity": "medium",
        },
        "armyworm": {
            "arabic": "دودة الحشد",
            "crops": ["maize", "sorghum", "millet"],
            "severity": "high",
        },
        "leaf_miner": {
            "arabic": "حفار الأوراق",
            "crops": ["tomato", "potato"],
            "severity": "medium",
        },
        "red_spider_mite": {
            "arabic": "عنكبوت أحمر",
            "crops": ["tomato", "potato", "coffee"],
            "severity": "medium",
        },
        "stem_borer": {
            "arabic": "حفار الساق",
            "crops": ["maize", "sorghum"],
            "severity": "high",
        },
        "rust": {
            "arabic": "صدأ",
            "crops": ["wheat", "barley"],
            "severity": "high",
        },
        "blight": {
            "arabic": "لفحة",
            "crops": ["potato", "tomato"],
            "severity": "high",
        },
        "bacterial_wilt": {
            "arabic": "ذبول بكتيري",
            "crops": ["tomato", "potato"],
            "severity": "high",
        },
        "coffee_borer": {
            "arabic": "حفار القهوة",
            "crops": ["coffee"],
            "severity": "high",
        },
        "coffee_rust": {
            "arabic": "صدأ القهوة",
            "crops": ["coffee"],
            "severity": "high",
        },
    }

    def __init__(self, model_path: str, device: str = "rpi5"):
        self.model_path = model_path
        self.device = device
        self.version = "2026.1-edge"
        self.input_size = (640, 640)
        self._label_cache: tuple[str, tuple[tuple[str, str], ...]] | None = None

        # Production: Load ONNX Runtime session
        # No model ⇒ detect() refuses (ModelNotProvisioned); nothing is simulated for callers.
        self._load_model()

    def _load_model(self):
        """Load quantized ONNX model."""
        if os.path.exists(self.model_path):
            try:
                import onnxruntime as ort

                # Use ARM64 optimized execution providers
                self.session = ort.InferenceSession(
                    self.model_path, providers=onnx_providers(self.device)
                )
                self.input_name = self.session.get_inputs()[0].name
            except ImportError:
                self.session = None
        else:
            self.session = None
            logger.info(
                f"[EdgePestDetector] Model not found: {self.model_path}. Capability dormant."
            )

    def labels(self) -> tuple[tuple[str, str], ...]:
        """The label manifest for the configured model (``PEST_LABELS_PATH`` or the default)."""
        path = os.getenv(PEST_LABELS_ENV, "").strip() or str(DEFAULT_PEST_LABELS_PATH)
        if self._label_cache is None or self._label_cache[0] != path:
            self._label_cache = (path, load_label_manifest(path, self.PEST_DB))
        return self._label_cache[1]

    def predict(self, image_bytes: bytes, confidence_threshold: float = 0.6) -> list[dict]:
        """
        Run inference on image bytes.
        Returns list of detections with Arabic names and actions.

        Gated on capabilities.ml_pest_active(): when PEST_MODEL_PATH points at an
        existing ONNX file AND onnxruntime is importable, run REAL model inference and
        tag detections "source": "ml_onnx". Otherwise fail closed with ModelNotProvisioned; no synthetic detections are returned.
        """
        # Preprocess (shared by both paths — image features are computed here).
        image = decode_rgb(image_bytes)  # يرفض ما فوق سقف البكسلات قبل الفكّ
        original_size = image.size

        # Resize
        image_resized = image.resize(self.input_size)
        img_array = np.array(image_resized).astype(np.float32) / 255.0
        img_array = np.transpose(img_array, (2, 0, 1))  # CHW
        img_array = np.expand_dims(img_array, axis=0)

        # ── Conditional REAL ONNX path (dormant unless a model file is provisioned) ──
        model_path = _ml_pest_model_path(self.model_path)
        if model_path is not None:
            session = _load_onnx_session(model_path, self.device)
            if session is not None:
                self.labels()  # an invalid manifest refuses before inference, not after
                input_name = session.get_inputs()[0].name
                outputs = session.run(None, {input_name: img_array})
                detections = self._parse_onnx_outputs(outputs, confidence_threshold, original_size)
                model_name = os.path.basename(model_path)
                for d in detections:
                    d["source"] = "ml_onnx"
                    d["model"] = model_name
                return detections

        # ── لا نموذج ONNX حقيقيّ ⇒ لا اختلاق ──
        # سابقاً كان يُرجِع _simulate_detection (آفات/ثقة/مربّعات عشوائيّة) مُقدَّمة
        # للمزارع كمُخرَج نموذج مع تنبيه رشّ مبيد. أمانةً نرفع استثناءً تُترجمه
        # طبقة الـAPI إلى 503 بدل تنبيهٍ مُختلَق. (_simulate_detection يبقى للاختبار
        # المحلّيّ فقط، غير مُستخدَم في مسار الإنتاج.)
        raise ModelNotProvisioned("نموذج كشف الآفات (ONNX) غير مُجهَّز — لا اختلاق كشوف")

    def _parse_onnx_outputs(self, outputs, threshold, original_size):
        """Parse YOLOv8-style ONNX outputs into the existing detection shape.

        Expects a YOLOv8 detection head: [batch, 4 + num_classes, num_anchors],
        where rows 0..3 are the box (cx, cy, w, h in input-normalized or pixel coords)
        and rows 4.. are per-class scores. Class index i means the label manifest's labels[i];
        any other width is refused (ModelOutputContractError), never truncated.
        Real outputs only — no fabrication; no candidate above threshold yields no detections.
        """
        labels = self.labels()
        n_classes = len(labels)
        width = YOLO_BOX_ROWS + n_classes
        if not outputs:
            raise ModelOutputContractError("pest_model_returned_no_output")
        preds = np.asarray(outputs[0])
        # Drop batch dim (one image per call): (1, C, A) -> (C, A).
        if preds.ndim == 3:
            if preds.shape[0] != 1:
                raise ModelOutputContractError(f"pest_model_batch_not_one: {preds.shape}")
            preds = preds[0]
        if preds.ndim != 2:
            raise ModelOutputContractError(f"pest_model_output_rank_unsupported: {preds.shape}")
        # Orient to (num_anchors, 4 + num_classes) by the manifest width, not by a guess.
        if preds.shape[0] == width:
            preds = preds.T
        elif preds.shape[1] != width:
            raise ModelOutputContractError(
                f"pest_model_output_width_mismatch: output {tuple(preds.shape)} does not carry "
                f"{YOLO_BOX_ROWS} box rows + {n_classes} manifest classes"
            )
        boxes = preds[:, :YOLO_BOX_ROWS]
        scores = preds[:, YOLO_BOX_ROWS:]

        # Normalize box coords to [0, 1] if they appear to be in input-pixel space.
        in_w, in_h = self.input_size
        scale = np.array([in_w, in_h, in_w, in_h], dtype=np.float32)
        if float(np.nanmax(np.abs(boxes))) > 1.5:
            boxes = boxes / scale

        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(scores.shape[0]), class_ids].astype(np.float64)
        candidates = np.flatnonzero(confidences >= threshold)
        cx, cy, bw, bh = (boxes[candidates, k].astype(np.float64) for k in range(4))
        xyxy = np.stack([cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0], axis=1)
        kept = _nms_per_class(
            xyxy.reshape(-1, 4),
            confidences[candidates],
            class_ids[candidates],
            NMS_IOU_THRESHOLD,
        )

        detections = []
        for k in kept:
            i = int(candidates[k])
            class_id = int(class_ids[i])
            confidence = float(confidences[i])
            pest_key, taxonomy_code = labels[class_id]
            pest_info = self.PEST_DB[pest_key]
            cx, cy, w, h = (float(v) for v in boxes[i, :4])
            x1, y1 = cx - w / 2.0, cy - h / 2.0
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": pest_key,
                    "taxonomy_code": taxonomy_code,
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
                    "action_policy": "observation_only",
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
                    "action_policy": "observation_only",
                    "severity": pest_info["severity"],
                }
            )

        # Sort by confidence
        detections.sort(key=lambda x: x["confidence"], reverse=True)
        return detections
