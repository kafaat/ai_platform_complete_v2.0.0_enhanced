"""Tests for identity (Dual-ID Strategy).
Internal UUID for engineering safety, external readable for human support.
The review insight: not 'either/or' but 'both, for different purposes'."""

import uuid

from core.identity import (
    EntityKind,
    IdentityIndex,
    IdentityPair,
    generate_readable,
    generate_uuid,
    identity_summary,
    new_identity,
    upgrade_legacy_id,
)


class TestUUIDGeneration:
    def test_generated_uuid_is_valid(self):
        u = generate_uuid()
        # يجب أن يكون UUID صالحاً قابلاً للتفسير
        uuid.UUID(u)  # لا يرفع exception

    def test_uuids_are_unique(self):
        # CRITICAL: 100 UUID في تتابع لا تتكرر
        ids = {generate_uuid() for _ in range(100)}
        assert len(ids) == 100


class TestReadableGeneration:
    def test_readable_includes_kind_prefix(self):
        r = generate_readable(EntityKind.FIELD, context="yem_alb", counter=203)
        assert r.startswith("fld_")
        assert "yem_alb" in r
        assert r.endswith("203")

    def test_readable_cleans_invalid_chars(self):
        # CRITICAL: نمط readable صارم (a-z, 0-9, _)
        r = generate_readable(EntityKind.FARM, context="Al-Bayda Region!")
        # الحروف الكبيرة تصبح صغيرة، - تصبح _، ! يُحذف
        assert r == "frm_al_bayda_region"

    def test_readable_without_context_uses_timestamp(self):
        # context فارغ → timestamp لتجنّب التضارب
        r = generate_readable(EntityKind.RECOMMENDATION)
        assert r.startswith("rec_")
        assert len(r) > 6  # rec_ + timestamp

    def test_consecutive_calls_unique(self):
        # حتى بدون counter، الـtimestamp يجعلها فريدة
        r1 = generate_readable(EntityKind.OBSERVATION, context="test")
        r2 = generate_readable(EntityKind.OBSERVATION, context="test", counter=1)
        r3 = generate_readable(EntityKind.OBSERVATION, context="test", counter=2)
        # الثلاثة يجب أن تكون فريدة (على الأقل r2 ≠ r3)
        assert len({r1, r2, r3}) == 3


class TestIdentityPair:
    def test_valid_pair_constructs(self):
        p = IdentityPair(uuid=generate_uuid(), readable="fld_test_01", kind=EntityKind.FIELD)
        assert p.kind == EntityKind.FIELD

    def test_invalid_uuid_rejected(self):
        # CRITICAL: لا اختراع UUID — يجب أن يكون صالحاً
        try:
            IdentityPair(uuid="not-a-uuid", readable="fld_x", kind=EntityKind.FIELD)
            raise AssertionError("كان يجب رفض UUID غير صالح")
        except ValueError as e:
            assert "UUID غير صالح" in str(e)

    def test_kind_prefix_mismatch_rejected(self):
        # CRITICAL: البادئة يجب أن تطابق النوع (لا "fld_xxx" لـRECOMMENDATION)
        try:
            IdentityPair(uuid=generate_uuid(), readable="fld_wrong", kind=EntityKind.RECOMMENDATION)
            raise AssertionError("كان يجب رفض mismatch البادئة")
        except ValueError as e:
            assert "بادئة" in str(e)

    def test_invalid_readable_pattern_rejected(self):
        # نمط readable صارم — لا مسافات، لا حروف كبيرة، لا رموز خاصّة
        try:
            IdentityPair(uuid=generate_uuid(), readable="Bad ID!", kind=EntityKind.FIELD)
            raise AssertionError("كان يجب رفض نمط غير صالح")
        except ValueError:
            pass


class TestIdentityIndex:
    """فهرس التحويل ثنائي الاتجاه."""

    def test_resolve_by_uuid(self):
        idx = IdentityIndex()
        pair = new_identity(EntityKind.FIELD, context="test_01")
        idx.register(pair)
        resolved = idx.resolve(pair.uuid)
        assert resolved.readable == pair.readable

    def test_resolve_by_readable(self):
        idx = IdentityIndex()
        pair = new_identity(EntityKind.RECOMMENDATION, context="irr_2026")
        idx.register(pair)
        resolved = idx.resolve(pair.readable)
        assert resolved.uuid == pair.uuid

    def test_resolve_unknown_returns_none(self):
        # CRITICAL: لا اختراع — معرّف غير معروف → None
        idx = IdentityIndex()
        assert idx.resolve("unknown_id") is None
        assert idx.resolve(generate_uuid()) is None  # UUID صحيح لكن غير مُسجَّل

    def test_to_uuid_conversion(self):
        idx = IdentityIndex()
        pair = new_identity(EntityKind.FARM, context="test")
        idx.register(pair)
        assert idx.to_uuid(pair.readable) == pair.uuid

    def test_to_readable_conversion(self):
        idx = IdentityIndex()
        pair = new_identity(EntityKind.USER, context="user_01")
        idx.register(pair)
        assert idx.to_readable(pair.uuid) == pair.readable


class TestConflictDetection:
    """منع التضارب — لا overwrite صامت."""

    def test_duplicate_uuid_rejected(self):
        # CRITICAL: تسجيل UUID مكرّر = خطأ صريح
        idx = IdentityIndex()
        p1 = new_identity(EntityKind.FIELD, context="a")
        p2 = IdentityPair(
            uuid=p1.uuid,
            readable="fld_b",  # نفس UUID
            kind=EntityKind.FIELD,
        )
        idx.register(p1)
        try:
            idx.register(p2)
            raise AssertionError("كان يجب رفض UUID مكرّر")
        except ValueError as e:
            assert "مُسجَّل بالفعل" in str(e)

    def test_duplicate_readable_rejected(self):
        # readable مكرّر أيضاً = خطأ
        idx = IdentityIndex()
        p1 = new_identity(EntityKind.FIELD, context="same")
        p2 = IdentityPair(uuid=generate_uuid(), readable=p1.readable, kind=EntityKind.FIELD)
        idx.register(p1)
        try:
            idx.register(p2)
            raise AssertionError("كان يجب رفض readable مكرّر")
        except ValueError:
            pass


class TestLegacyMigration:
    """الترقية من النواة الحالية — التوافق الخلفي محفوظ."""

    def test_valid_legacy_preserved(self):
        # CRITICAL: fld_03 الحالي يبقى كـreadable، يُضاف UUID
        upgraded = upgrade_legacy_id("fld_03", EntityKind.FIELD)
        assert upgraded.readable == "fld_03"
        assert upgraded.uuid  # غير فارغ
        uuid.UUID(upgraded.uuid)  # صالح

    def test_legacy_with_wrong_prefix_regenerated(self):
        # بادئة لا تطابق النوع → readable جديد يحفظ القديم في context
        upgraded = upgrade_legacy_id("xyz_07", EntityKind.FIELD)
        assert upgraded.readable.startswith("fld_")
        assert "xyz_07" in upgraded.readable.replace("__", "_")

    def test_legacy_invalid_format_cleaned(self):
        upgraded = upgrade_legacy_id("Old-ID-2023", EntityKind.FIELD)
        # يصبح: fld_legacy_old_id_2023
        assert upgraded.readable.startswith("fld_legacy_")


class TestCanonicalSchemasIntegration:
    """التوافق الخلفي مع canonical_schemas — id_uuid اختياري."""

    def test_field_schema_default_id_uuid_none(self):
        from core.canonical_schemas import FieldSchema

        f = FieldSchema(field_id="fld_01", tenant_id="t1", farm_id="frm_01", name_ar="x")
        assert hasattr(f, "id_uuid")
        assert f.id_uuid is None  # default للتوافق الخلفي

    def test_field_schema_accepts_uuid(self):
        from core.canonical_schemas import FieldSchema

        u = generate_uuid()
        f = FieldSchema(field_id="fld_01", tenant_id="t1", farm_id="frm_01", name_ar="x", id_uuid=u)
        assert f.id_uuid == u
