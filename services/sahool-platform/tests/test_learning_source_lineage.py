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


class TestTraceableIsNotApproved:
    """U07 (التدقيق الموحَّد 2026-09-13): وجود معرّف مصدر ≠ اعتماد زراعيّ."""

    def test_traceable_update_without_review_is_unapproved(self):
        r = resolve_learning_source({"source_type": "human_feedback", "source_id": "hf_1"})
        assert r["traceability_status"] == "traceable"
        assert r["review_status"] == "unreviewed"
        assert r["agronomically_approved"] is False
        assert r["review"] is None

    def test_approval_requires_reviewer_verdict_and_evidence(self):
        base = {"source_type": "recommendation_outcome", "source_id": "out_1"}
        full = resolve_learning_source(
            {
                **base,
                "review": {
                    "reviewer_id": "agronomist:7",
                    "verdict": "approved",
                    "evidence_ids": ["or_9"],
                    "reviewed_at": "2026-09-13",
                },
            }
        )
        assert full["review_status"] == "approved" and full["agronomically_approved"] is True
        assert full["review"]["evidence_ids"] == ["or_9"]
        no_evidence = resolve_learning_source(
            {**base, "review": {"reviewer_id": "agronomist:7", "verdict": "approved"}}
        )
        assert no_evidence["review_status"] == "unreviewed"
        no_reviewer = resolve_learning_source(
            {**base, "review": {"verdict": "approved", "evidence_ids": ["or_9"]}}
        )
        assert no_reviewer["review_status"] == "unreviewed"
        rejected = resolve_learning_source(
            {**base, "source": {"review": {"reviewer_id": "a", "verdict": "rejected"}}}
        )
        assert rejected["review_status"] == "rejected"
        assert rejected["agronomically_approved"] is False

    def test_summary_separates_traceable_from_approved(self):
        rows = [
            {"source_type": "human_feedback", "traceability_status": "traceable"},
            {
                "source_type": "human_feedback",
                "traceability_status": "traceable",
                "review_status": "approved",
            },
        ]
        s = summarize_learning_sources(rows)
        assert s["traceable"] == 2
        assert s["agronomically_approved"] == 1
        assert s["by_review_status"] == {"unreviewed": 1, "approved": 1}

    def test_blank_evidence_ids_do_not_approve(self):
        """Copilot على #1001: `[" "]` ليس دليلاً."""
        r = resolve_learning_source(
            {
                "source_type": "human_feedback",
                "source_id": "hf_1",
                "review": {
                    "reviewer_id": "a",
                    "verdict": "approved",
                    "evidence_ids": [" ", "", None, 7],
                },
            }
        )
        assert r["review_status"] == "unreviewed" and r["agronomically_approved"] is False
        # قائمةٌ مختلطة (عضوٌ صالح + عضوٌ خاطئ) تُرفَض كلُّها — لا ترشيحَ جزئيّ (Copilot على #1001).
        mixed = resolve_learning_source(
            {
                "source_type": "human_feedback",
                "source_id": "hf_1",
                "review": {"reviewer_id": "a", "verdict": "approved", "evidence_ids": ["ok_1", 7]},
            }
        )
        assert mixed["review_status"] == "unreviewed" and mixed["review"]["evidence_ids"] == []
        ok = resolve_learning_source(
            {
                "source_type": "human_feedback",
                "source_id": "hf_1",
                "review": {"reviewer_id": "a", "verdict": "approved", "evidence_ids": ["  or_9 "]},
            }
        )
        assert ok["review_status"] == "approved" and ok["review"]["evidence_ids"] == ["or_9"]

    def test_non_string_reviewer_is_not_a_reviewer(self):
        """Copilot على #1001: `reviewer_id: 7` كان يمرّ صادقاً فيُعتمَد بلا هويّة مراجِع صالحة."""
        for bad in (7, True, {"id": "a"}, ["a"], 0.5):
            r = resolve_learning_source(
                {
                    "source_type": "human_feedback",
                    "source_id": "hf_1",
                    "review": {"reviewer_id": bad, "verdict": "approved", "evidence_ids": ["e1"]},
                }
            )
            assert r["review_status"] == "unreviewed", bad
            assert r["review"]["reviewer_id"] is None
        rejected = resolve_learning_source(
            {
                "source_type": "human_feedback",
                "source_id": "hf_1",
                "review": {"reviewer_id": 7, "verdict": "rejected", "evidence_ids": []},
            }
        )
        assert rejected["review_status"] == "unreviewed"  # رفضٌ بلا مراجِع صالح لا يُحتسَب أيضاً

    def test_scalar_evidence_ids_are_not_a_list_of_evidence(self):
        """Copilot على #1001: `evidence_ids: "claim-1"` كان يُقطَّع حروفاً فيُعتمَد بلا قائمة."""
        for scalar in ("claim-1", 7, {"id": "x"}, True):
            r = resolve_learning_source(
                {
                    "source_type": "human_feedback",
                    "source_id": "hf_1",
                    "review": {"reviewer_id": "a", "verdict": "approved", "evidence_ids": scalar},
                }
            )
            assert r["review_status"] == "unreviewed", scalar
            assert r["review"]["evidence_ids"] == []
        # قائمةُ JSON وحدَها مقبولة — الصفُّ والمجموعة مرفوضان (ترتيبُ المجموعة غيرُ حتميّ فتختلف
        # بصمةُ التدقيق لمدخل واحد؛ Copilot على #1001).
        for seq in (("e1",), {"e1"}, frozenset({"e1"})):
            r = resolve_learning_source(
                {
                    "source_type": "human_feedback",
                    "source_id": "hf_1",
                    "review": {"reviewer_id": "a", "verdict": "approved", "evidence_ids": seq},
                }
            )
            assert r["review_status"] == "unreviewed", seq
        ok = resolve_learning_source(
            {
                "source_type": "human_feedback",
                "source_id": "hf_1",
                "review": {"reviewer_id": "a", "verdict": "approved", "evidence_ids": ["e1"]},
            }
        )
        assert ok["review_status"] == "approved"
