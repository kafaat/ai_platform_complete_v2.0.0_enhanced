"""Multi-tenant runtime validation."""

from __future__ import annotations

from typing import Any


class TenantIsolationViolation(PermissionError):
    pass


def validate_tenant_payload(expected_tenant_id: str, payload: Any, *, path: str = "$") -> None:
    if isinstance(payload, dict):
        actual = payload.get("tenant_id")
        if actual is not None and str(actual) != str(expected_tenant_id):
            raise TenantIsolationViolation(
                f"tenant leak at {path}: {actual} != {expected_tenant_id}"
            )
        for key, value in payload.items():
            validate_tenant_payload(expected_tenant_id, value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            validate_tenant_payload(expected_tenant_id, item, path=f"{path}[{idx}]")


class MultiTenantRuntimeValidator:
    def validate(self, tenant_id: str, payload: Any) -> bool:
        validate_tenant_payload(tenant_id, payload)
        return True
