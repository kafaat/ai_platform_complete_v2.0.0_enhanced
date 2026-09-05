"""بوّابةُ هويّة مصنوعة النموذج على الحافّة — `EDGE-MODEL-ARTIFACT-INTEGRITY-01`.

**العطلُ المقيس على `ad4ac5cc`:** كانت القدرةُ تُعلَن `active` بشرطين: ملفٌّ بالاسم
المتوقَّع موجود + `onnxruntime` مستورَد. **لا شيءَ يسأل ما البايتات.** ومُنزِّلُ
النماذج كان يقبل البصمةَ الفارغة (`if not expected: return True`) — وهي القيمةُ
المشحونة. فأيُّ ملفٍّ باسم `pest_detector_int8.onnx` من أيّ مصدرٍ كان يصير قدرةً
فعّالة، **ويُستدلّ به** على المزارع.

**القاعدة:** الاسمُ لا يُفعِّل. تُفعِّل البصمةُ المعتمدة المطابقةُ للبايتات المثبَّتة،
ويُقاس ذلك في `/capabilities` و`/readyz` **وعند كلّ استدلال**. والبصمةُ تُثبِت
الهويّةَ لا الصلاحيّة: الرخصةُ والتصنيفُ والمعايرةُ الإقليميّة سجلٌّ منفصل.

وهذه الوحدةُ **بلا FastAPI** عمداً: منطقُها الصرف يُقاس في `tests_v9` (بوّابة الدمج)
حيث لا تُثبَّت `python-multipart`، وتستهلكه `main.py` كما هو.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping, Sequence

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

#: ذاكرةُ البصمات بمفتاح (المسار · mtime_ns · الحجم): `/readyz` يُستدعى كثيراً
#: والنموذجُ ١٨ ميغابايت — بلا ذاكرةٍ يُجزَّأ كاملاً في كلّ مِسبار.
_SHA_CACHE: dict[tuple[str, int, int], str] = {}


def expected_sha256(env_name: str) -> str | None:
    """البصمةُ المعتمدة من البيئة، أو ``None`` إن غابت أو لم تكن 64 خانةً ستّ‑عشريّة."""
    value = (os.getenv(env_name) or "").strip().lower()
    return value if _SHA256_HEX.match(value) else None


def sha256_of_file(path: str) -> str:
    stat = os.stat(path)
    key = (path, int(stat.st_mtime_ns), int(stat.st_size))
    cached = _SHA_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    for stale in [k for k in _SHA_CACHE if k[0] == path and k != key]:
        _SHA_CACHE.pop(stale, None)
    _SHA_CACHE[key] = value
    return value


def model_capability(
    *,
    path: str,
    sha_env_name: str,
    runtime_available: bool,
) -> dict[str, object]:
    """حكمُ التفعيل. الترتيبُ يسمّي أوّلَ شرطٍ ساقط — لا «غير فعّال» مبهمة."""
    exists = os.path.exists(path)
    expected = expected_sha256(sha_env_name)
    actual = sha256_of_file(path) if exists else None
    verified = bool(exists and expected is not None and actual == expected)
    active = bool(exists and verified and runtime_available)
    reason: str | None = None
    if not exists:
        reason = "model_file_missing"
    elif expected is None:
        reason = "model_sha256_missing_or_invalid"
    elif not verified:
        reason = "model_sha256_mismatch"
    elif not runtime_available:
        reason = "onnxruntime_missing"
    return {
        "active": active,
        "model_path": path,
        "model_file_present": exists,
        "onnxruntime_available": runtime_available,
        "sha256_env": sha_env_name,
        "expected_sha256": expected,
        "actual_sha256": actual,
        "sha256_verified": verified,
        "reason": reason,
    }


def high_confidence_alert(detections: Sequence[Mapping[str, object]]) -> str | None:
    """تنبيهُ الكشف — **ملاحظةٌ لا علاج.**

    كان النصُّ يختم بـ«الإجراء المقترح: <اسم مبيد>» من جدولٍ ثابت في الكاشف؛ حُذِف
    الجدولُ والسطر. القرارُ العلاجيّ لطبقة سياسةٍ وتشخيصٍ معتمد، لا لكاشف صور.
    """
    high = [d for d in detections if float(d.get("confidence", 0.0)) > 0.8]
    if not high:
        return None
    top = high[0]
    return (
        "🐛 **تنبيه آفة عالية الثقة!**\n\n"
        f"الآفة المكتشفة: **{top.get('arabic_name')}**\n"
        f"الثقة: {float(top.get('confidence', 0.0)):.0%}\n"
        f"الموقع في الصورة: {top.get('bbox')}\n\n"
        "هذه ملاحظةُ كشفٍ فقط؛ الإجراءُ الزراعيّ أو العلاجيّ يحتاج سياسةً وتشخيصاً معتمداً."
    )


def shape_yield_result(prediction: Mapping[str, object]) -> dict[str, object]:
    """حقولُ الغلّة كما يُخرِجها النموذجُ — **لا فاصلَ ثقةٍ مُصطنَع.**

    كان `confidence_interval` يُحسَب `×0.85` و`×1.15` على أيّ تنبّؤ ويُقرأ في الواجهة
    فاصلَ ثقة. الآن: يُنشَر فقط إن أنتجه النموذجُ أو معايرتُه، وإلّا `None` مع قيدٍ مسمّى.
    """
    limitations: list[str] = []
    interval = prediction.get("confidence_interval")
    shaped_interval: dict[str, float] | None = None
    if (
        isinstance(interval, Mapping)
        and interval.get("lower") is not None
        and interval.get("upper") is not None
    ):
        shaped_interval = {
            "lower": round(float(interval["lower"]), 2),
            "upper": round(float(interval["upper"]), 2),
        }
    else:
        limitations.append("yield_uncertainty_not_calibrated")
    biomass = prediction.get("biomass_proxy")
    plant_count = prediction.get("plant_count")
    return {
        "estimated_yield_kg_ha": round(float(prediction["yield_kg_ha"]), 2),
        "confidence_interval": shaped_interval,
        "biomass_proxy": None if biomass is None else round(float(biomass), 2),
        "plant_count_estimate": None if plant_count is None else int(plant_count),
        "limitations": limitations,
    }
