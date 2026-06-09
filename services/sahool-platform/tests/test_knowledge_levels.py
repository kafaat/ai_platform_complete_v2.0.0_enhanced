"""Tests for the unified knowledge-level matrix: each source's epistemic ceiling,
and the unified fusion rule (confidence <= min ceiling). Guards matrix consistency."""
from core.knowledge_levels import (
    fuse_confidence, ceiling_for_source, level_of_source,
    KnowledgeLevel, level_info)


class TestCeilings:
    def test_generative_never_high(self):
        # CRITICAL: المستوى التوليدي لا يصل HIGH أبداً
        assert ceiling_for_source("llm") == "low"
        assert ceiling_for_source("chatbot") == "low"

    def test_lab_can_be_high(self):
        assert ceiling_for_source("lab") == "high"

    def test_physics_can_be_high(self):
        assert ceiling_for_source("fao56") == "high"

    def test_guess_is_none(self):
        assert ceiling_for_source("guess") == "none"

    def test_unknown_source_defaults_to_guess(self):
        # مصدر غير معروف → أحوط (استكشافي، سقف none)
        assert ceiling_for_source("random_xyz") == "none"

    def test_spectral_indices_are_inductive_medium(self):
        # القرائن الطيفية: سقف medium (لا تحكم كالمختبر)
        for s in ("ndvi", "bsi", "si"):
            assert ceiling_for_source(s) == "medium"


class TestUnifiedFusion:
    def test_lowest_ceiling_governs(self):
        # CRITICAL: الانصهar يأخذ أدنى سقف (lab=high + llm=low → low)
        c, _ = fuse_confidence(["lab", "llm"], proposed="high")
        assert c == "low"

    def test_physics_plus_lab_allows_high(self):
        c, _ = fuse_confidence(["fao56", "lab"], proposed="high")
        assert c == "high"

    def test_any_guess_drops_to_none(self):
        # تخمين واحد يُسقِط الكل (الصمت قرار)
        c, _ = fuse_confidence(["fao56", "lab", "guess"], proposed="high")
        assert c == "none"

    def test_empty_sources_none(self):
        c, _ = fuse_confidence([], proposed="high")
        assert c == "none"

    def test_proposed_cannot_exceed_ceiling(self):
        # حتى لو اقترحنا high، السقف يحكم
        c, _ = fuse_confidence(["ndvi"], proposed="high")
        assert c == "medium"


class TestMatrixConsistency:
    def test_levels_ordered_by_fsi(self):
        # اليقين المرجعي يتناقص مع المستوى (الرياضي أعلى، الاستكشافي أدنى)
        assert level_info(KnowledgeLevel.MATHEMATICAL).fsi > level_info(KnowledgeLevel.GUESS).fsi
        assert level_info(KnowledgeLevel.ANALYTICAL).fsi > level_info(KnowledgeLevel.GENERATIVE).fsi

    def test_matches_evidence_class_indication_ceiling(self):
        # الاتساق مع evidence_class: القرينة الطيفية سقفها منخفض هناك أيضاً
        from core.evidence_class import classify_evidence
        # المؤشّر الطيفي = قرينة (INDICATION) سقفها low/medium، لا high
        ec = classify_evidence("R5", "satellite")
        assert ec.max_confidence in ("low", "medium")
        # ومستواه هنا استقرائي سقفه medium — متّسق (كلاهما ليس high)
        assert ceiling_for_source("si") in ("low", "medium")
