"""C-38: verify tenant provisioning response across auth and web sources.

This is a source contract check. It does not certify authorization or Redis.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TENANT_API = ROOT / "services/auth/routers/tenants.py"
WEB_API = ROOT / "frontend/src/services/api/auth.ts"
MANAGER = ROOT / "frontend/src/sections/ManagerConsolePage.tsx"


def _backend_keys() -> set[str]:
    tree = ast.parse(TENANT_API.read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        if node.name == "provision_tenant"
    ]
    assert len(functions) == 1
    responses = [
        node.value
        for node in ast.walk(functions[0])
        if isinstance(node, ast.Return)
        if isinstance(node.value, ast.Dict)
    ]
    assert len(responses) == 1
    keys = responses[0].keys
    assert all(isinstance(key, ast.Constant) for key in keys)
    return {key.value for key in keys}


def _web_fields() -> dict[str, str]:
    source = WEB_API.read_text(encoding="utf-8")
    pattern = r"export\s+interface\s+TenantProvisionResult\s*\{([^}]+)\}"
    match = re.search(pattern, source, flags=re.S)
    assert match is not None
    field_pattern = r"^\s*(\w+)\s*:\s*([^;\n]+);"
    pairs = re.findall(field_pattern, match.group(1), flags=re.M)
    return dict(pairs)


@pytest.mark.unit
def test_c38_frontend_matches_backend_response():
    assert set(_web_fields()) == _backend_keys()


@pytest.mark.unit
def test_c38_setup_is_nullable_and_owner_role_is_literal():
    fields = _web_fields()
    assert fields["tenant_id"] == "string"
    assert fields["owner_user_id"] == "number"
    assert fields["owner_role"] == "'owner'"
    assert fields["setup_token"] == "string | null"
    assert fields["setup_link"] == "string | null"


@pytest.mark.unit
def test_c38_manager_uses_real_response_fields():
    source = MANAGER.read_text(encoding="utf-8")
    for field in ("owner_email", "owner_role", "setup_link", "message"):
        assert "tenantM.data." + field in source
    for field in ("email", "role", "reset_token", "reset_url"):
        assert "tenantM.data." + field not in source
