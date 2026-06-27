# SAHOOL — Container/API/Feature/UI Audit + Fix Report — 2026-06-25

## Scope
Audited the latest `weather_wind_layer` package for the visible product surface:

- Containers and service groups from `docker-compose.v9.yml`, `docker-compose.fixed.yml`, and `docker-compose.unified.yml`.
- Web route registry, RBAC/feature flags, API endpoint registry, and rendered pages.
- Mobile navigation, field workspace, daily activities/logs, operational modules, and API service methods.
- Daily distributed tasks and daily field logs, including whether data can be entered from the app.

## Executive Result

The web application has broad feature visibility and live API binding for the critical operational surfaces. The biggest gap found was in the mobile app: daily activities/logs were readable in the field workspace, but the mobile app did not provide a direct activity-entry form; daily distributed tasks also did not have a dedicated mobile screen. Both gaps were fixed.

## Fixes Applied

### 1. Mobile daily distributed tasks
Added:

- `mobile/sahool_app/lib/screens/tasks_screen.dart`
- `ApiService.fetchTasks()` → `GET /api/v1/tasks`
- `ApiService.updateTaskStatus()` → `PATCH /api/v1/tasks/{id}`
- Entry points in:
  - `MoreScreen`
  - `OperationsHubScreen`

User-visible behavior:

- Displays pending / in-progress / completed daily tasks.
- Supports filtering by status.
- Allows start and complete actions for roles allowed to mutate.
- Viewer role remains read-only.
- Does not fake success: API/network errors are shown honestly.

### 2. Mobile daily field logs / activities entry
Added:

- `ApiService.createFieldActivity()` → `POST /api/v1/fields/{id}/activities`
- `WAddActivityForm` inside field workspace activities tab.

User-visible behavior:

- From the field workspace, the user can now enter daily operations from the app:
  - irrigation
  - fertilization
  - spraying
  - scouting
  - planting/sowing
  - pruning
  - harvest
- The list refreshes after save.
- Viewer role does not see the entry form.
- Errors are surfaced via the existing `apiErrorMessage()` path.

### 3. Visibility / RBAC correctness
Confirmed and preserved:

- Management-only mobile modules remain hidden for non-management roles.
- Web navigation is derived from `NAV_SECTIONS`, filtered by `isPageEnabled()` and `canAccess()`.
- Hidden/infra services are not exposed as direct farmer UI modules.

## Container → Product Surface Matrix

| Service / Container Group | Should appear to user? | Expected UI Surface | Current/Fix Status |
|---|---:|---|---|
| `sahool-platform` | Yes | Dashboard, fields, activities, tasks, reports, governance | Visible in web; mobile field workspace now supports activity entry |
| `sahool-auth` | Yes | Login, signup, MFA, profile/session | Visible in web/mobile |
| `sahool-raster-service`, `sahool-vegetation-analysis`, `sahool-indicators-service` | Yes | Satellite, NDVI/EVI/NDWI/LAI, map layers, health indicators | Visible in web; mobile satellite/field workspace visible |
| `sahool-weather-service`, weather workers | Yes | Weather advice, map weather/wind overlay, irrigation/disease risk | Visible in web; mobile field weather tab visible |
| `sahool-supervisor-agent`, `local-ai-rag`, `guardrails` | Yes, through product UX only | AI advisor, recommendations, explainability/guarded actions | Visible as assistant/advanced pages; should not expose raw internal services |
| `sahool-actuator-service`, `edge`, `fastbee` | Yes, operationally | Devices, IoT, irrigation ops, equipment/actuation | Visible through operations screens |
| `sahool-odoo`, `odoo-bridge` | Admin/ops only | ERP bridge, inventory/equipment/accounting integration | Visible as operational/admin surfaces, not raw Odoo internals except configured bridge |
| `postgres`, `redis`, `nats`, `minio`, `qdrant`, `ollama` | No direct farmer UI | Health/observability only | Correct: should not be shown as product modules |
| `prometheus`, `grafana`, `jaeger`, `alertmanager` | Admin/devops only | System observability, not farmer workflow | Correct: not part of normal farmer UI |
| `nginx`, `migrate`, seed containers | No | Runtime infrastructure | Correct: hidden from product IA |

## Required User-Facing Modules Verified

### Web

- Dashboard / overview.
- Field and farm map.
- Field workspace.
- Satellite and indicators.
- Weather and wind map overlay.
- Irrigation planning and operations.
- Tasks and activities.
- Inventory, equipment, devices.
- Reports.
- Alerts and notification settings.
- Governance/audit.
- AI advisor and advanced decision/explainability surfaces.

### Mobile

- Dashboard.
- Field health / satellite.
- Fields / field workspace.
- Advisor.
- More / operations hub.
- Inventory, equipment, devices, irrigation ops.
- Documents and master data gated by role.
- **Fixed:** daily tasks screen.
- **Fixed:** daily activity/log entry form from field workspace.

## What Should Not Be Shown as Normal UI

These should remain hidden from ordinary farmer/worker navigation:

- Postgres, Redis, NATS, MinIO, Qdrant, Ollama.
- Migration/seed containers.
- Raw MCP endpoints.
- Raw observability dashboards unless admin/devops role.
- Guardrails internals.
- Service health internals except summarized status.
- Raw SQL workspace for non-admin roles.

## Best-Practice Alignment

The UI follows the right product model when it shows **capabilities**, not microservice names:

- Farmers see: fields, tasks, weather, irrigation, alerts, recommendations.
- Managers see: operations, reports, equipment, inventory, users/governance.
- Admin/devops see: health, audit, system configuration.
- Infrastructure remains hidden.

## Validation Run

Executed successfully:

- `python scripts/verify_review_fixes.py` → 23/23 passed.
- `npm run typecheck` → passed.
- `npm run build` → passed.
- Focused web tests:
  - `src/config/endpoints.test.ts` → passed.
  - `src/lib/routes.test.ts` → passed.
  - `src/components/maphub/OverlayMarkers.test.tsx` → passed.
  - `src/components/maphub/HubMapGL.test.tsx` → passed.
  - `src/sections/ReportsPage.test.tsx` → passed.
  - Total: 28/28 passed.

## Remaining Limitation

Flutter/Dart executable is not installed in this environment, so mobile compilation tests were not executed here. The mobile changes were kept conservative and localized, using existing project patterns: `ApiService`, `ErrorView`, `LoadingView`, `EmptyView`, RBAC helpers, and existing navigation style.
