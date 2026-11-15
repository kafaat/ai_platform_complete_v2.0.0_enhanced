"""C-38: enforce the auth provisioning response contract in the web consumer.

This is a static-source test; it does not certify tenant authorization (C-35),
database writes, Redis delivery, or deployed UI behavior.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "services/auth/routers/tenants.py"
CLIENT = ROOT / "frontend/src/services/api/auth.ts"
VIEW = ROOT / "frontend/src/sections/ManagerConsolePage.tsx"


def _server_keys() -> set[str]:
    module = ast.parse(SERVER.read_text(encoding="utf-8"))
    handlers = []
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef):
            if node.name == "provision_tenant":
                handlers.append(node)
    assert len(handlers) == 1
    returns = []
    for node in ast.walk(handlers[0]):
        if isinstance(node, ast.Return):
            if isinstance(node.value, ast.Dict):
                returns.append(node.value)
    assert len(returns) == 1
    keys = set()
    for key in returns[0].keys:
        assert isinstance(key, ast.Constant)
        assert isinstance(key.value, str)
        keys.add(key.value)
    return keys


def _client_fields() -> dict[str, str]:
    source = CLIENT.read_text(encoding="utf-8")
    pattern = r"export\s+interface\s+TenantProvisionResult\s*\{([^}]+)\}"
    match = re.search(pattern, source, flags=re.S)
    assert match is not None
    fields = {}
    field_pattern = r"^\s*(\w+)\s*:\s*([^;\n]+);"
    for name, kind in re.findall(field_pattern, match.group(1), flags=re.M):
        fields[name] = kind
    assert fields
    return fields


@pytest.mark.unit
def test_c38_server_fields_match_web_type():
    assert _server_keys() == set(_client_fields())


@pytest.mark.unit
def test_c38_nullable_setup_and_owner_role_types():
    fields = _client_fields()
    assert fields["tenant_id"] == "string"
    assert fields["owner_user_id"] == "number"
    assert fields["owner_role"] == "'owner'"
    assert fields["setup_token"] == "string | null"
    assert fields["setup_link"] == "string | null"


@pytest.mark.unit
def test_c38_manager_renders_actual_keys_only():
    source = VIEW.read_text(encoding="utf-8")
    for key in ("owner_email", "owner_role", "setup_link", "message"):
        assert f"tenantM.data.{key}" in source
    for key in ("email", "role", "reset_token", "reset_url"):
        assert f"tenantM.data.{key}" not in source
