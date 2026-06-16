"""اختبارات نقيّة لمساعِدات تشكيل ردّ موجِّه phenology (لا قاعدة، offline).

تختبر ``_shape_phenology`` و``_shape_stage_actions`` (دالّتان نقيّتان module-level)
مباشرةً بعد القراءة المفترضة من القاعدة — تماماً كما تستدعيهما النقطتان. تغطّي:
المسار السعيد (فاصوليا مبذورة قبل 60 يوماً ⇒ مرحلة 'mid'، خطّ زمن من 4 مراحل بحالات،
Kc طوريّ 1.15)، والمحصول المجهول، وغياب تاريخ البذار (صدق: available=False).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from api.routers.phenology import (
    _first_season_crop,
    _shape_phenology,
    _shape_stage_actions,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 6, 16)
SOWN_60D = TODAY - timedelta(days=60)


# ─── _shape_phenology ──────────────────────────────────────────────────────


def test_phenology_common_bean_60d_is_mid_stage():
    out = _shape_phenology("common bean", SOWN_60D, today=TODAY)
    assert out["available"] is True
    assert out["days_after_sowing"] == 60
    assert out["crop_id"] == "common_bean"
    assert out["current_stage"]["stage"] == "mid"


def test_phenology_timeline_has_four_stages_with_statuses():
    out = _shape_phenology("common bean", SOWN_60D, today=TODAY)
    timeline = out["timeline"]
    assert len(timeline) == 4
    statuses = [s["status"] for s in timeline]
    assert statuses == ["past", "past", "current", "upcoming"]
    # كلّ مرحلة بتواريخ مطلقة + اسم عربيّ
    for st in timeline:
        assert "start_date" in st and "end_date" in st
        assert st["name_ar"]


def test_phenology_current_stage_kc_is_115():
    out = _shape_phenology("common bean", SOWN_60D, today=TODAY)
    assert out["current_stage_kc"] == 1.15


def test_phenology_accepts_arabic_crop_name():
    out = _shape_phenology("فاصوليا", SOWN_60D, today=TODAY)
    assert out["available"] is True
    assert out["crop_id"] == "common_bean"
    assert out["current_stage"]["stage"] == "mid"


def test_phenology_unknown_crop_unavailable():
    out = _shape_phenology("zzz-not-a-crop", SOWN_60D, today=TODAY)
    assert out["available"] is False
    assert "reason_ar" in out and out["reason_ar"]
    assert "timeline" not in out


def test_phenology_no_sowing_date_unavailable():
    out = _shape_phenology("common bean", None, today=TODAY)
    assert out["available"] is False
    assert "reason_ar" in out and out["reason_ar"]


def test_phenology_none_crop_unavailable():
    out = _shape_phenology(None, SOWN_60D, today=TODAY)
    assert out["available"] is False


# ─── _shape_stage_actions ──────────────────────────────────────────────────


def test_stage_actions_common_bean_60d_suggests_mid_action():
    out = _shape_stage_actions("common bean", SOWN_60D, today=TODAY)
    assert out["available"] is True
    assert out["current_stage"] == "mid"
    assert len(out["suggestions"]) == 1
    sug = out["suggestions"][0]
    assert sug["stage"] == "mid"
    assert sug["stage_name_ar"]
    assert sug["action_ar"]
    # اقتراحات فقط — منوّه به في الردّ
    assert "note_ar" in out


def test_stage_actions_unknown_crop_unavailable():
    out = _shape_stage_actions("zzz-not-a-crop", SOWN_60D, today=TODAY)
    assert out["available"] is False
    assert "suggestions" not in out


def test_stage_actions_no_sowing_date_unavailable():
    out = _shape_stage_actions("common bean", None, today=TODAY)
    assert out["available"] is False


def test_stage_actions_age_past_cycle_unavailable():
    # عمر بعيد جدّاً يتجاوز آخر مرحلة ⇒ لا مرحلة حاليّة ⇒ available=False
    out = _shape_stage_actions("common bean", TODAY - timedelta(days=5000), today=TODAY)
    assert out["available"] is False


# ─── _first_season_crop ────────────────────────────────────────────────────


def test_first_season_crop_from_json_string():
    assert _first_season_crop('["common bean", "wheat"]', "fallback") == "common bean"


def test_first_season_crop_from_list():
    assert _first_season_crop(["wheat"], "fallback") == "wheat"


def test_first_season_crop_empty_falls_back():
    assert _first_season_crop([], "fallback") == "fallback"
    assert _first_season_crop("not-json", "fallback") == "fallback"
    assert _first_season_crop(None, "fallback") == "fallback"
