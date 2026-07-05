# مصفوفة تفويض المسارات — sahool-platform (`/api/v1` + `/auth`)

> مولَّدة من شجرة تبعيّات FastAPI الفعليّة (لا مسحاً نصّيّاً) — تحلّ التفويض على مستوى
> المسار والراوتر والتطبيق. تُغلق البند #4 من التدقيق الجنائيّ 2026-07-05.
> يُعاد التوليد بـ`scripts/ci/gen_route_auth_matrix.py`؛ حارس `test_route_auth_matrix_guard`.

## الحصيلة

| الفئة | user-auth (JWT) | service-token | PUBLIC | الإجمالي |
|---|---|---|---|---|
| **مُطفِّرة** (POST/PUT/PATCH/DELETE) | 194 | 1 | 2 | 197 |
| **قراءة** (GET) | 179 | 4 | 103 | 286 |

**لا مسار مُطفِّر مكشوف:** الوحيدان العامّان `POST /api/v1/auth/login` و`/signup` (عامّان بالضرورة — لا مصادقة قبلهما). حارس `test_all_mutating_endpoints_require_auth` يفشل fail-closed على أيّ انحدار.

## القراءات العامّة (103) — مرجعيّة/معرفيّة/طقس بلا بيانات مستأجِر

كلّها إمّا معرفة مرجعيّة ثابتة (تقاويم · أقاليم · أدلّة محاصيل · IPM · إكثار · أمثال)،
أو طقس (Open-Meteo passthrough)، أو تركيب نقيّ بلا حالة (`field/operational-state`:
كلّ مدخلاته query params، لا يقرأ القاعدة). لا تُرجِع أيّ بيانات حقل/مستأجِر مخزَّنة.

- `GET /api/v1/agricultural-proverbs`
- `GET /api/v1/agricultural-proverbs/for-date`
- `GET /api/v1/agro-zones/by-elevation`
- `GET /api/v1/agro-zones/identify`
- `GET /api/v1/agro-zones/identify-smart`
- `GET /api/v1/agro-zones/list`
- `GET /api/v1/agro-zones/profile`
- `GET /api/v1/agro-zones/suited-crops`
- `GET /api/v1/aromatic-crops/list`
- `GET /api/v1/astronomical-timing/stars`
- `GET /api/v1/calendars/context`
- `GET /api/v1/calendars/himyarite-months`
- `GET /api/v1/calendars/lunar-mansions`
- `GET /api/v1/calendars/regional-profiles`
- `GET /api/v1/calendars/today`
- `GET /api/v1/chemical-safety/banned`
- `GET /api/v1/climate-analogs/desert-crops`
- `GET /api/v1/climate-analogs/detail`
- `GET /api/v1/climate-analogs/list`
- `GET /api/v1/climate-analogs/strategic-tiers`
- `GET /api/v1/climate-analogs/strategy`
- `GET /api/v1/coffee/guide`
- `GET /api/v1/coffee/pests`
- `GET /api/v1/coffee/site-suitability`
- `GET /api/v1/coffee/varieties`
- `GET /api/v1/cultural-calendar`
- `GET /api/v1/diagnose/symptoms`
- `GET /api/v1/economics/break-even`
- `GET /api/v1/economics/cost-categories`
- `GET /api/v1/field/operational-state`
- `GET /api/v1/fodder-alternatives/list`
- `GET /api/v1/geo-locate/field`
- `GET /api/v1/geo-locate/recommend`
- `GET /api/v1/high-value-crops/detail`
- `GET /api/v1/high-value-crops/list`
- `GET /api/v1/introduction/candidates`
- `GET /api/v1/introduction/card`
- `GET /api/v1/ipm/crop-pests`
- `GET /api/v1/ipm/pests`
- `GET /api/v1/ipm/plan`
- `GET /api/v1/irrigation/moisture-decision`
- `GET /api/v1/irrigation/soil-types`
- `GET /api/v1/niche-crops/detail`
- `GET /api/v1/niche-crops/list`
- `GET /api/v1/orchard/economics`
- `GET /api/v1/orchard/plan`
- `GET /api/v1/planting/check`
- `GET /api/v1/planting/crops`
- `GET /api/v1/planting/window`
- `GET /api/v1/postharvest/best-practices`
- `GET /api/v1/postharvest/moisture-check`
- `GET /api/v1/postharvest/pests`
- `GET /api/v1/practices/guide`
- `GET /api/v1/practices/list`
- `GET /api/v1/propagation/crop`
- `GET /api/v1/propagation/method-guide`
- `GET /api/v1/propagation/methods`
- `GET /api/v1/propagation/rootstock`
- `GET /api/v1/recommendations/capacity-profiles`
- `GET /api/v1/regional-calendar`
- `GET /api/v1/rotation/evaluate`
- `GET /api/v1/rotation/principles`
- `GET /api/v1/rotation/suggest`
- `GET /api/v1/seasonal-risk/calendar`
- `GET /api/v1/seasonal-risk/chill-hours`
- `GET /api/v1/seasonal-risk/stage-check`
- `GET /api/v1/seed/criteria`
- `GET /api/v1/seed/germination-rate`
- `GET /api/v1/seed/sowing-depth`
- `GET /api/v1/seed/storage-check`
- `GET /api/v1/soil-sampling/depth`
- `GET /api/v1/soil-sampling/protocol`
- `GET /api/v1/soil-sampling/subsamples`
- `GET /api/v1/water-harvesting/method-guide`
- `GET /api/v1/water-harvesting/methods`
- `GET /api/v1/water-harvesting/potential`
- `GET /api/v1/water-harvesting/upstream-flood`
- `GET /api/v1/water-sensitivity/calendar`
- `GET /api/v1/water-sensitivity/crops`
- `GET /api/v1/water-sensitivity/wheat-calendar`
- `GET /api/v1/weather/action-recommendation`
- `GET /api/v1/weather/alerts`
- `GET /api/v1/weather/current`
- `GET /api/v1/weather/field-weather-summary`
- `GET /api/v1/weather/forecast`
- `GET /api/v1/weather/health`
- `GET /api/v1/weather/historical`
- `GET /api/v1/weather/layers`
- `GET /api/v1/weather/observability`
- `GET /api/v1/weather/operation-plan`
- `GET /api/v1/weather/operation-tile-data/{z}/{x}/{y}`
- `GET /api/v1/weather/operation-window`
- `GET /api/v1/weather/probe`
- `GET /api/v1/weather/rate-limit/backend`
- `GET /api/v1/weather/readyz`
- `GET /api/v1/weather/runtime-smoke-plan`
- `GET /api/v1/weather/self-test`
- `GET /api/v1/weather/tile-cache/backend`
- `GET /api/v1/weather/tile-cache/stats`
- `GET /api/v1/weather/tile-data/{z}/{x}/{y}`
- `GET /api/v1/weather/tile-series/{z}/{x}/{y}`
- `GET /api/v1/wofost/adaptation-guidance`
- `GET /api/v1/wofost/crop-types`
