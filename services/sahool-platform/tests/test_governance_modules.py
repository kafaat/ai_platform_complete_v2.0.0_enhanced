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
