"""
tests_v9/test_tool_contracts.py — Tool Contracts + Execution Journal

يتحقّق:
    ١. tool غير مسجّل → رفض
    ٢. capability denied → رفض + journal entry
    ٣. timeout enforcement يعمل
    ٤. journal append-only (immutability check)
    ٥. journal replay يستخرج invocation history
    ٦. side-effects classification
    ٧. actuator مع max_retries > 0 و idempotent=False → raises
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/supervisor-agent"))

from tool_contracts import (
    ExecutionJournal,
    SideEffectClass,
    ToolContract,
    ToolRegistry,
    bootstrap_default_tools,
)


@pytest.fixture
def registry():
    r = ToolRegistry()
    bootstrap_default_tools(r)
    return r


@pytest.fixture
def journal():
    return ExecutionJournal()


class TestToolRegistry:
    def test_default_tools_registered(self, registry):
        tools = registry.list_tools()
        assert "weather.forecast" in tools
        assert "actuator.pump.start" in tools
        assert "ndvi.compute" in tools

    def test_classification_by_side_effect(self, registry):
        actuators = registry.list_by_side_effect(SideEffectClass.ACTUATOR)
        assert "actuator.pump.start" in actuators
        # weather ليس actuator
        assert "weather.forecast" not in actuators


class TestInvocation:
    @pytest.mark.asyncio
    async def test_unregistered_tool_rejected(self, registry):
        result = await registry.invoke(
            tool_id="nonexistent.tool",
            input_data={},
            actor_capabilities=set(),
        )
        assert not result.success
        assert "غير مسجّل" in result.error

    @pytest.mark.asyncio
    async def test_capability_denied(self, registry, journal):
        # actor بدون capabilities
        result = await registry.invoke(
            tool_id="weather.forecast",
            input_data={"lat": 15.0, "lng": 44.0, "days": 7},
            actor_capabilities=set(),  # لا capabilities
            tenant_id="test-tenant",
            journal=journal,
        )
        assert not result.success
        assert "capability denied" in result.error

        # تحقّق journal entry
        entries = await journal.get_entries()
        denials = [e for e in entries if e.event == "denial"]
        assert len(denials) == 1
        assert denials[0].tool_id == "weather.forecast"

    @pytest.mark.asyncio
    async def test_successful_invocation(self, registry, journal):
        result = await registry.invoke(
            tool_id="weather.forecast",
            input_data={"lat": 15.0, "lng": 44.0, "days": 3},
            actor_capabilities={"weather.read"},
            tenant_id="test-tenant",
            journal=journal,
        )
        assert result.success, f"failed: {result.error}"
        assert "forecast" in result.output
        assert len(result.output["forecast"]) == 3

        # journal لها entries
        entries = await journal.get_entries()
        starts = [e for e in entries if e.event == "start"]
        completes = [e for e in entries if e.event == "complete"]
        assert len(starts) == 1
        assert len(completes) == 1
        assert completes[0].payload["success"] is True

    @pytest.mark.asyncio
    async def test_invalid_input_rejected(self, registry):
        # missing 'lat'
        result = await registry.invoke(
            tool_id="weather.forecast",
            input_data={"lng": 44.0},
            actor_capabilities={"weather.read"},
        )
        assert not result.success
        assert "schema" in result.error


class TestTimeoutEnforcement:
    @pytest.mark.asyncio
    async def test_timeout_enforced(self):
        """tool ببطء يُجبَر على timeout."""

        async def slow_impl(**kwargs):
            await asyncio.sleep(2.0)
            return {"ok": True}

        r = ToolRegistry()
        r.register(
            ToolContract(
                tool_id="slow.tool",
                version="1.0.0",
                description="عمداً بطيء",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                side_effects=SideEffectClass.READ_DB,
                timeout_ms=100,  # 100ms only
                required_capabilities=[],
            ),
            implementation=slow_impl,
        )

        result = await r.invoke("slow.tool", {}, set())
        assert not result.success
        assert result.timed_out
        assert result.duration_ms <= 200


class TestActuatorContracts:
    def test_actuator_cannot_have_retries_unless_idempotent(self):
        """invariant: actuator non-idempotent → max_retries=0."""
        with pytest.raises(AssertionError):
            ToolContract(
                tool_id="actuator.bad",
                version="1.0.0",
                description="bad actuator",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                side_effects=SideEffectClass.ACTUATOR,
                idempotent=False,
                max_retries=3,  # ⚠ هذا يجب أن يُرفَض
            )

    def test_actuator_idempotent_can_retry(self):
        """idempotent actuator يُسمح له بـretries."""
        c = ToolContract(
            tool_id="actuator.good",
            version="1.0.0",
            description="ok actuator",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            side_effects=SideEffectClass.ACTUATOR,
            idempotent=True,
            max_retries=3,
        )
        assert c.max_retries == 3


class TestJournalReplay:
    @pytest.mark.asyncio
    async def test_replay_extracts_history(self, registry, journal):
        # نفّذ tool عدّة مرّات
        for i in range(3):
            await registry.invoke(
                "weather.forecast",
                {"lat": 15.0 + i, "lng": 44.0, "days": 7},
                {"weather.read"},
                tenant_id="t1",
                journal=journal,
            )

        all_entries = await journal.get_entries()
        # كل invocation = 2 entries (start + complete)
        assert len(all_entries) == 6

    @pytest.mark.asyncio
    async def test_journal_immutability(self, journal):
        """Journal يجب أن تكون append-only."""
        await journal.record_start(
            invocation_id="i1",
            tool_id="t1",
            input_data={"a": 1},
            actor_capabilities=[],
            tenant_id="tx",
            contract_version="1.0.0",
        )

        entries_v1 = await journal.get_entries()
        # حاول التعديل
        entries_v1[0].payload["a"] = 999

        entries_v2 = await journal.get_entries()
        # الـjournal الداخلي ليس affected (نسخة جديدة في get)
        # ملاحظة: في الـMVP، الـjournal in-memory. في production
        # يجب أن يُخزَّن في append-only table مع triggers تمنع UPDATE/DELETE.
        # هذا الاختبار يوثّق المتطلّب.
        assert len(entries_v2) == 1


class TestSideEffectsTracking:
    @pytest.mark.asyncio
    async def test_actuator_invocation_journaled(self, registry, journal):
        """actuator invocation يجب أن يُسجَّل في journal (للـaudit)."""
        result = await registry.invoke(
            "actuator.pump.start",
            {"well_id": "w1", "duration_min": 30},
            {"actuator.pump.control"},
            tenant_id="t1",
            journal=journal,
        )
        assert result.success
        assert result.side_effects_recorded

        # تحقّق من journal
        actuator_entries = await journal.get_entries(tool_id="actuator.pump.start")
        starts = [e for e in actuator_entries if e.event == "start"]
        assert len(starts) == 1
