"""الأهليّة **مصنوعٌ مشتقّ** لا حقلٌ في اللقطة — `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`.

**القيد الذي يجعل هذا قراراً معماريّاً لا تفصيلاً تنفيذيّاً:** اللقطة **معنونة
بمحتواها**. ‏`main.py` يقولها صراحةً («content-addressed by snapshot_hash — the hash IS
the idempotency key»)، و`persistence.py` يُلغي التكرار على `(tenant_id, snapshot_hash)`،
والهجرة ٠١٩ تحمل `UNIQUE(tenant_id, snapshot_hash)` ومُشغِّلاً يمنع `UPDATE`/`DELETE`.

فإضافة حقل أهليّة **داخل جسم اللقطة** تُغيّر كلّ `snapshot_hash` قائم ⇒ تكسر إعادة
التشغيل ونَسَب الأدلّة. ولذلك:

  **اللقطة تبقى حقائق مرصودة ثابتة، والأهليّة كيانٌ مشتقّ مفتاحه**
  ``(snapshot_digest, policy_version)`` **وخارج الهاش تماماً.**

وهذا يشتري خاصّيّتين لا تُشترى بحقلٍ داخل اللقطة:

  ① **إعادة تقييم لقطة قديمة تحت سياسة جديدة** بلا لمس اللقطة ولا تاريخها.
  ② **والتقييم حتميّ:** نفس اللقطة ونفس السياسة ونفس `as_of` ⇒ النتيجة والبصمة
     نفساهما. البصمة تُحسَب على المُدخَلات والنتيجة، و`assessed_at` **مُستبعَد منها
     عمداً** — ساعةُ الحائط تجعل «الحتميّة» ادّعاءً لا خاصّيّة.

**السؤالان اللذان كانا في قيمة منطقيّة واحدة، مفصولان الآن:**

* `decision_eligible` (‏`generate_indicator_artifacts.py`) يبقى كما هو: **حقيقة عن
  المؤشّر** — «مُنفَّذ ومصدره حقيقيّ؟». نقطة توافق للخلف، لا تُوسَّع ولا تُمَسّ.
* وهذا الملفّ يجيب الثاني: **«هل يجوز لهذه اللقطة أن تقود هذه المرحلة الآن؟»** — وهو
  سياسةٌ تتغيّر بتغيّر المحصول والمرحلة وجودة المشهد، ولها **نسخة**.

**والمراحل أربع لا واحدة** (`discover` · `diagnose` · `propose` · `execute`): لقطةٌ
تكفي للاستكشاف قد لا تكفي للتنفيذ، وطيُّ ذلك في «صالحة/غير صالحة» هو نفسه الخلط الذي
أوجب الفجوة.

**الأسباب قابلة للآلة لا نصّاً حرّاً:** رمزٌ ثابت + الموضوع + المقيس + الحدّ. لأنّ
سبباً بشريّاً وحده لا يُبنى عليه مستهلِك، ونصّاً حرّاً يتغيّر بالصياغة فيكسر المقارنة.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

CONTRACT_VERSION = "eligibility-assessment.v1"

#: المراحل مرتّبة من الأقلّ خطراً إلى الأكثر. الترتيب جزء من العقد: مرحلةٌ مرفوضة
#: تُسقِط كلّ ما بعدها، فلا تُقترَح خطّة على لقطةٍ لا تكفي للتشخيص.
STAGES: tuple[str, ...] = ("discover", "diagnose", "propose", "execute")


@dataclass(frozen=True)
class Policy:
    """سياسة أهليّة **مُعرَّفة في الكود ولها نسخة** — تُبصَم فتُقارَن.

    ليست صفّاً في `decision_policies` (ذاك جدول تفويض لكلّ مستأجِر). هذه قواعد
    اشتقاق تُطبَّق على حقائق اللقطة، ونسختُها جزء من مفتاح التقييم.
    """

    version: str
    max_weather_age_h: dict[str, float]
    max_soil_age_h: dict[str, float]
    require_spectral: tuple[str, ...]
    min_valid_pixel_pct: dict[str, float]

    def digest(self) -> str:
        """بصمة السياسة من **تعريفها** لا من اسمها — تغييرُ عتبةٍ بلا رفع النسخة يظهر."""
        return _digest(
            {
                "version": self.version,
                "max_weather_age_h": self.max_weather_age_h,
                "max_soil_age_h": self.max_soil_age_h,
                "require_spectral": list(self.require_spectral),
                "min_valid_pixel_pct": self.min_valid_pixel_pct,
            }
        )


#: v1 — العتبات التي كانت مضمرة في `decision_eligible` وفي `min_valid_pixel_pct: 60.0`
#: من `generate_indicator_artifacts.py`، مُصرَّحاً بها لأوّل مرّة ومنسوبةً إلى مرحلة.
POLICY_V1 = Policy(
    version="v1",
    max_weather_age_h={"discover": 168.0, "diagnose": 72.0, "propose": 48.0, "execute": 24.0},
    max_soil_age_h={"discover": 8760.0, "diagnose": 4380.0, "propose": 2190.0, "execute": 720.0},
    require_spectral=("ndvi",),
    min_valid_pixel_pct={
        "discover": 30.0,
        "diagnose": 60.0,
        "propose": 60.0,
        "execute": 80.0,
    },
)

#: v2 — أشدّ على التنفيذ ويشترط `ndmi` معه. موجودةٌ ليُثبَت أنّ **إعادة تقييم لقطة
#: قديمة تحت سياسة جديدة** تعمل بلا لمس اللقطة، لا لأنّها قرار منتَج مُتَّخَذ.
POLICY_V2 = Policy(
    version="v2",
    max_weather_age_h={"discover": 168.0, "diagnose": 48.0, "propose": 24.0, "execute": 6.0},
    max_soil_age_h={"discover": 8760.0, "diagnose": 4380.0, "propose": 2190.0, "execute": 360.0},
    require_spectral=("ndvi", "ndmi"),
    min_valid_pixel_pct={
        "discover": 30.0,
        "diagnose": 60.0,
        "propose": 70.0,
        "execute": 90.0,
    },
)

POLICIES: dict[str, Policy] = {POLICY_V1.version: POLICY_V1, POLICY_V2.version: POLICY_V2}


class UnknownPolicyVersion(ValueError):
    """نسخة سياسة غير معروفة — **لا يُفترَض بديل**.

    السقوط إلى الأحدث يجعل تقييماً قديماً يُعاد بقواعد لم تكن قائمة، ويُنتِج بصمةً
    تُطابق بلا أن تُطابق الدلالة. فالخطأ صريح.
    """


@dataclass(frozen=True)
class Reason:
    """سببٌ قابل للآلة: رمز + موضوع + المقيس + الحدّ. النصّ الحرّ لا يُبنى عليه."""

    code: str
    subject: str
    observed: Any
    limit: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subject": self.subject,
            "observed": self.observed,
            "limit": self.limit,
        }


@dataclass(frozen=True)
class Assessment:
    snapshot_digest: str
    policy_version: str
    policy_digest: str
    as_of: str
    inputs_digest: str
    stages: dict[str, bool]
    reasons: dict[str, list[dict[str, Any]]]
    assessment_digest: str
    contract_version: str = CONTRACT_VERSION
    #: ساعةُ الحائط — تُسجَّل ولا تدخل البصمة. تُملأ عند الكتابة لا عند الحساب.
    assessed_at: str | None = field(default=None, compare=False)

    def as_row(self) -> dict[str, Any]:
        return {
            "snapshot_digest": self.snapshot_digest,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "as_of": self.as_of,
            "inputs_digest": self.inputs_digest,
            "stages": dict(self.stages),
            "reasons": {k: list(v) for k, v in self.reasons.items()},
            "assessment_digest": self.assessment_digest,
            "contract_version": self.contract_version,
        }


def _digest(obj: Any) -> str:
    """بصمة قانونيّة: مفاتيح مرتّبة وفواصل بلا فراغ — نفس صياغة `decision_bridge`."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _age_hours(observed: datetime, as_of: datetime) -> float:
    return (as_of - observed).total_seconds() / 3600.0


def assess(
    *,
    snapshot: dict[str, Any],
    policy_version: str,
    as_of: datetime,
    tenant_id: str,
) -> Assessment:
    """يُقيّم لقطةً تحت سياسةٍ عند لحظةٍ — **بلا مسّ اللقطة ولا كتابة أيّ شيء**.

    حتميّ بالبناء: كلّ ما يدخل البصمة مُشتقٌّ من الوسائط الأربعة. لا `now()` ولا
    عشوائيّة ولا ترتيب قاموس غير مضمون (`sort_keys=True`).

    **الفشل مُغلَق:** عدم تطابق المستأجِر يرفض **كلّ** المراحل — ولا يُقرأ الجسد
    أصلاً. لأنّ تقييماً يُحسَب على لقطة مستأجِرٍ آخر ثمّ يُرفَض لاحقاً قد يُسرّب في
    أسبابه ما لا يملكه الطالب.
    """
    policy = POLICIES.get(policy_version)
    if policy is None:
        raise UnknownPolicyVersion(policy_version)

    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    snapshot_digest = str(snapshot.get("snapshot_hash") or "")
    quality = snapshot.get("quality_gate") or {}
    manifest = snapshot.get("feature_manifest") or {}

    inputs = {
        "snapshot_digest": snapshot_digest,
        "tenant_id": str(snapshot.get("tenant_id") or ""),
        "acquisition_at": str(snapshot.get("acquisition_at") or ""),
        "data_available_at": str(snapshot.get("data_available_at") or ""),
        "weather_observed_at": str(quality.get("weather_observed_at") or ""),
        "soil_observed_at": str(quality.get("soil_observed_at") or ""),
        "valid_pixel_pct": quality.get("valid_pixel_pct"),
        "spectral_bands": sorted(str(b) for b in (manifest.get("spectral_bands") or [])),
    }
    inputs_digest = _digest(inputs)

    stages = dict.fromkeys(STAGES, True)
    reasons: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}

    def deny(stage: str, reason: Reason) -> None:
        stages[stage] = False
        reasons[stage].append(reason.as_dict())

    def deny_all(reason: Reason) -> None:
        for stage in STAGES:
            deny(stage, reason)

    # ① المستأجِر أوّلاً ومغلقاً — قبل قراءة أيّ حقيقة من الجسد.
    snapshot_tenant = str(snapshot.get("tenant_id") or "")
    if not snapshot_tenant or snapshot_tenant != str(tenant_id):
        deny_all(Reason("TENANT_MISMATCH", "tenant_id", "mismatch", str(tenant_id)))
        return _finish(snapshot_digest, policy, as_of, inputs_digest, stages, reasons)

    # ② طابعٌ مستقبليّ: لقطةٌ «رُصِدت» بعد لحظة التقييم ليست حقيقة بل خطأ ساعة أو حقن.
    acquisition = _as_dt(snapshot.get("acquisition_at"))
    if acquisition is None:
        deny_all(Reason("MISSING_TIMESTAMP", "acquisition_at", None, "required"))
        return _finish(snapshot_digest, policy, as_of, inputs_digest, stages, reasons)
    if acquisition > as_of:
        deny_all(
            Reason("FUTURE_TIMESTAMP", "acquisition_at", acquisition.isoformat(), as_of.isoformat())
        )
        return _finish(snapshot_digest, policy, as_of, inputs_digest, stages, reasons)

    # ③ بيانات بائدة — لكلّ مرحلة حدّها، فالبائد للتنفيذ قد يكفي للاستكشاف.
    weather_at = _as_dt(quality.get("weather_observed_at"))
    soil_at = _as_dt(quality.get("soil_observed_at"))
    for stage in STAGES:
        if weather_at is None:
            deny(stage, Reason("MISSING_WEATHER", "weather_observed_at", None, "required"))
        else:
            age = _age_hours(weather_at, as_of)
            limit = policy.max_weather_age_h[stage]
            if age > limit:
                deny(stage, Reason("STALE_WEATHER", "weather_observed_at", round(age, 3), limit))
        if soil_at is None:
            deny(stage, Reason("MISSING_SOIL", "soil_observed_at", None, "required"))
        else:
            age = _age_hours(soil_at, as_of)
            limit = policy.max_soil_age_h[stage]
            if age > limit:
                deny(stage, Reason("STALE_SOIL", "soil_observed_at", round(age, 3), limit))

    # ④ نطاقات طيفيّة ناقصة — تُرفَض كلّ المراحل لأنّ الطيف مُدخَل أساس لا تحسين.
    bands = {str(b).lower() for b in (manifest.get("spectral_bands") or [])}
    for required in policy.require_spectral:
        if required not in bands:
            deny_all(Reason("MISSING_SPECTRAL", "spectral_bands", sorted(bands), required))

    # ⑤ نسبة البكسل الصالح.
    valid_pct = quality.get("valid_pixel_pct")
    for stage in STAGES:
        limit = policy.min_valid_pixel_pct[stage]
        if not isinstance(valid_pct, (int, float)):
            deny(stage, Reason("MISSING_VALID_PIXEL_PCT", "valid_pixel_pct", valid_pct, limit))
        elif float(valid_pct) < limit:
            deny(stage, Reason("LOW_VALID_PIXEL_PCT", "valid_pixel_pct", float(valid_pct), limit))

    # ⑥ الترتيب جزء من العقد: مرحلةٌ مرفوضة تُسقِط ما بعدها.
    blocked = False
    for stage in STAGES:
        if blocked and stages[stage]:
            stages[stage] = False
            reasons[stage].append(
                Reason("UPSTREAM_STAGE_DENIED", "stage_order", stage, STAGES[0]).as_dict()
            )
        blocked = blocked or not stages[stage]

    return _finish(snapshot_digest, policy, as_of, inputs_digest, stages, reasons)


def _finish(
    snapshot_digest: str,
    policy: Policy,
    as_of: datetime,
    inputs_digest: str,
    stages: dict[str, bool],
    reasons: dict[str, list[dict[str, Any]]],
) -> Assessment:
    as_of_s = as_of.astimezone(UTC).isoformat()
    policy_digest = policy.digest()
    assessment_digest = _digest(
        {
            "contract_version": CONTRACT_VERSION,
            "snapshot_digest": snapshot_digest,
            "policy_version": policy.version,
            "policy_digest": policy_digest,
            "as_of": as_of_s,
            "inputs_digest": inputs_digest,
            "stages": stages,
            "reasons": reasons,
        }
    )
    return Assessment(
        snapshot_digest=snapshot_digest,
        policy_version=policy.version,
        policy_digest=policy_digest,
        as_of=as_of_s,
        inputs_digest=inputs_digest,
        stages=stages,
        reasons=reasons,
        assessment_digest=assessment_digest,
    )
