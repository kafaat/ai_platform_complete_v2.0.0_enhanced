# Railway live map — project `sahool-staging` (33c50993…), measured 2026-09-30 ~15:15 UTC

Scope: read-only. Tools used: describe-environment, describe-service, get-service-config, environment-status, list-deployments, get-deployment-diagnosis, get-logs (deploy/build/http), http-requests/error-rate/response-time, get-service-metrics, get-tracing-coverage, list-webhooks, list-feature-flags, get-staged-changes, list-tcp-proxies, domain-status. Not called: list-variables or any mutating tool. Repo reference: `origin/main` = `166bdebf` (#1112). The local `main` checkout is behind at `fb926af1`.

## 0. Headline findings

1. **Production auto-deploys from `main` at the same time as staging, and nothing gates it.** The same commit reaches both environments within a second: frontend `166bdebf`, staging `57b47082` / prod `3d04e090`, both at 14:38:45Z. Every repo-sourced service has `checkSuites:false`, so Railway doesn't wait for GitHub CI before it deploys. (Source: describe-service `config.source.checkSuites`; list-deployments.)
2. **`sahool-platform` doesn't deploy from `main` in either environment.**
   - Staging deploys from `deploy/sahool-platform-db-ready-eb6da9df` (`eb6da9df`, 2026-09-27). It is 4 commits behind `main` in its watch paths, and one of those is `7eccd76c` (#1097), which bumps PyJWT to 2.14.0 for **CVE-2026-102274** in `services/sahool-platform/api/requirements.txt`. **Staging platform runs the pre-fix PyJWT.**
   - Prod deploys from `deploy/sahool-staging-fa92a1f7` (`fa92a1f7`, 2026-09-15). It is 24 commits behind in its watch paths.
   - Prod's legacy `sahool-auth` uses the same branch and is 13 commits behind.
3. **`sahool-decision-service` was rolled back by a burst of redeploys.** Six redeploys of `sahool-decision-service` were created within about 14 s on 2026-09-28 at 12:40Z, carrying #1086 `63727907`, #1085 `7059d0dc` and `eff473aa`. The last one created, `c1acd33b` (`eff473aa`), is the one that is live on staging. Staging decision therefore **lacks #1085 and #1086** (tenant-boundary RLS policy composition, migration 034). Prod decision is live on `7059d0dc`, so it lacks #1086. Both commits were merged on 09-27, during a window when containers in both environments were stopped: every service logged "Stopping Container" at 2026-09-27 02:06Z and nothing restarted until the 09-28 12:40Z mass redeploy.
4. **Staging `sahool-notification-agent`: latest deploy FAILED.** Deploy `34324a40` (`32da2953`, #1102) failed at stage `HEALTHCHECK`. The logs repeat `Subscription unavailable: notif_* (Error)` every 5 s and `/readyz` returns 503. The old deploy `43af9d13` (`2a8903ab`) is still serving. This matches the known gap `NOTIFICATION-AGENT-LEGACY-PUSH-CONSUMERS-BLOCK-ZERO-DOWNTIME-REDEPLOY-01` (`sahool-brain/gaps/registry.md:16`). The same commit deployed fine in prod (`b7b739ed`, `/readyz` 200).
5. **Prod `sahool-migrate-main`: latest deploy FAILED and the service is offline.** Deploy `600fa8bb` was a redeploy on 09-28. Its build log ends with `railpack prepare exited with an error`, which means it used the Railpack builder even though the service config says DOCKERFILE. get-deployment-diagnosis **errored on this deployment** (tool output schema mismatch). The last 50 prod records hold no SUCCESS for this service (1 FAILED, 21 REMOVED, 28 SKIPPED), so prod migration state can't be established from Railway alone. Prod `sahool-postgres` disk use is 0.18 GB; staging's is 1.03 GB.
6. **Prod frontend nginx logs resolver errors every ~11 s** for four hosts that don't exist in prod: `sahool-ai-agronomist`, `sahool-supervisor-agent`, `sahool-rag-retrieval` and `sahool-remote-sensing-workspace-bff` `.railway.internal`. Staging fixed the same noise by setting `SAHOOL_*_UPSTREAM=absent` (`certification/evidence/frontend_absent_upstreams_railway_staging_20260929.json`). Prod lacks the `SAHOOL_RAG_RETRIEVAL_UPSTREAM`, `SAHOOL_SUPERVISOR_AGENT_UPSTREAM` and `SAHOOL_REMOTE_SENSING_WORKSPACE_BFF_UPSTREAM` variable names.
7. **Leftover and duplicate services are still running**, including one in prod. See §2.
8. **Observability is minimal.**
   - Tracing is disabled on every service (`tracing.tracingEnabled:false`), and platform coverage shows 0 spans in 24 h.
   - There are **no webhooks**, so no one is alerted when a deploy fails, and **no feature flags**.
   - Uvicorn and nginx write INFO lines to stderr, which Railway tags `severity:error`, so counting by severity is meaningless for this fleet.
9. **Public HTTP probing wasn't possible from this sandbox.** GET requests to `sahool-frontend-{staging,production}.up.railway.app` `/healthz`, `/readyz` and `/runtime-identity` were all refused by the egress proxy (`CONNECT tunnel failed, response 403`, a policy denial). They were not retried and no status is claimed.

## 1. Inventory — staging (env 70cc51f8…, 22 services, region asia-southeast1 unless noted)

| Service | Source | Builder / Dockerfile | Watch paths | Healthcheck | Restart | Vol | Domain | Live deploy (status, time, SHA) | Flags |
|---|---|---|---|---|---|---|---|---|---|
| sahool-platform | repo `deploy/sahool-platform-db-ready-eb6da9df` | DOCKERFILE `services/sahool-platform/Dockerfile` | `/services/sahool-platform/**`, `/shared/**` | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-28 12:40 `eb6da9df` (redeploy) | **non-main**; −4 commits incl. PyJWT CVE |
| sahool-auth-main | main | DOCKERFILE `services/auth/Dockerfile` | `/services/auth/**`, `/shared/**` | `/healthz` 300 s | max 3 | – | – | SUCCESS 09-30 00:24 `2fbca389` | healthz only |
| sahool-frontend | main | DOCKERFILE `deploy/railway/Dockerfile.frontend` | `/frontend/**`, Dockerfile.frontend, render_frontend.py | `/healthz` 300 s | max 3 | – | `sahool-frontend-staging.up.railway.app` → 8080 | SUCCESS 09-30 14:38 `166bdebf` (=main) | – |
| sahool-raster-service | main | DOCKERFILE `services/raster-service/Dockerfile`; start `uvicorn … --port 8001` | raster-service, shared | `/readyz` 300 s | max 3 | `/data/rasters` 50 GB | – | SUCCESS 09-30 05:17 `6565e39d` | – |
| sahool-raster-main-candidate | main (no rootDirectory) | same Dockerfile | same | `/readyz` 300 s | max 3 | **none** | – | SUCCESS 09-30 05:17 `6565e39d` | **duplicate / leftover candidate** |
| sahool-notification-agent | main | DOCKERFILE `agents/notification/Dockerfile` | agents/notification, base_agent.py, shared | `/readyz` 300 s | max 3 | – | – | active `43af9d13` SUCCESS 09-28 21:20 `2a8903ab`; **latest `34324a40` FAILED 09-30 01:53 `32da2953`** | failed deploy; stale |
| sahool-migrate-main | main | DOCKERFILE `deploy/railway/Dockerfile.migrate` | `/migrations/**`, Dockerfile.migrate | none (job) | NEVER, sleepApplication | – | – | SUCCESS 09-28 22:04 `2a8903ab` (log: "طُبّقت 231 هجرة", roles sahool_app / sahool_jobs / sahool_ingest* / odoo_app) | 0 migration commits since |
| sahool-migrate | **no source** | DOCKERFILE Dockerfile.migrate | – | none | NEVER | – | – | **no deployment ever** | **leftover**; region **europe-west4** |
| sahool-decision-service | main (no rootDirectory) | DOCKERFILE decision-service | decision-service, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-28 12:40 `eff473aa` | **rolled back**; −2 (#1085, #1086) |
| sahool-guardrails-engine | main | DOCKERFILE guardrails-engine | guardrails-engine, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-28 21:10 `2a8903ab` | **leftover staging-only preDeployCommand** (internal HTTP sweep + RS256 check, exits 1 if missing) |
| sahool-field-management-service | main | DOCKERFILE field-management-service | field-mgmt, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-28 12:40 `eff473aa` | 0 behind |
| sahool-vegetation-analysis | main | DOCKERFILE vegetation-analysis-service | veg, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-30 05:17 `6565e39d` | – |
| sahool-tts-service | main | DOCKERFILE tts-service | tts, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-30 00:24 `2fbca389` | – |
| sahool-soil-service | source `{branch:main}`, **no repo field** | DOCKERFILE soil-service | soil, shared | `/readyz` 300 s | max 3 | – | – | SUCCESS 09-29 13:51 `ede0d4e1` | repo link missing in config (deploys still carry branch=main) |
| sahool-ai-agronomist | source `{branch:main}`, **no repo field** | DOCKERFILE ai_agronomist | ai_agronomist, shared | `/healthz` 300 s | max 3 | – | – | SUCCESS 09-30 00:24 `2fbca389` | readyz 503 by design (rag/KG absent; RW-D05) |
| sahool-postgres | image `postgis/postgis:15-3.4` | – | – | none | default | `/var/lib/postgresql/data` 50 GB (1.03 GB used) | – | SUCCESS 09-28 12:40 | tag, no digest; PG 15.8 gap |
| sahool-redis | image `redis:7-alpine` | – | – | none | max 3 | none | – | SUCCESS 09-28 12:40 | tag; allkeys-lru 256 MB |
| sahool-redis-state | image `redis:7-alpine` | – | – | none | default | `/data` 50 GB | – | SUCCESS 09-28 12:40 | tag; noeviction 256 MB AOF |
| sahool-redis-state-0zaK | image `redis:7-alpine` | – | – | none | NEVER, sleepApplication | `/data` 50 GB | – | **SLEEPING** 09-28 12:40 | **duplicate redis-state** |
| sahool-nats | image `nats:2-alpine`, start `nats-server -js -sd /data/jetstream` | – | – | none | max 3 | `/data` 50 GB | – | SUCCESS 09-28 12:40 | tag; **0 variables → no auth** (known gap) |
| wc005-postgres-live-proof | image `postgres:16-alpine` | – | – | none | NEVER, sleep | none | – | SUCCESS 09-28 12:40 | **leftover proof** (from 09-23) |
| platform-db-proof-20260927 | image `python@sha256:a36c24f9…` (digest-pinned) | start: one-shot "decision033034_preflight_cleanup" | – | none | NEVER | – | – | SUCCESS 09-28 12:40 | **leftover proof** |

Shared variable names (both environments): `ADMIN_PASSWORD`, `AI_GENERATION_ENABLED`, `APP_DB_PASSWORD`, `DB_PASSWORD`, `DB_POOL_MAX`, `DB_POOL_MIN`, `DECISION_SERVICE_TOKEN`, `EDGE_PRODUCTION_REQUIRED`, `EDGE_READINESS_MODE`, `FEATURE_DEVICE_TWIN`, `FEATURE_IRRIGATION_NETWORK`, `FEATURE_NATS_PUBLISHERS`, `FEATURE_PORTFOLIO_COMMAND`, `FIELD_SERVICE_TENANT_ASSERTION_KEY`, `INGEST_DB_PASSWORD`, `JOBS_DB_PASSWORD`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_SECRET`, `MFA_AUDIT_HASH_KEY`, `MFA_SECRET_ENCRYPTION_KEY`, `RAILWAY_DOCKERFILE_PATH`, `REDIS_PASSWORD`, `SAHOOL_AGENT_TOKEN`, `SAHOOL_BUILD_ID`, `SAHOOL_ENV`, `SAHOOL_GIT_SHA`, `SAHOOL_SOURCE_REF`, `SAHOOL_SOURCE_REPOSITORY`, `STATE_REDIS_PASSWORD`.

Per-service variable names (key ones):
- **platform:** `DATABASE_URL`, `JOBS_DATABASE_URL`, `REDIS_URL`, `JWT_PUBLIC_KEY`, `JWT_SECRET`, `SAHOOL_JWT_SECRET`, `SAHOOL_DEV_AUTH`, `SAHOOL_DEBUG`, `*_SERVICE_URL`/`*_URL` (AI_AGRONOMIST, DECISION_SERVICE, KNOWLEDGE_GRAPH, RAG_RETRIEVAL, RASTER_SERVICE, SCOUT_INGEST, SEGMENTATION, SOIL_SERVICE, TITILER, WEATHER_SERVICE), plus the `FEATURE_*` and `SAHOOL_*` identity names.
- **auth-main:** `ADMIN_PASSWORD`, `AUTH_COOKIE_SAMESITE`, `AUTH_COOKIE_SECURE`, `CORS_ORIGINS`, `DATABASE_URL`, `ENFORCE_SENSITIVE_MFA`, `FRONTEND_URL`, `JWT_*`, `MFA_*`, `REDIS_URL`, `REFRESH_EXPIRE_DAYS`, `REQUIRE_MFA_ROLES`, `SAHOOL_*`.
- **frontend:** `SAHOOL_{AUTH,PLATFORM,RAG_RETRIEVAL,RASTER_SERVICE,REMOTE_SENSING_WORKSPACE_BFF,SUPERVISOR_AGENT,VEGETATION_ANALYSIS}_UPSTREAM`, `SAHOOL_RELEASE_CANDIDATE_SHA`, `VITE_*`.
- **notification:** `DATABASE_URL`, `FEATURE_MOBILE_PUSH`, `JWT_PUBLIC_KEY`, `NATS_URL`, `NOTIFICATION_CONSUMER_MODE`, `REDIS_URL`, `SAHOOL_AGENT_TOKEN`, `TTS_URL`.
- **migrate-main:** `PG*`, `APP_DB_*`, `JOBS_DB_*`, `INGEST_DB_PASSWORD`, `ODOO_DB_PASSWORD`, `MIG_DIR`, `SAHOOL_AUTH_DATABASE_URL`, `SAHOOL_AUTH_PROBE_BASE`.
- **decision:** `DATABASE_URL`, `DECISION_REQUIRE_AUTH_TOKEN`, `DECISION_SERVICE_AUTH_TOKEN`, `DECISION_SERVICE_SOR_ENABLED`, `DECISION_SOR_PLATFORM_URL`, `DECISION_STAGING_DIAGNOSTIC_RUN`, `DECISION_STAGING_MIGRATION_URL`, `SAHOOL_*`.
- **raster:** `DATABASE_URL`, `HISTORICAL_SEARCH_PROVIDER`, `RASTER_PERSISTENCE_MODE`, `RASTER_UPLOAD_DIR`, `RAILWAY_RUN_UID`, `HOME`, `JWT_PUBLIC_KEY`, `SAHOOL_*`. The raster-main-candidate has only a subset: no `SAHOOL_AGENT_TOKEN` and no identity vars.

## 1b. Inventory — production (env 79de27a7…, 20 services)

Config matches staging unless noted.

| Service | Source | Healthcheck | Live deploy | Difference vs staging |
|---|---|---|---|---|
| sahool-platform | `deploy/sahool-staging-fa92a1f7` | **`/healthz`** (staging uses `/readyz`) | SUCCESS 09-28 12:40 `fa92a1f7` | **non-main**, −24 commits; weaker healthcheck |
| **sahool-auth** (legacy, prod only) | `deploy/sahool-staging-fa92a1f7` | `/healthz` | SUCCESS 09-28 12:40 `fa92a1f7` | **non-main**, −13; duplicates sahool-auth-main |
| sahool-auth-main | main | `/healthz` | SUCCESS 09-30 00:24 `2fbca389` | – |
| sahool-frontend | main | `/healthz` | SUCCESS 09-30 14:38 `166bdebf` | domain `sahool-frontend-production.up.railway.app`; lacks the RAG, SUPERVISOR and BFF upstream variables and `SAHOOL_RELEASE_CANDIDATE_SHA` → resolver-error noise |
| sahool-notification-agent | main | `/readyz` | SUCCESS 09-30 01:53 `32da2953` | healthy at the commit that failed in staging |
| sahool-migrate-main | main | – | **FAILED** 09-28 12:40 (railpack prepare) | **offline** (environment-status warning); no sleepApplication |
| sahool-decision-service | main | `/readyz` | SUCCESS 09-28 12:40 `7059d0dc` | −1 (#1086); variable names lack `DECISION_REQUIRE_AUTH_TOKEN`, `DECISION_SERVICE_AUTH_TOKEN`, `DECISION_SOR_PLATFORM_URL` |
| sahool-raster-service | main, startCommand `""` | `/readyz` | SUCCESS 09-30 05:17 `6565e39d` | – |
| sahool-raster-main-candidate | main, start `uvicorn … 8001` | `/readyz` | SUCCESS 09-30 05:17 `6565e39d` | leftover duplicate |
| guardrails, field, vegetation, tts | main | `/readyz` | `2a8903ab` / `eff473aa` / `6565e39d` / `2fbca389` | guardrails has **no** preDeployCommand in prod |
| sahool-postgres | `postgis/postgis:15-3.4` | – | SUCCESS | volume **1 GB** (0.18 GB used) |
| sahool-redis, -redis-state, -redis-state-0zaK, -nats | tags | – | SUCCESS (0zaK running, not sleeping; restart default) | volumes 1 GB / 5 GB |
| wc005-postgres-live-proof | `postgres:16-alpine` | – | SUCCESS, **running continuously** (no sleep, default restart, ~40 MB RAM) | leftover |
| sahool-migrate | no source, europe-west4 | – | never deployed | leftover |
| *absent in prod* | – | – | – | soil-service, ai-agronomist, platform-db-proof |

Not found in either environment: TCP proxies (checked on postgres ×2 and wc005 prod; describe-service showed `tcpProxies:[]` for every staging service), staged changes (`staged:null`) and custom domains. The only public domains are the two frontend `*.up.railway.app` domains; domain-status for both returned `railwayManaged:true`, `certificate:null`, `dnsRecords:[]`.

## 2. Flags summary

- **Non-main branch:** staging platform (`deploy/sahool-platform-db-ready-eb6da9df`), prod platform and prod sahool-auth (`deploy/sahool-staging-fa92a1f7`).
- **No healthcheck:** all image services (postgres, redis ×3, nats, wc005, platform-db-proof) and the migrate jobs; the jobs are expected not to have one. Weak `/healthz`-only checks: auth-main, auth (prod), ai-agronomist, frontend, and prod platform.
- **Stale or behind main (watch-path commits missing):**
  - platform: staging −4, prod −24
  - prod legacy auth: −13
  - decision: staging −2, prod −1
  - notification staging: −1 (deploy failed)
  - All others: 0.
- **Failed or offline:** staging notification `34324a40` FAILED (HEALTHCHECK); prod migrate-main `600fa8bb` FAILED (build) and offline.
- **Recent failures (history):**
  - staging guardrails `8a3aece7` and `707620fd` (09-28 19:28–19:40, #1089)
  - staging auth-main `e88ff6ab` and `0538fc7e` (same window)
  - a series of 09-23…09-26 failures on raster, raster-candidate, decision, vegetation, tts and notification
  - Each failure was followed by a later SUCCESS. **No CRASHED deployments** project-wide.
- **Duplicates / leftovers:**
  - `sahool-raster-main-candidate`
  - `sahool-redis-state-0zaK` (vs `sahool-redis-state`)
  - `wc005-postgres-live-proof` (both environments, running in prod)
  - `platform-db-proof-20260927`
  - `sahool-migrate` (never deployed, EU region)
  - prod `sahool-auth` (vs `sahool-auth-main`)
  - staging guardrails `preDeployCommand` sweep
  - Which of the two redis-state services consumers actually reference can't be told without variable values.
- **Images pinned by tag without a digest:** `postgis/postgis:15-3.4`, `postgres:16-alpine`, `redis:7-alpine` ×3, `nats:2-alpine`. Only `python@sha256:…` is pinned.
- **Config drift staging↔prod:** platform branch and healthcheck path; decision auth variable names; frontend upstream variables; volume sizes (staging 50 GB ×5 vs prod 1–5 GB); raster startCommand; redis-state-0zaK restart/sleep; wc005 sleep.

## 3. Live health (tool evidence)

- **environment-status, 48 h:**
  - Staging: 22 services, 3 with issues. notification has 1 warning and its latest failed; guardrails and auth-main show 2 historical failures each. `pendingWork:[]`.
  - Prod: 20 services, 1 with issues (migrate-main offline, 1 warning).
- **HTTP (Railway edge; only the frontend has a domain):**
  - Staging frontend, 24 h: **0 requests**. 7 d: 12 requests (9 2xx, 3 4xx, 0 5xx), p50 8–26 ms, p99 ≤ 71 ms.
  - Prod frontend, 7 d: 20 requests (14 2xx, 4 4xx, **2 5xx**). Both 5xx were **502** at 2026-09-27 12:28–12:31Z, on `GET /api/v1/features` and `POST /auth/register`. Both fall inside the 09-27 02:06Z → 09-28 12:40Z window when the upstream containers were stopped (prod platform and auth logs show "Stopping Container" at 02:06:0x and restart at 12:47–12:48 on 09-28).
  - Platform staging, 24 h: 0 edge requests. It has no domain, so private traffic isn't counted here.
- **Logs by service:**
  - **platform (staging):** only probe traffic; 09-29 18:53Z `/healthz`, `/readyz` and `/runtime-identity` all 200. No application errors in the window read.
  - **raster (staging):** clean restart at 05:19Z; pydantic `schema` shadowing UserWarnings (×4, cosmetic); "layer-evict subscriber disabled (no REDIS_URL)"; Earth Search 200.
  - **auth-main (staging):** clean start; Redis connected; admin ensured.
  - **frontend:** staging is clean (nginx worker notices only). Prod logs resolver errors for 4 absent hosts every ~11 s, ongoing at 15:14Z.
  - **notification:** see §0.4. The live staging instance answers `/readyz` 200, and `/runtime-identity` 404 because the route isn't defined.
  - **migrate-main:** staging ran successfully on 09-28 22:04 (v206 RLS hardening NOTICEs, "128 policies tightened", role grants). Prod: see §0.5.
- **Metrics, 24 h:**
  - Staging postgres: CPU ≈ 0.001 vCPU, RAM 57 MB, disk 1.03 GB of 50 GB.
  - Prod postgres: RAM 34 MB, disk 0.18 GB of 1 GB.
  - Staging platform: RAM 150 MB, CPU ≈ 0.
  - Prod wc005: RAM 40 MB, running.
- **Deployment diagnosis:**
  - notification `34324a40`: `failureStage:HEALTHCHECK`, `failureError:"Healthcheck failure"`, `diagnosis:null`. The context reports builder `RAILPACK` although the config says DOCKERFILE; this is reported as returned.
  - prod migrate-main `600fa8bb`: **tool error** ("Structured content does not match the tool's output schema"). The build logs were read instead.

## 4. Tracing, webhooks, flags

- Tracing is off everywhere (`tracingEnabled:false`, `autoInstrumentationEnabled:false`). Coverage on staging platform, 09-29 15:00 → now: `spanCount:0`.
- Webhooks: `[]`.
- Feature flags (project and workspace): `[]`.
- Staged changes: none in either environment.

## 5. Repo verification assets vs live Railway

| Asset | What it checks | Targets live Railway today? |
|---|---|---|
| `certification/evidence/rw_d05_readiness_railway_staging_20260929.json` | 13-service `/healthz`, `/readyz` and `/runtime-identity` sweep over the private network, run from a **temporary preDeployCommand** | **Yes, one-off** (2026-09-29 18:53Z, staging). A fixed record, not a runnable script. |
| `certification/evidence/frontend_absent_upstreams_railway_staging_20260929.json`, `soilgrids_live_railway_staging_20260929.json`, `wc005_live_two_worker_proof.json` | Resolver noise before/after; SoilGrids classification; WC-005 two-worker proof | Yes, one-off staging measurements |
| `deploy/railway/probe_platform_db.py` (+ `tests/deploy/test_railway_platform_db_probe.py`) | Read-only DB identity: session/current user, rolsuper, rolbypassrls, fresh connection; never prints a DSN | Designed for **`railway ssh`** into platform; manual, needs owner CLI credentials |
| `deploy/railway/render_frontend.py`, `Dockerfile.frontend`, `Dockerfile.migrate` (+ `tests/deploy/test_railway_frontend_config.py`, `test_railway_migration_runner.py`) | Build-time nginx rendering (`SAHOOL_*_UPSTREAM`, `absent`); migration runner | Used by Railway builds; the tests are static (CI) |
| `services/auth/railway.json` | Config-as-code (DOCKERFILE path) for auth | Only the auth service has one |
| guardrails `preDeployCommand` (staging config, not in repo) | Internal sweep of frontend, tts, platform, decision, raster and vegetation, plus an RS256 backend check | **Runs on every staging guardrails deploy.** Output lines are prefixed `SAHOOL_DEPLOY_REVIEW`. |
| `scripts/runtime_smoke.sh`, `scripts/observability_smoke.sh`, `scripts/runtime/runtime_doctor.sh` + `env_doctor.py` | GET `/healthz` behind nginx paths (`/api/<svc>/healthz`); observability endpoints; env doctor | `BASE_URL` defaults to `http://localhost` (compose). They could point at the Railway frontend, but the frontend gateway doesn't expose `/api/<svc>/healthz` for every service (`/auth/healthz` returned 404 in staging http logs). |
| `scripts/smoke_e2e.py` | register → login → me → create field → workspace | Compose by default; **mutating** (creates a user and a field) |
| `scripts/weather_runtime_smoke.py` | Weather engine | Compose; weather-service isn't deployed on Railway |
| `.github/workflows/runtime-real-smoke.yml` | `scripts/ci/runtime_real_smoke.sh` on ubuntu-latest | CI only |
| `path3-runtime-verification.yml` | compose `docker-compose.v9.yml` + attested images on a self-hosted `sahool-path3-trusted` runner | Compose only (`trusted_environments.json`: `staging-pg16`); **not Railway** |
| `runtime-image-provenance.yml` | Builds and pushes `ghcr.io/…:<sha>` with SLSA/CycloneDX | Not consumed by Railway, which builds from the repo |
| `runtime-verification-promotion.yml`, `certify-run.yml`, `wx12-runtime-certification.yml`, `notification-rollout.yml`, `production-evidence-pack.yml` | Evidence promotion and certification over CI and compose (localhost PG/NATS) | No |
| `runtime-verification/functional_probes/*.json`, `service_identity_map.json` | Probe definitions per service | Data only; not bound to Railway |
| `scripts/deploy/deploy_{staging,production}.sh` | Helm upgrade to k8s | **Not Railway** (the helm path is unused by this project) |
| `docs/runbooks/RAILWAY_{DEPENDENCY_RECOVERY,AUTH_DEPLOYMENT,FRONTEND_DEPLOYMENT}.md`, `docs/evidence/railway_audit_review_20260920.md` | Manual acceptance procedures | Manual |

**No GitHub workflow references Railway** (`grep -il railway .github/workflows/*` returns nothing). Live verification is entirely manual or agent-driven today.

## 6. Live verification plan

### A. Read-only checks an agent can run at any time with the Railway MCP tools

| # | Procedure | Expected signal | Currently |
|---|---|---|---|
| A1 | `environment-status` for both environments, `hoursBack:24`, `includeSuccessful:true` | `servicesWithIssues:0`, `pendingWork:[]`, every replica `running==total` | staging 3, prod 1 |
| A2 | **SHA drift.** Run `list-deployments` with `status:SUCCESS` and `limit:50` per environment (the output spills to a file; parse it with python). Take the newest SUCCESS per service and compare it locally with `git log <sha>..origin/main -- <watchPatterns>` | 0 commits for every main-sourced service; platform flagged until it moves to main | platform −4/−24, prod auth −13, decision −2/−1, notification (staging) −1 |
| A3 | **Config drift.** `describe-service` for each service in both environments; diff source.branch, checkSuites, healthcheckPath, restartPolicy, preDeployCommand and the variable-NAME sets | Differences exist only where intended | see §2 drift list |
| A4 | **Failure triage.** `list-deployments` with `status:FAILED` and again with `CRASHED` since the last check; then `get-deployment-diagnosis` on each and fall back to `get-logs types:[build,deploy]` if it errors | Empty, or each failure superseded by a later SUCCESS | 2 open failures |
| A5 | **Log signatures.** `get-logs` per service with `filter` strings: `could not be resolved` (frontend), `Subscription unavailable` (notification), `" 503 "` (readyz), `Traceback`, `password authentication failed`, `railpack prepare exited`. Ignore `severity`, because uvicorn and nginx INFO lines appear as error. | 0 hits | prod frontend resolver errors ongoing |
| A6 | **Edge HTTP.** `http-requests`, `http-error-rate` and `http-response-time` on sahool-frontend in both environments, `hoursBack:168`, then `get-logs types:[http]` filtered with `@status:502` | 5xx = 0; p99 < 1 s | prod 2×502 on 09-27 (outage window) |
| A7 | **Capacity.** `get-service-metrics` with DISK_USAGE_GB on postgres and nats (vs volume size), and MEMORY_USAGE_GB on redis-state. redis-state is noeviction with a 256 MB cap, so writes fail once it is full. | disk < 70 % of volume; redis-state RAM < 0.2 GB | OK |
| A8 | **Exposure.** `list-tcp-proxies` on postgres, redis ×3 and nats; `list-domains` on every service | TCP proxies `[]`; the only domains are the two frontend ones | OK |
| A9 | `get-staged-changes` in both environments; `list-webhooks`; `list-feature-flags`; `get-tracing-coverage` on platform | `staged:null`. Webhooks and tracing are empty until B10 and B11 are done. | – |
| A10 | **Private identity evidence without mutating anything.** Read the latest guardrails staging deploy logs with filter `SAHOOL_DEPLOY_REVIEW`; the existing preDeployCommand emits HTTP status plus `service`, `git_sha` and `build_id` for 6 services on every guardrails deploy. Compare each `git_sha` with A2. | identity sha = Railway deployment commitHash | available only when guardrails redeploys |
| A11 | **Public GET probe.** `/healthz`, `/readyz` and `/runtime-identity` on the two `*.up.railway.app` frontend domains. This must run from a host whose egress allows it; **this sandbox's proxy returns 403.** | 200/200/200; `runtime-identity.git_sha` = the platform deployed SHA (per RW-D05 the frontend proxies it) | not measured |

### B. Needs owner approval (touches deployments, variables, DB, or needs credentials)

| # | Change | Exact procedure | Expected signal | Rollback |
|---|---|---|---|---|
| B1 | Move staging platform to main (gets the PyJWT CVE fix and 3 other commits) | `connect-service-source` or update-service: branch `main` on staging sahool-platform only; let it deploy; run A1, A2 and A10 | Deploy SUCCESS; `/readyz` 200; runtime-identity sha = main | `redeploy`/rollback to deployment `193dc233` (canRollback) and restore the branch `deploy/sahool-platform-db-ready-eb6da9df` |
| B2 | Then prod platform and legacy prod auth to main (or retire prod `sahool-auth` in favour of auth-main after confirming the frontend's `SAHOOL_AUTH_UPSTREAM` target) | Same as B1 on prod; switch the platform healthcheck to `/readyz` to match staging | SUCCESS; no 502 on the frontend edge | rollback to `b3873034` / `df8bb825` |
| B3 | Re-deploy decision-service at main (#1085, #1086), after the owner confirms migration 033/034 state. The commit text says "does not authorize live migration application" and the gap keeps a staging closure gate. | Run the SQL checks from B6 first; then redeploy the latest main snapshot. **Do not run a batch of redeploys:** the 09-28 12:40 race proves the last one created wins. | runtime-identity (authenticated, 401 without a token) shows `63727907`; `/readyz` 200 | rollback to `c1acd33b` (staging) / `cd1282d5` (prod) |
| B4 | Fix notification rolling deploys (gap NOTIFICATION-AGENT-LEGACY-PUSH-CONSUMERS…) | Owner picks either `NOTIFICATION_CONSUMER_MODE=queue_v1` (after the queue consumers exist on the `sahool` stream) or a no-overlap deploy; then redeploy staging | Deploy SUCCESS; no `Subscription unavailable` | restore the variable and roll back to `43af9d13` |
| B5 | Prod migrate-main build failure | Inspect: the redeploy snapshot built with Railpack, not the Dockerfile. Fix the builder / `RAILWAY_DOCKERFILE_PATH`, then one run. **This writes to the prod DB.** | SUCCESS; log shows "✓ التهيئة اكتملت" | Idempotent migrations; take a DB backup or volume snapshot first |
| B6 | Read-only DB verification (needs `railway ssh` credentials) | `railway ssh` into staging platform, then run `python deploy/railway/probe_platform_db.py`. Then, as the migrator in a read-only transaction: the migration ledger count vs 233 repo files (the log said 231 applied; reconcile), `SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname LIKE 'sahool%'`, `SELECT version()` (15.8 gap), and a count of RLS policies (expect v206's 128 tightened) | app role: `rolsuper=false`, `rolbypassrls=false` | none (read-only) |
| B7 | Private-network sweep, repeatable (RW-D05 method) | Temporarily add a preDeployCommand to one staging-only service, **or** use `railway ssh` plus a curl loop against `http://<svc>.railway.internal:<port>/{healthz,readyz,runtime-identity}` | 13/13 healthz 200; readyz 200 except ai-agronomist (by design) | remove the preDeployCommand. **Also remove the leftover guardrails one after capturing it.** |
| B8 | Cleanup of leftovers | Delete `wc005-postgres-live-proof` (both environments), `platform-db-proof-20260927`, `sahool-migrate` (EU), `sahool-raster-main-candidate`, and whichever of `sahool-redis-state` / `-0zaK` is unreferenced (the owner checks the reference variables). Snapshot volumes first. | Fewer services; no consumer errors | Volume deletion is irreversible, so back up first; services without volumes can be re-created from config in this report |
| B9 | Deploy gating | Set `checkSuites:true` on repo services; stop prod auto-deploy from `main` (release branch/tag or manual promotion) | Deploys wait for green CI; prod changes only on promotion | Toggle back |
| B10 | Observability | `set-service-tracing` on platform, auth-main and frontend (or OTEL variables); a webhook for deploy FAILED/CRASHED and monitor alerts | spans > 0 in `get-tracing-coverage`; webhook listed | Disable tracing; delete the webhook |
| B11 | Prod frontend upstream noise | Set `SAHOOL_{RAG_RETRIEVAL,SUPERVISOR_AGENT,REMOTE_SENSING_WORKSPACE_BFF}_UPSTREAM=absent` on prod, and decide the fate of `SAHOOL_AI_AGRONOMIST` (absent in prod) — as done on staging 09-29 | 0 `could not be resolved` after deploy | Unset the variables and redeploy |
| B12 | Security gaps on Railway | Pin images by digest; NATS `authorization` plus credentials (gap NATS-ON-RAILWAY…); Postgres 15.8 → 15.19 (gap POSTGRES-15-8…) | Digest in source; nats logs show auth required | Previous tag / volume snapshot |
| B13 | Authenticated journey on staging | `scripts/smoke_e2e.py` with `BASE_URL=https://sahool-frontend-staging.up.railway.app` on a dedicated test tenant. **Creates a user and a field.** | register/login/me 200; field create 201; workspace 200 | Delete the test tenant rows (owner-run SQL) |
