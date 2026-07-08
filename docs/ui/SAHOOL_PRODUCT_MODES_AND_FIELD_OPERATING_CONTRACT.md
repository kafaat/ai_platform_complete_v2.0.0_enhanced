# Sahool Product Modes and Field Operating Contract

This document converts the UI reorganization plan into an executable product taxonomy. It should be used by design, frontend, backend, QA, and product owners before adding navigation items, workspace panels, map layers, or recommendation flows.

## Product Modes

| Mode | Audience | Default scope | Hidden by default |
|---|---|---|---|
| `basic_farm` | individual farmer / small farm | fields, seasons, weather, basic tasks, simple reports | VRA, advanced zones, audit, enterprise economics, government aggregates |
| `precision` | precision farming operator / agronomist | imagery, zones, sensors, equipment, VRA, scouting, advanced recommendations | enterprise SLA, cross-tenant dashboards, government programs |
| `enterprise` | large farm company | teams, RBAC, audit, economics, integrations, SLA, fleet, reports | government regional oversight |
| `government_ngo` | government / NGO supervisor | regional maps, aggregate indicators, program monitoring, compliance reports | field-level private economics unless explicitly permitted |
| `demo` | demos, sales, testing | safe sample data, guided tours, simulated layers | real write operations unless sandboxed |

## Role-based UI

| Role | Primary surfaces | Restricted surfaces |
|---|---|---|
| Owner | economics, reports, approvals, performance, recommendations | low-level device calibration unless allowed |
| Manager | tasks, teams, equipment, planning, operations queue | tenant administration unless allowed |
| Agronomist | recommendations, scouting, imagery, weather risks, diseases | billing, sensitive audit |
| Worker | assigned tasks, execution, photos, GPS, offline sync | economics, approval workflows, user management |
| Government/NGO supervisor | aggregate maps, program reports, compliance | tenant-private operational details unless policy permits |

## Field Readiness Score

Field readiness is a user-facing completeness score that answers: “Is this field ready for useful intelligence?”

Recommended weighted inputs:

| Input | Weight | Notes |
|---|---:|---|
| active valid boundary | 20 | hard gate for analytics |
| active season | 15 | required for seasonal intelligence |
| crop selected | 10 | required for crop-specific logic |
| planting/start date | 10 | required for phenology/GDD |
| irrigation method | 10 | required for irrigation recommendations |
| weather available | 10 | required for operation windows |
| latest imagery fresh enough | 10 | threshold depends on crop/season |
| soil type or confidence | 8 | optional but confidence-affecting |
| open task state known | 4 | prevents duplicate recommendations |
| sensors available or explicitly absent | 3 | optional; absence is not failure if declared |

Display example:

```text
Field Readiness: 78%
✅ Boundary valid
✅ Active season
✅ Weather available
⚠ Soil type uncertain
⚠ No soil sample
⚠ Latest NDVI is 9 days old
```

## Data Completeness Panel

Every Field Workspace should show a compact data-completeness panel.

Categories:

```text
boundary
season
crop
soil
irrigation
imagery
weather
sensors
equipment
tasks
scouting
economics
reports
```

Each category supports:

```text
complete
partial
missing
not_available
stale
```

Each missing/partial state should provide a next action.

## Confidence Budget

Recommendations and risk scores must show confidence and deductions.

Required structure:

```json
{
  "confidence": 0.72,
  "base_confidence": 0.96,
  "deductions": [
    {"code": "unknown_soil_type", "label": "نوع التربة غير معروف", "points": 0.10},
    {"code": "missing_soil_moisture", "label": "لا توجد قراءة رطوبة", "points": 0.08},
    {"code": "stale_imagery", "label": "آخر صورة قمرية قديمة", "points": 0.06}
  ]
}
```

## Operational Priority Queue

A single queue should merge alerts, recommendations, tasks, operation windows, new imagery, and critical scouting observations.

Ranking formula inputs:

```text
severity
urgency_hours
yield_impact
confidence
equipment_availability
weather_window_quality
blocking_dependencies
```

## Map Clutter Control

Default map behavior:

```text
max_default_operational_layers = 3
critical_alerts_visible = true
critical_tasks_visible = true
sensor_clustering_enabled = true
equipment_live_layer_enabled_only_in_equipment_preset = true
stale_alerts_archived_or_dimmed = true
```

Presets:

| Preset | Default layers |
|---|---|
| health | field boundaries, truecolor, NDVI/stress zones, scouting tasks |
| irrigation | field boundaries, irrigation sectors, ET0, soil moisture, irrigation tasks |
| operations | field boundaries, tasks, equipment, alerts |
| weather | field boundaries, wind, rain, temperature, operation windows |
| scouting | field boundaries, observations, photos, scouting routes |
| economics | field boundaries, crop colors, cost/yield/profit overlays |

## Unified Field Timeline

The field timeline is the seasonal story and audit trail.

Event types:

```text
planting
satellite_image
weather_risk
sensor_alert
recommendation
task_created
task_completed
task_verified
scouting_observation
irrigation
spraying
fertilization
harvest
outcome_recorded
report_generated
```

## Action from Map

Map interactions must be operational:

| Map feature | Primary action |
|---|---|
| field polygon | open Field Workspace |
| low NDVI/stress zone | create scouting task |
| low soil moisture sensor | create irrigation task |
| pest observation | create scouting or spray task |
| equipment marker | assign task or open maintenance |
| weather operation window | create operation task |
| irrigation sector | schedule irrigation |
