"""Tests for Execution Control Plane (ECP) - structural enforcement.
Addresses the review's central point: 'convention vs structural enforcement'."""

from core.execution_control_plane import (
    CallRecord,
    EntryPointType,
    GovernanceMode,
    _bootstrap_known_entry_points,
    audit_call_log,
    bypass_alert_summary,
    call_stats,
    get_mode,
    governed,
    is_approved_entry_point,
    register_entry_point,
    reset_ecp_state,
    seal_direct_engine_access,
    set_mode,
    unregister_entry_point,
)


class TestEntryPointRegistration:
    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_known_entry_points_registered_on_bootstrap(self):
        # CRITICAL: safe_delivery + orchestrate يجب أن تكون مُسجَّلة
        assert is_approved_entry_point("core.recommendation_bridge.safe_delivery")
        assert is_approved_entry_point("core.internal_orchestrator.orchestrate_recommendation")

    def test_unknown_function_not_approved(self):
        # CRITICAL: لا اختراع — دالة غير مُسجَّلة → False
        assert not is_approved_entry_point("random.unregistered.fn")

    def test_register_new_entry_point(self):
        register_entry_point("test.new.fn", EntryPointType.CLI_TOOL)
        assert is_approved_entry_point("test.new.fn")

    def test_unregister(self):
        register_entry_point("test.temp", EntryPointType.TEST)
        assert unregister_entry_point("test.temp")
        assert not is_approved_entry_point("test.temp")


class TestGovernanceMode:
    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_default_is_observation(self):
        # CRITICAL: التطبيق التدرّجي — observation افتراضياً
        assert get_mode() == GovernanceMode.OBSERVATION

    def test_mode_transition_observation_to_strict(self):
        set_mode(GovernanceMode.WARNING)
        assert get_mode() == GovernanceMode.WARNING
        set_mode(GovernanceMode.STRICT)
        assert get_mode() == GovernanceMode.STRICT

    def test_set_mode_returns_previous(self):
        set_mode(GovernanceMode.OBSERVATION)
        prev = set_mode(GovernanceMode.WARNING)
        assert prev == GovernanceMode.OBSERVATION


class TestGovernedDecorator:
    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_governed_logs_call(self):
        @governed(EntryPointType.INTERNAL_SERVICE)
        def test_fn(x):
            return x + 1

        test_fn(5)
        stats = call_stats()
        assert stats["total_calls"] >= 1

    def test_governed_captures_duration(self):
        @governed(EntryPointType.INTERNAL_SERVICE)
        def slow_fn():
            return "x"

        slow_fn()
        log = audit_call_log(last_n=10)
        assert any(r.duration_ms is not None and r.duration_ms >= 0 for r in log)

    def test_governed_captures_failures(self):
        @governed(EntryPointType.INTERNAL_SERVICE)
        def failing_fn():
            raise ValueError("test error")

        try:
            failing_fn()
        except ValueError:
            pass

        failures = audit_call_log(last_n=10, only_failures=True)
        assert len(failures) >= 1
        assert all(not r.success for r in failures)


class TestStrictModeEnforcement:
    """CRITICAL: structural enforcement — bypass يُرفع exception."""

    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_strict_mode_blocks_unregistered_call(self):
        set_mode(GovernanceMode.STRICT)

        @governed(EntryPointType.INTERNAL_SERVICE, require_governance=True)
        def will_be_orphaned():
            return "x"

        # نُلغي تسجيله (محاكاة bypass attempt)
        from core.execution_control_plane import _APPROVED_ENTRY_POINTS

        qualname = next(k for k in _APPROVED_ENTRY_POINTS if "will_be_orphaned" in k)
        unregister_entry_point(qualname)

        try:
            will_be_orphaned()
            raise AssertionError("كان يجب رفع PermissionError")
        except PermissionError as e:
            assert "STRICT" in str(e)
            assert "safe_delivery" in str(e) or "orchestrate" in str(e)

    def test_observation_mode_does_not_block(self):
        # في observation: نسجّل، لا نرفض
        set_mode(GovernanceMode.OBSERVATION)

        @governed(EntryPointType.INTERNAL_SERVICE, require_governance=True)
        def fn():
            return "ok"

        # حتى لو ألغينا التسجيل، observation لا يرفض
        from core.execution_control_plane import _APPROVED_ENTRY_POINTS

        qualname = next(k for k in _APPROVED_ENTRY_POINTS if "fn" in k)
        unregister_entry_point(qualname)
        # يجب ألّا يرفع
        result = fn()
        assert result == "ok"

    def test_bypass_attempt_recorded(self):
        # CRITICAL: محاولة bypass تُسجَّل للـforensic
        set_mode(GovernanceMode.STRICT)

        @governed(EntryPointType.INTERNAL_SERVICE, require_governance=True)
        def orphan_fn():
            return "x"

        from core.execution_control_plane import _APPROVED_ENTRY_POINTS

        qualname = next(k for k in _APPROVED_ENTRY_POINTS if "orphan_fn" in k)
        unregister_entry_point(qualname)

        try:
            orphan_fn()
        except PermissionError:
            pass

        alert = bypass_alert_summary()
        assert alert["count"] >= 1
        assert "⚠️" in alert["summary_ar"]


class TestSealing:
    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_seal_excludes_generate_recommendation(self):
        # CRITICAL: __all__ يخفي generate_recommendation
        result = seal_direct_engine_access()
        assert result["sealed"]
        assert "generate_recommendation" not in result["exposed_symbols"]

    def test_seal_keeps_public_types(self):
        # Recommendation, FarmerView, etc. تبقى مكشوفة (data types)
        result = seal_direct_engine_access()
        exposed = result["exposed_symbols"]
        assert "Recommendation" in exposed
        assert "FarmerView" in exposed

    def test_after_seal_import_star_does_not_expose_engine(self):
        # CRITICAL: التحقّق الآلي من السلوك الفعلي
        seal_direct_engine_access()
        from core import recommendation_engine

        assert hasattr(recommendation_engine, "__all__")
        assert "generate_recommendation" not in recommendation_engine.__all__


class TestCallStats:
    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_stats_include_summary(self):
        stats = call_stats()
        assert "mode" in stats
        assert "total_calls" in stats
        assert "bypass_attempts" in stats
        assert "summary_ar" in stats

    def test_audit_filter_by_bypass(self):
        log = audit_call_log(only_bypass=True)
        # كل العناصر يجب أن تحوي bypass=True
        for r in log:
            assert r.bypass_attempt


class TestThreadSafety:
    """ECP يجب أن يعمل thread-safe (lock داخلي)."""

    def setup_method(self):
        reset_ecp_state()
        _bootstrap_known_entry_points()

    def test_concurrent_calls_no_corruption(self):
        import threading

        @governed(EntryPointType.INTERNAL_SERVICE)
        def concurrent_fn(i):
            return i * 2

        results = []
        threads = [
            threading.Thread(target=lambda i=i: results.append(concurrent_fn(i))) for i in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        stats = call_stats()
        # 20 استدعاء على الأقل (قد يكون أكثر بسبب اختبارات سابقة في نفس class)
        assert stats["total_calls"] >= 20
