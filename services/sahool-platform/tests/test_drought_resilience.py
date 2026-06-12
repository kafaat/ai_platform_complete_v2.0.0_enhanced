"""اختبارات درجة تحمّل الجفاف (offline) — من صفات موثّقة، لا اختراع.

يتحقّق من: حساب الدرجة المركّبة من صفات سهول (عمق جذور/حرارة إزهار/ملوحة)،
تحذير الإجهاد الحراري عند تجاوز حدّ الإزهار، الصدق عند غياب الصفات (لا درجة)،
وترتيب المحاصيل بالأصمد. لا قاعدة/شبكة.
"""

from core.engines.drought_resilience import (
    compare_crops_resilience,
    compute_drought_resilience,
)

# ─── الدرجة المفردة ──────────────────────────────────────────────────────


def test_known_crop_gets_score_and_components():
    out = compute_drought_resilience("sorghum")  # ذرة رفيعة: جذور عميقة، حرّ عالٍ
    assert out["resilience_score"] is not None
    assert 0.0 <= out["resilience_score"] <= 1.0
    assert out["components"]["root_depth_m"] == 1.5
    assert "risk_level_ar" in out


def test_unknown_crop_is_honest_no_score():
    out = compute_drought_resilience("dragonfruit")
    assert out["resilience_score"] is None  # صدق: لا صفات → لا درجة
    assert out["confidence"] == "none"


def test_heat_warning_when_forecast_exceeds_flowering_max():
    # القمح حدّ إزهاره 32°؛ توقّع 38° ⇒ تحذير حراري
    out = compute_drought_resilience("wheat", forecast_max_temp_c=38.0)
    assert "heat_warning_ar" in out
    assert out["components"]["heat_headroom_c"] == -6.0


def test_no_heat_warning_within_safe_range():
    out = compute_drought_resilience("wheat", forecast_max_temp_c=28.0)
    assert "heat_warning_ar" not in out
    assert out["components"]["heat_headroom_c"] == 4.0


def test_deep_root_crop_scores_higher_than_shallow():
    # الذرة الرفيعة (جذور 1.5م، ملوحة 6.8) أصمد من البطاطس (0.5م، 1.7)
    sorghum = compute_drought_resilience("sorghum")["resilience_score"]
    potato = compute_drought_resilience("potato")["resilience_score"]
    assert sorghum > potato


# ─── المقارنة ────────────────────────────────────────────────────────────


def test_compare_ranks_by_resilience_desc():
    out = compare_crops_resilience(["potato", "sorghum", "barley"])
    ranked = out["ranked_by_resilience"]
    scores = [r["resilience_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)  # تنازلي
    assert out["most_resilient"] == ranked[0]["crop_id"]


def test_compare_excludes_unknown_crops():
    out = compare_crops_resilience(["wheat", "unknowncrop"])
    ids = [r["crop_id"] for r in out["ranked_by_resilience"]]
    assert "unknowncrop" not in ids  # المجهول يُستبعَد (لا درجة مخترعة)
    assert "wheat" in ids
