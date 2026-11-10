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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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


# ── AC-1/AC-6 lineage for one governed producer: the field irrigation candidate ──────────
# EX-WATER-01 (path B). decision-service refuses a governed decision without its agronomic
# lineage when AC-1 is enforced (always in production). The field irrigation route sent none of
# it, so a production submission could only end in an unexplained 422 (registry
# DECISION-PROVENANCE-AND-SOD-01). The pure half lives here, next to the assembler it feeds;
# the network half (compose + vegetation read) is ``decision_service_client.irrigation_candidate_lineage``.

REQUIRED_LINEAGE_FIELDS = (
    "season_id",
    "crop_id",
    "cultivar_id",
    "agronomic_context_snapshot_id",
    "field_historical_context_snapshot_id",
    "feature_manifest_id",
    "feature_manifest_hash",
    "vegetation_snapshot_id",
)
_CONTEXT_REFERENCE_FIELDS = REQUIRED_LINEAGE_FIELDS[3:7]
BLOCKED_STATE = "blocked_agronomic_context_incomplete"


def agronomic_context_required() -> bool:
    """Same rule as decision-service ``agronomic_context_required``: explicit flag anywhere,
    always in production — production cannot silently skip AC-1."""
    explicit = os.getenv("DECISION_REQUIRE_AGRONOMIC_CONTEXT", "").strip().lower()
    environment = os.getenv("ENVIRONMENT", os.getenv("SAHOOL_ENV", "development")).strip().lower()
    return explicit in {"1", "true", "yes", "on"} or environment in {"production", "prod"}


def _day_start(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value)[:10] if value is not None else ""
    try:
        return datetime.fromisoformat(text).replace(tzinfo=UTC) if text else None
    except ValueError:
        return None


def irrigation_candidate_features(
    *,
    cutoff: datetime,
    field_id: str,
    crop_id: str | None,
    cultivar_id: str | None,
    days_since_sowing: Any,
    inputs: dict[str, Any],
    ledger_date: Any,
    weather: dict[str, Any],
    et0: dict[str, Any],
) -> list[dict[str, Any]]:
    """The route's own inputs as assembler features (group + full provenance).

    A value the route does not hold is simply absent — its group is then reported missing by
    ``assemble_agronomic_context``; nothing is filled in.
    """
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must carry a timezone")
    now = {"observed_at": cutoff, "available_at": cutoff}
    feats: list[dict[str, Any]] = []
    if crop_id:
        feats.append(
            {
                "group": "crop",
                "name": "crop_id",
                "value": crop_id,
                "source_service": "sahool-platform.crop_cards",
                "quality_status": "verified",
                **now,
            }
        )
    if cultivar_id:
        feats.append(
            {
                "group": "crop",
                "name": "cultivar_id",
                "value": cultivar_id,
                "source_service": "sahool-platform.seasons",
                "quality_status": "verified",
                **now,
            }
        )
    if days_since_sowing is not None:
        feats.append(
            {
                "group": "crop",
                "name": "days_since_sowing",
                "value": days_since_sowing,
                "unit": "d",
                "source_service": "sahool-platform.seasons",
                "quality_status": "verified",
                **now,
            }
        )
    texture = (inputs.get("soil_provenance") or {}).get("texture") or {}
    sampled = (
        _day_start(texture.get("sampled_on")) if texture.get("source") == "lab_measured" else None
    )
    if inputs.get("taw_mm") is not None:
        feats.append(
            {
                "group": "soil",
                "name": "total_available_water_mm",
                "value": inputs["taw_mm"],
                "unit": "mm",
                "source_service": "sahool-platform",
                "source_snapshot_id": f"soil_lab_test:{texture.get('sampled_on')}"
                if sampled
                else None,
                "observed_at": sampled or cutoff,
                "available_at": cutoff,
                "quality_status": "verified" if sampled else "accepted_with_warning",
                "formula_version": f"soil_water_params:{inputs.get('taw_source')}",
            }
        )
    age = inputs.get("ledger_age_hours")
    if inputs.get("depletion_mm") is not None and age is not None:
        updated = cutoff - timedelta(hours=max(float(age), 0.0))
        feats.append(
            {
                "group": "irrigation",
                "name": "root_zone_depletion_mm",
                "value": inputs["depletion_mm"],
                "unit": "mm",
                "source_service": "sahool-platform",
                "source_snapshot_id": f"water_ledger:{field_id}:{ledger_date}",
                "observed_at": updated,
                "available_at": updated,
                # A derived daily balance, never a measurement.
                "quality_status": "accepted_with_warning",
                "formula_version": "water_ledger.daily_balance",
                "temporal_scope": f"ledger_date:{ledger_date}",
            }
        )
    if et0.get("et0_mm") is not None:
        valid = weather.get("valid_time")
        feats.append(
            {
                "group": "weather",
                "name": "et0_mm",
                "value": et0["et0_mm"],
                "unit": "mm/day",
                "source_service": "weather-service",
                "source_snapshot_id": et0.get("weather_snapshot_id"),
                "quality_status": "verified"
                if et0.get("quality_status") == "validated"
                else "accepted_with_warning",
                "formula_version": et0.get("formula_version"),
                "temporal_scope": f"valid_time:{valid}" if valid else None,
                **now,
            }
        )
    return feats


def irrigation_candidate_compose_payload(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str | None,
    cutoff: datetime,
    features: list[dict[str, Any]],
    inputs: dict[str, Any],
    ledger_date: Any,
) -> dict[str, Any]:
    """``ContextComposeIn`` body for the irrigation candidate, via the existing assembler."""
    history_from = _day_start(ledger_date) or (cutoff - timedelta(days=1))
    if history_from > cutoff:
        history_from = cutoff - timedelta(days=1)
    unheld = "not composed by the field irrigation route"
    return assemble_agronomic_context(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        as_of_time=cutoff,
        decision_cutoff_time=cutoff,
        features=features,
        empty_group_reasons={"climate": unheld, "terrain": unheld, "operations": unheld},
        history={
            "history_from": _iso(history_from),
            "history_to": _iso(cutoff),
            "manifest_version": "irrigation-route-history.v1",
            "history": {
                "water_ledger_latest": {
                    "ledger_date": str(ledger_date) if ledger_date is not None else None,
                    "depletion_mm": inputs.get("depletion_mm"),
                    "applied_water_status": inputs.get("applied_water_status"),
                }
            },
        },
    )["payload"]


@dataclass(frozen=True)
class Ac1Binding:
    """What could be bound, what is missing, and whether the gap blocks submission."""

    record_fields: dict[str, str]
    missing: tuple[str, ...]
    required: bool
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.required and bool(self.missing)

    def blocked_state(self) -> tuple[str, str]:
        return BLOCKED_STATE, "agronomic_context_incomplete — لم يُقدَّم: " + ", ".join(self.missing)

    def refusal(self, status_code: int, detail: Any) -> tuple[str, str] | None:
        """decision-service's own AC-1 refusal (it enforces where this process did not expect
        it) as the same named block — never a server error."""
        if (
            status_code == 422
            and isinstance(detail, dict)
            and detail.get("code") == "agronomic_context_required"
        ):
            return BLOCKED_STATE, "agronomic_context_incomplete — لم يُقدَّم: " + ", ".join(
                detail.get("missing") or []
            )
        return None

    def report(self) -> dict[str, Any]:
        if not self.missing:
            status = "bound"
        elif self.blocked:
            status = "blocked"
        else:
            status = "partially_bound" if self.record_fields.keys() - {"season_id"} else "unbound"
        return {
            "status": status,
            "required": self.required,
            "missing": list(self.missing),
            "bound_fields": sorted(self.record_fields),
            "detail": self.detail,
        }


def lineage_binding(
    *,
    season_id: str | None,
    crop_id: str | None,
    cultivar_id: str | None,
    context: dict[str, Any] | None,
    vegetation: dict[str, Any] | None,
    required: bool,
    detail: dict[str, Any],
) -> Ac1Binding:
    """Decide what may be bound. The four context references go all-or-none (decision-service
    rejects a partial binding); vegetation only with an executable quality gate."""
    fields: dict[str, str] = {}
    if season_id:
        fields["season_id"] = season_id
    if crop_id:
        fields["crop_id"] = crop_id
    else:
        detail.setdefault("crop_id", "crop not resolved to a crop card")
    if cultivar_id and str(cultivar_id).strip():
        fields["cultivar_id"] = str(cultivar_id).strip()
    else:
        detail.setdefault("cultivar_id", "season has no cultivar")
    if context is not None:
        ids = {
            "agronomic_context_snapshot_id": context.get("snapshot_id"),
            "field_historical_context_snapshot_id": context.get("historical_snapshot_id"),
            "feature_manifest_id": context.get("feature_manifest_id"),
            "feature_manifest_hash": context.get("feature_manifest_hash"),
        }
        if all(ids.values()) and context.get("persisted") is True:
            fields.update({k: str(v) for k, v in ids.items()})
        else:
            detail.setdefault("context", "composer did not confirm a persisted, complete context")
    if vegetation is not None:
        gate = (
            vegetation.get("quality_gate")
            if isinstance(vegetation.get("quality_gate"), dict)
            else {}
        )
        if vegetation.get("snapshot_id") and gate.get("executable") is True:
            fields["vegetation_snapshot_id"] = str(vegetation["snapshot_id"])
        else:
            detail.setdefault(
                "vegetation",
                {
                    "snapshot_id": vegetation.get("snapshot_id"),
                    "reason": "quality gate not executable",
                    "gate_reasons": gate.get("reasons"),
                },
            )
    missing = tuple(k for k in REQUIRED_LINEAGE_FIELDS if k not in fields)
    return Ac1Binding(record_fields=fields, missing=missing, required=required, detail=detail)
