# SAHOOL v9 — models/image_decode.py
"""فكّ صور الإدخال بسقف بكسلات قبل فكّ البيانات.

Pillow يقرأ الأبعاد من الترويسة عند ``Image.open`` ولا يفكّ البكسلات إلّا عند
``load``/``convert``. ملفّ PNG من ~٥٠٠ ك.ب يمكن أن يُعلن 13000×13000 فيُفكّ إلى ~١٫٣ غ.ب
على جهاز حافة. لذا نرفض ``width × height`` فوق السقف قبل أيّ فكّ، ونحوّل
``DecompressionBombWarning`` (التي يكتفي Pillow افتراضيّاً بالتحذير منها) إلى رفض.
"""

from __future__ import annotations

import io
import os
import warnings

from models.errors import ImageTooLarge
from PIL import Image

MAX_IMAGE_PIXELS_ENV = "EDGE_MAX_IMAGE_PIXELS"
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000  # 40 ميغابكسل — أكبر من كاميرات الهاتف الشائعة


def max_image_pixels() -> int:
    """السقف من البيئة؛ قيمة غير صالحة أو غير موجبة ⇒ الافتراضيّ (لا سقف مفتوح)."""
    raw = os.getenv(MAX_IMAGE_PIXELS_ENV, "").strip()
    try:
        value = int(raw) if raw else DEFAULT_MAX_IMAGE_PIXELS
    except ValueError:
        return DEFAULT_MAX_IMAGE_PIXELS
    return value if value > 0 else DEFAULT_MAX_IMAGE_PIXELS


def decode_rgb(image_bytes: bytes) -> Image.Image:
    """يُرجِع صورة RGB مفكوكة، أو يرفع ImageTooLarge قبل فكّ صورة فوق السقف."""
    limit = max_image_pixels()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            image = Image.open(io.BytesIO(image_bytes))
            width, height = image.size
            if width * height > limit:
                raise ImageTooLarge(f"image_too_large:{width}x{height}>{limit}px")
            return image.convert("RGB")
        except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
            raise ImageTooLarge("image_decompression_bomb") from exc
