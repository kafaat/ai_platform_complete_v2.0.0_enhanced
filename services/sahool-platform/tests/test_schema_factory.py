"""Tests for schema_factory - addresses 'Dual-ID convention-only' gap.
The factory makes Dual-ID DEFAULT, not optional."""
import uuid
from core.canonical_schemas import (
    UserRole, FieldQuality, IrrigationMethod, ObservationSource)
from core.schema_factory import (
    make_tenant, make_user, make_farm, make_field,
    make_crop_season, make_observation, make_recommendation,
    make_default_pair_for_entity)
from core.identity import EntityKind


class TestFactoryAutogenerates:
    """CRITICAL: factory يُولّد id_uuid افتراضياً (يحلّ فجوة المراجعة)."""

    def test_make_tenant_has_uuid(self):
        t = make_tenant(name_ar="جمعية البيضاء")
        assert t.id_uuid is not None
        uuid.UUID(t.id_uuid)   # صالح

    def test_make_user_has_uuid(self):
        u = make_user(tenant_id="tnt_test", role=UserRole.AGRONOMIST,
                     name_ar="مهندس")
        assert u.id_uuid is not None
        uuid.UUID(u.id_uuid)

    def test_make_farm_has_uuid(self):
        f = make_farm(tenant_id="tnt_test", name_ar="مزرعة الشمال")
        assert f.id_uuid is not None

    def test_make_field_has_uuid(self):
        f = make_field(tenant_id="tnt_001", farm_id="frm_01",
                      name_ar="حقل القمح")
        assert f.id_uuid is not None
        uuid.UUID(f.id_uuid)

    def test_make_season_has_uuid(self):
        s = make_crop_season(tenant_id="tnt_001", field_id="fld_01",
                           crop_id="wheat", season_name_ar="صيف 2026",
                           season_year=2026)
        assert s.id_uuid is not None

    def test_make_observation_has_uuid(self):
        o = make_observation(
            tenant_id="t1", field_id="f1", observable_id="ndvi",
            value=0.55, unit="ratio", source=ObservationSource.SENSOR,
            confidence="medium", measured_at="2026-01-01")
        assert o.id_uuid is not None

    def test_make_recommendation_has_uuid(self):
        r = make_recommendation(tenant_id="t1",
                              recommendation_ar="اروِ")
        assert r.id_uuid is not None


class TestReadableIDGeneration:
    """readable id يُولَّد من السياق — لا hash عشوائي."""

    def test_tenant_readable_starts_with_tnt(self):
        t = make_tenant(name_ar="مزرعة x")
        assert t.tenant_id.startswith("tnt_")

    def test_field_readable_starts_with_fld(self):
        f = make_field(tenant_id="t1", farm_id="frm_01", name_ar="حقل")
        assert f.field_id.startswith("fld_")

    def test_recommendation_readable_starts_with_rec(self):
        r = make_recommendation(tenant_id="t1", recommendation_ar="x")
        assert r.rec_id.startswith("rec_")


class TestBackwardCompat:
    """التوافق الخلفي: تمرير readable id يُحترَم."""

    def test_explicit_readable_preserved(self):
        # عند تمرير id قديم (مثل fld_03)، يُحفَظ كما هو
        f = make_field(tenant_id="t1", farm_id="frm_01",
                      name_ar="حقل", field_id_readable="fld_03")
        assert f.field_id == "fld_03"
        # لكنّ id_uuid يُولَّد رغم ذلك
        assert f.id_uuid is not None

    def test_tenant_explicit_id_preserved(self):
        t = make_tenant(name_ar="x", tenant_id_readable="tnt_legacy")
        assert t.tenant_id == "tnt_legacy"
        assert t.id_uuid is not None


class TestUniqueness:
    """كل factory call يُنتج UUID فريداً."""

    def test_multiple_fields_unique_uuids(self):
        # CRITICAL: 100 حقل بنفس البيانات → 100 UUID فريد
        fields = [
            make_field(tenant_id="t1", farm_id="frm_01", name_ar="حقل")
            for _ in range(100)
        ]
        uuids = {f.id_uuid for f in fields}
        assert len(uuids) == 100

    def test_recommendation_uuids_unique(self):
        recs = [make_recommendation(tenant_id="t1", recommendation_ar="x")
                for _ in range(50)]
        uuids = {r.id_uuid for r in recs}
        assert len(uuids) == 50


class TestDefaultsPropagation:
    """factory يحفظ افتراضيات canonical_schemas."""

    def test_field_default_quality_blocked(self):
        # حسب canonical_schemas، الافتراضي BLOCKED
        f = make_field(tenant_id="t1", farm_id="frm_01", name_ar="حقل")
        assert f.quality_state == FieldQuality.BLOCKED

    def test_user_default_active(self):
        u = make_user(tenant_id="t1", role=UserRole.WORKER, name_ar="x")
        assert u.is_active

    def test_season_default_planned(self):
        s = make_crop_season(tenant_id="t1", field_id="f1",
                            crop_id="wheat", season_name_ar="صيف",
                            season_year=2026)
        # SeasonStatus.PLANNED بشكل افتراضي
        assert s.status.value == "planned"


class TestMakeDefaultPair:
    def test_returns_uuid_and_readable(self):
        u, r = make_default_pair_for_entity(EntityKind.FIELD,
                                            context="test")
        uuid.UUID(u)
        assert r.startswith("fld_")
