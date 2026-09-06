#!/usr/bin/env python3
"""
SAHOOL v9.0 — edge_inference/download_models.py
تحميل نماذج ONNX اختيارياً؛ عند الفشل تبقى الخدمة fail-closed ولا تستخدم محاكاة
"""

import hashlib
import logging
import os
import re
import sys
import urllib.request

logger = logging.getLogger("model-downloader")

MODELS_BASE = os.getenv(
    "MODELS_BASE_URL", "https://github.com/sahool-ai/models/releases/download/v9.0"
)
MODELS_DIR = os.getenv("MODELS_DIR", "/models")

#: البصمةُ المعتمدة تأتي من البيئة — الاسمان نفسُهما اللذان يقرؤهما `main.py`
#: عند تفعيل القدرة، فلا يقبل المُنزِّلُ ملفّاً ترفضه الخدمة.
REQUIRED_MODELS = {
    "pest_detector_int8.onnx": {
        "url": f"{MODELS_BASE}/pest_detector_int8.onnx",
        "size_mb": 18,
        "sha256": os.getenv("PEST_MODEL_SHA256", ""),
        "fallback": "not_provisioned",
    },
    "yield_estimator_int8.onnx": {
        "url": f"{MODELS_BASE}/yield_estimator_int8.onnx",
        "size_mb": 12,
        "sha256": os.getenv("YIELD_MODEL_SHA256", ""),
        "fallback": "not_provisioned",
    },
}

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def verify_sha256(path: str, expected: str) -> bool:
    """يفشل **مغلقاً**: بصمةٌ فارغةٌ أو غيرُ صالحة ترفض الملفّ، لا تقبله.

    **العطلُ المقيس:** كان `if not expected: return True` — فالبصمةُ الفارغةُ
    (وهي القيمةُ المشحونة) تجعل «التحقّق» يمرّ على أيّ بايتات. ملفٌّ بالاسم
    المتوقَّع من أيّ مصدر كان يُقرأ «✅ downloaded OK».
    """
    expected = (expected or "").strip().lower()
    if not _SHA256_HEX.match(expected):
        logger.error("  ❌ %s: لا بصمةَ معتمدةً (PEST_MODEL_SHA256/YIELD_MODEL_SHA256) — يُرفَض", path)
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest() == expected


def download_model(name: str, info: dict) -> bool:
    # بلا بصمةٍ معتمدة لا يُنزَّل شيءٌ أصلاً — لا «نزِّل ثمّ ارفض»: كلُّ بايتٍ يُجلَب
    # من `MODELS_BASE` بلا هويّةٍ منتظَرة بايتٌ مجهول لا مكانَ له على القرص.
    if not _SHA256_HEX.match((info.get("sha256") or "").strip().lower()):
        logger.error("  ❌ %s: لا بصمةَ معتمدةً — لا تنزيل (يبقى %s)", name, info["fallback"])
        return False
    dest = os.path.join(MODELS_DIR, name)
    if os.path.exists(dest):
        if verify_sha256(dest, info.get("sha256", "")):
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
            except Exception:
                if attempt == 2:
                    raise
                import time

                time.sleep(5 * (attempt + 1))
        if verify_sha256(dest, info.get("sha256", "")):
            logger.info(f"  ✅ {name} downloaded OK")
            return True
        else:
            logger.error(f"  ❌ {name} checksum failed")
            os.remove(dest)
            return False
    except Exception as e:
        logger.warning(f"  ⚠️  Cannot download {name}: {e} — model remains {info['fallback']}")
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
        logger.warning(
            f"Missing models (not provisioned; inference endpoints fail closed): {missing}"
        )
    else:
        logger.info("All models ready!")
    sys.exit(0)
