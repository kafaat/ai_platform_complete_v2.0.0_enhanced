# Sahool UI Product Rules

Status: mandatory product contract  
Scope: Web, Mobile, Admin, Field Workspace, MapHub, Command Center, recommendations, tasks, reports, and offline field execution.

This document is the non-breakable operating constitution for the Sahool user experience. It prevents UI sprawl by forcing every screen, map layer, recommendation, task, and mobile action to be tied to field context, season context, evidence, lineage, and an executable operation.

## 1. Product Operating Contract

Every user-facing feature must declare a Product Operating Contract before it is exposed in navigation.

Required fields:

```text
feature_id
product_mode
roles
ui_component
domain_hook
api_contract
backend_route
data_owner
empty_state
loading_state
error_state
stale_state
degraded_state
tests_or_guards
```

Rule: no orphan button, no orphan tab, no orphan map layer, and no route without a data owner.

## 2. Field Context Rule

Every field-scoped view, layer, task, recommendation, report, and timeline event must carry `field_id`.

No field operation may silently fall back to a global context. If `field_id` is missing, the UI must render a disabled explanation or a clear selection prompt.

## 3. Season Context Rule

Every seasonal view, recommendation, crop model, irrigation decision, yield estimate, report, and economics calculation must carry `season_id` when the meaning is season-specific.

When a field has no active season, the UI must show an explicit “no active season” state and a direct action to create one.

## 4. Active Boundary Rule

No satellite, raster, zonal, weather-polygon, irrigation-zone, field-intelligence, or recommendation workflow may run unless the field has an `active_valid_boundary`.

Allowed states:

```text
field.draft
field.boundary_pending
field.boundary_invalid
field.boundary_validated
field.active
field.archived
```

Only `boundary_validated` and `active` may enter analytics. Invalid boundary states must show a boundary-quality repair path.

## 5. Recommendation Evidence Rule

No recommendation may be shown without:

```text
recommendation_id
decision_id
evidence_snapshot_id
confidence
confidence_budget
evidence[]
primary_action
feedback_action
lineage
```

A recommendation without lineage is not a recommendation; it is a draft insight and must not create tasks.

## 6. Task Verification Rule

No task may become `verified` without verification evidence.

Task lifecycle:

```text
draft → open → assigned → in_progress → completed → verified → outcome_recorded
```

`completed` means the operator said it was done. `verified` means a manager, sensor, image, GPS trace, photo, or rule confirmed it. `outcome_recorded` means the learning system has a measurable outcome.

## 7. Outcome Learning Rule

No learning update may be generated unless an `outcome_recorded` event exists and is tied to:

```text
task_id
recommendation_id or decision_id
field_id
season_id when applicable
outcome_metric
source_evidence
recorded_at
```

## 8. Map Layer Contract Rule

Every map layer must declare a layer contract.

Required fields:

```text
id
label
category
render_type
source_service
source_endpoint
legend
opacity_supported
freshness
confidence
requires_field
requires_season
default_enabled
compare_enabled
empty_state
error_state
stale_state
degraded_state
allowed_product_modes
allowed_roles
why_this
primary_actions
```

A layer cannot be added to Layer Manager without this contract.

## 9. Mobile Offline Action Rule

Every mobile field action must be idempotent and sync-aware.

Required fields:

```text
operation_id
action_type
field_id
season_id optional
local_created_at
sync_status
retry_count
conflict_status
payload_hash
```

Sync states:

```text
local_pending
syncing
synced
failed
conflict
```

The mobile UI must show local-pending operations clearly.

## 10. No Silent Error Rule

Every panel must support:

```text
loading_state
empty_state
error_state
stale_state
degraded_state
```

If raster, weather, sensors, or decision services fail, the Field Workspace remains usable with degraded panels and cached/partial data where possible.

## 11. No Wide Rewrite Rule

No large UI replacement is allowed without a strangler phase.

Preferred pattern:

```text
existing component
→ shell wrapper
→ extracted contract-driven child
→ guard
→ remove legacy branch only after parity
```

Applies immediately to `MapHub.tsx`, `api.ts`, `AddFieldWithMap.tsx`, `SeasonStep.tsx`, mobile `api_service.dart`, and `field_create_wizard.dart`.

## 12. Product Mode Rule

The UI must not expose all power features to every user by default.

Supported modes:

```text
basic_farm
precision
enterprise
government_ngo
demo
```

Navigation, Layer Manager, Field Workspace tabs, reports, and advanced cards must be filtered by product mode and role.

## 13. Readiness and Completeness Rule

Each field must expose a visible Field Readiness Score and a Data Completeness Panel.

Readiness inputs include:

```text
active_valid_boundary
active_season
crop_selected
planting_or_start_date
irrigation_method
soil_type_confidence
latest_imagery_age
weather_available
open_tasks_state
sensor_availability optional
```

The UI must convert missing data into visible next actions, not silent absence.

## 14. Confidence Budget Rule

Every confidence score must explain its deductions.

Example:

```text
confidence: 72
budget:
  base: 96
  deductions:
    - reason: unknown_soil_type
      points: -10
    - reason: missing_soil_moisture_sensor
      points: -8
    - reason: stale_satellite_image
      points: -6
```

## 15. Why This Rule

Every recommendation, alert, operation-window card, risk indicator, and non-trivial map layer must expose a “Why this?” explanation.

The explanation must show human-readable evidence, not internal model jargon.

## 16. Operational Priority Queue Rule

The main command center must surface one unified operational priority queue instead of forcing users to inspect separate alert/task/recommendation/weather lists.

Priority is ranked by:

```text
severity
time_window
expected_yield_impact
equipment_availability
weather_suitability
confidence
```

## 17. Map Clutter Control Rule

The map must protect itself from layer overload.

Default constraints:

```text
max_default_operational_layers = 3
critical_tasks_always_visible = true
stale_alerts_auto_archive = true
sensor_cluster_zoom_threshold = configurable
equipment_live_only_in_equipment_mode = true
```

Layer presets:

```text
health
irrigation
operations
weather
scouting
economics
```

## 18. Action from Map Rule

No operational layer is display-only.

Every feature on the map must expose at least one contextual action when actionable:

```text
low_ndvi_zone → create scouting task
low_moisture_sensor → create irrigation task
equipment_marker → assign task or open maintenance
pest_observation → create spray/scouting task
field_polygon → open Field Workspace
```

## 19. Unified Field Timeline Rule

Every field must have a unified timeline that can include:

```text
planting
satellite_image
alert
task
scouting_observation
irrigation
spraying
fertilization
recommendation
verification
outcome
report
```

This timeline is the season narrative and the audit surface for learning.

## 20. Design QA Gate Rule

Before any major UI merge, these gates must pass:

```text
RTL smoke
mobile viewport smoke
layer contract smoke
no orphan buttons
no direct service URLs
no feature without data owner
no recommendation without lineage
no task without field or season when seasonal
no map layer without empty/error/stale/degraded state
bundle budget
```
