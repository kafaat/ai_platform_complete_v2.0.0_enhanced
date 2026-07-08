"""حُرّاس موحِّد نموذجَي النتائج (Outcome Reconciler — جسر #3). منطق نقيّ."""

from __future__ import annotations

from core.outcome_reconciler import (
    normalize_outcome_record,
    normalize_recommendation_outcome,
    reconcile_outcomes,
)


class TestNormalize:
    def test_outcome_record_is_decision_effect(self):
        u = normalize_outcome_record(
            {
                "outcome_id": "out_1",
                "decision_id": "dec_9",
                "field_id": "F1",
                "success": True,
                "planned": {"irrigation_mm": 25},
                "actual": {"irrigation_mm": 25},
                "metrics": {"ndvi_delta": 0.06},
            }
        )
        assert u["source_model"] == "outcome_record" and u["kind"] == "decision_effect"
        assert u["decision_id"] == "dec_9" and u["success"] is True
        assert u["recommendation_id"] is None

    def test_recommendation_outcome_is_yield_learning(self):
        u = normalize_recommendation_outcome(
            {
                "outcome_id": 7,
                "recommendation_id": "rec_3",
                "field_id": "F1",
                "season_id": "ssn_2",
                "predicted_yield_t_ha": 4.0,
                "actual_yield_t_ha": 4.4,
                "accepted": True,
                "matured_within_lag": True,
            }
        )
        assert u["source_model"] == "recommendation_outcomes" and u["kind"] == "yield_learning"
        assert u["recommendation_id"] == "rec_3" and u["season_id"] == "ssn_2"
        assert u["result"]["yield_delta_t_ha"] == 0.4
        assert u["success"] is True  # مقبولة + فعليّ ≥ متوقّع


class TestHonestSuccessDerivation:
    def test_unaccepted_has_no_success_verdict(self):
        u = normalize_recommendation_outcome(
            {
                "recommendation_id": "r",
                "predicted_yield_t_ha": 4,
                "actual_yield_t_ha": 5,
                "accepted": False,
            }
        )
        assert u["success"] is None  # لم تُتَّبَع ⇒ لا يُنسَب نجاح

    def test_incomplete_yield_has_no_success(self):
        u = normalize_recommendation_outcome(
            {
                "recommendation_id": "r",
                "predicted_yield_t_ha": 4,
                "actual_yield_t_ha": None,
                "accepted": True,
            }
        )
        assert u["success"] is None  # لم تكتمل الغلّة الفعليّة

    def test_underperformance_is_false(self):
        u = normalize_recommendation_outcome(
            {
                "recommendation_id": "r",
                "predicted_yield_t_ha": 5,
                "actual_yield_t_ha": 3.5,
                "accepted": True,
            }
        )
        assert u["success"] is False


class TestReconcile:
    def _data(self):
        return (
            [
                {
                    "outcome_id": "out_1",
                    "decision_id": "dec_9",
                    "field_id": "F1",
                    "success": True,
                    "planned": {},
                    "actual": {},
                    "metrics": {},
                }
            ],
            [
                {
                    "outcome_id": 7,
                    "recommendation_id": "rec_3",
                    "field_id": "F1",
                    "predicted_yield_t_ha": 4.0,
                    "actual_yield_t_ha": 4.4,
                    "accepted": True,
                }
            ],
        )

    def test_keeps_both_sources_with_counts(self):
        recs, ro = self._data()
        out = reconcile_outcomes(recs, ro)
        assert out["total"] == 2
        assert out["by_source"] == {"outcome_record": 1, "recommendation_outcomes": 1}
        assert out["by_kind"] == {"decision_effect": 1, "yield_learning": 1}

    def test_dispatch_link_joins_the_two_models(self):
        recs, ro = self._data()
        out = reconcile_outcomes(recs, ro, dispatch_links={"rec_3": "dec_9"})
        # الآن كلاهما يشترك dec_9 ⇒ مجموعة مربوطة واحدة (سلسلة سببيّة واحدة).
        assert len(out["linked_groups"]) == 1
        grp = out["linked_groups"][0]
        assert grp["decision_id"] == "dec_9" and len(grp["members"]) == 2

    def test_no_link_keeps_them_separate(self):
        recs, ro = self._data()
        out = reconcile_outcomes(recs, ro)  # بلا dispatch_links
        assert out["linked_groups"] == []

    def test_authoritative_note_declares_complementary(self):
        out = reconcile_outcomes([], [])
        assert "متكاملان لا مكرّران" in out["authoritative_note"]
        assert out["total"] == 0

    def test_empty_inputs_safe(self):
        out = reconcile_outcomes(None, None)
        assert out["total"] == 0 and out["unified"] == []
