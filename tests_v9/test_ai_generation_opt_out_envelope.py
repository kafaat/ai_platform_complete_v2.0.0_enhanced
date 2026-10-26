"""A tenant that turned AI generation off gets no generation from any provider.

``tenant_ai_policies.ai_generation_allowed`` used to be folded only into
``external_llm_allowed``, so a tenant with the flag off still received local (vLLM)
generation. The platform envelope now carries the flag explicitly and the ai_agronomist
gate refuses every provider unless it is exactly ``True``. An envelope minted before the
flag existed is still parseable but authorizes no generation.
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
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = _load(
    "services/sahool-platform/core/ai_policy_envelope.py", "sahool_ai_policy_envelope_opt_out"
)
from services.ai_agronomist import policy_envelope as PE  # noqa: E402

_TENANT = "22222222-2222-2222-2222-222222222222"
_MODES = ("local_only", "redacted_external", "full_external")


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("external", [False, True])
def test_opted_out_tenant_gets_no_generation_from_any_provider(mode, external):
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": False, "external_data_sharing_level": mode}
    )
    assert env["ai_generation_allowed"] is False
    gate = PE.gate_generation(env, external=external)
    assert gate["decision"] == PE.DECISION_BLOCKED
    assert gate["reason"] == PE.REASON_AI_GENERATION_NOT_ALLOWED


def test_row_without_the_flag_is_not_an_opt_in():
    env = BUILDER.build_ai_policy_envelope(_TENANT, {"external_data_sharing_level": "local_only"})
    assert env["ai_generation_allowed"] is False
    assert PE.gate_generation(env, external=False)["decision"] == PE.DECISION_BLOCKED


def test_envelope_minted_before_the_flag_is_judged_as_before():
    """The platform deploys from its own branch, so ai_agronomist can run ahead of it.
    An envelope without the key keeps the old behaviour instead of switching AI off for
    every tenant: local generation proceeds, external stays behind the mode and
    ``external_llm_allowed`` (into which the old platform already folds the opt-out)."""
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": True, "external_data_sharing_level": "local_only"}
    )
    del env["ai_generation_allowed"]
    assert PE.validate_envelope(env) == (True, None)
    assert PE.gate_generation(env, external=False)["decision"] == PE.DECISION_ALLOWED
    external = PE.gate_generation(env, external=True)
    assert external["decision"] == PE.DECISION_BLOCKED
    assert external["reason"] == PE.REASON_LOCAL_ONLY_BLOCKS_EXTERNAL


def test_legacy_envelope_of_an_opted_out_tenant_still_blocks_external():
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": False, "external_data_sharing_level": "full_external"}
    )
    del env["ai_generation_allowed"]
    assert env["external_llm_allowed"] is False
    gate = PE.gate_generation(env, external=True)
    assert gate["decision"] == PE.DECISION_BLOCKED
    assert gate["reason"] == PE.REASON_EXTERNAL_LLM_NOT_ALLOWED


def test_flag_false_blocks_local_generation_too():
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": False, "external_data_sharing_level": "local_only"}
    )
    assert env["ai_generation_allowed"] is False
    gate = PE.gate_generation(env, external=False)
    assert gate["decision"] == PE.DECISION_BLOCKED
    assert gate["reason"] == PE.REASON_AI_GENERATION_NOT_ALLOWED


@pytest.mark.parametrize("value", ["true", 1, None])
def test_non_boolean_flag_is_malformed(value):
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": True, "external_data_sharing_level": "local_only"}
    )
    env["ai_generation_allowed"] = value
    assert PE.validate_envelope(env) == (False, PE.REASON_ENVELOPE_MALFORMED)
    assert PE.gate_generation(env, external=False)["decision"] == PE.DECISION_BLOCKED


def test_explicit_opt_in_keeps_local_generation():
    env = BUILDER.build_ai_policy_envelope(
        _TENANT, {"ai_generation_allowed": True, "external_data_sharing_level": "local_only"}
    )
    assert env["ai_generation_allowed"] is True
    assert PE.gate_generation(env, external=False)["decision"] == PE.DECISION_ALLOWED
    assert PE.gate_generation(env, external=True)["reason"] == (
        PE.REASON_LOCAL_ONLY_BLOCKS_EXTERNAL
    )


def test_tenant_without_a_policy_row_keeps_the_column_default():
    # No row means the v124 column default (ai_generation_allowed = true), not an opt-out:
    # local generation stays available, nothing leaves the tenant boundary.
    for row in (None, {}):
        env = BUILDER.build_ai_policy_envelope(_TENANT, row)
        assert env["policy_mode"] == "local_only"
        assert env["external_llm_allowed"] is False
        assert env["ai_generation_allowed"] is True
        assert PE.gate_generation(env, external=False)["decision"] == PE.DECISION_ALLOWED
        assert PE.gate_generation(env, external=True)["decision"] == PE.DECISION_BLOCKED
