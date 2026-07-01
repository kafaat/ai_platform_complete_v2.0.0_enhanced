"""حارس منفّذ أدوات الوكيل (V55 — المرحلة ٢).

يفرض:
- تطابق ``_TOOL_META`` (منفّذ ai_agronomist) مع ``shared/ai/tool_registry`` (لا drift).
- بوّابة الحوكمة fail-closed: مجهول/قدرة مفقودة ⇒ denied · مُعدِّلة/عالية ⇒ pending_approval
  · قراءة+قدرة ⇒ allowed.
- التنفيذ: القراءة المسموحة تستدعي الجالب وتُرجِع executed+data · فشل الجالب ⇒ failed بلا
  استثناء · المرفوضة/المؤجَّلة لا تستدعي الجالب أبداً.
- كلّ نتيجة تحمل سجلّ تدقيق مُنقَّح.

منطق صرف بلا خدمات (``-m unit``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.ai import tool_registry as REG  # noqa: E402


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


EX = _load("services/ai_agronomist/tool_executor.py", "sahool_tool_executor_v55")
_TS = "2026-07-01T00:00:00Z"
_ALL_CAPS = list(REG.CAPABILITIES)


def test_tool_meta_matches_registry_no_drift():
    reg = {t.name: (t.capability, t.risk, t.mutating, t.requires_approval) for t in REG.TOOLS}
    assert EX._TOOL_META == reg, "انحراف بين منفّذ ai_agronomist وسجلّ الأدوات القانونيّ"


def test_unknown_tool_denied_fail_closed():
    plan = EX.plan_tool_call("mystery", {}, _ALL_CAPS)
    assert plan["outcome"] == EX.OUTCOME_DENIED
    assert plan["reason"] == "unknown_tool"
    assert plan["requires_approval"] is True


def test_read_tool_allowed_with_capability():
    plan = EX.plan_tool_call("get_field_state", {"field_id": "f1"}, ["can_read_field_data"])
    assert plan["outcome"] == EX.DECISION_ALLOWED


def test_read_tool_denied_without_capability():
    plan = EX.plan_tool_call("get_index_timeline", {"field_id": "f1"}, ["can_read_field_data"])
    # يحتاج can_read_historical_imagery لا can_read_field_data
    assert plan["outcome"] == EX.OUTCOME_DENIED
    assert plan["reason"] == "capability_not_granted"


def test_mutating_tool_pending_approval_even_with_capability():
    # V58.2b — كلّ أداة مُعدِّلة صارت تتطلّب موافقة صريحة، فالسبب الأصدق needs_human_approval.
    plan = EX.plan_tool_call("create_scouting_task", {"field_id": "f", "zone": "z"}, _ALL_CAPS)
    assert plan["outcome"] == EX.OUTCOME_PENDING_APPROVAL
    assert plan["reason"] == "needs_human_approval"
    assert plan["requires_approval"] is True


def test_high_risk_tool_needs_human_approval():
    plan = EX.plan_tool_call("send_recommendation", {}, _ALL_CAPS)
    assert plan["outcome"] == EX.OUTCOME_PENDING_APPROVAL
    assert plan["reason"] == "needs_human_approval"


def test_execute_read_tool_calls_fetcher_and_audits():
    calls = []

    def fetcher(name, params):
        calls.append((name, params))
        return {"crop": "قمح", "ndvi": 0.62}

    res = EX.execute_read_tool(
        "get_field_state",
        {"field_id": "f1"},
        ["can_read_field_data"],
        fetcher,
        tenant_id="t1",
        actor="ai",
        timestamp=_TS,
    )
    assert res["outcome"] == EX.OUTCOME_EXECUTED
    assert res["data"]["crop"] == "قمح"
    assert calls == [("get_field_state", {"field_id": "f1"})]
    assert res["audit"]["outcome"] == "executed" and res["audit"]["timestamp"] == _TS


def test_execute_denied_tool_never_calls_fetcher():
    called = {"n": 0}

    def fetcher(name, params):
        called["n"] += 1
        return {}

    res = EX.execute_read_tool(
        "get_index_timeline",
        {},
        ["can_read_field_data"],
        fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert res["outcome"] == EX.OUTCOME_DENIED
    assert res["data"] is None
    assert called["n"] == 0


def test_execute_mutating_tool_never_calls_fetcher():
    called = {"n": 0}

    def fetcher(name, params):
        called["n"] += 1

    res = EX.execute_read_tool(
        "request_imagery_backfill",
        {"field_id": "f", "months": 24},
        _ALL_CAPS,
        fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert res["outcome"] == EX.OUTCOME_PENDING_APPROVAL
    assert called["n"] == 0


def test_fetcher_failure_is_safe():
    def fetcher(name, params):
        raise RuntimeError("service down")

    res = EX.execute_read_tool(
        "get_weather_history",
        {"field_id": "f", "days": 730},
        ["can_read_field_data"],
        fetcher,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert res["outcome"] == EX.OUTCOME_FAILED
    assert res["reason"] == "fetcher_error"
    assert res["data"] is None


def test_allowed_read_without_fetcher_is_failed():
    res = EX.execute_read_tool(
        "get_alerts",
        {"field_id": "f"},
        ["can_read_field_data"],
        None,
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert res["outcome"] == EX.OUTCOME_FAILED and res["reason"] == "no_fetcher"


def test_audit_redacts_secrets():
    res = EX.execute_read_tool(
        "get_field_state",
        {"field_id": "f", "api_token": "SECRET"},
        ["can_read_field_data"],
        lambda n, p: {},
        tenant_id="t",
        actor="ai",
        timestamp=_TS,
    )
    assert res["audit"]["params"]["api_token"] == "[redacted]"
