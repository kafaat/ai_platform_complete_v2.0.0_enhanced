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
    # Forensic hardening (73666ee audit): append-only command ledger (F-02/F-06),
    # identifier/hash CHECKs (F-07), monotonic projection revision.
    "services/decision-service/migrations/025_worker_tenant_command_ledger.sql": [
        "decision_runtime_worker_tenant_commands",
        "UNIQUE(worker_id, idempotency_key)",
        "resulting_revision",
        "request_hash ~ '^[0-9a-f]{64}$'",
        "ADD COLUMN IF NOT EXISTS revision",
    ],
    "services/decision-service/persistence.py": [
        "register_runtime_worker_tenant",
        "list_worker_tenants",
        "worker_tenant_authorized",
        # F-01 staged fail-closed flag + F-02 replay against the ledger, not the projection.
        "strict_worker_tenants_enabled",
        "DECISION_STRICT_WORKER_TENANTS",
        "return not strict_worker_tenants_enabled()",
        "decision_runtime_worker_tenant_commands",
    ],
    "services/decision-service/main.py": [
        "worker_tenant_unauthorized",
        '"/v1/learning/runtime-workers/{worker_id}/tenants"',
        "X-Registered-By",
        # F-09: authoritative mode without a configured bearer token must not be "ready".
        "auth_token_missing_in_sor",
        "DECISION_REQUIRE_AUTH_TOKEN",
    ],
    "services/model-registry-adapter/service.py": [
        "def resolve_tenants",
        "RUNTIME_TENANT_IDS",
        "/v1/learning/runtime-workers/",
        "no tenant assignment",
    ],
    # Behavior proofs on real Postgres+HTTP (F-08: the static gate alone is not the evidence).
    "services/decision-service/tests/test_runtime_worker_tenants.py": [
        "test_stale_replay_cannot_resurrect_revocation",
        "test_strict_mode_denies_unknown_workers",
        "test_command_ledger_is_append_only_with_constraint_checks",
        "test_feed_enforces_worker_partition_end_to_end",
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
