#!/usr/bin/env python3
"""
SAHOOL v9.0 — edge_inference/download_models.py
FIX: تحميل نماذج ONNX تلقائياً عند الـ startup
"""
import hashlib, logging, os, urllib.request, sys

logger = logging.getLogger("model-downloader")

MODELS_BASE = os.getenv("MODELS_BASE_URL", "https://github.com/sahool-ai/models/releases/download/v9.0")
MODELS_DIR  = os.getenv("MODELS_DIR", "/models")

REQUIRED_MODELS = {
    "pest_detector_int8.onnx": {
        "url":  f"{MODELS_BASE}/pest_detector_int8.onnx",
        "size_mb": 18,
        "sha256": "",  # set in production
        "fallback": "simulation",
    },
    "yield_estimator_int8.onnx": {
        "url":  f"{MODELS_BASE}/yield_estimator_int8.onnx",
        "size_mb": 12,
        "sha256": "",
        "fallback": "regression",
    },
}

def verify_sha256(path: str, expected: str) -> bool:
    if not expected: return True
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""): h.update(chunk)
    return h.hexdigest() == expected

def download_model(name: str, info: dict) -> bool:
    dest = os.path.join(MODELS_DIR, name)
    if os.path.exists(dest):
        if verify_sha256(dest, info.get("sha256","")):
            logger.info(f"  ✅ {name} already present")
            return True
        else:
            logger.warning(f"  ⚠️ {name} checksum mismatch — re-downloading")
            os.remove(dest)
    try:
        logger.info(f"  ⬇️  Downloading {name} ({info['size_mb']} MB)...")
        # Download with timeout and retry
        for attempt in range(3):
            try:
                import socket
                socket.setdefaulttimeout(120)
                urllib.request.urlretrieve(info["url"], dest)
                break
            except Exception as e:
                if attempt == 2: raise
                import time; time.sleep(5 * (attempt + 1))
        if verify_sha256(dest, info.get("sha256","")):
            logger.info(f"  ✅ {name} downloaded OK")
            return True
        else:
            logger.error(f"  ❌ {name} checksum failed")
            os.remove(dest)
            return False
    except Exception as e:
        logger.warning(f"  ⚠️  Cannot download {name}: {e} — will use {info['fallback']} mode")
        return False

def download_all() -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    results = {}
    for name, info in REQUIRED_MODELS.items():
        results[name] = download_model(name, info)
    return results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(f"Downloading SAHOOL edge models to {MODELS_DIR}...")
    results = download_all()
    missing = [n for n, ok in results.items() if not ok]
    if missing:
        logger.warning(f"Missing models (simulation mode): {missing}")
    else:
        logger.info("All models ready!")
    sys.exit(0)
