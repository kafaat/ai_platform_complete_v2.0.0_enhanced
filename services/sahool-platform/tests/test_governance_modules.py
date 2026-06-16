"""اختبارات وحدات الحوكمة/الذكاء الخمس (offline صرف — بلا قاعدة/شبكة).

تغطّي عقد كلّ وحدة:
  • rbac_governance      — who_can / permission_matrix / preview_role_change
  • learning_activation  — البوّابة المدفوعة بالبيانات (خاملة بصدق قبل العتبة)
  • economic_adaptation  — تكييف يحترم استقلاليّة المزارع (كلّ الخيارات مرئيّة)
  • decision_regression  — بوّابة تحقّق على الحالات المرجعيّة (الجوف/السنيدار)
  • fleet_health         — كشف صمت الأجهزة الاستباقي مع تمييز الحرجيّة

المبدأ المُتحقَّق منه: الطبقات المعرفيّة/الحوكميّة صادقة (display أو حوكمة)،
وطبقة التكييف الاقتصادي وحدها توصية فعليّة تُبقي كلّ الخيارات مرئيّة.
"""

from core.decision_regression import (
    GOLDEN_CASES,
    evaluate_threshold_change,
    run_regression,
)
from core.economic_adaptation import (
    adapt_recommendation,
    get_capacity_profiles,
    infer_capacity_tier,
)
from core.learning_activation import (
    MIN_COMPLETED_OUTCOMES,
    DataFlowSnapshot,
    activation_summary,
    evaluate_activation,
)
from core.rbac_governance import permission_matrix, preview_role_change, who_can

# ─── rbac_governance ─────────────────────────────────────────────────────


def test_permission_matrix_lists_all_roles():
    m = permission_matrix()
    assert m["roles"], "يجب أن تُرجِع المصفوفة أدواراً"
    assert m["total_permissions"] > 0
    # كلّ دور له عدّ صلاحيّات + علم الحرجيّة
    for role in m["roles"]:
        assert "count" in m["matrix"][role]
        assert "has_safety_critical" in m["matrix"][role]
    # الصلاحيّات الحرجة مُميَّزة صراحةً
    assert isinstance(m["safety_critical_permissions"], list)


def test_who_can_returns_roles_for_permission():
    from core.authorization import Permission

    perm = next(iter(Permission))  # أيّ صلاحيّة حقيقيّة
    result = who_can(perm)
    assert result["permission"] == perm.value
    assert isinstance(result["roles_with_permission"], list)
    assert result["role_count"] == len(result["roles_with_permission"])
    assert isinstance(result["is_safety_critical"], bool)


def test_preview_role_change_reports_delta():
    roles = permission_matrix()["roles"]
    # تغيير دور إلى نفسه ⇒ لا اكتساب ولا فقدان
    same = preview_role_change(roles[0], roles[0])
    assert same["gained_count"] == 0
    assert same["lost_count"] == 0


def test_preview_role_change_rejects_invalid_role():
    out = preview_role_change("not_a_real_role", "also_fake")
    assert "error_ar" in out


# ─── who_can: قرارات تفويض سلوكيّة (من يقدر فعلاً على ماذا) ───────────────
# تُثبِّت نتائج التفويض الحقيقيّة لكلّ زوج (دور+فعل)، لا مجرّد الأنواع/الوجود.
# المرجع الوحيد للحقيقة: _ROLE_PERMISSIONS في core.authorization.


def test_who_can_harvest_authorize_is_owner_only():
    # تخطّي بوّابة PHI (إذن الحصاد) صلاحيّة حرجة قصوى ⇒ المالك حصراً.
    # المهندس لا يملكها عمداً (التعليق في الوحدة: HARVEST_AUTHORIZE يحتاج OWNER).
    from core.authorization import Permission

    out = who_can(Permission.HARVEST_AUTHORIZE)
    assert out["roles_with_permission"] == ["owner"]
    assert out["role_count"] == 1
    assert out["is_safety_critical"] is True
    # تأكيد صريح على المنع: لا أحد سوى المالك (مدير/مهندس/عامل/مشاهد ممنوعون)
    for denied in ("manager", "agronomist", "worker", "viewer"):
        assert denied not in out["roles_with_permission"]


def test_who_can_change_role_is_owner_only_no_privilege_escalation():
    # تغيير الأدوار = مفتاح التصعيد. لو ملكه المدير لاستطاع ترقية نفسه مالكاً.
    # يجب أن يبقى حكراً على المالك (حارس تصعيد الامتياز الجوهري).
    from core.authorization import Permission

    out = who_can(Permission.USER_CHANGE_ROLE)
    assert out["roles_with_permission"] == ["owner"]
    assert out["is_safety_critical"] is True
    assert "manager" not in out["roles_with_permission"]


def test_who_can_pesticide_approve_owner_and_agronomist_only():
    # الموافقة على المبيدات (سلامة) ⇒ المالك + المهندس الزراعي فقط.
    # العامل ينفّذ ميدانيّاً لكنه لا يوافق؛ المشاهد قراءة فقط.
    from core.authorization import Permission

    out = who_can(Permission.PESTICIDE_APPROVE)
    assert set(out["roles_with_permission"]) == {"owner", "agronomist"}
    assert out["is_safety_critical"] is True
    for denied in ("manager", "worker", "viewer"):
        assert denied not in out["roles_with_permission"]


def test_who_can_recommendation_override_is_owner_only():
    # تجاوز توصية المحرّك قرار حرج (يبطل ضمانة السلامة) ⇒ المالك حصراً.
    from core.authorization import Permission

    out = who_can(Permission.RECOMMENDATION_OVERRIDE)
    assert out["roles_with_permission"] == ["owner"]
    assert out["is_safety_critical"] is True


def test_who_can_farm_delete_is_owner_only():
    # حذف مزرعة عمليّة هدّامة لا رجعة فيها ⇒ المالك حصراً (لا المدير).
    from core.authorization import Permission

    out = who_can(Permission.FARM_DELETE)
    assert out["roles_with_permission"] == ["owner"]
    assert out["is_safety_critical"] is True
    assert "manager" not in out["roles_with_permission"]


def test_who_can_user_invite_owner_and_manager_not_agronomist():
    # دعوة مستخدم (إدارة فريق، غير حرجة) ⇒ المالك + المدير. المدير يدعو
    # لكن لا يغيّر أدواراً (الفصل بين USER_INVITE وUSER_CHANGE_ROLE).
    from core.authorization import Permission

    out = who_can(Permission.USER_INVITE)
    assert set(out["roles_with_permission"]) == {"owner", "manager"}
    assert out["is_safety_critical"] is False
    for denied in ("agronomist", "worker", "viewer"):
        assert denied not in out["roles_with_permission"]


def test_who_can_activity_execute_excludes_agronomist_and_viewer():
    # تنفيذ نشاط ميداني (إكمال/تخطّي) ⇒ المالك + المدير + العامل.
    # المهندس يخطّط ولا ينفّذ؛ المشاهد قراءة فقط — تمييز التخطيط عن التنفيذ.
    from core.authorization import Permission

    out = who_can(Permission.ACTIVITY_EXECUTE)
    assert set(out["roles_with_permission"]) == {"owner", "manager", "worker"}
    assert "agronomist" not in out["roles_with_permission"]
    assert "viewer" not in out["roles_with_permission"]


def test_who_can_farm_view_is_granted_to_every_role():
    # الرؤية الأساسيّة (farm:view) ممنوحة لكلّ الأدوار الخمسة دون استثناء —
    # حدّ القراءة الأدنى المشترك (حتى المشاهد يراها).
    from core.authorization import Permission

    out = who_can(Permission.FARM_VIEW)
    assert set(out["roles_with_permission"]) == {
        "owner",
        "manager",
        "agronomist",
        "worker",
        "viewer",
    }
    assert out["role_count"] == 5
    assert out["is_safety_critical"] is False


def test_who_can_master_data_manage_excludes_worker_and_viewer():
    # إدارة البيانات المرجعيّة ⇒ المالك + المدير + المهندس. العامل والمشاهد
    # يريانها (master_data:view) لكن لا يديرانها (تمييز العرض عن الإدارة).
    from core.authorization import Permission

    out = who_can(Permission.MASTER_DATA_MANAGE)
    assert set(out["roles_with_permission"]) == {"owner", "manager", "agronomist"}
    assert "worker" not in out["roles_with_permission"]
    assert "viewer" not in out["roles_with_permission"]


def test_viewer_is_read_only_no_mutating_permission():
    # المشاهد قراءة فقط بصدق: لا يملك أيّ صلاحيّة كتابة/تنفيذ/إدارة.
    # نتحقّق سلوكيّاً بأنّ كلّ فعل مُغيِّر لا يضمّ "viewer" في حامليه.
    from core.authorization import Permission

    mutating = [
        Permission.FARM_CREATE,
        Permission.FARM_EDIT,
        Permission.FARM_DELETE,
        Permission.FIELD_CREATE,
        Permission.ACTIVITY_EXECUTE,
        Permission.OBSERVATION_RECORD,
        Permission.PESTICIDE_APPROVE,
        Permission.USER_INVITE,
        Permission.USER_CHANGE_ROLE,
        Permission.MASTER_DATA_MANAGE,
        Permission.IRRIGATION_MANAGE,
    ]
    for perm in mutating:
        assert "viewer" not in who_can(perm)["roles_with_permission"], (
            f"المشاهد يجب ألّا يملك صلاحيّة مُغيِّرة: {perm.value}"
        )


def test_every_safety_critical_permission_denied_to_viewer_and_worker():
    # حدّ امتياز: لا الدور المشاهد ولا العامل يملك أيّ صلاحيّة حرجة (سلامة).
    # نشتقّ القائمة الحرجة من الوحدة نفسها (لا قائمة مكرّرة في الاختبار).
    from core.authorization import Permission, is_safety_critical_permission

    critical = [p for p in Permission if is_safety_critical_permission(p)]
    assert critical, "يجب أن توجد صلاحيّات حرجة معرّفة"
    for perm in critical:
        holders = who_can(perm)["roles_with_permission"]
        assert "viewer" not in holders, f"المشاهد يملك صلاحيّة حرجة: {perm.value}"
        assert "worker" not in holders, f"العامل يملك صلاحيّة حرجة: {perm.value}"


# ─── has_permission / authorize: الفرض الفعلي + fail-closed ───────────────


def _make_user(role, *, is_active=True, tenant_id="t1", farm_ids=None):
    """مساعد: يبني UserSchema حقيقيّاً لاختبار قرارات الفرض الفعليّة."""
    from core.canonical_schemas import UserRole, UserSchema

    return UserSchema(
        user_id="u1",
        tenant_id=tenant_id,
        role=UserRole(role),
        name_ar="مستخدم اختبار",
        farm_ids_access=farm_ids or [],
        is_active=is_active,
    )


def test_has_permission_allows_owner_denies_viewer_for_delete():
    # الفرض الفعلي يطابق مصفوفة الأدوار: المالك يحذف، المشاهد لا.
    from core.authorization import Permission, has_permission

    owner = _make_user("owner")
    viewer = _make_user("viewer")
    assert has_permission(owner, Permission.FARM_DELETE) is True
    assert has_permission(viewer, Permission.FARM_DELETE) is False


def test_has_permission_fail_closed_for_inactive_user():
    # مستخدم مُعطَّل = منع مطلق حتى لو كان مالكاً (Fail closed: شكّ = منع).
    from core.authorization import Permission, has_permission

    inactive_owner = _make_user("owner", is_active=False)
    assert has_permission(inactive_owner, Permission.FARM_VIEW) is False


def test_authorize_denies_cross_tenant_even_with_permission():
    # الخطّ الأحمر المطلق: المالك يملك الصلاحيّة لكن عزل tenant يمنع الوصول
    # لمورد مستأجر آخر — الفرض لا يكفي بصلاحيّة الدور وحدها.
    from core.authorization import Permission, authorize

    owner = _make_user("owner", tenant_id="t1")
    decision = authorize(owner, Permission.FARM_VIEW, resource_tenant_id="t2")
    assert decision.allowed is False
    assert "tenant" in decision.reason_ar


def test_authorize_denies_farm_outside_access_scope():
    # وصول مزرعة مُقيَّد: المالك له farm_ids_access=['f1'] فقط ⇒ يُمنَع عن 'f9'
    # رغم امتلاكه الصلاحيّة (الطبقة الثالثة من الحراسة).
    from core.authorization import Permission, authorize

    scoped_owner = _make_user("owner", tenant_id="t1", farm_ids=["f1"])
    denied = authorize(scoped_owner, Permission.FIELD_VIEW, resource_tenant_id="t1", farm_id="f9")
    assert denied.allowed is False
    allowed = authorize(scoped_owner, Permission.FIELD_VIEW, resource_tenant_id="t1", farm_id="f1")
    assert allowed.allowed is True


def test_preview_role_change_worker_to_owner_flags_escalation():
    # ترقية عامل ⇒ مالك تصعيد امتياز: تكتسب صلاحيّات حرجة ⇒ يجب أن تُعلَّم.
    out = preview_role_change("worker", "owner")
    assert out["is_escalation"] is True
    assert out["gained_count"] > 0
    # تكتسب صلاحيّات حرجة فعليّة (تغيير أدوار + موافقة مبيدات + حذف مزرعة...)
    assert "user:change_role" in out["gained_safety_critical"]
    assert "harvest:authorize" in out["gained_safety_critical"]


def test_preview_role_change_owner_to_viewer_is_demotion_not_escalation():
    # تنزيل مالك ⇒ مشاهد: لا اكتساب (is_escalation=False) لكن فقدان حرج كبير
    # يجب الإفصاح عنه للتأكّد أنّه مقصود.
    out = preview_role_change("owner", "viewer")
    assert out["is_escalation"] is False
    assert out["gained_count"] == 0
    assert out["lost_count"] > 0
    assert "user:change_role" in out["lost_safety_critical"]


# ─── learning_activation ─────────────────────────────────────────────────


def test_empty_snapshot_is_dormant_not_active():
    # لا بيانات ⇒ خاملة بصدق، لا تتظاهر بالتعلّم
    snap = DataFlowSnapshot(
        tenant_id="t1",
        completed_outcomes=0,
        total_recommendations=0,
        accepted_recommendations=0,
        outcomes_within_lag=0,
    )
    out = evaluate_activation(snap)
    assert out["state"] == "dormant"
    assert out["can_activate"] is False
    assert out["progress_pct"] == 0.0
    assert out["blockers"], "يجب أن يُفصِح عمّا ينقص"


def test_full_threshold_snapshot_becomes_ready():
    # تدفّق ناضج يبلغ كلّ العتبات ⇒ جاهزة للتفعيل
    n = MIN_COMPLETED_OUTCOMES
    snap = DataFlowSnapshot(
        tenant_id="t1",
        completed_outcomes=n,
        total_recommendations=n,
        accepted_recommendations=n,  # قبول 100%
        outcomes_within_lag=n,  # نضج زمني 100%
    )
    out = evaluate_activation(snap)
    assert out["state"] == "ready"
    assert out["can_activate"] is True
    assert out["blockers"] == []


def test_activation_summary_is_per_tenant():
    snaps = [
        DataFlowSnapshot("a", 0, 0, 0, 0),
        DataFlowSnapshot(
            "b",
            MIN_COMPLETED_OUTCOMES,
            MIN_COMPLETED_OUTCOMES,
            MIN_COMPLETED_OUTCOMES,
            MIN_COMPLETED_OUTCOMES,
        ),
    ]
    summary = activation_summary(snaps)
    assert summary["total_tenants"] == 2
    assert summary["ready_to_activate"] == 1  # سيادة البيانات: B فقط جاهز


# ─── economic_adaptation ─────────────────────────────────────────────────


def test_infer_capacity_tier_from_area():
    assert infer_capacity_tier(1.0).value == "smallholder"
    assert infer_capacity_tier(5.0).value == "mid"
    assert infer_capacity_tier(50.0).value == "commercial"
    assert infer_capacity_tier(None).value == "smallholder"  # افتراض حذر


def test_adapt_recommendation_keeps_all_options_visible():
    # المبدأ الجوهري: التكييف يرتّب لكن لا يُخفي — استقلاليّة المزارع
    options = [
        {"name_ar": "قمح", "upfront_cost_level": "low"},
        {"name_ar": "عنب", "upfront_cost_level": "high"},
    ]
    out = adapt_recommendation(options, area_ha=1.0)  # صغير الحوزة
    assert out["all_options_visible"] is True
    assert len(out["adapted_options"]) == len(options)  # لا حذف
    # صغير الحوزة: الأقلّ تكلفة أوّلاً
    assert out["adapted_options"][0]["upfront_cost_level"] == "low"
    # هذه توصية فعليّة (لا مجرّد عرض)
    assert out["display_only"] is False
    assert out["used_in_decision_engine"] is True
    assert out["agency_note_ar"]


def test_get_capacity_profiles_has_three_tiers():
    profiles = get_capacity_profiles()
    tiers = {t["tier"] for t in profiles["tiers"]}
    assert tiers == {"smallholder", "mid", "commercial"}


# ─── decision_regression ─────────────────────────────────────────────────


def test_golden_cases_all_pass_at_current_thresholds():
    # العتبات الحاليّة يجب أن تُصنّف كلّ الحالات المرجعيّة صحيحاً
    out = run_regression()
    assert out["total"] == len(GOLDEN_CASES)
    assert out["all_pass"] is True, f"إخفاقات: {out['failures']}"
    assert out["failed"] == 0


def test_regression_detects_threshold_change():
    # عتبة ملوحة فضفاضة جدّاً (EC≥2) تُدهور حالات نظيفة ⇒ تُكشف
    out = run_regression(ec_threshold=2.0)
    assert out["all_pass"] is False
    assert out["failed"] > 0


def test_evaluate_threshold_change_rejects_regression():
    verdict = evaluate_threshold_change(new_ec_threshold=2.0)
    assert verdict["regressed"] is True
    # تغيير غير مُدهور (نفس العتبة) يُقبَل
    safe = evaluate_threshold_change(new_ec_threshold=4.0)
    assert safe["regressed"] is False


# ─── fleet_health ────────────────────────────────────────────────────────


def test_assess_fleet_flags_critical_silent_device():
    from api.fleet_health import DeviceHealthRecord, assess_fleet

    records = [
        # حسّاس رطوبة صامت 200د (عتبته 30) في حقل نشط ⇒ حرج صامت
        DeviceHealthRecord("d1", "حسّاس وادي", "soil_moisture", "fld_1", 200.0),
        # كاميرا نشطة ⇒ ليست صامتة
        DeviceHealthRecord("d2", "كاميرا", "camera", "fld_1", 5.0),
    ]
    out = assess_fleet(records, active_field_ids={"fld_1"})
    assert out["total_devices"] == 2
    assert out["silent"] == 1
    assert out["critical_silent"] == 1
    assert "🔴" in out["fleet_status_ar"]


def test_assess_fleet_healthy_when_all_active():
    from api.fleet_health import DeviceHealthRecord, assess_fleet

    records = [DeviceHealthRecord("d1", "حسّاس", "soil_moisture", "fld_1", 5.0)]
    out = assess_fleet(records)
    assert out["silent"] == 0
    assert "🟢" in out["fleet_status_ar"]
