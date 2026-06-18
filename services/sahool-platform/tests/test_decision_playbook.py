"""اختبارات محرّك «دليل القرار» (core.decision_playbook) — ذكاء قابل للتفسير.

نقيّة وحتميّة (لا I/O، لا خدمات) ⇒ مُعلَّمة `unit` لتُنفَّذ في بوّابة CI السريعة.
تثبّت العقد: سيادة الصقيع على الحُكم وإجراءاته الوقائيّة وأفقه القصير، فرصة الرشّ
النظيفة، سيناريو المرض وتجنّب الريّ المسائيّ، ظهور التغذية الراجعة السالبة في الأدلّة
والتصعيد، السياق الفارغ (حُكم محايد منخفض الثقة بلا انهيار)، حدود الثقة، الحتميّة،
وأولويّة الصقيع على الرشّ عند اجتماعهما.
"""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.crop_risk import CropRisk  # noqa: E402
from core.decision_playbook import (  # noqa: E402
    DecisionPlaybook,
    PlaybookContext,
    build_playbook,
)
from core.soil_feedback_proxy import (  # noqa: E402
    SoilFeedbackInputs,
    assess_plant_soil_feedback,
)
from core.weather_signals import WeatherSignal  # noqa: E402


# ── أدوات بناء سياق ──
def _frost_signal(conf: float = 0.8, hours: int = 5) -> WeatherSignal:
    return WeatherSignal("frost_imminent", conf, {"frost_hours": hours})


def _spray_signal(conf: float = 0.7) -> WeatherSignal:
    return WeatherSignal("spray_window_open", conf, {"suitable_fraction": conf})


def _disease_signal(conf: float = 0.75) -> WeatherSignal:
    return WeatherSignal("disease_risk_high", conf, {"risk_fraction": conf})


def _negative_soil():
    # مدخلات تدفع نحو تغذية راجعة سالبة عالية الثقة: تكرار عائل + أمراض + إفراط أسمدة.
    return assess_plant_soil_feedback(
        SoilFeedbackInputs(
            host_repeat_risk=0.95,
            disease_incidents_recent=5,
            synthetic_fertilizer_intensity=0.9,
            tillage_intensity=0.9,
            salinity_ds_m=7.5,
            rotation_diversity=0.05,
            cover_crop_ratio=0.0,
            legume_ratio=0.0,
            organic_matter_additions_per_yr=0.0,
            soil_organic_carbon_pct=0.4,
        )
    )


def _positive_soil():
    return assess_plant_soil_feedback(
        SoilFeedbackInputs(
            rotation_diversity=0.9,
            legume_ratio=0.8,
            cover_crop_ratio=0.85,
            organic_matter_additions_per_yr=4.0,
            soil_organic_carbon_pct=3.0,
            tillage_intensity=0.05,
            host_repeat_risk=0.05,
            disease_incidents_recent=0,
            synthetic_fertilizer_intensity=0.1,
            salinity_ds_m=0.5,
        )
    )


# ── السيناريو 1: الصقيع يسيطر على الحُكم ──
def test_frost_signal_dominates_judgement():
    pb = build_playbook(PlaybookContext(crop="tomato", weather_signals=(_frost_signal(),)))
    assert isinstance(pb, DecisionPlaybook)
    assert "صقيع" in pb.main_judgement
    # do_today وقائيّ من الصقيع.
    assert any("حماية من الصقيع" in a for a in pb.do_today)
    # avoid_now يمنع الرشّ/التسميد الورقيّ ليلاً.
    assert any("رشّ" in a or "تسميد" in a for a in pb.avoid_now)
    # أفق قصير.
    assert pb.review_after == "خلال ٢٤ ساعة"
    # escalate_if يذكر استمرار الصقيع.
    assert any("صقيع" in e or "الحرارة" in e for e in pb.escalate_if)


def test_frost_via_high_crop_risk_only():
    # خطر صقيع عالٍ من CropRisk دون إشارة طقس ⇒ الصقيع يسيطر أيضاً.
    risk = CropRisk("frost_damage", "potato", "high", 0.8, "خطر ضرر صقيع على البطاطس.")
    pb = build_playbook(PlaybookContext(crop="potato", crop_risks=(risk,)))
    assert "صقيع" in pb.main_judgement
    assert any("صقيع" in e for e in pb.evidence)


# ── السيناريو 2: نافذة رشّ نظيفة ──
def test_clean_spray_window_recommends_spraying():
    pb = build_playbook(PlaybookContext(crop="wheat", weather_signals=(_spray_signal(),)))
    assert "رشّ" in pb.main_judgement
    assert any("الرشّ المخطّط" in a for a in pb.do_today)
    assert any("نافذة رشّ" in e for e in pb.evidence)


# ── السيناريو 3: المرض ──
def test_disease_scenario_avoids_evening_irrigation():
    pb = build_playbook(PlaybookContext(crop="tomato", weather_signals=(_disease_signal(),)))
    assert "مرض" in pb.main_judgement
    assert any("رشّ وقائيّ" in a or "فحص" in a for a in pb.do_today)
    assert any("ريّ الغمر المسائيّ" in a or "الرطوبة" in a for a in pb.avoid_now)
    assert any("بؤر إصابة" in e for e in pb.escalate_if)


# ── السيناريو 4: التغذية الراجعة السالبة ──
def test_negative_soil_feedback_surfaces():
    soil = _negative_soil()
    assert soil.direction == "negative"
    pb = build_playbook(PlaybookContext(crop="potato", soil_feedback=soil))
    assert "تغذية راجعة" in pb.main_judgement
    # تظهر في الأدلّة (verdict_ar).
    assert any("تغذية راجعة" in e or "ممرض" in e for e in pb.evidence)
    # وفي التصعيد.
    assert any("تدهور" in e or "موسم" in e for e in pb.escalate_if)


def test_positive_soil_feedback_is_reinforcing_not_alarming():
    soil = _positive_soil()
    assert soil.direction == "positive"
    pb = build_playbook(PlaybookContext(crop="wheat", soil_feedback=soil))
    # لا إنذار: حُكم مستقرّ، ولا تصعيد من التربة.
    assert "مستقرّ" in pb.main_judgement
    assert pb.escalate_if == ()


# ── السيناريو 5: السياق الفارغ ──
def test_empty_context_is_neutral_low_confidence_no_crash():
    pb = build_playbook(PlaybookContext())
    assert "بيانات غير كافية" in pb.main_judgement
    assert pb.confidence <= 0.2
    assert pb.review_after  # غير فارغ دائماً
    assert pb.evidence  # يفسّر سبب الحياد
    assert pb.do_today == ()
    assert pb.avoid_now == ()


# ── حدود الثقة ──
def test_confidence_within_bounds():
    for ctx in (
        PlaybookContext(),
        PlaybookContext(weather_signals=(_frost_signal(1.0),)),
        PlaybookContext(
            crop="tomato",
            weather_signals=(_frost_signal(), _spray_signal(), _disease_signal()),
            soil_feedback=_negative_soil(),
            recommendation_ar="راقب الطقس",
        ),
    ):
        pb = build_playbook(ctx)
        assert 0.0 <= pb.confidence <= 1.0


def test_more_context_raises_confidence():
    sparse = build_playbook(PlaybookContext(weather_signals=(_frost_signal(0.5),)))
    rich = build_playbook(
        PlaybookContext(
            crop="tomato",
            weather_signals=(_frost_signal(0.9),),
            crop_risks=(CropRisk("frost_damage", "tomato", "high", 0.9, "صقيع"),),
            soil_feedback=_negative_soil(),
            recommendation_ar="راقب",
        )
    )
    assert rich.confidence >= sparse.confidence


# ── الحتميّة ──
def test_determinism_same_context_same_playbook():
    ctx = PlaybookContext(
        crop="potato",
        weather_signals=(_disease_signal(), _spray_signal()),
        crop_risks=(CropRisk("fungal_disease", "potato", "high", 0.8, "لفحة"),),
        soil_feedback=_negative_soil(),
    )
    assert build_playbook(ctx) == build_playbook(ctx)


# ── ترتيب الأولويّة: الصقيع يفوق الرشّ ──
def test_frost_beats_spray_priority():
    pb = build_playbook(
        PlaybookContext(
            crop="wheat",
            weather_signals=(_spray_signal(0.9), _frost_signal(0.6)),
        )
    )
    assert "صقيع" in pb.main_judgement
    assert "رشّ" not in pb.main_judgement
    # الرشّ يُؤجَّل بسبب الحاجب.
    assert any("أجّل الرشّ" in a for a in pb.avoid_now)


def test_disease_beats_spray_priority():
    pb = build_playbook(PlaybookContext(weather_signals=(_spray_signal(0.9), _disease_signal(0.6))))
    assert "مرض" in pb.main_judgement
    assert any("أجّل الرشّ" in a for a in pb.avoid_now)


# ── تعدّد المخاطر: كلّ المواضيع تظهر في الأدلّة ولو فاز الأعلى أولويّة ──
def test_multiple_themes_all_appear_in_evidence():
    pb = build_playbook(
        PlaybookContext(
            crop="maize",
            weather_signals=(
                _frost_signal(),
                _disease_signal(),
                WeatherSignal("heat_stress", 0.5, {"heat_hours": 7}),
                WeatherSignal("trafficability_poor", 0.6, {"trafficability": 20.0}),
            ),
        )
    )
    assert "صقيع" in pb.main_judgement  # الأعلى أولويّة يفوز
    joined = " | ".join(pb.evidence)
    assert "صقيع" in joined
    assert "مرض" in joined
    assert "حراريّ" in joined
    assert "مرور" in joined
