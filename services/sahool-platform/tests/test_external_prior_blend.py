"""اختبارات مزج السابقة الخارجيّة المنشورة ببيانات اليمن (offline).

يتحقّق من: الوزن التدرّجي n/(n+K)؛ سقف مصداقيّة السابقة الخارجيّة (≤0.5)؛ تلاشيها
مع تراكم المحلّي؛ التصعيد عند هيمنة السابقة؛ ورفض المحصول غير المزروع في اليمن.
"""

import math

from core.engines.external_prior_blend import (
    EXTERNAL_PRIOR_MAX_CREDIBILITY,
    blend_external_prior,
    blend_maturity,
)
from core.engines.human_escalation import EscalationLevel
from core.learning.prediction_calibration import SHRINKAGE_K, confidence_weight

# ─── الانطباق + الصدق ────────────────────────────────────────────────────


def test_crop_not_grown_in_yemen_is_inapplicable():
    out = blend_external_prior(5.0, 4.0, 50, crop_grown_in_yemen=False)
    assert out["applicable"] is False
    assert out["blended_estimate"] is None
    # لا إجابة مولّدة ⇒ تصعيد حاكم (لا اختراع قيمة أجنبيّة).
    assert out["escalation"]["level"] == EscalationLevel.BLOCKED.value


def test_no_evidence_at_all_blocks():
    out = blend_external_prior(None, None, 0, crop_grown_in_yemen=True)
    assert out["blended_estimate"] is None
    assert out["escalation"]["level"] == EscalationLevel.BLOCKED.value


# ─── الوزن التدرّجي (نفس انكماش prediction_calibration) ───────────────────


def test_no_local_data_leans_fully_on_external_prior_as_hint():
    # n=0 ⇒ المحلّي بلا وزن، التقدير = السابقة الخارجيّة لكنّه تلميح يُراجَع.
    out = blend_external_prior(6.0, None, 0, crop_grown_in_yemen=True)
    assert out["blended_estimate"] == 6.0
    assert out["local_weight"] == 0.0
    assert out["external_weight"] == 1.0
    # الثقة مقصوصة بمصداقيّة السابقة (≤0.5) ⇒ ليست يقيناً ⇒ تصعيد.
    assert out["output_confidence"] <= EXTERNAL_PRIOR_MAX_CREDIBILITY
    assert out["escalation"]["needs_escalation"] is True
    assert out["prior_faded"] is False


def test_blend_weight_matches_shrinkage_formula():
    n = SHRINKAGE_K  # عند n=K الوزن المحلّي = 0.5 بالضبط
    out = blend_external_prior(10.0, 4.0, n, crop_grown_in_yemen=True)
    assert math.isclose(out["local_weight"], confidence_weight(n), rel_tol=1e-9)
    assert math.isclose(out["local_weight"], 0.5, rel_tol=1e-9)
    # مزج: 0.5·4 + 0.5·10 = 7.0
    assert math.isclose(out["blended_estimate"], 7.0, rel_tol=1e-9)


def test_custom_k_changes_weight():
    # k المُمرَّر يجب أن يؤثّر فعليّاً على الوزن (لا يُتجاهَل لصالح SHRINKAGE_K).
    out = blend_external_prior(10.0, 4.0, 30, crop_grown_in_yemen=True, k=5)
    assert out["local_weight"] == round(30 / 35, 3)  # ≈0.857، لا 0.5 (k=30)
    assert out["local_weight"] > 0.5  # k=5 < SHRINKAGE_K ⇒ وزن أعلى من حالة k=30


def test_external_credibility_is_capped():
    # حتّى لو طُلبت مصداقيّة عالية للسابقة الخارجيّة، تُقصّ إلى الحدّ.
    out = blend_external_prior(6.0, None, 0, crop_grown_in_yemen=True, external_credibility=0.95)
    assert out["external_credibility"] == EXTERNAL_PRIOR_MAX_CREDIBILITY


# ─── التلاشي مع تراكم بيانات اليمن ────────────────────────────────────────


def test_prior_fades_as_local_data_grows():
    small = blend_external_prior(10.0, 4.0, 10, crop_grown_in_yemen=True)
    large = blend_external_prior(10.0, 4.0, 9 * SHRINKAGE_K, crop_grown_in_yemen=True)
    # وزن المحلّي يرتفع، ووزن السابقة الخارجيّة ينخفض.
    assert large["local_weight"] > small["local_weight"]
    assert large["external_weight"] < small["external_weight"]
    # عند n ≥ 9K تُعتبر السابقة متلاشية.
    assert large["prior_faded"] is True
    assert small["prior_faded"] is False
    # ومع التلاشي يقترب التقدير من المحلّي (4) بعيداً عن السابقة (10).
    assert abs(large["blended_estimate"] - 4.0) < abs(small["blended_estimate"] - 4.0)


def test_local_only_when_no_external_prior():
    out = blend_external_prior(None, 4.2, 50, crop_grown_in_yemen=True)
    assert out["blended_estimate"] == 4.2
    assert out["local_weight"] == 1.0
    assert out["external_weight"] == 0.0


# ─── نضج المزج عبر السياقات ───────────────────────────────────────────────


def test_blend_maturity_splits_matured_vs_external_dependent():
    ctxs = {
        "wheat@aljawf": blend_external_prior(10.0, 4.0, 9 * SHRINKAGE_K, crop_grown_in_yemen=True),
        "barley@dhamar": blend_external_prior(10.0, 4.0, 5, crop_grown_in_yemen=True),
        "maize@abroad": blend_external_prior(8.0, 5.0, 5, crop_grown_in_yemen=False),
    }
    out = blend_maturity(ctxs)
    assert out["total_contexts"] == 3
    assert "barley@dhamar" in out["still_external_dependent"]
    # غير المنطبق (خارج اليمن) لا يُحسَب في أيّ مجموعة.
    assert "maize@abroad" not in out["still_external_dependent"]
    assert "maize@abroad" not in out["matured_local_contexts"]
