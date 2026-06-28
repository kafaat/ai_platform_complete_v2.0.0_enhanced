# SAHOOL Phase 9–12 Runtime Activation Patch

Date: 2026-06-26

## Scope
This patch closes the concrete runtime-activation gaps found in the Phase 12 archive without adding a new phase.

## Applied changes

### 1. Mounted Phase 9–12 routers in `api/main.py`
Added imports and `app.include_router(...)` calls for:

- `api.phase9_autonomous_farm_os`
- `api.phase10_continuous_learning`
- `api.phase11_federated_agents`
- `api.phase12_marketplace_ecosystem`

Verified through FastAPI route smoke import. Representative live paths now exist:

- `/v1/phase9/autonomy/plan`
- `/v1/phase10/learning/dataset`
- `/v1/phase11/federation/cycle`
- `/v1/ecosystem/marketplace/apps`

### 2. Added official migration-manifest coverage
Added missing Phase 6–12 SQL files into `migrations/MANIFEST.txt` and copied Phase 12 marketplace SQL from Alembic into the canonical `migrations/` directory:

- `v114_cloud_native_gis_best_practices.sql`
- `v115_precision_agriculture_phase6.sql`
- `v116_enterprise_gis_phase7.sql`
- `v117_global_scale_phase8.sql`
- `v118_phase9_autonomous_farm_os.sql`
- `v119_phase10_continuous_learning.sql`
- `v120_phase11_federated_agents.sql`
- `v121_marketplace_ecosystem.sql`

### 3. Added optional runtime persistence adapter
Created:

- `services/sahool-platform/api/phase_runtime_store.py`

This adapter uses `app.state.db_pool` if available and degrades truthfully with `runtime_persistence.persisted=false` if the DB pool or tenant/field UUID is unavailable.

### 4. Exposed app DB pool to mounted routers
`api/main.py` now sets:

- `app.state.db_pool = _DB_POOL`

when the pool is initialized, and resets it on shutdown.

### 5. Phase 9 persistence wiring
`phase9_autonomous_farm_os.py` now persists, when DB is available:

- execution plans → `autonomous_execution_plan`
- actuator commands → `actuator_command_outbox`
- verification events → `execution_verification_event`
- registered models → `model_registry_version`

### 6. Phase 10 persistence wiring
`phase10_continuous_learning.py` now persists, when DB and `X-Tenant-Id` are available:

- feature specs → `feature_set_specs`
- training dataset manifests → `training_datasets`

### 7. Phase 11 persistence wiring
`phase11_federated_agents.py` now persists federation cycles and proposals, when DB and `X-Tenant-Id` are available:

- federation cycles → `agent_federation_cycles`
- agent proposals → `agent_proposals`

### 8. Phase 12 marketplace persistence wiring
`phase12_marketplace_ecosystem.py` now persists, when DB is available:

- marketplace apps → `marketplace_apps`
- installations → `marketplace_installations`
- webhooks → `webhook_subscriptions`
- usage metering → `usage_metering_records`

### 9. Added RLS hardening to Phase 9 and Phase 10 migrations
Appended tenant-isolation policies and FORCE RLS to Phase 9/10 runtime tables that previously lacked explicit policies.

### 10. Added regression guard test
Added:

- `tests_v9/test_phase9_12_runtime_activation.py`

It verifies that Phase 9–12 routers are mounted and Phase 6–12 migrations are represented in the official manifest.

## Verification performed in this environment

Passed:

```bash
python -m py_compile \
  services/sahool-platform/api/phase_runtime_store.py \
  services/sahool-platform/api/phase9_autonomous_farm_os.py \
  services/sahool-platform/api/phase10_continuous_learning.py \
  services/sahool-platform/api/phase11_federated_agents.py \
  services/sahool-platform/api/phase12_marketplace_ecosystem.py \
  services/sahool-platform/api/main.py
```

Passed:

```bash
PYTHONPATH=services/sahool-platform:. python - <<'PY'
import os
os.environ.setdefault('SAHOOL_JWT_SECRET','x'*40)
from api.main import app
paths = {getattr(r, 'path', '') for r in app.routes}
assert '/v1/phase9/autonomy/plan' in paths
assert '/v1/phase10/learning/dataset' in paths
assert '/v1/phase11/federation/cycle' in paths
assert '/v1/ecosystem/marketplace/apps' in paths
print('main route activation smoke passed')
PY
```

Could not run `pytest tests_v9/...` in this container because `tests_v9/conftest.py` requires `jose`, which is not installed in the current execution environment. The repository-level test file is included and should run in the normal project environment where the existing 93 + 44 focused tests were run.

## Remaining production work not fully closed by this patch

This patch activates runtime routes and durable persistence hooks. It does not fully implement external production systems:

- MQTT / Modbus / LoRaWAN physical equipment adapters are still not implemented.
- GraphQL is still a schema facade, not a live resolver server.
- Marketplace plugin execution sandbox/isolation is still a policy contract, not an execution runtime.
- ML artifact registry/model serving/promotion jobs are still not a full MLflow/KServe/Feast stack.
- Full Docker/Kong/DB/NATS/Redis/Raster/Frontend/Workers E2E was not run in this container.
