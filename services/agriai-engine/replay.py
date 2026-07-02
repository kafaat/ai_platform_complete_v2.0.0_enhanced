"""SAHOOL agriai-engine — replay.py (وحدة صرفة، بلا FastAPI).

حتميّة إعادة التشغيل: من (طلب توصية + حزمة أدلّة) نُنتج مظروف نتيجة حتميّاً، مع
``replay_hash`` = hash(canonical(inputs) + engine_version). لا ساعة جدار ولا عشوائيّة
في المحتوى المُبصَم — أيّ طوابع زمنيّة تُحقن من المُستدعي.

verify_replay(inputs, prior_hash) ⇒ True فقط إذا طابقت إعادة الحساب البصمة السابقة.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

# مجلّد الخدمة في مسار الاستيراد كي تعمل الوحدة قائمةً بذاتها (تحميل عبر spec في الاختبارات).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from evidence_bundle import canonical_bytes, canonical_json  # noqa: E402

# نسخة المحرّك تدخل في المحتوى المُبصَم: ترقية المنطق ⇒ بصمات مختلفة عمداً.
ENGINE_VERSION = "agriai-engine/9.1.0"


def compute_replay_hash(inputs: Any, *, engine_version: str = ENGINE_VERSION) -> str:
    """sha256 (hex) لـ canonical(inputs) مُلحَقاً بنسخة المحرّك.

    حتميّ ومستقلّ عن ترتيب المفاتيح (canonical يُرتّبها). خالٍ من الطوابع الحيّة.
    """
    hasher = hashlib.sha256()
    hasher.update(canonical_bytes(inputs))
    hasher.update(b"\x00")  # فاصل لا يظهر في JSON canonical
    hasher.update(str(engine_version).encode("utf-8"))
    return hasher.hexdigest()


def build_envelope(
    inputs: dict[str, Any],
    result: dict[str, Any],
    *,
    engine_version: str = ENGINE_VERSION,
    evidence_hash: str | None = None,
) -> dict[str, Any]:
    """يبني مظروف نتيجة حتميّاً حول (inputs, result).

    ``replay_hash`` يُشتقّ من inputs فقط + نسخة المحرّك — لا من result — كي تتمكّن
    ``verify_replay`` من التحقّق بإعادة الحساب من المدخلات وحدها.
    """
    envelope = {
        "engine_version": str(engine_version),
        "inputs": inputs,
        "result": result,
        "replay_hash": compute_replay_hash(inputs, engine_version=engine_version),
    }
    if evidence_hash is not None:
        envelope["evidence_hash"] = str(evidence_hash)
    return envelope


def verify_replay(inputs: Any, prior_hash: str, *, engine_version: str = ENGINE_VERSION) -> bool:
    """True فقط إذا طابقت إعادة حساب البصمة من ``inputs`` البصمةَ السابقة."""
    if not prior_hash:
        return False
    return compute_replay_hash(inputs, engine_version=engine_version) == str(prior_hash)


def canonicalize(inputs: Any) -> str:
    """كشف مساعد: التمثيل القانونيّ للمدخلات (للتدقيق/التصحيح)."""
    return canonical_json(inputs)
