"""Tests for canonical_schemas (data contracts).
Each schema versioned, validation strict, multi-tenant by design."""
from core.canonical_schemas import (
    TenantSchema, UserSchema, FarmSchema, FieldSchema, CropSeasonSchema,
    ObservationSchema, RecommendationSchema, UserRole, FieldQuality,
    IrrigationMethod, SeasonStatus, TenantStatus, ObservationSource,
    validate_entity, entities_catalog, SCHEMA_VERSIONS)


class TestSchemaCreation:
    def test_tenant_with_required_fields(self):
        t = TenantSchema(tenant_id="tnt_001", name_ar="مزرعة الشمال")
        assert t.tenant_id == "tnt_001"
        assert t.status == TenantStatus.ACTIVE   # default
        assert t.schema_version == "1.0"

    def test_user_requires_role(self):
        u = UserSchema(user_id="u1", tenant_id="t1",
                      role=UserRole.AGRONOMIST, name_ar="مهندس")
        assert u.role == UserRole.AGRONOMIST
        assert u.is_active     # default

    def test_field_links_to_farm(self):
        # CRITICAL: Field يجب أن يحمل farm_id (Farm hierarchy)
        f = FieldSchema(field_id="fld_1", tenant_id="t1",
                       farm_id="frm_1", name_ar="حقل")
        assert f.farm_id == "frm_1"
        assert f.quality_state == FieldQuality.BLOCKED   # default

    def test_crop_season_uniqueness_implicit(self):
        # القيد العالمي: (field_id, season_id) فريد - يُفرض في DB
        s = CropSeasonSchema(season_id="s1", tenant_id="t1", field_id="f1",
                            crop_id="wheat", season_name_ar="صيف 2026",
                            season_year=2026)
        assert s.crop_id == "wheat"
        assert s.status == SeasonStatus.PLANNED
        assert s.irrigation_method == IrrigationMethod.RAINFED


class TestValidation:
    def test_complete_field_passes(self):
        result = validate_entity(
            {"field_id": "fld_01", "tenant_id": "tnt_001", "farm_id": "frm_01",
             "name_ar": "اسم"}, FieldSchema)
        assert result.valid

    def test_missing_required_fails(self):
        # CRITICAL: name_ar ناقص → invalid + missing مذكور
        result = validate_entity(
            {"field_id": "fld_01", "tenant_id": "tnt_001", "farm_id": "frm_01"},
            FieldSchema)
        assert not result.valid
        assert "name_ar" in result.missing_fields

    def test_short_tenant_id_invalid(self):
        # tenant_id < 3 حروف = غير صالح (يمنع "t" أو "1")
        result = validate_entity(
            {"field_id": "f", "tenant_id": "t", "farm_id": "fa",
             "name_ar": "x"}, FieldSchema)
        assert not result.valid
        assert any("tenant_id" in v for v in result.invalid_values)

    def test_missing_schema_version_warns_not_fails(self):
        # CRITICAL: عدم تحديد schema_version = تحذير لا رفض
        result = validate_entity(
            {"field_id": "fld_01", "tenant_id": "tnt_001", "farm_id": "frm_01",
             "name_ar": "x"}, FieldSchema)
        assert result.valid
        assert any("schema_version" in w for w in result.warnings_ar)


class TestCatalog:
    def test_all_seven_entities_listed(self):
        catalog = entities_catalog()
        expected = {"Tenant", "User", "Farm", "Field",
                   "CropSeason", "Observation", "Recommendation"}
        assert set(catalog.keys()) == expected

    def test_each_entity_has_version_and_required(self):
        catalog = entities_catalog()
        for name, info in catalog.items():
            assert "version" in info
            assert "required" in info
            assert len(info["required"]) >= 1

    def test_recommendation_v2_for_provenance(self):
        # Recommendation v2.0 — تطوّر بسبب provenance
        assert SCHEMA_VERSIONS["Recommendation"] == "2.0"


class TestEnumsCompleteness:
    """التحقّق من اكتمال Enums الجوهرية."""

    def test_user_roles_are_five(self):
        # المراجعة الاستراتيجية حدّدت 5 أدوار
        roles = list(UserRole)
        assert len(roles) == 5
        for r in [UserRole.OWNER, UserRole.MANAGER, UserRole.AGRONOMIST,
                 UserRole.WORKER, UserRole.VIEWER]:
            assert r in roles

    def test_field_quality_matches_lifecycle(self):
        # FieldQuality يجب أن يطابق field_lifecycle
        states = [s.value for s in FieldQuality]
        for s in ["BLOCKED", "LIMITED", "PENDING_LAB", "READY"]:
            assert s in states

    def test_observation_source_includes_historical(self):
        # historical_loader يستخدم HISTORICAL
        sources = list(ObservationSource)
        assert ObservationSource.HISTORICAL in sources
        assert ObservationSource.SENSOR in sources
        assert ObservationSource.LAB in sources
