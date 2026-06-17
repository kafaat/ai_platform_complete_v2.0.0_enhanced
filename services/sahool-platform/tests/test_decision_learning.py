"""اختبارات التعلُّم المستمرّ (core.decision_learning) — المرحلة C، الشريحة 9.

نقيّة وحتميّة ⇒ `unit`. تثبّت: عتبة العيّنة الدنيا (لا اقتراح على قِلّة بيانات)، اقتراح
الحذر عند نجاح منخفض، تخفيف الاحتكاك عند نجاح عالٍ، ترجيح كفاءة الماء، والأدلّة.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from core.decision_learning import derive_learning_suggestions  # noqa: E402


def test_min_sample_blocks_noise():
    # 3 قرارات < 5 (الافتراضيّ) ⇒ لا اقتراح
    by_action = {"spray": {"executed": 1, "failed": 2, "water_saved_mm": 0.0}}
    assert derive_learning_suggestions(by_action) == []


def test_low_success_suggests_raise_approvals():
    by_action = {"spray": {"executed": 2, "failed": 8, "water_saved_mm": 0.0}}
    sugg = derive_learning_suggestions(by_action)
    kinds = {s.kind for s in sugg}
    assert "raise_approvals" in kinds
    s = next(s for s in sugg if s.kind == "raise_approvals")
    assert s.action_type == "spray"
    assert s.evidence["success_rate"] == 0.2
    assert 0 < s.confidence <= 1


def test_high_success_suggests_relax_friction():
    by_action = {"spray": {"executed": 19, "failed": 1, "water_saved_mm": 0.0}}
    sugg = derive_learning_suggestions(by_action)
    assert any(s.kind == "relax_friction" for s in sugg)


def test_water_saving_irrigation_suggests_efficiency():
    by_action = {
        "defer_irrigation": {"executed": 10, "failed": 0, "water_saved_mm": 120.0},
    }
    sugg = derive_learning_suggestions(by_action)
    kinds = {s.kind for s in sugg}
    # نجاح عالٍ ⇒ relax_friction، وتوفير ماء ⇒ favor_water_efficiency
    assert "favor_water_efficiency" in kinds
    assert "relax_friction" in kinds


def test_water_efficiency_not_for_non_irrigation():
    by_action = {"spray": {"executed": 10, "failed": 0, "water_saved_mm": 50.0}}
    sugg = derive_learning_suggestions(by_action)
    assert all(s.kind != "favor_water_efficiency" for s in sugg)


def test_mid_success_no_friction_suggestion():
    # نجاح بين 0.6 و0.9 ⇒ لا حذر ولا تخفيف
    by_action = {"spray": {"executed": 7, "failed": 3, "water_saved_mm": 0.0}}
    sugg = derive_learning_suggestions(by_action)
    assert all(s.kind not in ("raise_approvals", "relax_friction") for s in sugg)


def test_suggestions_serializable():
    import json

    by_action = {"spray": {"executed": 2, "failed": 8, "water_saved_mm": 0.0}}
    sugg = derive_learning_suggestions(by_action)
    blob = json.dumps([s.to_dict() for s in sugg], ensure_ascii=False)
    assert json.loads(blob)[0]["kind"] == "raise_approvals"
