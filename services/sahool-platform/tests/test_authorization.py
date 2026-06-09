"""Tests for authorization: RBAC + Farm hierarchy + tenant isolation.
Tenant isolation is the hard red line - the most important test category."""
from core.authorization import (
    authorize, has_permission, Permission, AuthDecision,
    farms_accessible_to_user, fields_in_farm_for_user,
    audit_user_permissions, is_safety_critical_permission)
from core.canonical_schemas import UserSchema, FarmSchema, FieldSchema, UserRole


def _user(role: UserRole, tenant_id="tnt_001", farm_access=None,
          is_active=True) -> UserSchema:
    return UserSchema(user_id=f"u_{role.value}", tenant_id=tenant_id,
                     role=role, name_ar="test",
                     farm_ids_access=farm_access or [], is_active=is_active)


class TestTenantIsolation:
    """الخطّ الأحمر — تنفيذ آلي يحرس عزل tenant."""

    def test_cross_tenant_denied(self):
        # CRITICAL: المستخدم في tnt_001 لا يصل لـtnt_999 أبداً
        u = _user(UserRole.OWNER)   # حتى OWNER!
        d = authorize(u, Permission.RECOMMENDATION_VIEW,
                     resource_tenant_id="tnt_999")
        assert not d.allowed
        assert "عزل tenant" in d.reason_ar

    def test_same_tenant_allowed(self):
        u = _user(UserRole.OWNER, "tnt_001")
        d = authorize(u, Permission.RECOMMENDATION_VIEW,
                     resource_tenant_id="tnt_001")
        assert d.allowed

    def test_no_resource_tenant_check_uses_user_tenant(self):
        # إن لم يُحدّد resource_tenant_id → افتراض tenant المستخدم
        u = _user(UserRole.MANAGER)
        d = authorize(u, Permission.FARM_VIEW)   # لا resource_tenant_id
        assert d.allowed


class TestRolePermissions:
    """كل دور يملك ما يحتاجه — لا أقلّ، لا أكثر."""

    def test_owner_has_all_critical_perms(self):
        u = _user(UserRole.OWNER)
        for p in [Permission.FARM_DELETE, Permission.USER_CHANGE_ROLE,
                 Permission.HARVEST_AUTHORIZE]:
            assert has_permission(u, p), f"OWNER يجب أن يملك {p.value}"

    def test_manager_cannot_delete_farm(self):
        # MANAGER إدارة فقط، لا حذف ملكية
        u = _user(UserRole.MANAGER)
        assert not has_permission(u, Permission.FARM_DELETE)

    def test_agronomist_cannot_change_roles(self):
        u = _user(UserRole.AGRONOMIST)
        assert not has_permission(u, Permission.USER_CHANGE_ROLE)

    def test_agronomist_can_approve_pesticide(self):
        # المهندس مسؤول عن الموافقة على المبيدات
        u = _user(UserRole.AGRONOMIST)
        assert has_permission(u, Permission.PESTICIDE_APPROVE)

    def test_agronomist_cannot_authorize_harvest(self):
        # تخطّي PHI يحتاج OWNER (السلامة لا تُتخطّى إلا من المالك)
        u = _user(UserRole.AGRONOMIST)
        assert not has_permission(u, Permission.HARVEST_AUTHORIZE)

    def test_worker_can_execute_not_plan(self):
        u = _user(UserRole.WORKER)
        assert has_permission(u, Permission.ACTIVITY_EXECUTE)
        assert not has_permission(u, Permission.ACTIVITY_PLAN)

    def test_viewer_only_reads(self):
        u = _user(UserRole.VIEWER)
        # كل صلاحياته يجب أن تنتهي بـ:view
        from core.authorization import _ROLE_PERMISSIONS
        for p in _ROLE_PERMISSIONS[UserRole.VIEWER]:
            assert p.value.endswith(":view")


class TestFarmAccess:
    """الطبقة الثالثة: حصر الوصول لمزارع محدّدة."""

    def test_empty_access_means_all_farms(self):
        # CRITICAL: farm_ids_access فارغة = كل مزارع tenant
        u = _user(UserRole.AGRONOMIST, farm_access=[])
        d = authorize(u, Permission.FIELD_VIEW,
                     resource_tenant_id="tnt_001", farm_id="any_farm")
        assert d.allowed

    def test_explicit_access_limits(self):
        u = _user(UserRole.AGRONOMIST, farm_access=["frm_01", "frm_02"])
        d_ok = authorize(u, Permission.FIELD_VIEW,
                        resource_tenant_id="tnt_001", farm_id="frm_01")
        d_no = authorize(u, Permission.FIELD_VIEW,
                        resource_tenant_id="tnt_001", farm_id="frm_99")
        assert d_ok.allowed
        assert not d_no.allowed
        assert "صلاحية على المزرعة" in d_no.reason_ar


class TestInactiveUsers:
    def test_inactive_user_denied_everything(self):
        # CRITICAL: مستخدم معطّل لا يفعل شيئاً
        u = _user(UserRole.OWNER, is_active=False)
        d = authorize(u, Permission.FARM_VIEW, resource_tenant_id="tnt_001")
        assert not d.allowed
        assert "غير نشط" in d.reason_ar

    def test_has_permission_respects_active(self):
        u = _user(UserRole.OWNER, is_active=False)
        assert not has_permission(u, Permission.FARM_VIEW)


class TestFarmHierarchyHelpers:
    def test_farms_accessible_filters_by_tenant(self):
        # CRITICAL: لا يُرجع مزارع من tenant آخر
        farms = [
            FarmSchema(farm_id="f1", tenant_id="tnt_001", name_ar="A"),
            FarmSchema(farm_id="f2", tenant_id="tnt_001", name_ar="B"),
            FarmSchema(farm_id="f3", tenant_id="tnt_999", name_ar="C"),   # tenant آخر
        ]
        u = _user(UserRole.MANAGER, "tnt_001")
        accessible = farms_accessible_to_user(u, farms)
        assert len(accessible) == 2
        assert not any(f.farm_id == "f3" for f in accessible)

    def test_inactive_user_sees_no_farms(self):
        farms = [FarmSchema(farm_id="f1", tenant_id="tnt_001", name_ar="A")]
        u = _user(UserRole.OWNER, is_active=False)
        assert farms_accessible_to_user(u, farms) == []


class TestSafetyCritical:
    def test_pesticide_is_safety_critical(self):
        assert is_safety_critical_permission(Permission.PESTICIDE_APPROVE)

    def test_harvest_authorize_critical(self):
        assert is_safety_critical_permission(Permission.HARVEST_AUTHORIZE)

    def test_role_change_critical(self):
        assert is_safety_critical_permission(Permission.USER_CHANGE_ROLE)

    def test_view_not_critical(self):
        assert not is_safety_critical_permission(Permission.FARM_VIEW)


class TestAudit:
    def test_audit_returns_full_inventory(self):
        u = _user(UserRole.AGRONOMIST)
        audit = audit_user_permissions(u)
        assert audit["role"] == "agronomist"
        assert audit["permissions_count"] > 0
        assert "tenant" in audit["summary_ar"]
