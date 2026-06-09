"""Tests for skills_registry (Tool-Orchestrated Agronomic Intelligence).
Reviewer insight #14: AI shouldn't 'know everything' - it should orchestrate tools.
This registry IS the orchestration layer. No LLM, no chatbot - just explicit
catalog with rigorous signatures."""

from core.skills_registry import (
    ConfidenceCeiling,
    SkillCategory,
    SkillSignature,
    all_skills,
    available_for_field,
    by_category,
    get,
    model_versions_snapshot,
    register,
    registry_health,
    safety_critical_skills,
    unregister,
)


class TestRegistryBasics:
    def test_default_skills_registered_on_import(self):
        # 12 محرّك + 2 موصّل + 2 بيانات + 2 تعلّم = 16
        skills = all_skills()
        assert len(skills) >= 16
        assert get("fao56_etc") is not None
        assert get("pesticide_phi_gate") is not None

    def test_unknown_skill_returns_none(self):
        # CRITICAL: لا اختراع — skill غير مسجَّلة → None لا dummy
        assert get("nonexistent_skill") is None

    def test_duplicate_registration_rejected(self):
        # CRITICAL: لا overwrite صامت — حماية من تعارض النسخ
        try:
            register(
                SkillSignature(
                    name="fao56_etc",
                    version="v9.9",
                    category=SkillCategory.AGRONOMIC,
                    description_ar="dup",
                    required_inputs=[],
                    optional_inputs=[],
                    outputs=[],
                    requires_quality_grade="READY",
                    confidence_ceiling=ConfidenceCeiling.HIGH,
                )
            )
            raise AssertionError("كان يجب رفض التكرار")
        except ValueError as e:
            assert "مُسجَّلة بالفعل" in str(e)


class TestEligibilityFiltering:
    """Setup before prompting: لا نعرض skill بلا متطلّبات متوفّرة."""

    def test_blocked_field_only_data_skills(self):
        # CRITICAL: حقل BLOCKED لا يحصل على توصيات زراعية
        eligible = available_for_field("BLOCKED", {"tenant_id", "field_id", "sensor_type", "value"})
        # يقبل sensor_intake لأن requires_quality_grade=BLOCKED
        assert any(s.name == "sensor_intake" for s in eligible)
        # لا يقبل fao56 لأن متطلباته غير متوفّرة + يحتاج LIMITED
        assert not any(s.name == "fao56_etc" for s in eligible)

    def test_ready_field_with_inputs_unlocks_advanced(self):
        # حقل READY مع بيانات كاملة يفتح كل الإمكانات
        eligible = available_for_field(
            "READY",
            {
                "et0",
                "kc",
                "growth_stage",
                "calibration_residuals",
                "crop_id",
                "last_spray_date",
                "phi_days",
                "harvest_planned_date",
            },
        )
        names = {s.name for s in eligible}
        assert "fao56_etc" in names
        assert "yield_interval_conformal" in names
        assert "pesticide_phi_gate" in names

    def test_missing_required_input_blocks_skill(self):
        # CRITICAL: مدخل إلزامي ناقص → skill لا تظهر (لا توصية بناقص)
        eligible = available_for_field("READY", {"et0", "kc"})  # ناقص growth_stage
        assert not any(s.name == "fao56_etc" for s in eligible)


class TestSafetyClassification:
    def test_pesticide_phi_marked_safety_critical(self):
        # CRITICAL: PHI gate من الـskills الحرجة (السلامة لا تُتخطّى)
        skill = get("pesticide_phi_gate")
        assert skill.safety_critical
        assert skill in safety_critical_skills()

    def test_suitability_safety_critical(self):
        # ملاءمة المحصول حرجة (قرار 5-20 سنة للأشجار)
        skill = get("suitability_assessment")
        assert skill.safety_critical

    def test_irrigation_not_safety_critical(self):
        # الري ليس حرجاً للسلامة (خطؤه لا يضرّ المستهلك)
        skill = get("fao56_etc")
        assert not skill.safety_critical


class TestVersionSnapshot:
    """جسر إلى recommendation_replay لكشف drift."""

    def test_snapshot_includes_all_registered(self):
        snapshot = model_versions_snapshot()
        assert len(snapshot) >= 16
        assert "fao56_etc" in snapshot
        assert snapshot["fao56_etc"] == "v2.1"

    def test_snapshot_is_serializable_for_provenance(self):
        # CRITICAL: يجب أن يكون قابلاً للحفظ في JSON
        import json

        snapshot = model_versions_snapshot()
        serialized = json.dumps(snapshot)
        restored = json.loads(serialized)
        assert restored == snapshot


class TestCategoryFiltering:
    def test_safety_category_includes_phi(self):
        safety = by_category(SkillCategory.SAFETY)
        assert any(s.name == "pesticide_phi_gate" for s in safety)

    def test_connector_category_separate(self):
        connectors = by_category(SkillCategory.CONNECTOR)
        # الموصّلات ليست محرّكات
        for s in connectors:
            assert s.category == SkillCategory.CONNECTOR


class TestRegistryHealth:
    def test_health_reports_all_documented(self):
        health = registry_health()
        # كل skill افتراضي يجب أن يكون موثّقاً
        assert health["issues"] == []
        assert "التوثيق كامل" in health["summary_ar"]

    def test_undocumented_skill_flagged(self):
        # سجّل skill ناقصة التوثيق ثم تأكّد أنها تُكتشف
        try:
            register(
                SkillSignature(
                    name="test_undocumented_xyz",
                    version="v0.1",
                    category=SkillCategory.AGRONOMIC,
                    description_ar="",  # وصف فارغ
                    required_inputs=[],
                    optional_inputs=[],
                    outputs=[],  # مخرجات فارغة
                    requires_quality_grade="READY",
                    confidence_ceiling=ConfidenceCeiling.LOW,
                )
            )
            health = registry_health()
            assert len(health["issues"]) >= 2  # وصف + مخرجات
        finally:
            unregister("test_undocumented_xyz")


class TestUnregister:
    def test_unregister_returns_true_when_exists(self):
        # سجّل ثم احذف
        register(
            SkillSignature(
                name="temp_test_skill",
                version="v0.1",
                category=SkillCategory.DIAGNOSTIC,
                description_ar="مؤقت",
                required_inputs=["x"],
                optional_inputs=[],
                outputs=["y"],
                requires_quality_grade="LIMITED",
                confidence_ceiling=ConfidenceCeiling.LOW,
            )
        )
        assert unregister("temp_test_skill") is True
        assert get("temp_test_skill") is None

    def test_unregister_returns_false_when_missing(self):
        assert unregister("nonexistent") is False
