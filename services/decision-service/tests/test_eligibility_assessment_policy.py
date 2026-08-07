"""`CANONICAL-SNAPSHOT-ELIGIBILITY-POLICY-01`: الأهليّة مشتقّة، واللقطة لا تُمَسّ.

الحالات هنا هي التي سمّاها نطاق المالك، وكلٌّ منها تؤكّد **خاصّيّة** لا صياغة:
سياسة v1 مقابل v2 · بيانات بائدة · طيف مفقود · طابع مستقبليّ · عدم تطابق مستأجِر
يفشل مغلقاً · وتغيير السياسة **لا** يُغيّر `snapshot_digest`.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SERVICE = Path(__file__).resolve().parents[1]


def _load():
    """يُسجَّل في `sys.modules` **قبل** التنفيذ.

    بدونه يفشل `@dataclass` نفسه: يستدعي `sys.modules.get(cls.__module__)` ليحلّ
    التلميحات، فيجد `None`. خطأٌ يبدو في الديكوريتر وسببُه في المُحمِّل.
    """
    spec = importlib.util.spec_from_file_location(
        "eligibility_policy", _SERVICE / "eligibility_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["eligibility_policy"] = module
    spec.loader.exec_module(module)
    return module


EP = _load()

TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "22222222-2222-2222-2222-222222222222"
AS_OF = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


def snapshot(**overrides):
    """لقطة صالحة تماماً — كلّ اختبار يُفسِد **عاملاً واحداً** منها."""
    quality = {
        "weather_observed_at": (AS_OF - timedelta(hours=1)).isoformat(),
        "soil_observed_at": (AS_OF - timedelta(hours=10)).isoformat(),
        "valid_pixel_pct": 95.0,
    }
    quality.update(overrides.pop("quality_gate", {}))
    base = {
        "snapshot_hash": DIGEST,
        "tenant_id": TENANT,
        "acquisition_at": (AS_OF - timedelta(hours=2)).isoformat(),
        "data_available_at": (AS_OF - timedelta(hours=1)).isoformat(),
        "quality_gate": quality,
        "feature_manifest": {"spectral_bands": ["ndvi", "ndmi"]},
        "payload": {},
    }
    base.update(overrides)
    return base


def assess(snap=None, policy="v1", as_of=AS_OF, tenant=TENANT):
    return EP.assess(
        snapshot=snap if snap is not None else snapshot(),
        policy_version=policy,
        as_of=as_of,
        tenant_id=tenant,
    )


def codes(result, stage="execute") -> set[str]:
    return {r["code"] for r in result.reasons[stage]}


# ── الحتميّة ────────────────────────────────────────────────────────────────


def test_the_same_inputs_give_the_same_digest():
    """نفس اللقطة والسياسة و`as_of` ⇒ النتيجة والبصمة نفساهما."""
    assert assess().assessment_digest == assess().assessment_digest


def test_wall_clock_never_enters_the_digest():
    """`assessed_at` ساعةُ حائط — لو دخلت البصمة لَما كانت الحتميّة خاصّيّة بل ادّعاءً.

    مُقاس لا مُفترَض: نسختان تختلفان في `assessed_at` وحده تتساويان **وتتطابق
    بصمتاهما**.
    """
    import dataclasses

    first = assess()
    stamped = dataclasses.replace(first, assessed_at="2026-01-01T00:00:00+00:00")
    assert stamped.assessment_digest == first.assessment_digest
    assert stamped == first, "`assessed_at` يشارك في المساواة — فالحتميّة تنكسر"


def test_a_different_as_of_is_a_different_assessment():
    """`as_of` مُدخَل حقيقيّ لا زينة: تغييرُه يجب أن يُغيّر البصمة."""
    later = assess(as_of=AS_OF + timedelta(hours=1))
    assert later.assessment_digest != assess().assessment_digest


# ── العقد المعماريّ: اللقطة لا تُمَسّ ────────────────────────────────────────


def test_changing_the_policy_does_not_change_the_snapshot_digest():
    """**القيد الذي أوجب الفجوة كلّها.**

    اللقطة معنونة بمحتواها؛ فلو حمل التقييمُ نفسه أثراً في `snapshot_hash` لَتغيّر
    كلّ هاش قائم عند أوّل تغيير سياسة، وانكسرت إعادة التشغيل ونَسَب الأدلّة.
    """
    snap = snapshot()
    before = dict(snap)
    v1, v2 = assess(snap, policy="v1"), assess(snap, policy="v2")

    assert v1.snapshot_digest == v2.snapshot_digest == DIGEST
    assert snap == before, "التقييم عدّل اللقطة — وهي حقائق ثابتة"
    assert v1.assessment_digest != v2.assessment_digest, "السياستان تُنتِجان التقييم نفسه"


def test_neither_policy_version_nor_assessment_id_is_inside_the_snapshot():
    """لا `policy_version` ولا `eligibility_assessment_id` داخل جسم اللقطة."""
    snap = snapshot()
    assess(snap)
    assert "policy_version" not in snap
    assert "eligibility_assessment_id" not in snap
    assert "assessment_digest" not in snap


def test_an_old_snapshot_can_be_reassessed_under_a_new_policy():
    """الخاصّيّة التي يشتريها الفصل: إعادة تقييم لقطة قديمة بلا لمس تاريخها."""
    old = snapshot(
        acquisition_at=(AS_OF - timedelta(days=200)).isoformat(),
        quality_gate={
            "weather_observed_at": (AS_OF - timedelta(hours=1)).isoformat(),
            "soil_observed_at": (AS_OF - timedelta(hours=10)).isoformat(),
        },
    )
    for version in ("v1", "v2"):
        assert assess(old, policy=version).snapshot_digest == DIGEST


# ── السياسة v1 مقابل v2 ─────────────────────────────────────────────────────


def test_v2_is_stricter_than_v1_on_execute():
    """طقسٌ عمره ١٢ ساعة: مقبولٌ للتنفيذ في v1 (٢٤) ومرفوضٌ في v2 (٦)."""
    snap = snapshot(quality_gate={"weather_observed_at": (AS_OF - timedelta(hours=12)).isoformat()})
    assert assess(snap, policy="v1").stages["execute"] is True
    v2 = assess(snap, policy="v2")
    assert v2.stages["execute"] is False
    assert "STALE_WEATHER" in codes(v2)
    assert v2.stages["discover"] is True, "التشدّد سرى إلى مرحلة لا تعنيها العتبة"


def test_a_policy_digest_is_derived_from_the_definition_not_the_name():
    """تغييرُ عتبةٍ بلا رفع النسخة يجب أن يظهر في البصمة."""
    tampered = EP.Policy(
        version="v1",
        max_weather_age_h=dict(EP.POLICY_V1.max_weather_age_h) | {"execute": 999.0},
        max_soil_age_h=EP.POLICY_V1.max_soil_age_h,
        require_spectral=EP.POLICY_V1.require_spectral,
        min_valid_pixel_pct=EP.POLICY_V1.min_valid_pixel_pct,
    )
    assert tampered.digest() != EP.POLICY_V1.digest()


def test_an_unknown_policy_version_is_refused_not_defaulted():
    """السقوط إلى الأحدث يُعيد تقييماً قديماً بقواعد لم تكن قائمة — فالخطأ صريح."""
    with pytest.raises(EP.UnknownPolicyVersion):
        assess(policy="v99")


# ── الحالات التي سمّاها النطاق ──────────────────────────────────────────────


def test_stale_weather_is_denied_with_a_machine_readable_reason():
    snap = snapshot(
        quality_gate={"weather_observed_at": (AS_OF - timedelta(hours=200)).isoformat()}
    )
    result = assess(snap)
    assert result.stages["execute"] is False
    reason = next(r for r in result.reasons["execute"] if r["code"] == "STALE_WEATHER")
    assert reason["subject"] == "weather_observed_at"
    assert reason["observed"] > reason["limit"], "السبب لا يحمل المقيس والحدّ"


def test_stale_soil_is_denied():
    snap = snapshot(quality_gate={"soil_observed_at": (AS_OF - timedelta(days=200)).isoformat()})
    assert assess(snap).stages["execute"] is False
    assert "STALE_SOIL" in codes(assess(snap))


def test_missing_spectral_denies_every_stage():
    """الطيف مُدخَل أساس لا تحسين — فلا مرحلة تنجو منه."""
    snap = snapshot(feature_manifest={"spectral_bands": ["ndmi"]})
    result = assess(snap)
    assert not any(result.stages.values())
    assert "MISSING_SPECTRAL" in codes(result, "discover")


def test_v2_requires_a_band_that_v1_does_not():
    snap = snapshot(feature_manifest={"spectral_bands": ["ndvi"]})
    assert assess(snap, policy="v1").stages["discover"] is True
    assert assess(snap, policy="v2").stages["discover"] is False


def test_a_future_timestamp_denies_everything():
    """لقطةٌ «رُصِدت» بعد لحظة التقييم ليست حقيقة بل خطأ ساعة أو حقن."""
    snap = snapshot(acquisition_at=(AS_OF + timedelta(hours=1)).isoformat())
    result = assess(snap)
    assert not any(result.stages.values())
    assert "FUTURE_TIMESTAMP" in codes(result, "discover")


def test_a_tenant_mismatch_fails_closed_and_leaks_nothing():
    """الفشل مغلق، **ولا يُقرأ الجسد أصلاً**.

    تقييمٌ يُحسَب على لقطة مستأجِرٍ آخر ثمّ يُرفَض لاحقاً قد يُسرّب في أسبابه ما لا
    يملكه الطالب — فالرفض قبل قراءة أيّ حقيقة، وسببه واحد لا قائمة تشخيص.
    """
    result = assess(tenant=OTHER_TENANT)
    assert not any(result.stages.values())
    for stage in EP.STAGES:
        assert [r["code"] for r in result.reasons[stage]] == ["TENANT_MISMATCH"]


def test_a_snapshot_without_a_tenant_is_refused_too():
    assert not any(assess(snapshot(tenant_id="")).stages.values())


# ── ترتيب المراحل ───────────────────────────────────────────────────────────


def test_a_denied_stage_blocks_the_ones_after_it(monkeypatch):
    """لا تُقترَح خطّة على لقطةٍ لا تكفي للتشخيص.

    **وهذا الثابت لا يمكن قياسه بالسياستين المشحونتين:** عتباتهما **مُطّردة** (تشتدّ
    مرحلةً بعد مرحلة)، فكلّ ما يُسقِط `diagnose` يُسقِط `propose` بحدّه هو — والتتالي
    لا يُطلِق أبداً. أوّل صياغة عندي أكّدته على `valid_pixel_pct=45` فسقطت، لأنّ
    `propose` كان مرفوضاً **بسببه الخاصّ**.

    فالقياس على سياسة **غير مُطّردة** مبنيّة هنا عمداً: تشدّ `diagnose` وتُرخي
    `propose`. وهي الحالة التي يحرسها التتالي فعلاً — سياسةٌ مستقبليّة تُرخي مرحلةً
    متأخّرة بلا انتباه، فتُقترَح خطّة على لقطةٍ لم تُشخَّص.
    """
    non_monotone = EP.Policy(
        version="test-non-monotone",
        max_weather_age_h={"discover": 168.0, "diagnose": 2.0, "propose": 500.0, "execute": 500.0},
        max_soil_age_h=EP.POLICY_V1.max_soil_age_h,
        require_spectral=EP.POLICY_V1.require_spectral,
        min_valid_pixel_pct=dict.fromkeys(EP.STAGES, 10.0),
    )
    monkeypatch.setitem(EP.POLICIES, non_monotone.version, non_monotone)

    snap = snapshot(quality_gate={"weather_observed_at": (AS_OF - timedelta(hours=6)).isoformat()})
    result = assess(snap, policy=non_monotone.version)

    assert result.stages["discover"] is True
    assert result.stages["diagnose"] is False, "العتبة المشدودة لم تُسقِط التشخيص"
    assert result.stages["propose"] is False, "خطّة اقتُرِحت على لقطةٍ لم تُشخَّص"
    assert codes(result, "propose") == {"UPSTREAM_STAGE_DENIED"}
    assert codes(result, "execute") == {"UPSTREAM_STAGE_DENIED"}


def test_the_shipped_policies_are_monotone_across_stages():
    """السبب الذي يجعل الاختبار أعلاه يحتاج سياسةً مصنوعة — مُثبَّتٌ لا مشروحٌ فقط.

    ولو ارتخت عتبةٌ متأخّرة في v1 أو v2 يوماً، سقط هذا الاختبار وسمّى الحقل — فيُنتبَه
    إلى أنّ التتالي صار حيّاً بدل أن يمرّ التغيير صامتاً.
    """
    for policy in (EP.POLICY_V1, EP.POLICY_V2):
        for limits, tighter_is_smaller in (
            (policy.max_weather_age_h, True),
            (policy.max_soil_age_h, True),
            (policy.min_valid_pixel_pct, False),
        ):
            ordered = [limits[stage] for stage in EP.STAGES]
            pairs = list(zip(ordered, ordered[1:], strict=False))
            assert all((a >= b) if tighter_is_smaller else (a <= b) for a, b in pairs), (
                f"{policy.version}: عتبة متأخّرة أرخى من سابقتها ⇒ {ordered}"
            )


def test_a_fully_valid_snapshot_passes_every_stage():
    """بلا هذا، «يرفض كلّ شيء» يُرضي كلّ اختبار أعلاه."""
    result = assess()
    assert all(result.stages.values())
    assert all(result.reasons[stage] == [] for stage in EP.STAGES)
