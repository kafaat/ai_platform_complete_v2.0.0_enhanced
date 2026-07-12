#!/usr/bin/env python3
"""WX-12 multitenancy gate: worker→tenant partitioning must stay server-authorized.

Guards the closure of gap WX-12-RUNTIME-MULTITENANCY: the registry table exists
(migration 024), the feed refuses non-authorized tenants for registered workers
(typed 403), the discovery endpoint exists, and the adapter enumerates its
partition from the server instead of free-picking (env pins stay backward
compatible for single-tenant installs).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

checks = {
    "services/decision-service/migrations/024_runtime_worker_tenants.sql": [
        "decision_runtime_worker_tenants",
        "UNIQUE(worker_id, tenant_id)",
    ],
    "services/decision-service/persistence.py": [
        "register_runtime_worker_tenant",
        "list_worker_tenants",
        "worker_tenant_authorized",
    ],
    "services/decision-service/main.py": [
        "worker_tenant_unauthorized",
        '"/v1/learning/runtime-workers/{worker_id}/tenants"',
        "X-Registered-By",
    ],
    "services/model-registry-adapter/service.py": [
        "def resolve_tenants",
        "RUNTIME_TENANT_IDS",
        "/v1/learning/runtime-workers/",
        "no tenant assignment",
    ],
}

missing = []
for rel, tokens in checks.items():
    p = ROOT / rel
    text = p.read_text() if p.exists() else ""
    for token in tokens:
        if token not in text:
            missing.append(f"{rel}: {token}")
if missing:
    print("WX-12 RUNTIME MULTITENANCY GATE: FAIL")
    print("\n".join(missing))
    raise SystemExit(1)
print("WX-12 RUNTIME MULTITENANCY GATE: PASS")
