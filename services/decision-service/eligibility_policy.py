"""الأهليّة **مصنوعٌ مشتقّ** لا حقلٌ في اللقطة — `CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`.

**القيد الذي يجعل هذا قراراً معماريّاً لا تفصيلاً تنفيذيّاً:** اللقطة **معنونة
بمحتواها**. `main.py` يقولها صراحةً («content-addressed by snapshot_hash — the hash IS
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

* `decision_eligible` (`generate_indicator_artifacts.py`) يبقى كما هو: **حقيقة عن
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
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

CONTRACT_VERSION = "eligibility-assessment.v1"

#: هويّة اللقطة: نفس القيد الذي تفرضه القاعدة (`CHECK (snapshot_hash ~ ...)`).
#: يُفرَض هنا أيضاً كي يفشل المقيّم مغلقاً بدل أن يُحيل الرفض إلى القاعدة لاحقاً.
_HEX64 = re.compile(r"[a-fA-F0-9]{64}")

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
    #: من أين جاءت هذه القيم — **مصدرٌ لا شرحٌ**. عتبةٌ بلا مصدر تُقرأ حكماً
    #: زراعيّاً وهي رقمٌ اختاره كاتب الشريحة.
    provenance: str = ""
    #: هل حُكِّمت هذه السياسة من صاحب القرار؟ **`False` هو الصدق الافتراضيّ.**
    #: سياسةٌ تُقدَّم مُحكَّمة بلا تحكيم أخطر من غيابها، لأنّ من يقرؤها يبني عليها.
    adjudicated: bool = False

    def digest(self) -> str:
        """بصمة السياسة من **تعريفها** لا من اسمها — تغييرُ عتبةٍ بلا رفع النسخة يظهر."""
        return _digest(
            {
                "version": self.version,
                "adjudicated": self.adjudicated,
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
    provenance=(
        "المُحكَّم في الشجرة: `source == real` و`status == implemented` و`min_valid_pixel_pct = 60.0` — كلّها من `scripts/ci/generate_indicator_artifacts.py:55-61` وهي أصل `decision_eligible`. **وما عداها من وضع هذه الشريحة بلا مصدر قرار:** أعمار الطقس والتربة، وعتبتا ٣٠٪ (discover) و٨٠٪ (execute)، ونسبة النطاقات المطلوبة. تبقى `provisional` حتّى يُحكّمها المالك، ولا تُقدَّم حكماً زراعيّاً."
    ),
    adjudicated=False,
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
    provenance=(
        "تجريبيّة بالكامل: وُضِعت لتُثبِت أنّ **إعادة تقييم لقطة قديمة تحت سياسة "
        "جديدة** تعمل بلا لمس اللقطة. عتباتها ليست حكماً زراعيّاً ولا مصدر قرار "
        "لها، وأساسها المُحكَّم هو أساس v1 نفسه "
        "(`scripts/ci/generate_indicator_artifacts.py`)."
    ),
    adjudicated=False,
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

    stages = dict.fromkeys(STAGES, True)
    reasons: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}

    def deny(stage: str, reason: Reason) -> None:
        stages[stage] = False
        reasons[stage].append(reason.as_dict())

    def deny_all(reason: Reason) -> None:
        for stage in STAGES:
            deny(stage, reason)

    # ① المستأجِر أوّلاً — **قبل قراءة أيّ حقل من الجسد وقبل بصمه**.
    #
    # أوّل صياغة عندي بصمَت المُدخَلات ثمّ فحصت المستأجِر، فكان `assessment_digest`
    # يتغيّر بتغيّر جسد لقطةِ مستأجِرٍ آخر رغم ثبات سبب الرفض — **هاش أوراكل**:
    # يُسرّب أنّ الجسد تغيّر لمن لا يملك قراءته. والوصف كان يقول «لا يُقرأ الجسد
    # أصلاً» بينما الكود يقرؤه. الآن البصمة عند الرفض مُشتقّة من **الهويّة وحدها**.
    snapshot_tenant = str(snapshot.get("tenant_id") or "")
    if not snapshot_tenant or snapshot_tenant != str(tenant_id):
        deny_all(Reason("TENANT_MISMATCH", "tenant_id", "mismatch", str(tenant_id)))
        return _finish("", policy, as_of, _digest({"denied": "TENANT_MISMATCH"}), stages, reasons)

    snapshot_digest = str(snapshot.get("snapshot_hash") or "")

    # ② هويّة اللقطة قبل أيّ حكم: بصمةٌ مفقودة أو مشوّهة ليست لقطة.
    #
    # كانت `""` تمرّ فتُمنَح المراحل الأربع ثمّ ترفضها القاعدة لاحقاً — والمقيّم
    # الذي يمنح أهليّة لِما لا هويّة له يُنتِج قراراً لا يمكن نسبُه إلى دليل.
    if not _HEX64.fullmatch(snapshot_digest):
        deny_all(Reason("MALFORMED_SNAPSHOT_DIGEST", "snapshot_hash", snapshot_digest, "64-hex"))
        return _finish(
            snapshot_digest,
            policy,
            as_of,
            _digest({"denied": "MALFORMED_SNAPSHOT_DIGEST", "tenant_id": snapshot_tenant}),
            stages,
            reasons,
        )

    quality = snapshot.get("quality_gate") or {}
    manifest = snapshot.get("feature_manifest") or {}

    inputs = {
        "snapshot_digest": snapshot_digest,
        "tenant_id": snapshot_tenant,
        "acquisition_at": str(snapshot.get("acquisition_at") or ""),
        "data_available_at": str(snapshot.get("data_available_at") or ""),
        "weather_observed_at": str(quality.get("weather_observed_at") or ""),
        "soil_observed_at": str(quality.get("soil_observed_at") or ""),
        "valid_pixel_pct": quality.get("valid_pixel_pct"),
        "spectral_bands": sorted(str(b) for b in (manifest.get("spectral_bands") or [])),
        "source": str(manifest.get("source") or ""),
        "status": str(manifest.get("status") or ""),
    }
    inputs_digest = _digest(inputs)

    def finish() -> Assessment:
        return _finish(snapshot_digest, policy, as_of, inputs_digest, stages, reasons)

    # ③ طابعٌ مستقبليّ: لقطةٌ «رُصِدت» بعد لحظة التقييم ليست حقيقة بل خطأ ساعة أو حقن.
    acquisition = _as_dt(snapshot.get("acquisition_at"))
    if acquisition is None:
        deny_all(Reason("MISSING_TIMESTAMP", "acquisition_at", None, "required"))
        return finish()
    if acquisition > as_of:
        deny_all(
            Reason("FUTURE_TIMESTAMP", "acquisition_at", acquisition.isoformat(), as_of.isoformat())
        )
        return finish()

    # ④ **الإتاحة قبل اللحظة** — القيد الذي كان يدخل البصمة ولا يُفحَص.
    #
    # `data_available_at` هو متى صارت البيانات **قابلة للاستعمال**. فتقييمٌ عند
    # `as_of` سابقٍ لها يبني قراراً على معلومةٍ لم تكن متاحة حينها — وهو تسريبٌ
    # من المستقبل يُفسِد كلّ إعادة تشغيل تاريخيّة، ولا يظهر في أيّ اختبار حتميّة.
    available = _as_dt(snapshot.get("data_available_at"))
    if available is None:
        deny_all(Reason("MISSING_TIMESTAMP", "data_available_at", None, "required"))
        return finish()
    if available > as_of:
        deny_all(
            Reason(
                "NOT_YET_AVAILABLE", "data_available_at", available.isoformat(), as_of.isoformat()
            )
        )
        return finish()

    # ⑤ العقد القانونيّ للمؤشّر: `source == "real"` و`status == "implemented"`.
    #
    # هذان **مُحكَّمان فعلاً** في الشجرة (`generate_indicator_artifacts.py`) وهما
    # أصل `decision_eligible`. فمؤشّرٌ اصطناعيّ أو غير مُنفَّذ لا يقود مرحلةً مهما
    # كانت أعماره سليمة — وربطُهما هنا يجعل السياسة تمتدّ من العقد لا تُوازيه.
    source = str(manifest.get("source") or "")
    status = str(manifest.get("status") or "")
    if source != "real":
        deny_all(Reason("SOURCE_NOT_REAL", "feature_manifest.source", source or None, "real"))
    if status != "implemented":
        deny_all(
            Reason(
                "STATUS_NOT_IMPLEMENTED", "feature_manifest.status", status or None, "implemented"
            )
        )

    # ⑥ بيانات بائدة — **أو مستقبليّة**. العمر السالب كان يمرّ لأنّ الفحص `>` وحده.
    for subject, observed_at, limits, stale, missing in (
        (
            "weather_observed_at",
            _as_dt(quality.get("weather_observed_at")),
            policy.max_weather_age_h,
            "STALE_WEATHER",
            "MISSING_WEATHER",
        ),
        (
            "soil_observed_at",
            _as_dt(quality.get("soil_observed_at")),
            policy.max_soil_age_h,
            "STALE_SOIL",
            "MISSING_SOIL",
        ),
    ):
        if observed_at is None:
            for stage in STAGES:
                deny(stage, Reason(missing, subject, None, "required"))
            continue
        if observed_at > as_of:
            deny_all(
                Reason("FUTURE_OBSERVATION", subject, observed_at.isoformat(), as_of.isoformat())
            )
            continue
        age = _age_hours(observed_at, as_of)
        for stage in STAGES:
            if age > limits[stage]:
                deny(stage, Reason(stale, subject, round(age, 3), limits[stage]))

    # ⑦ نطاقات طيفيّة ناقصة — تُرفَض كلّ المراحل لأنّ الطيف مُدخَل أساس لا تحسين.
    bands = {str(b).lower() for b in (manifest.get("spectral_bands") or [])}
    for required in policy.require_spectral:
        if required not in bands:
            deny_all(Reason("MISSING_SPECTRAL", "spectral_bands", sorted(bands), required))

    # ⑧ نسبة البكسل الصالح — **بمجالها**. `inf`/`nan`/‏-5/‏١٢٠ ليست نِسباً:
    # `nan` يجعل كلّ مقارنة `False` فتمرّ صامتةً، و`inf` يتفوّق على أيّ عتبة.
    valid_pct = quality.get("valid_pixel_pct")
    valid: float | None = None
    if isinstance(valid_pct, bool) or not isinstance(valid_pct, (int, float)):
        deny_all(Reason("MISSING_VALID_PIXEL_PCT", "valid_pixel_pct", valid_pct, "0..100"))
    elif not isfinite(float(valid_pct)) or not (0.0 <= float(valid_pct) <= 100.0):
        deny_all(Reason("OUT_OF_RANGE_VALID_PIXEL_PCT", "valid_pixel_pct", valid_pct, "0..100"))
    else:
        valid = float(valid_pct)
    if valid is not None:
        for stage in STAGES:
            limit = policy.min_valid_pixel_pct[stage]
            if valid < limit:
                deny(stage, Reason("LOW_VALID_PIXEL_PCT", "valid_pixel_pct", valid, limit))

    # ⑨ الترتيب جزء من العقد: مرحلةٌ مرفوضة تُسقِط ما بعدها.
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
