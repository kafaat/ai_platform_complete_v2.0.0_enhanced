# SAHOOL v9 — models/errors.py
"""أخطاء طبقة النماذج على الحافة.

ModelNotProvisioned: يُرفع حين لا يتوفّر نموذج ONNX حقيقيّ. بدل اختلاق كشوف/
أرقام عشوائيّة وتقديمها للمزارع كمُخرَج نموذج (وهو ما كان يحدث في مسار المحاكاة
الاحتياطيّ)، نرفع هذا الاستثناء فتُترجمه طبقة الـAPI إلى 503 صريح — أمانةً مع
المستخدم (نفس فلسفة weather-service الذي يردّ 501 بدل بيانات مُختلَقة).
"""


class ModelNotProvisioned(RuntimeError):
    """نموذج الاستدلال غير مُجهَّز (لا ملفّ ONNX/لا onnxruntime) — لا اختلاق."""


class ImageTooLarge(ValueError):
    """صورة إدخال تتجاوز سقف البكسلات (أو قنبلة فكّ ضغط) — تُرفض قبل فكّها."""


class ModelOutputContractError(RuntimeError):
    """W1-19 (scout-9): the model's output does not match its label manifest.

    A class count that differs from the manifest (or an unreadable/invalid manifest) means
    class index -> pest name is unknown. The detector refuses (HTTP 503) instead of
    truncating to the shorter list and naming the wrong pest.
    """
