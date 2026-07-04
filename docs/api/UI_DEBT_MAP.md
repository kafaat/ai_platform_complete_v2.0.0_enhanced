# خريطة دَين الواجهة — Backend مواجِه بلا شاشة بعد

> يُولَّد من `config/endpoint_ui_coverage_waivers.json`. البوّابة العكسيّة تُجمّد الحدّ؛
> هذه قائمة العمل لتقليص الدَّين: كلّما بُنيت شاشة، انقل مسارها من الإعفاءات إلى core.

## ملخّص

- **دَين واجهة حقيقيّ (backlog-ui):** 170 مسار
- **إعفاء تشغيليّ دائم (admin-ops/operational):** 11 مسار — لا تتطلّب شاشة مستخدم
- **مرتبط فعلاً بالواجهة (core):** 243 مسار ✅

## دَين الواجهة بالمجال (الأولويّة تنازليّاً)

| المجال | مسارات بلا شاشة |
|---|---|
| weather | 15 |
| agro | 9 |
| decision | 8 |
| auth | 7 |
| agro-zones | 6 |
| recommendations | 5 |
| calendars | 4 |
| climate-analogs | 4 |
| gis | 4 |
| water-sensitivity | 4 |
| districts | 3 |
| farm-ledger | 3 |
| introduction | 3 |
| learning | 3 |
| propagation | 3 |
| rbac | 3 |
| soil-sampling | 3 |
| astronomical-timing | 2 |
| chemical-safety | 2 |
| confidence | 2 |
| consistency | 2 |
| crops | 2 |
| economics | 2 |
| field | 2 |
| geo-locate | 2 |
| high-value-crops | 2 |
| irrigation | 2 |
| market | 2 |
| niche-crops | 2 |
| notifications | 2 |
| onboarding | 2 |
| orchard | 2 |
| planting | 2 |
| practices | 2 |
| reports | 2 |
| rotation | 2 |
| temporal | 2 |
| weather-analytics | 2 |
| wofost | 2 |
| analytics | 1 |
| aromatic-crops | 1 |
| calibration | 1 |
| cameras | 1 |
| confidence-gate | 1 |
| crop-suitability | 1 |
| crop-twin | 1 |
| cultural-calendar | 1 |
| data-readiness | 1 |
| escalation | 1 |
| evidence | 1 |
| failures | 1 |
| field-portfolio | 1 |
| fields | 1 |
| fodder-alternatives | 1 |
| indicators | 1 |
| indices | 1 |
| irrigation-method | 1 |
| irrigation-recommendation | 1 |
| lab | 1 |
| lineage | 1 |
| me | 1 |
| nutrients | 1 |
| observations | 1 |
| outcome | 1 |
| policy-learning | 1 |
| postharvest | 1 |
| regional-calendar | 1 |
| replay | 1 |
| sampling | 1 |
| seasonal-risk | 1 |
| seed | 1 |
| settings | 1 |
| sharing | 1 |
| simulate | 1 |
| trials | 1 |
| water-balance | 1 |
| water-harvesting | 1 |
| work-orders | 1 |

## التفصيل الكامل (backlog-ui)

### weather (15)
- `/api/v1/weather/alerts`
- `/api/v1/weather/alerts/notify`
- `/api/v1/weather/env-doctor`
- `/api/v1/weather/field-weather-summary`
- `/api/v1/weather/layers`
- `/api/v1/weather/observability`
- `/api/v1/weather/rate-limit/backend`
- `/api/v1/weather/runtime-contract`
- `/api/v1/weather/runtime-smoke-plan`
- `/api/v1/weather/self-test`
- `/api/v1/weather/tile-cache/backend`
- `/api/v1/weather/tile-cache/prune`
- `/api/v1/weather/tile-cache/stats`
- `/api/v1/weather/tile-series/{z}/{x}/{y}`
- `/api/v1/weather/wind-source-selftest`

### agro (9)
- `/api/v1/agro/crop-risk`
- `/api/v1/agro/crop-rotation`
- `/api/v1/agro/decision-playbook`
- `/api/v1/agro/kc-timeseries`
- `/api/v1/agro/kc-timeseries/{field_id}`
- `/api/v1/agro/kc-timeseries/{field_id}/compare`
- `/api/v1/agro/plant-soil-feedback`
- `/api/v1/agro/plant-soil-feedback/trend`
- `/api/v1/agro/season-comparison`

### decision (8)
- `/api/v1/decision/dispatch/consume`
- `/api/v1/decision/dispatch/execute`
- `/api/v1/decision/economics`
- `/api/v1/decision/explain`
- `/api/v1/decision/for-location`
- `/api/v1/decision/policies/resolve`
- `/api/v1/decision/record`
- `/api/v1/decision/unified`

### auth (7)
- `/api/v1/auth/me`
- `/api/v1/auth/signup`
- `/auth/me`
- `/auth/tenants`
- `/auth/users`
- `/auth/users/{user_id}/deactivate`
- `/auth/users/{user_id}/role`

### agro-zones (6)
- `/api/v1/agro-zones/by-elevation`
- `/api/v1/agro-zones/identify`
- `/api/v1/agro-zones/identify-smart`
- `/api/v1/agro-zones/list`
- `/api/v1/agro-zones/profile`
- `/api/v1/agro-zones/suited-crops`

### recommendations (5)
- `/api/v1/recommendations/candidates`
- `/api/v1/recommendations/capacity-profiles`
- `/api/v1/recommendations/economic-adaptation`
- `/api/v1/recommendations/engines`
- `/api/v1/recommendations/outcomes`

### calendars (4)
- `/api/v1/calendars/context`
- `/api/v1/calendars/himyarite-months`
- `/api/v1/calendars/lunar-mansions`
- `/api/v1/calendars/regional-profiles`

### climate-analogs (4)
- `/api/v1/climate-analogs/desert-crops`
- `/api/v1/climate-analogs/detail`
- `/api/v1/climate-analogs/strategic-tiers`
- `/api/v1/climate-analogs/strategy`

### gis (4)
- `/api/v1/gis/buffer`
- `/api/v1/gis/split`
- `/api/v1/gis/union`
- `/api/v1/gis/validate`

### water-sensitivity (4)
- `/api/v1/water-sensitivity/crops`
- `/api/v1/water-sensitivity/integrated-advice`
- `/api/v1/water-sensitivity/stress-risk`
- `/api/v1/water-sensitivity/wheat-calendar`

### districts (3)
- `/api/v1/districts`
- `/api/v1/districts/{district_id}`
- `/api/v1/districts/{district_id}/active-pests`

### farm-ledger (3)
- `/api/v1/farm-ledger/autowrite-preview`
- `/api/v1/farm-ledger/erp-projection/{season_id}`
- `/api/v1/farm-ledger/inventory-projection/{season_id}`

### introduction (3)
- `/api/v1/introduction/candidates`
- `/api/v1/introduction/card`
- `/api/v1/introduction/field-fit`

### learning (3)
- `/api/v1/learning/activation-status`
- `/api/v1/learning/external-prior-blend`
- `/api/v1/learning/prediction-calibration`

### propagation (3)
- `/api/v1/propagation/method-guide`
- `/api/v1/propagation/methods`
- `/api/v1/propagation/rootstock`

### rbac (3)
- `/api/v1/rbac/permission-matrix`
- `/api/v1/rbac/preview-role-change`
- `/api/v1/rbac/who-can`

### soil-sampling (3)
- `/api/v1/soil-sampling/depth`
- `/api/v1/soil-sampling/protocol`
- `/api/v1/soil-sampling/subsamples`

### astronomical-timing (2)
- `/api/v1/astronomical-timing/cross-check`
- `/api/v1/astronomical-timing/stars`

### chemical-safety (2)
- `/api/v1/chemical-safety/banned`
- `/api/v1/chemical-safety/check`

### confidence (2)
- `/api/v1/confidence/irrigation`
- `/api/v1/confidence/ndvi`

### consistency (2)
- `/api/v1/consistency/freshness`
- `/api/v1/consistency/irrigation`

### crops (2)
- `/api/v1/crops/compare-drought-resilience`
- `/api/v1/crops/drought-resilience`

### economics (2)
- `/api/v1/economics/cost-categories`
- `/api/v1/economics/feasibility`

### field (2)
- `/api/v1/field/operational-state`
- `/api/v1/field/{field_id}/lineage`

### geo-locate (2)
- `/api/v1/geo-locate/field`
- `/api/v1/geo-locate/recommend`

### high-value-crops (2)
- `/api/v1/high-value-crops/detail`
- `/api/v1/high-value-crops/list`

### irrigation (2)
- `/api/v1/irrigation/moisture-decision`
- `/api/v1/irrigation/soil-types`

### market (2)
- `/api/v1/market/crop-classification-readiness`
- `/api/v1/market/crop-gap`

### niche-crops (2)
- `/api/v1/niche-crops/detail`
- `/api/v1/niche-crops/list`

### notifications (2)
- `/api/v1/notifications/delivery`
- `/api/v1/notifications/ws`

### onboarding (2)
- `/api/v1/onboarding/questionnaire`
- `/api/v1/onboarding/responses`

### orchard (2)
- `/api/v1/orchard/economics`
- `/api/v1/orchard/plan`

### planting (2)
- `/api/v1/planting/crops`
- `/api/v1/planting/window`

### practices (2)
- `/api/v1/practices/guide`
- `/api/v1/practices/list`

### reports (2)
- `/api/v1/reports/build`
- `/api/v1/reports/operation`

### rotation (2)
- `/api/v1/rotation/evaluate`
- `/api/v1/rotation/principles`

### temporal (2)
- `/api/v1/temporal/check`
- `/api/v1/temporal/coherence`

### weather-analytics (2)
- `/api/v1/weather-analytics/analyze`
- `/api/v1/weather-analytics/planting-guide`

### wofost (2)
- `/api/v1/wofost/adaptation-guidance`
- `/api/v1/wofost/crop-types`

### analytics (1)
- `/api/v1/analytics/costs/by-field`

### aromatic-crops (1)
- `/api/v1/aromatic-crops/list`

### calibration (1)
- `/api/v1/calibration/feedback`

### cameras (1)
- `/api/v1/cameras/snapshot-evidence`

### confidence-gate (1)
- `/api/v1/confidence-gate`

### crop-suitability (1)
- `/api/v1/crop-suitability`

### crop-twin (1)
- `/api/v1/crop-twin/compose`

### cultural-calendar (1)
- `/api/v1/cultural-calendar`

### data-readiness (1)
- `/api/v1/data-readiness`

### escalation (1)
- `/api/v1/escalation/assess`

### evidence (1)
- `/api/v1/evidence/corroborate`

### failures (1)
- `/api/v1/failures/check`

### field-portfolio (1)
- `/api/v1/field-portfolio/optimize`

### fields (1)
- `/api/v1/fields/validate-geometry`

### fodder-alternatives (1)
- `/api/v1/fodder-alternatives/list`

### indicators (1)
- `/api/v1/indicators/map-layers`

### indices (1)
- `/api/v1/indices/coverage-report`

### irrigation-method (1)
- `/api/v1/irrigation-method/gross`

### irrigation-recommendation (1)
- `/api/v1/irrigation-recommendation`

### lab (1)
- `/api/v1/lab/water-results`

### lineage (1)
- `/api/v1/lineage/link`

### me (1)
- `/api/v1/me`

### nutrients (1)
- `/api/v1/nutrients/4r-plan`

### observations (1)
- `/api/v1/observations`

### outcome (1)
- `/api/v1/outcome/record`

### policy-learning (1)
- `/api/v1/policy-learning/threshold-suggestions`

### postharvest (1)
- `/api/v1/postharvest/pests`

### regional-calendar (1)
- `/api/v1/regional-calendar`

### replay (1)
- `/api/v1/replay/reconstruct`

### sampling (1)
- `/api/v1/sampling/strategy`

### seasonal-risk (1)
- `/api/v1/seasonal-risk/stage-check`

### seed (1)
- `/api/v1/seed/evaluate-source`

### settings (1)
- `/api/v1/settings`

### sharing (1)
- `/api/v1/sharing/generate-key`

### simulate (1)
- `/api/v1/simulate/what-if`

### trials (1)
- `/api/v1/trials/analyze`

### water-balance (1)
- `/api/v1/water-balance`

### water-harvesting (1)
- `/api/v1/water-harvesting/upstream-flood`

### work-orders (1)
- `/api/v1/work-orders/from-recommendation`

