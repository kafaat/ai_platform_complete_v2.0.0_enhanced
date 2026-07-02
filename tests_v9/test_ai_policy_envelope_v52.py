"""Tenant AI Policy Envelope (v52) — pure unit tests (no DB / no providers).

Covers the platform builder (policy authority) and the ai_agronomist consumer
(enforcement): most-restrictive default, fail-closed refusal without an envelope,
per-mode external-provider gating, and the tool allow-list gate on the governed loop.
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


def _load(rel_path: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    assert spec and spec.loader, f"cannot load {rel_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# Platform builder loaded by file path (``services/sahool-platform`` is not an importable pkg).
BUILDER = _load("services/sahool-platform/core/ai_policy_envelope.py", "sahool_ai_policy_envelope")
# Consumer enforcement + governed tool loop are importable as a package.
from services.ai_agronomist import policy_envelope as PE  # noqa: E402
from services.ai_agronomist import tool_loop as LOOP  # noqa: E402

_TENANT = "11111111-1111-1111-1111-111111111111"
_TS = "2026-07-01T00:00:00Z"


# ── Builder: fail-closed most-restrictive default ───────────────────────────
def test_builder_default_is_most_restrictive_when_row_absent():
    for row in (None, {}):
        env = BUILDER.build_ai_policy_envelope(_TENANT, row)
        assert env["policy_mode"] == "local_only"
        assert env["external_llm_allowed"] is False
        assert env["version"] == "v52"
        assert env["tenant_id"] == _TENANT
        assert env["allowed_data_classes"] == ["field_local"]
        # Minimal tools = read-only set; no mutating tool leaks into the default allow-list.
        assert "get_field_state" in env["allowed_tools"]
        assert "send_recommendation" not in env["allowed_tools"]
        assert "export_enterprise_data" not in env["allowed_tools"]


def test_builder_never_fabricates_permissive_default_from_partial_row():
    # A row missing the generation flag must NOT become external-capable (fail-closed).
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"external_data_sharing_level": "full_external"}
    )
    assert env["policy_mode"] == "full_external"
    assert env["external_llm_allowed"] is False  # no explicit ai_generation_allowed=True


def test_builder_maps_redacted_and_full_from_explicit_row():
    red = BUILDER.build_ai_policy_envelope(
        _TENANT,
        {"ai_generation_allowed": True, "external_data_sharing_level": "redacted_external"},
    )
    assert red["policy_mode"] == "redacted_external"
    assert red["external_llm_allowed"] is True
    assert red["max_context_bytes"] == BUILDER.REDACTED_MAX_CONTEXT_BYTES

    full = BUILDER.build_ai_policy_envelope(
        _TENANT,
        {"ai_generation_allowed": True, "external_data_sharing_level": "full_external"},
    )
    assert full["policy_mode"] == "full_external"
    assert full["external_llm_allowed"] is True
    assert "full_external" in full["allowed_data_classes"]


def test_builder_illegal_mode_falls_back_to_local_only():
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": True, "external_data_sharing_level": "hack"}
    )
    assert env["policy_mode"] == "local_only"
    assert env["external_llm_allowed"] is False


def test_platform_envelope_is_accepted_by_consumer_validator():
    # Cross-service contract: what the platform stamps, the consumer must accept.
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": True, "external_data_sharing_level": "full_external"}
    )
    ok, reason = PE.validate_envelope(env)
    assert ok and reason is None


# ── Consumer: fail-closed refusal when the pack has no valid envelope ────────
def test_missing_envelope_refuses_request_fail_closed():
    for pack in (None, {}, {"ai_policy_envelope": None}, {"ai_policy_envelope": {"bad": 1}}):
        envelope, decision = PE.enforce_request(pack)
        assert envelope is None
        assert decision is not None
        assert decision["decision"] == PE.DECISION_BLOCKED
        assert decision["refused"] is True


def test_missing_envelope_blocks_external_provider():
    gate = PE.gate_generation(None, external=True)
    assert gate["decision"] == PE.DECISION_BLOCKED
    assert gate["reason"] == PE.REASON_ENVELOPE_MISSING


# ── Consumer: per-mode external-provider gating ─────────────────────────────
def _env(mode: str, external_allowed: bool) -> dict:
    return BUILDER.build_ai_policy_envelope(
        _TENANT,
        {
            "ai_generation_allowed": external_allowed,
            "external_data_sharing_level": mode,
        },
    )


def test_local_only_blocks_external_but_allows_local():
    env = _env("local_only", True)
    blocked = PE.gate_generation(env, external=True)
    assert blocked["decision"] == PE.DECISION_BLOCKED
    assert blocked["reason"] == PE.REASON_LOCAL_ONLY_BLOCKS_EXTERNAL
    # A local provider is never blocked by data-sharing mode (data never leaves).
    local = PE.gate_generation(env, external=False)
    assert local["decision"] == PE.DECISION_ALLOWED
    assert local["requires_redaction"] is False


def test_redacted_external_requires_redaction():
    env = _env("redacted_external", True)
    gate = PE.gate_generation(env, external=True)
    assert gate["decision"] == PE.DECISION_ALLOWED
    assert gate["requires_redaction"] is True
    assert gate["reason"] == PE.REASON_REDACTED_REQUIRES_REDACTION


def test_full_external_gated_on_explicit_flag():
    # Explicit external permission ⇒ allowed.
    allowed = PE.gate_generation(_env("full_external", True), external=True)
    assert allowed["decision"] == PE.DECISION_ALLOWED
    assert allowed["reason"] == PE.REASON_FULL_EXTERNAL_ALLOWED
    # Same mode but generation not granted ⇒ external_llm_allowed False ⇒ blocked.
    denied = PE.gate_generation(_env("full_external", False), external=True)
    assert denied["decision"] == PE.DECISION_BLOCKED
    assert denied["reason"] == PE.REASON_EXTERNAL_LLM_NOT_ALLOWED


# ── Consumer: tool allow-list gate (composes with capability governance) ─────
def test_tool_allowed_helper_respects_allow_list():
    env = BUILDER.build_ai_policy_envelope(_TENANT, None)
    assert PE.tool_allowed(env, "get_field_state") is True
    assert PE.tool_allowed(env, "send_recommendation") is False
    # No envelope ⇒ no allow-list ⇒ fail-closed False.
    assert PE.tool_allowed(None, "get_field_state") is False


def test_tool_loop_blocks_tool_outside_allow_list():
    calls: list[str] = []

    def fetcher(name, params):
        calls.append(name)
        return {"field_id": params.get("field_id"), "ok": True}

    out = LOOP.run_tool_calls(
        [
            {"tool": "get_field_state", "params": {"field_id": "f1"}, "id": "a"},
            {"tool": "get_weather_history", "params": {"field_id": "f1", "days": 30}, "id": "b"},
        ],
        allowed_capabilities=["can_read_field_data"],
        fetcher=fetcher,
        tenant_id=_TENANT,
        actor="ai_agronomist",
        timestamp=_TS,
        allowed_tools={"get_field_state"},  # get_weather_history intentionally excluded
    )
    results = {r["tool"]: r for r in out["tool_calls"]}
    assert results["get_weather_history"]["outcome"] == LOOP.OUTCOME_TOOL_BLOCKED_BY_POLICY
    assert results["get_weather_history"]["reason"] == "tool_not_in_allowed_tools"
    # The blocked tool never reached the fetcher; the allowed one did.
    assert "get_weather_history" not in calls
    assert "get_field_state" in calls
    assert results["get_field_state"]["outcome"] == "executed"


def test_tool_loop_without_allow_list_is_backward_compatible():
    # allowed_tools=None ⇒ no envelope gate (preserves pre-v52 behaviour).
    out = LOOP.run_tool_calls(
        [{"tool": "get_field_state", "params": {"field_id": "f1"}, "id": "a"}],
        allowed_capabilities=["can_read_field_data"],
        fetcher=lambda name, params: {"field_id": params.get("field_id")},
        tenant_id=_TENANT,
        actor="ai_agronomist",
        timestamp=_TS,
    )
    assert out["tool_calls"][0]["outcome"] == "executed"
