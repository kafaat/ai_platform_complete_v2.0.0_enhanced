# خريطة دَين الواجهة — مُصنّفة بالكامل

> **تحديث ٥ (إغلاق نهائيّ): صفر دَين واجهة (backlog-ui = 0).** بُنيت النقاط الثلاث الأخيرة بواجهات حقيقيّة:
> اتّجاه نبات-تربة متعدّد المواسم (في AgroAnalyticsCard) · سلسلة طقس زمنيّة للبلاطة (في DistrictsWeatherCard،
> بلاطة تُشتقّ من إحداثيّات الحقل) · تهيئة مستأجِر (في ManagerConsolePage، admin). **العقد 438 core + 28 إعفاء**
> (كلّها admin-ops/operational — machine، لا شاشة بالتصميم). كلّ قدرة backend مواجِهة للمستخدم لها الآن قارئ واجهة.
> **تحديث ٤ (نهائيّ): سُدّدت شريحة P3-منخفض كاملةً (50 مساراً)** — 3 بطاقات FieldView
> (المحاصيل الاختصاصيّة · GIS/الزمن/المحاكاة · التعلُّم والدليل) + صفحة «كونسول المدير»
> (`/admin/manager-console`، 18 مساراً محكومة بـcanManage). العقد الآن **435 core + 31 إعفاء**.
> **لم يبقَ إلا 3 دَين واجهة مُوثَّق** (عمل معماريّ متمايز، لا يُختلَق له UI أجوف): اتّجاه
> نبات-تربة متعدّد المواسم · مصدر بلاطات طقس زمنيّة (طبقة خريطة) · تهيئة مستأجِر جديد
> (`/v1/auth/tenants`، admin). بدأ اليوم بـ24 endpoint ملزَماً؛ انتهى بـ435.
> **تحديث ٣ (فجراً): سُدّدت شريحة P2-متوسّط كاملةً (32 مساراً)** — بطاقات «المحاصيل المتخصّصة
> والتوقيت التراثيّ» و«المديريّات والطقس والتهيئة» و«اتّساق البيانات والدورة وWOFOST والعمليّات»
> في FieldView (خبير). العقد الآن **385 core + 81 إعفاء** — لم يبقَ إلا P3-منخفض.
> **تحديث ٢ (ليلاً): سُدّدت شريحة P1-عالٍ كاملةً (30 مساراً)** — بطاقات «سلامة المدخلات
> ومعرفة المحاصيل» و«التحليلات الزراعيّة-البيئيّة» (بما فيها **حفظ Kc** upsert) و«عمليّات
> الماء والحقل» في FieldView (خبير) + «أعضاء الفريق والأدوار» في الإعدادات (ثلاثيّ
> auth/users بجمهور admin المصحَّح). العقد الآن **352 core + 114 إعفاء** — المتبقّي P2/P3 فقط.
> **تحديث 2026-07-04 (مساءً): سُدّدت شريحة P0-الحرِجة كاملةً (21 مساراً)** — لوحتا «القرار العميق»
> و«دورة حياة التوصية» في كونسول تشغيل القرار + بطاقة «مساعدات قرار الريّ والعيّنات» في FieldView
> (وضع الخبير)، ورُقّيت المسارات الـ21 إلى العقد الملزم (core=320). `dispatch/consume` أُعيد تصنيفه
> **operational** (مستهلِك طابور آليّ بقفل FOR UPDATE SKIP LOCKED — ليس دَين واجهة).
> المتبقّي في السجلّ: 146 إعفاء (الجدول أدناه يعكس حالة ما قبل السداد؛ P1 هي الشريحة التالية).

> 143 دَين واجهة (كلّها مستهلكها **human** — فُرزت بالكامل، لا mixed) + 24 تشغيليّ (machine).
> حارس CI يمنع: تصنيف مسار service-token كدَين · إعفاء بلا مستهلك مُعلَن · دَين بلا أهمّية.

## المستهلك (النظام كاملاً)

- دَين واجهة (human، يحتاج شاشة): 143
- تشغيليّ (machine، لا شاشة): 24

## شرائح الأهمّية

| الشريحة | عدد |
|---|---|
| P0-حرِج | 21 |
| P1-عالٍ | 32 |
| P2-متوسّط | 40 |
| P3-منخفض | 50 |

## القائمة (أهمّية ↓)

| # | أهمّية | شريحة | حرجيّة | المسار | جهد |
|---|---|---|---|---|---|
| 1 | 98 | P0-حرِج | critical | `/api/v1/recommendations/candidates` | page |
| 2 | 90 | P0-حرِج | critical | `/api/v1/decision/economics` | button |
| 3 | 90 | P0-حرِج | critical | `/api/v1/recommendations/outcomes` | page |
| 4 | 88 | P0-حرِج | critical | `/api/v1/confidence/irrigation` | page |
| 5 | 88 | P0-حرِج | critical | `/api/v1/confidence/ndvi` | page |
| 6 | 88 | P0-حرِج | critical | `/api/v1/decision/dispatch/execute` | page |
| 7 | 88 | P0-حرِج | critical | `/api/v1/water-sensitivity/crops` | button |
| 8 | 82 | P0-حرِج | critical | `/api/v1/decision/explain` | button |
| 9 | 82 | P0-حرِج | critical | `/api/v1/recommendations/engines` | button |
| 10 | 80 | P0-حرِج | decision-support | `/api/v1/agro/plant-soil-feedback/trend` | page |
| 11 | 80 | P0-حرِج | critical | `/api/v1/decision/dispatch/consume` | page |
| 12 | 80 | P0-حرِج | critical | `/api/v1/decision/for-location` | button |
| 13 | 80 | P0-حرِج | critical | `/api/v1/decision/policies/resolve` | page |
| 14 | 80 | P0-حرِج | critical | `/api/v1/decision/record` | page |
| 15 | 80 | P0-حرِج | critical | `/api/v1/decision/unified` | page |
| 16 | 80 | P0-حرِج | critical | `/api/v1/irrigation-method/gross` | page |
| 17 | 80 | P0-حرِج | critical | `/api/v1/irrigation/moisture-decision` | button |
| 18 | 80 | P0-حرِج | critical | `/api/v1/irrigation/soil-types` | button |
| 19 | 80 | P0-حرِج | critical | `/api/v1/recommendations/capacity-profiles` | button |
| 20 | 80 | P0-حرِج | critical | `/api/v1/recommendations/economic-adaptation` | page |
| 21 | 78 | P0-حرِج | critical | `/api/v1/soil-sampling/protocol` | button |
| 22 | 74 | P1-عالٍ | critical | `/api/v1/soil-sampling/depth` | button |
| 23 | 72 | P1-عالٍ | critical | `/api/v1/soil-sampling/subsamples` | button |
| 24 | 70 | P1-عالٍ | critical | `/api/v1/chemical-safety/check` | page |
| 25 | 68 | P1-عالٍ | critical | `/api/v1/chemical-safety/banned` | button |
| 26 | 68 | P1-عالٍ | decision-support | `/api/v1/planting/crops` | button |
| 27 | 68 | P1-عالٍ | decision-support | `/api/v1/planting/window` | button |
| 28 | 68 | P1-عالٍ | critical | `/api/v1/water-sensitivity/integrated-advice` | page |
| 29 | 68 | P1-عالٍ | critical | `/api/v1/water-sensitivity/stress-risk` | page |
| 30 | 68 | P1-عالٍ | critical | `/api/v1/water-sensitivity/wheat-calendar` | button |
| 31 | 66 | P1-عالٍ | critical | `/api/v1/postharvest/pests` | button |
| 32 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/crop-risk` | page |
| 33 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/crop-rotation` | page |
| 34 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/decision-playbook` | page |
| 35 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/kc-timeseries` | page |
| 36 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/kc-timeseries/{field_id}` | panel |
| 37 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/kc-timeseries/{field_id}/compare` | panel |
| 38 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/plant-soil-feedback` | page |
| 39 | 60 | P1-عالٍ | decision-support | `/api/v1/agro/season-comparison` | page |
| 40 | 60 | P1-عالٍ | informational | `/api/v1/field/{field_id}/lineage` | panel |
| 41 | 60 | P1-عالٍ | informational | `/api/v1/geo-locate/field` | button |
| 42 | 60 | P1-عالٍ | informational | `/api/v1/high-value-crops/detail` | button |
| 43 | 60 | P1-عالٍ | informational | `/api/v1/niche-crops/detail` | button |
| 44 | 60 | P1-عالٍ | informational | `/api/v1/weather/alerts` | button |
| 45 | 60 | P1-عالٍ | informational | `/v1/auth/users/{user_id}/role` | page |
| 46 | 58 | P1-عالٍ | critical | `/api/v1/escalation/assess` | page |
| 47 | 58 | P1-عالٍ | informational | `/api/v1/introduction/candidates` | button |
| 48 | 58 | P1-عالٍ | critical | `/api/v1/lab/water-results` | page |
| 49 | 58 | P1-عالٍ | critical | `/api/v1/nutrients/4r-plan` | page |
| 50 | 58 | P1-عالٍ | critical | `/api/v1/outcome/record` | page |
| 51 | 58 | P1-عالٍ | critical | `/api/v1/water-balance` | page |
| 52 | 58 | P1-عالٍ | critical | `/api/v1/water-harvesting/upstream-flood` | button |
| 53 | 58 | P1-عالٍ | informational | `/api/v1/weather/layers` | button |
| 54 | 50 | P2-متوسّط | informational | `/api/v1/onboarding/responses` | page |
| 55 | 50 | P2-متوسّط | informational | `/api/v1/orchard/economics` | button |
| 56 | 50 | P2-متوسّط | informational | `/api/v1/orchard/plan` | button |
| 57 | 48 | P2-متوسّط | informational | `/api/v1/consistency/irrigation` | button |
| 58 | 48 | P2-متوسّط | informational | `/api/v1/reports/operation` | page |
| 59 | 48 | P2-متوسّط | decision-support | `/api/v1/rotation/evaluate` | button |
| 60 | 48 | P2-متوسّط | decision-support | `/api/v1/rotation/principles` | button |
| 61 | 48 | P2-متوسّط | decision-support | `/api/v1/wofost/adaptation-guidance` | button |
| 62 | 48 | P2-متوسّط | decision-support | `/api/v1/wofost/crop-types` | button |
| 63 | 48 | P2-متوسّط | informational | `/v1/auth/tenants` | page |
| 64 | 46 | P2-متوسّط | informational | `/api/v1/weather/field-weather-summary` | button |
| 65 | 44 | P2-متوسّط | informational | `/api/v1/districts` | button |
| 66 | 42 | P2-متوسّط | informational | `/api/v1/aromatic-crops/list` | button |
| 67 | 42 | P2-متوسّط | informational | `/api/v1/astronomical-timing/stars` | button |
| 68 | 42 | P2-متوسّط | informational | `/api/v1/fodder-alternatives/list` | button |
| 69 | 42 | P2-متوسّط | informational | `/api/v1/geo-locate/recommend` | button |
| 70 | 42 | P2-متوسّط | informational | `/api/v1/high-value-crops/list` | button |
| 71 | 42 | P2-متوسّط | informational | `/api/v1/introduction/card` | button |
| 72 | 42 | P2-متوسّط | informational | `/api/v1/niche-crops/list` | button |
| 73 | 40 | P2-متوسّط | informational | `/api/v1/astronomical-timing/cross-check` | page |
| 74 | 40 | P2-متوسّط | informational | `/api/v1/auth/me` | button |
| 75 | 40 | P2-متوسّط | informational | `/api/v1/auth/signup` | page |
| 76 | 40 | P2-متوسّط | informational | `/api/v1/consistency/freshness` | button |
| 77 | 40 | P2-متوسّط | informational | `/api/v1/cultural-calendar` | button |
| 78 | 40 | P2-متوسّط | informational | `/api/v1/districts/{district_id}` | panel |
| 79 | 40 | P2-متوسّط | informational | `/api/v1/districts/{district_id}/active-pests` | panel |
| 80 | 40 | P2-متوسّط | informational | `/api/v1/field-portfolio/optimize` | page |
| 81 | 40 | P2-متوسّط | informational | `/api/v1/field/operational-state` | button |
| 82 | 40 | P2-متوسّط | informational | `/api/v1/fields/validate-geometry` | page |
| 83 | 40 | P2-متوسّط | informational | `/api/v1/introduction/field-fit` | page |
| 84 | 40 | P2-متوسّط | informational | `/api/v1/irrigation-recommendation` | page |
| 85 | 40 | P2-متوسّط | informational | `/api/v1/me` | button |
| 86 | 40 | P2-متوسّط | informational | `/api/v1/onboarding/questionnaire` | button |
| 87 | 40 | P2-متوسّط | informational | `/api/v1/regional-calendar` | button |
| 88 | 40 | P2-متوسّط | informational | `/api/v1/weather-analytics/analyze` | page |
| 89 | 40 | P2-متوسّط | informational | `/api/v1/weather-analytics/planting-guide` | page |
| 90 | 40 | P2-متوسّط | informational | `/api/v1/weather/tile-series/{z}/{x}/{y}` | page |
| 91 | 40 | P2-متوسّط | informational | `/v1/auth/me` | button |
| 92 | 40 | P2-متوسّط | informational | `/v1/auth/users` | button |
| 93 | 40 | P2-متوسّط | informational | `/v1/auth/users/{user_id}/deactivate` | page |
| 94 | 38 | P3-منخفض | decision-support | `/api/v1/crop-suitability` | page |
| 95 | 38 | P3-منخفض | decision-support | `/api/v1/crop-twin/compose` | page |
| 96 | 38 | P3-منخفض | informational | `/api/v1/propagation/methods` | button |
| 97 | 38 | P3-منخفض | decision-support | `/api/v1/seasonal-risk/stage-check` | button |
| 98 | 38 | P3-منخفض | decision-support | `/api/v1/simulate/what-if` | page |
| 99 | 34 | P3-منخفض | informational | `/api/v1/gis/validate` | page |
| 100 | 30 | P3-منخفض | informational | `/api/v1/economics/feasibility` | page |
| 101 | 30 | P3-منخفض | informational | `/api/v1/gis/buffer` | page |
| 102 | 30 | P3-منخفض | informational | `/api/v1/gis/split` | page |
| 103 | 30 | P3-منخفض | informational | `/api/v1/gis/union` | page |
| 104 | 30 | P3-منخفض | informational | `/api/v1/practices/list` | button |
| 105 | 30 | P3-منخفض | informational | `/api/v1/temporal/check` | page |
| 106 | 30 | P3-منخفض | informational | `/api/v1/temporal/coherence` | page |
| 107 | 28 | P3-منخفض | informational | `/api/v1/crops/compare-drought-resilience` | button |
| 108 | 28 | P3-منخفض | informational | `/api/v1/crops/drought-resilience` | button |
| 109 | 28 | P3-منخفض | informational | `/api/v1/farm-ledger/autowrite-preview` | page |
| 110 | 28 | P3-منخفض | informational | `/api/v1/learning/activation-status` | button |
| 111 | 28 | P3-منخفض | informational | `/api/v1/learning/external-prior-blend` | page |
| 112 | 28 | P3-منخفض | informational | `/api/v1/learning/prediction-calibration` | button |
| 113 | 28 | P3-منخفض | informational | `/api/v1/practices/guide` | button |
| 114 | 28 | P3-منخفض | informational | `/api/v1/propagation/method-guide` | button |
| 115 | 28 | P3-منخفض | informational | `/api/v1/propagation/rootstock` | button |
| 116 | 28 | P3-منخفض | informational | `/api/v1/reports/build` | page |
| 117 | 24 | P3-منخفض | informational | `/api/v1/sampling/strategy` | button |
| 118 | 22 | P3-منخفض | informational | `/api/v1/observations` | page |
| 119 | 20 | P3-منخفض | informational | `/api/v1/calibration/feedback` | page |
| 120 | 20 | P3-منخفض | informational | `/api/v1/failures/check` | page |
| 121 | 20 | P3-منخفض | informational | `/api/v1/settings` | page |
| 122 | 18 | P3-منخفض | informational | `/api/v1/analytics/costs/by-field` | button |
| 123 | 18 | P3-منخفض | informational | `/api/v1/cameras/snapshot-evidence` | page |
| 124 | 18 | P3-منخفض | informational | `/api/v1/confidence-gate` | page |
| 125 | 18 | P3-منخفض | informational | `/api/v1/data-readiness` | page |
| 126 | 18 | P3-منخفض | informational | `/api/v1/economics/cost-categories` | button |
| 127 | 18 | P3-منخفض | informational | `/api/v1/evidence/corroborate` | page |
| 128 | 18 | P3-منخفض | informational | `/api/v1/farm-ledger/erp-projection/{season_id}` | panel |
| 129 | 18 | P3-منخفض | informational | `/api/v1/farm-ledger/inventory-projection/{season_id}` | panel |
| 130 | 18 | P3-منخفض | informational | `/api/v1/indicators/map-layers` | button |
| 131 | 18 | P3-منخفض | informational | `/api/v1/indices/coverage-report` | button |
| 132 | 18 | P3-منخفض | informational | `/api/v1/lineage/link` | page |
| 133 | 18 | P3-منخفض | informational | `/api/v1/market/crop-classification-readiness` | button |
| 134 | 18 | P3-منخفض | informational | `/api/v1/market/crop-gap` | button |
| 135 | 18 | P3-منخفض | informational | `/api/v1/policy-learning/threshold-suggestions` | button |
| 136 | 18 | P3-منخفض | informational | `/api/v1/rbac/permission-matrix` | button |
| 137 | 18 | P3-منخفض | informational | `/api/v1/rbac/preview-role-change` | button |
| 138 | 18 | P3-منخفض | informational | `/api/v1/rbac/who-can` | button |
| 139 | 18 | P3-منخفض | informational | `/api/v1/replay/reconstruct` | page |
| 140 | 18 | P3-منخفض | informational | `/api/v1/seed/evaluate-source` | page |
| 141 | 18 | P3-منخفض | informational | `/api/v1/sharing/generate-key` | page |
| 142 | 18 | P3-منخفض | informational | `/api/v1/trials/analyze` | page |
| 143 | 18 | P3-منخفض | informational | `/api/v1/work-orders/from-recommendation` | page |

## تشغيليّ (machine — لا شاشة مستخدم)

- `/api/v1/admin/break-glass` — مسار إداريّ/تشغيليّ — أدوات التشغيل منفصلة؛ لا شاشة مستخدم نهائيّ.
- `/api/v1/admin/break-glass/{grant_id}` — مسار إداريّ/تشغيليّ — أدوات التشغيل منفصلة؛ لا شاشة مستخدم نهائيّ.
- `/api/v1/admin/break-glass/{token}/fields` — مسار إداريّ/تشغيليّ — أدوات التشغيل منفصلة؛ لا شاشة مستخدم نهائيّ.
- `/api/v1/admin/events/dead-letter/requeue-all` — مسار إداريّ/تشغيليّ — أدوات التشغيل منفصلة؛ لا شاشة مستخدم نهائيّ.
- `/api/v1/admin/outbox/dead-letter/requeue` — مسار إداريّ/تشغيليّ — أدوات التشغيل منفصلة؛ لا شاشة مستخدم نهائيّ.
- `/api/v1/automation/imagery/register-field` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/automation/imagery/status` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/automation/weather/cached` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/automation/weather/register` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/automation/weather/status` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/cameras/register` — مسار أتمتة/تسجيل خلفيّ يُستدعى آليّاً (scheduler/worker) لا من واجهة.
- `/api/v1/notifications/delivery` — upsert إيصال تسليم إشعار — تكامل خلفيّ (بوّابة تسليم) لا مستخدم.
- `/api/v1/notifications/ws` — نقطة WebSocket (بروتوكول آلة، @router.websocket) — لا واجهة REST مرئيّة.
- `/api/v1/weather/alerts/notify` — POST إرسال إشعار تنبيه — تكامل تسليم (بوّابة) لا عرض مستخدم.
- `/api/v1/weather/env-doctor` — تقرير حارس تشغيليّ لإعدادات محرّك الطقس (Depends _require_service_token، internal/admin) — مستهلكه آلة/مشغّل لا مستخدم.
- `/api/v1/weather/observability` — مشاهدة تشغيليّة خفيفة لمحرّك الطقس (مقاييس) — مستهلكها لوحة مراقبة/مشغّل لا مستخدم.
- `/api/v1/weather/rate-limit/backend` — يكشف backend تحديد المعدّل الفعّال — تشخيص تشغيليّ لا واجهة.
- `/api/v1/weather/runtime-contract` — مسار عقد تشغيل ثابت (Depends _require_service_token) لفحوص تكامل CI/UI — لا شاشة مستخدم نهائيّ.
- `/api/v1/weather/runtime-smoke-plan` — خطّة smoke موجّهة للمشغّلين (Docker/Compose/K8s) وCI — لا شاشة مستخدم نهائيّ.
- `/api/v1/weather/self-test` — اختبار ذاتيّ جافّ لمحرّك الطقس (dry-run بلا I/O) — CI/تشخيص لا واجهة.
- `/api/v1/weather/tile-cache/backend` — كشف تهيئة backend كاش الطقس (بلا Redis URL) — تشخيص تشغيليّ لا واجهة.
- `/api/v1/weather/tile-cache/prune` — صيانة تشذيب ذاكرة البلاطات (Depends _require_service_token) — عمليّة آلة.
- `/api/v1/weather/tile-cache/stats` — إحصاء كاش بلاطات الطقس — مراقبة تشغيليّة لا واجهة مستخدم.
- `/api/v1/weather/wind-source-selftest` — اختبار ذاتيّ لمصدر الرياح — تشخيص محرّك لا واجهة مستخدم.
