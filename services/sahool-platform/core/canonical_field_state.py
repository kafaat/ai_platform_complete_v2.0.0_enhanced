"""Canonical field-state contract shared by intelligence consumers.

This module validates, fingerprints and combines owner-produced state products.  It
never computes weather, water, soil or spectral facts and never accepts an
unversioned dictionary as canonical truth.

``operational_eligible`` answers exactly one question — *are the required products
present?* — and it is kept at that meaning because consumers already depend on it.
Presence is not fitness: a product that is present while its own owner marks it
``degraded`` still counts as available.  ``eligibility`` therefore sits beside it as
a per-action-level ladder (``discover`` · ``diagnose`` · ``propose`` · ``execute``),
each level carrying the reasons it is blocked.

The ladder judges **declarations, not facts**.  Owners know when their own reading
goes stale and say so in their product; recomputing that here would fork the owner's
logic into a second copy that drifts in silence.  And ``execute`` is not a higher
grade of ``propose`` but a different kind of permission: this state carries no
approval, no signature and no approver identity, so it reports that it cannot answer
rather than answering ``true`` from inputs that were never about authorization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "canonical_field_state.v1"

# ── الأهليّة بمستوى العمل ───────────────────────────────────────────────────
# ``CANONICAL-FIELD-STATE-ELIGIBILITY-IS-PRESENCE-ONLY-01``
#
# ``operational_eligible`` سؤالٌ واحد: «هل المنتَجات المطلوبة **موجودة**؟» وهو سؤال
# صحيح ولا يكفي وحده حكماً تشغيليّاً: منتَج موجود يُعلن عن نفسه أنّه ``degraded``
# يجعل الحالة «مؤهّلة» بينما مالكه يقول إنّها ليست صالحة. الحقل يبقى بمعناه تماماً —
# له مستهلكون قائمون، وتغيير معناه تحتهم أخطر من نقصه — ويُضاف بجانبه سُلَّم صريح.
#
# **القاعدة الحاكمة، وهي حدّ هذه الوحدة لا كسلٌ فيها:** المُجمِّع لا يحسب حقائق ولا
# يخترع عتبات حداثة. المالك وحده يعرف متى يصير رصده بائتاً، وهو يُعلن حكمه في
# منتَجه (``quality_status`` · ``operational_eligible`` · ``limitations``). فهذه
# الوحدة تحكم على **الإعلانات** لا على الوقائع؛ ولو حسبت عمراً بعتبة من عندها
# لأعادت إنتاج منطق المالك بنسخة ثانية تتباعد عنه صامتاً.
ELIGIBILITY_LEVELS = ("discover", "diagnose", "propose", "execute")

# مفردات الجودة **ليست موحَّدة بين المُلّاك** — مقيس لا مُقدَّر:
# `canonical_weather_state` يُخرِج validated/degraded/insufficient/invalid،
# و`canonical_water_state` يُخرِج verified/degraded. فلا يجوز افتراض مفردة واحدة.
# المقبول هنا اتّحاد المصطلحين الصحّيّين المعروفين؛ وأيّ مصطلح **غير معروف** يُعامَل
# «غير مُثبَت» لا «سليم» — لأنّ مفردة جديدة من مالك جديد يجب أن تُقرأ قراءة صريحة
# قبل أن تُمنَح ثقة، لا أن تمرّ لأنّها ليست في قائمة السيّئ.
HEALTHY_QUALITY_TERMS = frozenset({"validated", "verified"})


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _schema_of(value: dict[str, Any]) -> str | None:
    return value.get("schema_version") or value.get("schema")


def _require_product(
    name: str, value: dict[str, Any] | None, accepted_prefixes: tuple[str, ...]
) -> tuple[dict[str, Any] | None, str | None]:
    if value is None:
        return None, f"{name}_missing"
    if not isinstance(value, dict):
        return None, f"{name}_not_object"
    schema = _schema_of(value)
    if not isinstance(schema, str) or not schema.startswith(accepted_prefixes):
        return None, f"{name}_noncanonical_schema"
    return value, None


def _product_health(name: str, product: dict[str, Any]) -> list[str]:
    """أسباب امتناع منتَج **موجود** عن كونه صالحاً لتوصية — من إعلانه هو.

    ثلاثة إعلانات يقرأها المُجمِّع ولا يُنتِج أيّاً منها:
      • ``operational_eligible: False`` — المالك يقول صراحةً «لا يصلح تشغيليّاً».
      • ``quality_status`` خارج المصطلحات الصحّيّة المعروفة — بما فيه المجهول.
      • ``limitations`` غير فارغة — المالك سمّى حدّاً على منتَجه.

    غياب ``quality_status`` رأساً ليس سلامةً: منتَج لا يُصرّح بجودته لا يُمنَح ثقةً
    ضمنيّة، فيُسجَّل ``quality_undeclared``.
    """
    reasons: list[str] = []
    if product.get("operational_eligible") is False:
        reasons.append(f"{name}_owner_declares_not_operational")
    quality = product.get("quality_status")
    if quality is None:
        reasons.append(f"{name}_quality_undeclared")
    elif not isinstance(quality, str) or quality not in HEALTHY_QUALITY_TERMS:
        reasons.append(f"{name}_quality_{quality}")
    if product.get("limitations"):
        reasons.append(f"{name}_owner_declared_limitations")
    return reasons


def _eligibility_matrix(
    *,
    required: tuple[str, ...],
    accepted: dict[str, dict[str, Any] | None],
    missing_required: list[str],
) -> dict[str, dict[str, Any]]:
    """سُلَّم أهليّة رتيب: ما يمنع مستوى أدنى يمنع كلّ ما فوقه.

    الرتابة مقصودة وليست تفصيلاً: مصفوفة يسمح فيها ``execute`` بما يمنعه ``propose``
    ليست سُلَّماً بل أربعة أحكام مستقلّة يسهل أن تتناقض.
    """
    presence = [f"required_{name}_unavailable" for name in sorted(missing_required)]
    health: list[str] = []
    for name in sorted(required):
        product = accepted.get(name)
        if product is not None:
            health.extend(_product_health(name, product))

    # الاستكشاف يقرأ الموجود ويُسمّي الناقص — لا يُحجَب، وإلّا امتنعت رؤية سبب الحجب.
    matrix: dict[str, dict[str, Any]] = {
        "discover": {"allowed": True, "reasons": list(presence)},
        "diagnose": {"allowed": not presence, "reasons": list(presence)},
        "propose": {"allowed": not presence and not health, "reasons": [*presence, *health]},
    }
    # التنفيذ ليس درجةً أعلى من الاقتراح بل **نوع آخر من الإذن**: توصية جيّدة ليست
    # أمراً مأذوناً. وهذه الحالة لا تحمل إذناً ولا توقيعاً ولا هويّة مُوافِق، فالصادق
    # أن تُعلن أنّها لا تملك الجواب بدل أن تُجيب بـtrue من مُدخَلات لا تخصّ الإذن.
    matrix["execute"] = {
        "allowed": False,
        "reasons": [*presence, *health, "execution_authorization_not_carried_by_field_state"],
    }
    return matrix


@dataclass(frozen=True)
class CanonicalFieldState:
    schema_version: str
    field_id: str
    season_id: str | None
    as_of_time: str
    weather: dict[str, Any] | None
    water: dict[str, Any] | None
    soil: dict[str, Any] | None
    spectral: dict[str, Any] | None
    availability: dict[str, bool]
    limitations: list[str]
    evidence_digests: dict[str, str]
    state_digest: str
    operational_eligible: bool
    eligibility: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compose_canonical_field_state(
    *,
    field_id: str,
    season_id: str | None,
    as_of_time: str,
    weather: dict[str, Any] | None = None,
    water: dict[str, Any] | None = None,
    soil: dict[str, Any] | None = None,
    spectral: dict[str, Any] | None = None,
    required: tuple[str, ...] = ("weather", "water", "soil"),
) -> CanonicalFieldState:
    if not field_id or not as_of_time:
        raise ValueError("field_id and as_of_time are required")
    specs = {
        "weather": (weather, ("wx10/canonical-weather-state/", "canonical_weather_state")),
        "water": (water, ("canonical_water_state.",)),
        "soil": (soil, ("canonical_soil_state.", "soil-profile.")),
        "spectral": (spectral, ("canonical_spectral_state.", "validated-raster-product.")),
    }
    accepted: dict[str, dict[str, Any] | None] = {}
    limitations: list[str] = []
    availability: dict[str, bool] = {}
    evidence: dict[str, str] = {}
    for name, (value, prefixes) in specs.items():
        product, limitation = _require_product(name, value, prefixes)
        accepted[name] = product
        availability[name] = product is not None
        if limitation:
            limitations.append(limitation)
        elif product is not None:
            evidence[name] = _digest(product)
    missing_required = [name for name in required if not availability.get(name, False)]
    limitations.extend(f"required_{name}_unavailable" for name in missing_required)
    body = {
        "schema_version": SCHEMA_VERSION,
        "field_id": field_id,
        "season_id": season_id,
        "as_of_time": as_of_time,
        **accepted,
        "availability": availability,
        "limitations": list(dict.fromkeys(limitations)),
        "evidence_digests": evidence,
    }
    digest = _digest(body)
    # `eligibility` تبقى **خارج** الجسم المُبصَم، تماماً كـ`operational_eligible`
    # و`state_digest`. البصمة تُعرِّف **المُدخَلات** لا الحكم عليها؛ فلو دخل الحكم فيها
    # لتغيّرت بصمة كلّ حالة قائمة بلا تغيّر مُدخَل واحد، وانكسر كلّ ما رُبِط ببصمة
    # مُخزَّنة (approval pinned to digest) لسبب تحريريّ لا موضوعيّ.
    return CanonicalFieldState(
        **body,
        state_digest=digest,
        operational_eligible=not missing_required,
        eligibility=_eligibility_matrix(
            required=required, accepted=accepted, missing_required=missing_required
        ),
    )
