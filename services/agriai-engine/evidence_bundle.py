"""SAHOOL agriai-engine — evidence_bundle.py (وحدة صرفة، بلا FastAPI).

تجميع بنود أدلّة مُصنّفة (source, kind, value, unit, observed_at, strength) في حزمة،
ثمّ إخراجها إلى JSON قانونيّ (canonical: مفاتيح مرتّبة، فواصل ثابتة، أرقام عائمة مُطبّعة)
وحساب بصمة محتوى مستقرّة (sha256 لبايتات القانون).

المبدأ: نفس المدخلات (بغضّ النظر عن ترتيب المفاتيح) ⇒ بايتات وبصمة متطابقة.

هرميّة الأدلّة (مرآة services/ai_agronomist/decision_contracts.py) — الأقوى أوّلاً:
    Lab > IoT > Weather > Satellite > RAG/KG
لا نُلفّق: القيمة المجهولة تبقى None، ولا نمنح ثقة لا نراها (fail-closed).
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Any

# دقّة تطبيع الأرقام العائمة: تُثبّت البايتات عبر التشغيلات (تتجنّب 0.1+0.2).
FLOAT_NDIGITS = 10


class EvidenceStrength(str, Enum):
    """قوّة الدليل حسب المصدر (مرآة decision_contracts.EvidenceStrength)."""

    LAB = "lab"
    IOT = "iot"
    WEATHER = "weather"
    SATELLITE = "satellite"
    RAG = "rag"
    KG = "kg"


# أوزان الهرميّة — Lab الأعلى، RAG/KG لا يهيمنان على الأدلّة الحاكمة.
EVIDENCE_WEIGHTS: dict[EvidenceStrength, float] = {
    EvidenceStrength.LAB: 1.00,
    EvidenceStrength.IOT: 0.90,
    EvidenceStrength.WEATHER: 0.85,
    EvidenceStrength.SATELLITE: 0.60,
    EvidenceStrength.RAG: 0.25,
    EvidenceStrength.KG: 0.20,
}


def _coerce_strength(value: Any) -> EvidenceStrength:
    """يحوّل نصّاً/عضو Enum إلى EvidenceStrength — يفشل بوضوح على المجهول."""
    if isinstance(value, EvidenceStrength):
        return value
    try:
        return EvidenceStrength(str(value).lower())
    except ValueError as exc:  # fail-closed: لا نُخمّن قوّة دليل لا نعرفها
        raise ValueError(f"قوّة دليل غير معروفة: {value!r}") from exc


def _normalize(obj: Any) -> Any:
    """تطبيع متكرّر لبنية شبيهة بـJSON لضمان بايتات قانونيّة مستقرّة.

    - float ⇒ يُدوّر إلى FLOAT_NDIGITS ويُطبّع 0.0- إلى 0.0 (يرفض inf/nan).
    - Enum ⇒ قيمته.
    - dict ⇒ مفاتيح نصّيّة (الترتيب يُحسم لاحقاً بـsort_keys).
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("قيمة عائمة غير منتهية (inf/nan) غير مسموحة في الأدلّة")
        out = round(obj, FLOAT_NDIGITS)
        return 0.0 if out == 0.0 else out
    if isinstance(obj, int):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    return obj


def make_evidence_item(
    *,
    source: str,
    kind: str,
    value: Any,
    unit: str | None = None,
    observed_at: str | None = None,
    strength: Any,
) -> dict[str, Any]:
    """يبني بند دليل مُصنّفاً واحداً (dict قانونيّ الشكل).

    observed_at يُحقن كنصّ ISO من المُستدعي — لا ساعة جدار هنا (لضمان إعادة الإنتاج).
    """
    st = _coerce_strength(strength)
    return {
        "source": str(source),
        "kind": str(kind),
        "value": value,
        "unit": str(unit) if unit is not None else None,
        "observed_at": str(observed_at) if observed_at is not None else None,
        "strength": st.value,
        "weight": EVIDENCE_WEIGHTS[st],
    }


def assemble_bundle(
    items: list[dict[str, Any]], *, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """يجمّع بنود الأدلّة في حزمة مُطبّعة.

    البنود تُرتَّب داخليّاً ترتيباً حتميّاً (حسب قوّتها ثمّ محتواها القانونيّ) كي لا
    يؤثّر ترتيب الإدخال على البايتات. context اختياريّ (وسم/بيانات وصفيّة).
    """
    normalized_items = [_normalize(it) for it in items]
    # ترتيب حتميّ مستقلّ عن ترتيب الإدخال: مفتاح = تمثيل قانونيّ للبند.
    normalized_items.sort(key=lambda it: json.dumps(it, sort_keys=True, separators=(",", ":")))
    bundle = {
        "schema": "sahool.agriai.evidence_bundle/1",
        "items": normalized_items,
        "context": _normalize(context) if context else {},
    }
    return bundle


def canonical_json(obj: Any) -> str:
    """يُنتج نصّ JSON قانونيّاً: مفاتيح مرتّبة، فواصل ثابتة، أرقام مُطبّعة."""
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """بايتات UTF-8 للتمثيل القانونيّ."""
    return canonical_json(obj).encode("utf-8")


def content_hash(obj: Any) -> str:
    """sha256 (hex) للبايتات القانونيّة — بصمة محتوى مستقرّة."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def bundle_hash(bundle: dict[str, Any]) -> str:
    """بصمة محتوى الحزمة (اختصار مقروء)."""
    return content_hash(bundle)


def compose_confidence(items: list[dict[str, Any]]) -> float:
    """مُركّب ثقة موزون بهرميّة الأدلّة (مرآة decision_contracts.compose_confidence).

    كلّ بند قد يحمل ``confidence`` في [0,1]؛ في غيابه نفترض 1.0 (وجود قياس مؤكّد).
    RAG/KG لا يهيمنان: وزنهما منخفض أصلاً. يُرجع 0.0 لحزمة فارغة (fail-closed).
    """
    if not items:
        return 0.0
    total_weight = 0.0
    weighted = 0.0
    for it in items:
        st = _coerce_strength(it.get("strength"))
        weight = EVIDENCE_WEIGHTS[st]
        conf = it.get("confidence", 1.0)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        weighted += max(0.0, min(1.0, conf)) * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return round(weighted / total_weight, 4)
