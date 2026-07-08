"""حُرّاس نَسَب مصدر التعلّم (Learning Source Lineage — جسر #2). منطق نقيّ."""

from __future__ import annotations

from core.learning_source_lineage import (
    classify_traceability,
    resolve_learning_source,
    summarize_learning_sources,
)


class TestTraceableSources:
    def test_update_from_outcome_carries_lineage(self):
        # (1) تحديث من نتيجة توصية يحمل نَسَباً كاملاً ⇒ traceable + applies.
        r = resolve_learning_source(
            {
                "source_type": "recommendation_outcome",
                "source_id": "out_123",
                "field_id": "F1",
                "season_id": "ssn_9",
                "recommendation_id": "rec_5",
                "decision_id": "dec_2",
            }
        )
        assert r["traceability_status"] == "traceable"
        assert r["applies"] is True
        assert r["field_id"] == "F1" and r["recommendation_id"] == "rec_5"

    def test_update_from_human_feedback_carries_lineage(self):
        # (2) تحديث من تغذية بشريّة راجعة ⇒ traceable.
        r = resolve_learning_source({"source_type": "human_feedback", "source_id": "hf_1"})
        assert r["traceability_status"] == "traceable" and r["applies"] is True

    def test_nested_source_block_supported(self):
        r = resolve_learning_source(
            {"source": {"source_type": "outcome_record", "source_id": "or_7", "field_id": "F2"}}
        )
        assert r["applies"] is True and r["field_id"] == "F2"


class TestUntraceableDoesNotApply:
    def test_missing_source_type_rejected_and_not_applied(self):
        # (3) تحديث بلا مصدر ⇒ rejected_untraceable ولا يُطبِّق تغيير سياسة.
        r = resolve_learning_source({"update_id": "u1", "action": "apply"})
        assert r["traceability_status"] == "rejected_untraceable"
        assert r["applies"] is False

    def test_invalid_source_type_rejected(self):
        r = resolve_learning_source({"source_type": "random_noise", "source_id": "x"})
        assert r["traceability_status"] == "rejected_untraceable"
        assert r["applies"] is False

    def test_valid_type_without_id_is_pending_not_applied(self):
        # نوع صحيح لكن بلا معرّف ⇒ pending_review (قرينة ناقصة، لا تُطبَّق).
        r = resolve_learning_source({"source_type": "execution_feedback", "source_id": ""})
        assert r["traceability_status"] == "pending_review"
        assert r["applies"] is False


class TestSummaryShowsSourceCounts:
    def test_learning_summary_source_counts(self):
        # (4) مُلخّص التعلّم يعرض أعداد المصادر + نسبة المُتتبَّع.
        rows = [
            {"source_type": "recommendation_outcome", "traceability_status": "traceable"},
            {"source_type": "human_feedback", "traceability_status": "traceable"},
            {"source_type": None, "traceability_status": "rejected_untraceable"},
            {"traceability_status": None},  # سجلّ قديم ⇒ unverified
        ]
        s = summarize_learning_sources(rows)
        assert s["total"] == 4 and s["traceable"] == 2 and s["untraceable"] == 2
        assert s["by_traceability_status"]["traceable"] == 2
        assert s["by_traceability_status"]["unverified"] == 1
        assert s["traceable_ratio"] == 0.5

    def test_empty_summary_honest(self):
        s = summarize_learning_sources([])
        assert s["total"] == 0 and s["traceable_ratio"] is None


class TestNoOrphanClassifierTotal:
    def test_classifier_is_total_no_orphan(self):
        # (5) المُصنِّف كلّيّ: أيّ مُدخَل يُنتِج حالةً معروفة (لا يتيم بلا حكم).
        valid = {"traceable", "pending_review", "rejected_untraceable"}
        cases = [
            (None, None),
            ("", ""),
            ("human_feedback", None),
            ("human_feedback", "id"),
            ("bogus", "id"),
            ("outcome_record", ""),
        ]
        for stype, sid in cases:
            assert classify_traceability(stype, sid) in valid

    def test_resolve_always_sets_status_and_applies(self):
        for upd in ({}, {"source_type": "x"}, {"source_id": "y"}, {"source": {}}):
            r = resolve_learning_source(upd)
            assert r["traceability_status"] in {
                "traceable",
                "pending_review",
                "rejected_untraceable",
            }
            assert isinstance(r["applies"], bool)
