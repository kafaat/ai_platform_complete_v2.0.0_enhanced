"""اختبارات كتالوج أنواع الحقول (Field Type Catalog).

تتحقّق من: الكتالوج غير فارغ، المعرّفات فريدة، نوع الهندسة ضمن المسموح، وكلّ نشاط
مسموح به هو **نوع نشاط حقيقيّ** (يُستورَد من core.activity_log كمصدر للحقيقة)،
بالإضافة إلى سلوك get_field_type / activities_for.
"""

from api.field_type_catalog import (
    GEOMETRY_KINDS,
    FieldType,
    activities_for,
    get_field_type,
    list_field_types,
)
from core.activity_log import ActivityType

# مجموعة معرّفات الأنشطة الحقيقيّة كما يعرّفها المصدر الفعليّ (ActivityType).
_REAL_ACTIVITY_IDS = {a.value for a in ActivityType}


class TestCatalogShape:
    def test_catalog_non_empty(self):
        assert len(list_field_types()) > 0

    def test_all_entries_are_field_type(self):
        assert all(isinstance(ft, FieldType) for ft in list_field_types())

    def test_ids_unique(self):
        ids = [ft.id for ft in list_field_types()]
        assert len(ids) == len(set(ids))

    def test_geometry_kind_in_allowed_set(self):
        for ft in list_field_types():
            assert ft.geometry_kind in GEOMETRY_KINDS

    def test_seeded_ids_present(self):
        ids = {ft.id for ft in list_field_types()}
        assert {"open_field", "orchard", "greenhouse", "pasture"} <= ids


class TestActivitiesGrounded:
    def test_every_allowed_activity_is_real(self):
        # كلّ نشاط مسموح به في أيّ نوع حقل لا بدّ أن يكون نوع نشاط حقيقيّاً.
        for ft in list_field_types():
            assert set(ft.allowed_activities) <= _REAL_ACTIVITY_IDS, ft.id

    def test_allowed_activities_non_empty(self):
        assert all(ft.allowed_activities for ft in list_field_types())

    def test_orchard_excludes_seeding(self):
        # المعمّرات: لا بذر روتينيّ (موثّق في الوصف).
        orchard = get_field_type("orchard")
        assert orchard is not None
        assert "seeding" not in orchard.allowed_activities
        assert "pruning" in orchard.allowed_activities


class TestLookups:
    def test_get_field_type_known(self):
        ft = get_field_type("open_field")
        assert ft is not None
        assert ft.id == "open_field"
        assert ft.name_ar

    def test_get_field_type_unknown_returns_none(self):
        assert get_field_type("does_not_exist") is None

    def test_activities_for_returns_tuple(self):
        acts = activities_for("open_field")
        assert isinstance(acts, tuple)
        assert acts == get_field_type("open_field").allowed_activities

    def test_activities_for_unknown_returns_empty(self):
        assert activities_for("nope") == ()
