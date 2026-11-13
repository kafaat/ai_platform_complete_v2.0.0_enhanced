"""C-38: tenant provisioning API response and web consumer must agree.

Source-level contract gate; no DB/Redis/network needed. It deliberately compares
the *actual* keys returned by the auth handler with the TypeScript response
interface instead of trusting the interface alone. It does not certify
tenant-provisioning authorization (C-35) or live onboarding.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AUTH_TENANTS = ROOT / "services/auth/routers/tenants.py"
WEB_AUTH = ROOT / "frontend/src/services/api/auth.ts"
WEB_MANAGER = ROOT / "frontend/src/sections/ManagerConsolePage.tsx"


def _server_response_keys() -> set[str]:
    module = ast.parse(AUTH_TENANTS.read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "provision_tenant"
    ]
    assert len(functions) == 1, "Expected exactly one provision_tenant handler"
    returns = [
        node.value
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
    ]
    assert len(returns) == 1, "Expected exactly one literal response dictionary"
    keys = returns[0].keys
    assert all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in keys)
    return {key.value for key in keys}


def _client_response_fields() -> dict[str, str]:
    source = WEB_AUTH.read_text(encoding="utf-8")
    match = re.search(
        r"export\s+interface\s+TenantProvisionResult\s*\{([^}]+)\}",
        source,
        flags=re.S,
    )
    assert match, "TenantProvisionResult interface not found"
    fields = dict(
        re.findall(r"^\s*(\w+)\s*:\s*([^;\n]+);", match.group(1), flags=re.M)
    )
    assert fields, "Client response interface must have declared fields"
    return fields


@pytest.mark.unit
def test_c38_client_response_has_exact_backend_keys():
    assert set(_client_response_fields()) == _server_response_keys()


@pytest.mark.unit
def test_c38_types_preserve_nullable_setup_and_literal_owner_role():
    fields = _client_response_fields()
    assert fields["tenant_id"] == "string"
    assert fields["owner_user_id"] == "number"
    assert fields["owner_role"] == "'owner'"
    assert fields["setup_token"] == "string | null"
    assert fields["setup_link"] == "string | null"


@pytest.mark.unit
def test_c38_manager_consumes_server_fields_not_nonexistent_aliases():
    source = WEB_MANAGER.read_text(encoding="utf-8")
    for name in ("owner_email", "owner_role", "setup_link", "message"):
        assert f"tenantM.data.{name}" in source, f"ManagerConsole missing {name}"
    for nonexistent in ("email", "role", "reset_token", "reset_url"):
        assert f"tenantM.data.{nonexistent}" not in source, (
            f"ManagerConsole uses phantom API field: {nonexistent}"
        )
