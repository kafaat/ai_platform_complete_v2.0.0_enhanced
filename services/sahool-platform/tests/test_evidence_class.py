"""Tests for the indication-vs-evidence distinction: spectral indices are indications (don't govern), lab analyses are evidence (govern)."""

from core.evidence_class import EvidenceClass, classify_evidence, enforce_indication_ceiling


class TestEvidenceClassification:
    def test_lab_salinity_is_evidence(self):
        r = classify_evidence("S3", "governing")
        assert r.evidence_class == EvidenceClass.EVIDENCE
        assert r.can_govern_decision is True
        assert r.can_lift_blocked is True

    def test_spectral_salinity_is_indication(self):
        # SI (spectral salinity index) is an indication, NOT proof
        r = classify_evidence("R5", "diagnostic")
        assert r.evidence_class == EvidenceClass.INDICATION
        assert r.can_govern_decision is False
        assert r.can_lift_blocked is False

    def test_indication_capped_at_low_confidence(self):
        r = classify_evidence("R4", "diagnostic")
        assert r.max_confidence == "low"

    def test_evidence_allows_high_confidence(self):
        r = classify_evidence("S4", "governing")
        assert r.max_confidence == "high"

    def test_unknown_type_defaults_to_indication(self):
        # SAFE DEFAULT: unknown → treat as mere indication, never as proof
        r = classify_evidence("X9", "unknown_type")
        assert r.evidence_class == EvidenceClass.INDICATION
        assert r.can_govern_decision is False


class TestCeilingEnforcement:
    def test_indication_high_confidence_capped(self):
        # CORE RULE: an indication can never be promoted to evidence-level confidence
        r = enforce_indication_ceiling("R5", "diagnostic", "high")
        assert r["was_capped"] is True
        assert r["allowed_confidence"] == "low"

    def test_evidence_keeps_high_confidence(self):
        r = enforce_indication_ceiling("S3", "governing", "high")
        assert r["was_capped"] is False
        assert r["allowed_confidence"] == "high"

    def test_indication_low_confidence_not_capped(self):
        r = enforce_indication_ceiling("R4", "diagnostic", "low")
        assert r["was_capped"] is False


class TestCorroboration:
    def test_single_indication_no_corroboration(self):
        from core.evidence_class import corroborate_indications

        r = corroborate_indications("ملوحة", [("SI", True)])
        assert not r.agree
        assert r.elevated_confidence == "low"

    def test_same_source_limited_elevation(self):
        # CRITICAL: indications from the SAME source share error → limited elevation
        from core.evidence_class import corroborate_indications

        r = corroborate_indications(
            "ملوحة", [("SI", True), ("NDVI", True), ("BSI", True)]
        )  # all optical
        assert r.n_independent_sources == 1
        assert r.elevated_confidence == "low_plus"  # not high

    def test_independent_sources_elevate_more(self):
        from core.evidence_class import corroborate_indications

        r = corroborate_indications(
            "ملوحة", [("SI", True), ("RVI", True), ("district_context", True)]
        )  # 3 sources
        assert r.n_independent_sources == 3
        assert r.elevated_confidence in ("medium", "high")

    def test_strict_governor_never_lifts_blocked(self):
        # THE KEY LIMIT: corroboration never lifts BLOCKED for strict governors
        from core.evidence_class import corroborate_indications

        r = corroborate_indications(
            "ملوحة",
            [("SI", True), ("RVI", True), ("district_context", True)],
            is_strict_governor=True,
        )
        assert r.lifts_blocked is False
        assert r.can_govern is False
        assert "دليل" in r.note_ar  # explicitly says lab evidence still required

    def test_strict_governor_capped_at_medium(self):
        # even 3 independent sources can't push a strict governor to "high"
        from core.evidence_class import corroborate_indications

        r = corroborate_indications(
            "ملوحة",
            [("SI", True), ("RVI", True), ("district_context", True)],
            is_strict_governor=True,
        )
        assert r.elevated_confidence == "medium"  # not high

    def test_disagreeing_indications_no_elevation(self):
        from core.evidence_class import corroborate_indications

        r = corroborate_indications("ملوحة", [("SI", True), ("NDVI", False)])
        assert not r.agree

    def test_corroboration_never_lifts_blocked_even_nonstrict(self):
        # corroboration raises confidence/priority but never lifts BLOCKED
        from core.evidence_class import corroborate_indications

        r = corroborate_indications(
            "إجهاد", [("NDVI", True), ("RVI", True), ("CWSI", True)], is_strict_governor=False
        )
        assert r.lifts_blocked is False


class TestConflictHandling:
    def test_minority_conflict_downgrades(self):
        # FIX: a conflicting indication must weaken confidence, not be ignored
        from core.evidence_class import corroborate_indications

        all_agree = corroborate_indications(
            "ملوحة", [("SI", True), ("RVI", True), ("district_context", True)]
        )
        with_conflict = corroborate_indications(
            "ملوحة", [("SI", True), ("RVI", True), ("NDVI", False)]
        )
        # confidence with conflict must be lower than full agreement
        levels = {"low": 0, "low_plus": 1, "medium": 2, "high": 3}
        assert levels[with_conflict.elevated_confidence] < levels[all_agree.elevated_confidence]

    def test_majority_conflict_no_corroboration(self):
        from core.evidence_class import corroborate_indications

        r = corroborate_indications("ملوحة", [("SI", True), ("RVI", False), ("NDVI", False)])
        assert r.agree is False
        assert r.elevated_confidence == "low"
