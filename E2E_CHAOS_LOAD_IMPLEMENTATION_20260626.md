# تنفيذ E2E حي كامل + Chaos + Load Testing — 2026-06-26

## ما أُضيف

### 1) E2E حي كامل
- `scripts/e2e/live_full_e2e.py`
  - تسجيل/دخول مستخدم اختبار.
  - إنشاء حقل Polygon.
  - تعديل هندسة الحقل.
  - قراءة `GET /api/v1/fields/{id}/geometry/history`.
  - حساب مقارنة Timeline محلياً للتأكد من وجود فرق مساحة صالح.
  - اختبار تعارض `base_version` قديم ⇒ `409`.
  - اختبار هندسة فاسدة ⇒ `422`.
  - يتخطى بأمان عند غياب مكدس حي، ويمكن إجباره على الفشل عبر `REQUIRE_LIVE_E2E=1`.

### 2) E2E واجهة Timeline + Comparison Mode
- `frontend/e2e/gis-tools-timeline-comparison.spec.ts`
  - يفتح `/analysis/gis-tools`.
  - يفعّل Timeline + Comparison Mode.
  - يتحقق من تحميل مراجعات `geometry/history`.
  - يختار مراجعتين ويؤكد ظهور فرق المساحة والرؤوس وسجل المراجعات.
- `frontend/e2e/support/seed.ts`
  - أُضيفت تركيبة حية-هرمسية لمسار `/api/v1/fields/{id}/geometry/history`.

### 3) Chaos + Load Testing
- `scripts/e2e/chaos_load.py`
  - Load test متوازي بمكتبة Python القياسية فقط.
  - يقيس `p50`, `p95`, `error_rate`.
  - Chaos probes لطلبات malformed / impossible update.
  - يفشل عند تجاوز `P95_MS` أو `MAX_ERROR_RATE` أو ظهور 5xx/transport error في probes.

### 4) مداخل تشغيل
- `Makefile`
  - `make e2e-live-full`
  - `make chaos-load`
  - `make gis-timeline-e2e`
- `frontend/package.json`
  - `npm run e2e:gis-timeline`

## التشغيل المقترح

```bash
# بعد تشغيل المكدس الحي
docker compose -f docker-compose.v9.yml up -d

# E2E حي كامل
BASE_URL=http://localhost REQUIRE_LIVE_E2E=1 make e2e-live-full

# Chaos + Load
BASE_URL=http://localhost AUTH_TOKEN=<jwt> REQUESTS=500 CONCURRENCY=30 P95_MS=1500 MAX_ERROR_RATE=0.02 make chaos-load

# E2E واجهة GIS Timeline
cd frontend
npm install
npm run e2e:gis-timeline
```

## تحقق تم داخل هذه البيئة

- تم فحص syntax لسكريبتات Python الجديدة بنجاح.
- تم تشغيل السكريبتين بدون مكدس حي، وكانت النتيجة `SKIPPED (no live stack)` كما هو مصمم.
- لم أستطع تشغيل Playwright/Vitest فعلياً لأن البيئة الحالية لا تحتوي `node_modules`.
