# RUNBOOK — تشغيل منصّة سهول محليّاً/حيّاً

دليل تشغيل موجز للتحقّق الحيّ (E2E، الطقس، Edge، WebSocket، MFA). كلّ الكود مدموج في
`main`؛ هذا الملفّ يوثّق **كيف تُشغّله بنفسك** (لا يمكن تشغيله داخل بيئة CI المعزولة).

## أيّ compose؟

| الملفّ | الغرض | يشمل |
|--------|-------|------|
| **`docker-compose.v9.yml`** | **القانونيّ/الكامل (موصى به للتشغيل الفعليّ)** | مسار **Edge** الآمن (`/api/edge/`)، أدوار RLS الحقيقيّة (`sahool_app`)، قولبة nginx (envsubst)، كلّ الخدمات |
| `docker-compose.fixed.yml` | بداية تطوير سريعة مُختزَلة | **بلا** مسار Edge (بوّابة غير مُقولَبة)، **تجاوز RLS مُفعَّل** (dev فقط)، soil مُعطَّل، depends_on مُقلَّم |

> للتحقّق الحيّ الكامل (خصوصاً Edge pest-detect وعزل RLS) استخدم **`docker-compose.v9.yml`**.
> `fixed.yml` للتجربة السريعة فقط؛ تجاوز RLS فيه افتراضيّ (1) ولا يُستخدَم خارج المحلّيّ
> (حارس CI `tests_v9/test_compose_rls_bypass_guard.py` يمنع تسرّبه لأيّ compose إنتاجيّ).

## 1) الإعداد

```bash
cp .env.example .env
```
املأ المتغيّرات **الإلزاميّة** (وإلّا يرفض compose الإقلاع):
`JWT_SECRET · DATABASE_URL · DB_PASSWORD · REDIS_PASSWORD · MINIO_ROOT_PASSWORD ·
QDRANT_API_KEY · ADMIN_PASSWORD · GRAFANA_PASSWORD · SH_CLIENT_ID · SH_CLIENT_SECRET ·
TELEGRAM_BOT_TOKEN · TELEGRAM_WEBHOOK_SECRET · ODOO_PASSWORD · SAHOOL_AGENT_TOKEN`

- **`SAHOOL_AGENT_TOKEN`** مهمّ: تحقنه بوّابة v9 في رأس `X-Agent-Token` لمسار `/api/edge/`
  (Edge pest-detect)؛ بدونه يردّ Edge ‏401 بصدق.

## 2) أعلام الميزات المتقدّمة (FEATURE_* / VITE_ENABLE_*)

الراوترات المتقدّمة مُطفأة افتراضاً ⇒ الـbackend يردّ 404، والواجهة تعرض حالة **«ميزة
غير مُفعَّلة»** صادقة (لا شاشة مكسورة). لتفعيلها:

- **Backend (وقت التشغيل):** اضبط `FEATURE_*=1` في `.env` (مُمرَّرة الآن في `v9.yml`
  و`fixed.yml` بقيم `${...:-0}`). المصدر: `services/sahool-platform/api/feature_registry.py`.
- **Frontend (وقت البناء):** اضبط `VITE_ENABLE_*=true` **قبل** بناء صورة الواجهة (متغيّرات
  Vite تُحقَن وقت البناء لا التشغيل). الخريطة في `frontend/src/lib/featureFlags.ts`.

| الصفحة | Backend `FEATURE_*` | Frontend `VITE_ENABLE_*` |
|--------|----------------------|---------------------------|
| nl-gis | `FEATURE_NATURAL_LANGUAGE_GIS` | `VITE_ENABLE_NL_GIS` |
| decision-studio | `FEATURE_DECISION_STUDIO` | `VITE_ENABLE_DECISION_STUDIO` |
| decision-confidence | `FEATURE_DECISION_CONFIDENCE` | `VITE_ENABLE_DECISION_CONFIDENCE` |
| execution-feedback | `FEATURE_EXECUTION_FEEDBACK` | `VITE_ENABLE_EXECUTION_FEEDBACK` |
| lineage | `FEATURE_UNIFIED_LINEAGE` | `VITE_ENABLE_UNIFIED_LINEAGE` |
| learning-dashboard | `FEATURE_LEARNING_DASHBOARD` | `VITE_ENABLE_LEARNING_DASHBOARD` |
| evidence-map | `FEATURE_EVIDENCE_MAP` | `VITE_ENABLE_EVIDENCE_MAP` |
| replay-map | `FEATURE_REPLAY_MAP` | `VITE_ENABLE_REPLAY_MAP` |
| operations-wall | `FEATURE_OPERATIONS_WALL` | `VITE_ENABLE_OPERATIONS_WALL` |
| irrigation-network | `FEATURE_IRRIGATION_NETWORK` | `VITE_ENABLE_IRRIGATION_NETWORK` |
| portfolio-command | `FEATURE_PORTFOLIO_COMMAND` | `VITE_ENABLE_PORTFOLIO_COMMAND` |
| device-twin | `FEATURE_DEVICE_TWIN` | `VITE_ENABLE_DEVICE_TWIN` |

(`FEATURE_DELTA_SYNC` و`FEATURE_GIS_KERNEL` خلفيّان بلا صفحة مخصّصة.)

## 3) الإقلاع

```bash
docker compose -f docker-compose.v9.yml up -d --build      # أوّل مرّة بطيء (يبني ~15 صورة)
docker compose -f docker-compose.v9.yml ps                 # انتظر healthy
docker compose -f docker-compose.v9.yml logs -f sahool-platform sahool-auth sahool-nginx
```
nginx يستمع على `80/443`.

## 4) فحص الدخان الجاهز (register → login → field → workspace)

```bash
BASE_URL=http://localhost python scripts/smoke_e2e.py
```

## 5) الفحوص الحيّة المتبقّية

- **الطقس:** `GET /api/v1/weather/current?lat=..&lon=..` ⇒ بيانات Open-Meteo حقيقيّة.
- **الدردشة:** الواجهة تستدعي `/api/agent/query` (supervisor، JWT) ⇒ ردّ `response_ar`.
- **Edge pest-detect (v9):** `POST /api/edge/v1/inference/pest-detect` بـJWT صالح + صورة
  (البوّابة تحقن `X-Agent-Token`؛ يلزم ضبط `SAHOOL_AGENT_TOKEN`).
- **Agent health:** `GET /api/agent/health` ⇒ 200.
- **WebSocket:** اتّصل بـ`/ws/notifications` وأرسل أوّل إطار `{"type":"auth","token":"<JWT>"}`
  ⇒ قبول؛ توكن خاطئ ⇒ إغلاق 1008.
- **MFA:** `POST /auth/mfa/setup` → امسح QR في تطبيق TOTP → `POST /auth/mfa/activate`
  بالرمز، ثمّ سجّل دخولاً برمز MFA.
- **Push (FCM):** يتطلّب مشروع Firebase + `google-services.json`/APNs + جهاز حقيقيّ.

## ملاحظات تطوير

- **تجاوز RLS:** `SAHOOL_ALLOW_RLS_BYPASS_ROLE=1` افتراضيّ في `fixed.yml` فقط (لا يُنشئ
  `sahool_app`). **لا تستخدم `fixed.yml` في الإنتاج.** v9 يستعمل `sahool_app` ويُبقي
  الحارس مُفعَّلاً.
- **إقلاع أسرع للتطوير:** في `fixed.yml` بوّابة nginx لم تعد تنتظر صحّة الخدمات الثقيلة
  الاختياريّة (market/odoo/rag) — `service_started` بدل `service_healthy`.

## Production Validation Gate — final preflight

قبل أي نشر فعلي، شغّل البوابة الموحدة التالية من جذر المشروع:

```bash
./scripts/production_validation_gate.sh
```

هذه البوابة تمنع أهم انحدارات الإنتاج المعروفة في SAHOOL:

1. عدم وجود أسرار فعلية أو token مولّد داخل الملفات الملتزمة.
2. منع `DATABASE_URL` من استخدام `postgres` أو `sahool_user` في runtime.
3. تثبيت runtime app role على `sahool_app` فقط.
4. حصر `JOBS_DATABASE_URL` في مسارات الخلفية المعتمدة فقط.
5. منع `SAHOOL_ALLOW_RLS_BYPASS_ROLE` في compose.
6. فحص صياغة `docker-compose.v9.yml` قبل التشغيل.
7. فحص ترتيب `migrations/MANIFEST.txt` وعدم تكرار إصدارات الهجرات.
8. فحص compile لكل ملفات Python القابلة للفحص.

قاعدة التشغيل: إذا فشلت هذه البوابة، لا تبدأ `docker compose up` للإنتاج.

### التسلسل المقترح بعد نجاح البوابة

```bash
./scripts/production_validation_gate.sh
docker compose -f docker-compose.v9.yml config
docker compose -f docker-compose.v9.yml up -d
BASE_URL=http://localhost ./scripts/runtime_smoke.sh
SAHOOL_JWT=<jwt> TENANT_ID=<tenant> FIELD_ID=<field> BASE_URL=http://localhost ./scripts/e2e/e2e_field_imagery_ai.sh
./scripts/recovery/recovery_smoke.sh
```

## Phase 13 — Production Observability Dashboards

Before production, validate the monitoring assets:

```bash
python scripts/observability/validate_observability_assets.py
pytest -q tests/observability/test_phase13_observability_assets.py
```

Start monitoring services:

```bash
docker compose -f docker-compose.v9.yml up -d sahool-prometheus sahool-alertmanager sahool-grafana
```

Check readiness:

```bash
curl -fsS http://localhost:9090/-/ready
curl -fsS http://localhost:3001/api/health
```

Grafana should provision:

- `SAHOOL Production Overview`
- `SAHOOL Field Imagery AI Runtime`

Prometheus should load the `sahool-production-slos` group from `prometheus/alerts.yml`.

## Phase 14 release packaging gate

Before handing this bundle to deployment or operations, run:

```bash
python scripts/release/build_release_bundle.py
python scripts/release/validate_release_package.py
```

Expected generated assets:

```text
release/SAHOOL_RELEASE_MANIFEST_20260626.json
release/FILE_CHECKSUMS.sha256
release/SBOM_MINIMAL.json
release/DEPLOYMENT_READINESS_CHECKLIST.md
```

A release is blocked if checksum validation fails, if required runtime gates are missing, or if the release manifest reports missing required assets.



## Phase 15 — Kubernetes / Helm Deployment Gate

Before deploying to Kubernetes:

```bash
./scripts/production_validation_gate.sh
python scripts/observability/validate_observability_assets.py
python scripts/deploy/validate_helm_readiness.py --env production
python scripts/release/validate_release_package.py
```

Staging deployment:

```bash
./scripts/deploy/deploy_staging.sh
```

Production deployment:

```bash
./scripts/deploy/deploy_production.sh
```

Required production secrets must be created by External Secrets, Sealed Secrets, or the platform secret manager. Do not deploy placeholder secret manifests.

Post-deploy checks:

```bash
kubectl -n sahool get pods
kubectl -n sahool get ingress
kubectl -n sahool rollout status deploy/sahool-platform
kubectl -n sahool rollout status deploy/sahool-raster-service
kubectl -n sahool rollout status deploy/sahool-ai-agronomist
```

## CI/CD Quality Gates

Before opening a release PR or deploying to staging/production, run:

```bash
./scripts/ci/local_quality_gate.sh
```

The GitHub workflow `.github/workflows/sahool-production-gates.yml` mirrors the local gate and must pass before merge. The workflow intentionally uses read-only repository permissions and does not allow soft-failing quality gates.

## Phase 17 Runtime Bootstrap Doctor

Before starting services, run the environment doctor. It checks required assets, environment variables, runtime DB roles, migration registration, compose static safety, Docker availability, and local port conflicts.

```bash
python scripts/runtime/env_doctor.py --mode preflight --format text
```

After Docker Compose or Kubernetes ingress is available, run runtime checks:

```bash
BASE_URL=http://localhost python scripts/runtime/env_doctor.py --mode runtime --format text
```

For a JSON report suitable for CI artifacts or handoff packages:

```bash
MODE=full BASE_URL=http://localhost ./scripts/runtime/runtime_doctor.sh
```

Readiness meanings:

- `ready`: no blocking failures or warnings.
- `attention`: no blocking failures, but operator review is required.
- `blocked`: do not deploy until failed checks are resolved.


## Phase 18 urgent runtime fixes

- Fixed GitHub Actions shell syntax and added workflow shell `bash -n` validation.
- Made chaos E2E/outbox checks blocking instead of `|| true`.
- Added production fail-closed persistence for Phase 9-12 when `db_pool` or `X-Tenant-Id` is missing.
- Added Phase runtime workers for outbox, plugins, model rollback, and actuator dispatch.
- Added `v113_phase_runtime_workers_jobs.sql` for RLS-safe `sahool_jobs` worker policies.
- Rebuilt `migrations/MANIFEST.md` to mirror `migrations/MANIFEST.txt`.

## Phase 19 operational notes

Before applying database changes, use the manifest validator:

```bash
python scripts/migrations/validate_migration_manifest.py --root .
```

Use the compatibility migration entry points only after this check passes; both are now generated or driven from `migrations/MANIFEST.txt`:

```bash
python scripts_v9/migrate.py status
python scripts_v9/migrate.py up --dry-run
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts_v9/run_migrations.sql
```

Operational shell scripts may be executed directly when executable bits are preserved, but CI and runbooks should prefer `bash path/to/script.sh` for ZIP/platform compatibility.


## Phase 20 Runtime Worker Side-Effect Configuration

Before enabling real side effects, configure the following explicitly:

```bash
# Plugin execution
PLUGIN_EXECUTION_ENABLED=true
PLUGIN_EXECUTOR_URL=http://plugin-runner:8080

# Model serving
MODEL_SERVING_ENABLED=true
MODEL_SERVING_ROLLBACK_ENABLED=true
MODEL_SERVING_BACKEND_URL=http://model-serving:8080

# Physical adapters: example only; keep disabled until hardware verification is complete.
PHYSICAL_ACTUATION_ENABLED=true
ACTUATOR_ADAPTER_CONFIG_JSON='{"modbus_tcp":{"enabled":true,"mode":"real","endpoint":"tcp://10.0.0.10:502"}}'
```

Expected worker states:

- Plugin execution without `PLUGIN_EXECUTOR_URL`: `blocked`.
- Model promotion without artifact metadata or serving backend: `blocked` / alias remains non-final.
- Actuator dispatch without real adapter config: `adapter_required`.
- Actuator dispatch with real adapter config: `waiting_ack`, not `physical_effect=true` until telemetry/ACK verification is implemented.

## Phase 21 certification readiness

Run static certification readiness gates:

```bash
python3 scripts/architecture/legacy_path_audit.py --root . --strict
python3 scripts/architecture/source_of_truth_audit.py --root . --strict
python3 scripts/certification/validate_certification_matrix.py --root .
```

Prepare a 7-day or 14-day soak:

```bash
TENANTS=1000 FIELDS=100000 DAYS=7 bash scripts/soak/run_soak_test.sh
# After live workload aggregation:
python3 scripts/soak/soak_assertions.py --metrics-json soak-results/metrics.json
python3 scripts/soak/soak_report.py --scenario-json soak-results/scenario.json --metrics-json soak-results/metrics.json
```

Do not mark Sahool as `Production Certified` until the certification matrix has been updated with runtime, staging, and soak evidence.

## Phase 22 RLS Write-Path Gate

Before production deployment, run:

```bash
python scripts/security/validate_rls_write_policies.py --root .
bash scripts/production_validation_gate.sh
```

The migration `v122_rls_with_check_session_unification.sql` must be applied after all legacy migrations. It backfills `WITH CHECK` on tenant write policies and normalizes `app.current_tenant` / `app.tenant_id`.
