"""AC-COMPOSER (الشريحة 1) — المُجمِّع الخادميّ الذرّيّ للسياق الزراعيّ.

يملأ الفجوة **P0-3**: نصف «الجمع» المفقود من مُركِّب السياق. اليوم يُثبِّت decision-service
عقود السياق (``compose_agronomic_context`` — PIT + idempotency + persistence) لكنّه يستقبل
``payload`` **مُركَّباً خارجيّاً** (مدخلات عميل عبر crop_twin). هذه الوحدة تبني ذلك الـpayload
**خادميّاً** من منتجات قانونيّة مقروءة من ملّاكها، فيصبح السياق سلطةً خادميّةً لا ادّعاء عميل.

نقيّ بالكامل (بلا شبكة/إطار): يأخذ منتجات قانونيّة مُجلَبة مسبقاً (نمط ``_resolve_server_spectral``
في crop_twin) ويُركِّبها في عقد ``ContextComposeIn`` (AC-1) بحقول نَسَب كاملة لكلّ ميزة، ثمّ
يُعيد الـpayload الجاهز للتمرير إلى ``compose_agronomic_context`` القائم (المُثبِّت + بوّابة PIT).

صدق صارم (يطابق فلسفة سهول ونقاط التدقيق):
  * **لا اختلاق (P1-1/P2):** مصدر غائب/غير مؤهّل ⇒ مجموعة ``missing`` بلا قيمة (لا رقم افتراضيّ).
  * **منع التسرّب الزمنيّ (P0-5/PIT):** ميزة ``available_at > decision_cutoff`` تُستبعَد وتُسجَّل
    قيداً ``future_leakage_excluded`` (بوّابة PIT في decision-service تبقى السلطة النهائيّة).
  * **تماسك زمنيّ (P1-4):** تجاوز الانحراف الأقصى بين المشاهدات ⇒ قيد ``inconsistent_inputs``.
  * **نَسَب لكلّ ميزة (P0-2):** observed_at/available_at/source_service/quality_status/... إلزاميّة.
  * **حتميّة:** ``content_digest`` و``idempotency_key`` من محتوى مُرتَّب فقط (لا وقت جدار/عشوائيّة)
    ⇒ إعادة تشغيل تُعيد استخدام نفس اللقطة.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any

# المجموعات السبع التي يجب أن يحملها العقد (AC-1 contracts.CONTEXT_GROUPS — مصدر واحد للحقيقة،
# مُكرَّر هنا كثابت حدوديّ لأنّ المنصّة لا تستورد داخليّات decision-service عبر الحدّ).
CONTEXT_GROUPS = ("crop", "soil", "irrigation", "weather", "climate", "terrain", "operations")

# حالات الجودة المقبولة (AC-1 contracts.QUALITY_STATES) مُرتَّبة من الأفضل للأسوأ.
_QUALITY_ORDER = ("verified", "accepted_with_warning", "stale", "missing", "rejected")
_QUALITY_RANK = {q: i for i, q in enumerate(_QUALITY_ORDER)}

# أقصى انحراف زمنيّ مقبول بين مشاهدات الميزات قبل وسم «مدخلات غير متماسكة» (P1-4).
DEFAULT_MAX_TEMPORAL_SKEW_HOURS = 48.0

COMPOSER_VERSION = "ac-compose-1"


def agronomic_context_compose_enabled() -> bool:
    """راية تفعيل المُجمِّع الخادميّ (افتراض معطَّل — سلوك التشغيل بلا تغيير حتى يُفعِّلها
    المشغّل، نمط ``COMPOSE_SERVER_AUTHORITATIVE_SPECTRAL_ENABLED``)."""
    return os.getenv("AGRONOMIC_CONTEXT_COMPOSE_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _stable_hash(obj: Any) -> str:
    """sha256 على JSON مُرتَّب المفاتيح (نمط ``_stable_hash`` في decision-service:459)."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _worst_quality(statuses: list[str]) -> str:
    """أسوأ حالة جودة حاضرة (الأدنى رتبةً يفوز)؛ لا حالات ⇒ ``missing``."""
    ranked = [s for s in statuses if s in _QUALITY_RANK]
    if not ranked:
        return "missing"
    return max(ranked, key=lambda s: _QUALITY_RANK[s])


def assemble_agronomic_context(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    as_of_time: datetime,
    decision_cutoff_time: datetime,
    features: list[dict[str, Any]],
    empty_group_reasons: dict[str, str] | None = None,
    history: dict[str, Any] | None = None,
    max_temporal_skew_hours: float = DEFAULT_MAX_TEMPORAL_SKEW_HOURS,
) -> dict[str, Any]:
    """يُركِّب لقطة سياق زراعيّ ذرّيّة من منتجات قانونيّة مقروءة خادميّاً.

    ``features``: قائمة منتجات قانونيّة، كلٌّ dict يحمل على الأقلّ ``group`` و``name`` و``value``
    و``source_service`` و``observed_at``/``available_at`` (datetime) و``quality_status``. القيم
    غير المقروءة تُمرَّر ببساطة **غائبة** — لا تُمرَّر بقيمة مُختلَقة.

    يعيد ``{payload, quality_matrix, limitations, temporal_skew_hours, content_digest}`` حيث
    ``payload`` جاهز حرفيّاً للتمرير إلى ``compose_agronomic_context`` (يجتاز بوّابة PIT إن لم
    يُقدَّم مدخل مُتسرِّب). لا يكتب شيئاً — تركيب نقيّ.
    """
    empty_group_reasons = empty_group_reasons or {}
    limitations: dict[str, Any] = {}

    # ── (1) تصفية PIT/النَسَب: استبعاد المُتسرِّب زمنيّاً والمُشوَّه، مع تسجيل السبب ──
    admissible: list[dict[str, Any]] = []
    future_leaked: list[str] = []
    invalid_provenance: list[str] = []
    for f in features:
        obs = f.get("observed_at")
        avail = f.get("available_at")
        if not isinstance(obs, datetime) or not isinstance(avail, datetime):
            invalid_provenance.append(str(f.get("name", "?")))
            continue
        if avail > decision_cutoff_time:  # تسرّب مستقبليّ ⇒ يُستبعَد (السبب الأكثر أهمّية)
            future_leaked.append(str(f.get("name", "?")))
            continue
        if obs > avail:  # نَسَب مُشوَّه (رُصِد بعد أن أُتيح) ⇒ يُستبعَد ولا يُسكَت عنه
            invalid_provenance.append(str(f.get("name", "?")))
            continue
        admissible.append(f)
    if future_leaked:
        limitations["future_leakage_excluded"] = sorted(future_leaked)
    if invalid_provenance:
        limitations["invalid_provenance_excluded"] = sorted(invalid_provenance)

    # ── (2) بناء ميزات العقد (نَسَب كامل لكلّ ميزة — P0-2) ──
    typed_features: list[dict[str, Any]] = []
    for f in admissible:
        typed_features.append(
            {
                "name": str(f["name"]),
                "value": f.get("value"),
                "unit": f.get("unit"),
                "source_service": str(f["source_service"]),
                "source_snapshot_id": f.get("source_snapshot_id"),
                "observed_at": _iso(f["observed_at"]),
                "available_at": _iso(f["available_at"]),
                "quality_status": f.get("quality_status", "verified"),
                "formula_version": f.get("formula_version"),
                "spatial_scope": f.get("spatial_scope"),
                "temporal_scope": f.get("temporal_scope"),
            }
        )
    typed_features.sort(key=lambda r: (r["name"], r["source_service"]))

    # ── (3) جودة كلّ مجموعة + المجموعات الغائبة (لا اختلاق) ──
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in CONTEXT_GROUPS}
    for f in admissible:
        g = f.get("group")
        if g in by_group:
            by_group[g].append(f)
    quality_matrix: dict[str, dict[str, Any]] = {}
    context: dict[str, Any] = {}
    missing_groups: list[str] = []
    for g in CONTEXT_GROUPS:
        members = by_group[g]
        if members:
            q = _worst_quality([str(m.get("quality_status", "verified")) for m in members])
            quality_matrix[g] = {"quality": q, "feature_count": len(members)}
            context[g] = {"quality": q, "feature_count": len(members)}
        else:
            reason = empty_group_reasons.get(g, "no_qualified_product")
            quality_matrix[g] = {"quality": "missing", "feature_count": 0, "reason": reason}
            context[g] = {"quality": "missing", "reason": reason}
            missing_groups.append(g)
    if missing_groups:
        limitations["missing_groups"] = missing_groups

    # ── (4) تماسك زمنيّ بين المشاهدات المؤهّلة (P1-4) ──
    temporal_skew_hours = 0.0
    obs_times = [f["observed_at"] for f in admissible]
    if len(obs_times) >= 2:
        temporal_skew_hours = (max(obs_times) - min(obs_times)).total_seconds() / 3600.0
        if temporal_skew_hours > max_temporal_skew_hours:
            limitations["inconsistent_inputs"] = {
                "temporal_skew_hours": round(temporal_skew_hours, 3),
                "max_allowed_hours": max_temporal_skew_hours,
            }

    # ── (5) نافذة التاريخ (تجتاز بوّابة PIT: غير فارغة، لا تتجاوز as_of) ──
    if history is not None:
        historical = history
    else:
        historical = {
            "history_from": _iso(as_of_time - timedelta(days=1)),
            "history_to": _iso(as_of_time),
            "manifest_version": "ac-1",
            "history": {},
        }

    # ── (6) مفتاح idempotency حتميّ من المحتوى (لا وقت جدار) ──
    feature_digest = _stable_hash(typed_features)
    idempotency_key = (
        "acx_"
        + _stable_hash(
            {
                "tenant": tenant_id,
                "field": field_id,
                "season": season_id,
                "as_of": _iso(as_of_time),
                "cutoff": _iso(decision_cutoff_time),
                "features": feature_digest,
            }
        )[:32]
    )

    payload: dict[str, Any] = {
        "field_id": field_id,
        "season_id": season_id,
        "as_of_time": _iso(as_of_time),
        "decision_cutoff_time": _iso(decision_cutoff_time),
        "schema_version": "ac-1",
        "composer_version": COMPOSER_VERSION,
        "context": context,
        "historical": historical,
        "features": typed_features,
        "idempotency_key": idempotency_key,
    }

    return {
        "payload": payload,
        "quality_matrix": quality_matrix,
        "limitations": limitations,
        "temporal_skew_hours": round(temporal_skew_hours, 3),
        "content_digest": _stable_hash(payload),
    }
