"""حُرّاس سلامة مرجعيّة حلقة التوصية (جسر #5) — كشف الأيتام لا فرض FK. منطق نقيّ."""

from __future__ import annotations

from core.loop_referential_integrity import (
    find_orphan_dispatches,
    find_orphan_outcomes,
    reconciliation_report,
)


class TestOrphanOutcomes:
    def test_orphan_outcome_detected(self):
        rows = [
            {"outcome_id": "o1", "decision_id": "dec_1"},
            {"outcome_id": "o2", "decision_id": "dec_ghost"},
        ]
        orphans = find_orphan_outcomes(rows, {"dec_1"})
        assert [r["outcome_id"] for r in orphans] == ["o2"]

    def test_non_orphan_is_clean(self):
        rows = [{"outcome_id": "o1", "decision_id": "dec_1"}]
        assert find_orphan_outcomes(rows, {"dec_1", "dec_2"}) == []

    def test_empty_decision_id_not_orphan(self):
        # المُعرِّف الفارغ/None لا مرجع له ⇒ لا يُعَدّ يتيماً.
        rows = [
            {"outcome_id": "o1", "decision_id": None},
            {"outcome_id": "o2", "decision_id": ""},
            {"outcome_id": "o3"},
        ]
        assert find_orphan_outcomes(rows, set()) == []

    def test_none_and_empty_inputs_safe(self):
        assert find_orphan_outcomes(None, None) == []
        assert find_orphan_outcomes([], None) == []
        assert find_orphan_outcomes(None, {"dec_1"}) == []

    def test_known_ids_accept_list_or_set(self):
        rows = [{"outcome_id": "o1", "decision_id": "dec_1"}]
        assert find_orphan_outcomes(rows, ["dec_1"]) == []
        assert find_orphan_outcomes(rows, ["dec_x"]) == rows


class TestOrphanDispatches:
    def test_orphan_dispatch_detected(self):
        rows = [
            {"id": "d1", "recommendation_id": "rec_1"},
            {"id": "d2", "recommendation_id": "rec_ghost"},
        ]
        orphans = find_orphan_dispatches(rows, {"rec_1"})
        assert [r["id"] for r in orphans] == ["d2"]

    def test_empty_recommendation_id_not_orphan(self):
        rows = [{"id": "d1", "recommendation_id": None}, {"id": "d2"}]
        assert find_orphan_dispatches(rows, set()) == []


class TestReconciliationReport:
    def test_clean_when_no_orphans(self):
        rep = reconciliation_report(
            outcome_rows=[{"outcome_id": "o1", "decision_id": "dec_1"}],
            known_decision_ids={"dec_1"},
            dispatch_rows=[{"id": "d1", "recommendation_id": "rec_1"}],
            known_recommendation_ids={"rec_1"},
        )
        assert rep["clean"] is True
        assert rep["orphan_outcome_count"] == 0
        assert rep["orphan_dispatch_count"] == 0
        assert rep["orphan_outcome_ratio"] == 0.0
        assert rep["orphan_dispatch_ratio"] == 0.0

    def test_ratios_and_counts(self):
        rep = reconciliation_report(
            outcome_rows=[
                {"outcome_id": "o1", "decision_id": "dec_1"},
                {"outcome_id": "o2", "decision_id": "ghost"},
                {"outcome_id": "o3", "decision_id": "ghost2"},
                {"outcome_id": "o4", "decision_id": "dec_1"},
            ],
            known_decision_ids={"dec_1"},
            dispatch_rows=[
                {"id": "d1", "recommendation_id": "rec_1"},
                {"id": "d2", "recommendation_id": "ghost"},
            ],
            known_recommendation_ids={"rec_1"},
        )
        assert rep["clean"] is False
        assert rep["orphan_outcome_count"] == 2
        assert rep["total_outcomes"] == 4
        assert rep["orphan_outcome_ratio"] == 0.5
        assert rep["orphan_dispatch_count"] == 1
        assert rep["total_dispatches"] == 2
        assert rep["orphan_dispatch_ratio"] == 0.5

    def test_empty_inputs_clean_with_null_ratios(self):
        rep = reconciliation_report()
        assert rep["clean"] is True
        assert rep["total_outcomes"] == 0
        assert rep["total_dispatches"] == 0
        assert rep["orphan_outcome_ratio"] is None
        assert rep["orphan_dispatch_ratio"] is None

    def test_note_declares_detection_not_enforcement(self):
        rep = reconciliation_report()
        assert "كشف لا فرض" in rep["note_ar"]
        assert "FK" in rep["note_ar"]
