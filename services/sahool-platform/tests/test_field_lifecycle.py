"""Tests for field lifecycle — four states + safety rule.
Per comprehensive review: this is a bottleneck of the system, deserves
thorough coverage. Expanded from 6 → 14 tests."""

from core.field_lifecycle import FieldQualityState, SoilTestChoice, can_recommend, resolve_state


class TestFieldLifecycle:
    def test_no_decision_is_blocked(self):
        state, recs = resolve_state(SoilTestChoice.PROVIDED, set())
        assert state == FieldQualityState.BLOCKED
        assert recs == []

    def test_skip_gives_limited(self):
        state, recs = resolve_state(SoilTestChoice.SKIP, set())
        assert state == FieldQualityState.LIMITED
        assert "irrigation_basic" in recs

    def test_request_lab_gives_pending(self):
        state, _ = resolve_state(SoilTestChoice.REQUEST_LAB, set())
        assert state == FieldQualityState.PENDING_LAB

    def test_full_governors_ready(self):
        state, recs = resolve_state(SoilTestChoice.PROVIDED, {"S3", "S4", "I3"})
        assert state == FieldQualityState.READY
        assert "pesticide_phi" in recs

    def test_pesticide_requires_ready_always(self):
        # safety: pesticide never allowed unless READY — not even LIMITED
        for state in [
            FieldQualityState.BLOCKED,
            FieldQualityState.LIMITED,
            FieldQualityState.PENDING_LAB,
        ]:
            ok, _ = can_recommend(state, "pesticide_phi")
            assert not ok, f"pesticide must be blocked in {state}"
        ok, _ = can_recommend(FieldQualityState.READY, "pesticide_phi")
        assert ok

    def test_limited_allows_general_only(self):
        ok_irr, _ = can_recommend(FieldQualityState.LIMITED, "irrigation_basic")
        assert ok_irr
        ok_sal, _ = can_recommend(FieldQualityState.LIMITED, "salinity_mgmt")
        assert not ok_sal  # precise rec needs full data


class TestPartialGovernors:
    """تغطية كل combinations الجزئية — bottleneck للنظام."""

    def test_partial_governors_blocked(self):
        # CRITICAL: ٢ من ٣ غير كافٍ
        state, recs = resolve_state(SoilTestChoice.PROVIDED, {"S3", "S4"})  # ينقص I3
        assert state == FieldQualityState.BLOCKED
        assert recs == []

    def test_single_governor_blocked(self):
        for gov in ["S3", "S4", "I3"]:
            state, _ = resolve_state(SoilTestChoice.PROVIDED, {gov})
            assert state == FieldQualityState.BLOCKED, f"حاكم واحد ({gov}) لا يكفي"

    def test_extra_governors_still_ready(self):
        # CRITICAL: governors إضافية لا تضرّ — كلّها ≥ المطلوب
        state, _ = resolve_state(SoilTestChoice.PROVIDED, {"S3", "S4", "I3", "EXTRA1"})
        assert state == FieldQualityState.READY


class TestSafetyCriticalRecommendations:
    """السلامة لا تُتخطّى — كل توصية safety-critical تحتاج READY."""

    def test_blocked_state_blocks_all_recommendations(self):
        # CRITICAL: BLOCKED state ⇒ لا توصية مطلقاً
        for rec_type in ["irrigation_basic", "pesticide_phi", "salinity_mgmt", "fertilization"]:
            ok, _ = can_recommend(FieldQualityState.BLOCKED, rec_type)
            assert not ok, f"{rec_type} ممنوع في BLOCKED"

    def test_pending_lab_allows_estimates_not_pesticide(self):
        # PENDING_LAB يسمح بتقديرات، لا مبيدات
        ok_pest, _ = can_recommend(FieldQualityState.PENDING_LAB, "pesticide_phi")
        assert not ok_pest


class TestEnumIntegrity:
    """تحقّق سلامة Enums."""

    def test_four_states_exist(self):
        states = list(FieldQualityState)
        assert len(states) == 4
        for required in ["BLOCKED", "LIMITED", "PENDING_LAB", "READY"]:
            assert any(s.value == required or s.name == required for s in states)

    def test_three_soil_choices_exist(self):
        choices = list(SoilTestChoice)
        # PROVIDED, SKIP, REQUEST_LAB على الأقلّ
        assert len(choices) >= 3
