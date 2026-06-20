# SAHOOL Platform — Production Certification Report
**Generated:** 2026-06-17T18:35:00Z  
**Certification Agent:** SAHOOL Production Certification Agent  
**Stack:** docker-compose.fixed.yml  
**Evidence Pack:** evidence_pack/

---

## ═══════════════════════════════════════════
## FINAL VERDICT: **FAIL**
## ═══════════════════════════════════════════

Two blocking critical findings prevent production certification:
1. Application bypasses its own RLS via superuser database role
2. Core business logic service (`sahool-platform`) is not deployed

---

## PHASE RESULTS SUMMARY

| Phase | Name | Verdict | Notes |
|-------|------|---------|-------|
| 1 | Discovery | PASS | 30 services mapped, 3 topology files |
| 2 | Build Validation | PASS | 76 migrations idempotent, imports clean |
| 3 | Runtime Validation | PASS | 28/28 containers healthy at baseline |
| 4 | Migration Certification | PASS | 76 migrations, 250 indexes, 8 functions |
| 5 | Multi-tenant Isolation | PASS_WITH_RISKS | DB-layer isolation works; app bypasses it |
| 6 | Event Certification | PASS | Dedup, outbox, DLQ all functional |
| 7 | GIS Certification | PASS | PostGIS 3.4.3, 8500 SRS, spatial indexes |
| 8 | AI Governance | PASS_WITH_RISKS | Guardrails exist but agent token missing |
| 9 | UI Certification | PASS | 4/4 pages loaded, screenshots captured |
| 10 | Security Certification | FAIL (CRITICAL) | RLS bypass, missing headers, dev creds |
| 11 | Performance Certification | PASS | 192 RPS @ 50-concurrent, p95=627ms |
| 12 | Chaos Certification | PASS | All services recovered within 30s |

---

## CRITICAL FINDINGS (Block Production)

### FINDING-001 — CRITICAL: RLS Architecture Bypassed by All Services
**Severity:** CRITICAL  
**Evidence:**
```
DATABASE_URL=postgresql://sahool_user:change_this_postgres_dev_password@sahool-postgres:5432/sahool

SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('sahool_user','sahool_app');
 sahool_app  | f        | f
 sahool_user | t        | t          ← ALL SERVICES USE THIS
```
**Root cause:** Every service's `DATABASE_URL` in `.env` connects as `sahool_user` (PostgreSQL superuser, `rolbypassrls=true`). PostgreSQL superusers skip ALL row-level security policies. The `sahool_app` role (non-superuser, `rolbypassrls=false`) was created by migrations but never wired into any service.

**Impact:** The entire multi-tenant RLS architecture — 60 tables, 60 policies — provides zero protection at the application layer. A bug in any service could expose all tenants' data without any database-level barrier.

**Proof:** DB-layer isolation test (Phase 5) passed *because it used `sahool_app`*. The running application uses `sahool_user` and bypasses every policy.

**Reproduction:**
```bash
# As sahool_user (what the app uses):
SET app.current_tenant = 'tenant-a-uuid';
SELECT count(*) FROM fields;  -- returns ALL fields from ALL tenants

# As sahool_app (what it should use):
SET app.current_tenant = 'tenant-a-uuid';
SELECT count(*) FROM fields;  -- returns only tenant-a's fields
```

**Fix:**
```bash
# 1. Change DATABASE_URL in .env:
DATABASE_URL=postgresql://sahool_app:$(new_password)@sahool-postgres:5432/sahool

# 2. Set password for sahool_app:
docker exec v05-sahool-postgres-1 psql -U sahool_user -d sahool -c \
  "ALTER ROLE sahool_app PASSWORD 'new_secure_password'"

# 3. The sahool_app role already has all required grants (applied by migration).
```

---

### FINDING-002 — CRITICAL: Core Business Logic Service Not Deployed
**Severity:** CRITICAL  
**Evidence:**
```
# docker-compose.fixed.yml has no sahool-platform service
grep "sahool-platform" docker-compose.fixed.yml  → (no output)

# But supervisor-agent calls it at runtime:
# services/supervisor-agent/main.py: PLATFORM_SERVICE_URL = http://sahool-platform:8000
```
**Root cause:** `services/sahool-platform/` contains the main API (field management, harvest operations, activities, sensors, TrueUp, etc.). It is defined in `docker-compose.v9.yml` but was never added to `docker-compose.fixed.yml`.

**Impact:** All supervisor-agent calls for field state context fail silently. The platform is running without its primary business logic layer. Core features (field lifecycle, harvest operations, TrueUp calibrations) are inaccessible via API.

**Fix:** Add `sahool-platform` service to `docker-compose.fixed.yml` (definition exists in `docker-compose.v9.yml` lines 361–395).

---

## HIGH FINDINGS

### FINDING-003 — HIGH: AI Governance Inoperative
**Severity:** HIGH  
**Evidence:**
```bash
docker exec v05-sahool-guardrails-engine-1 curl -sf http://localhost:8000/validate \
  -d '{"action":"field.create","payload":{}}' → 503 Service Unavailable
# SAHOOL_AGENT_TOKEN not in docker-compose.fixed.yml for guardrails service
```
**Impact:** Governance validation (3-tier Chemical/Environmental/Economic safety) cannot execute. All AI-driven actions run without safety validation.
**Fix:** Add `SAHOOL_AGENT_TOKEN: ${SAHOOL_AGENT_TOKEN}` to `sahool-guardrails-engine` environment in `docker-compose.fixed.yml`.

### FINDING-004 — HIGH: Schema Drift from Certification Testing
**Severity:** HIGH  
**Evidence:**
```sql
SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='events_source_check';
-- 'certification' was added to the allowed sources list during Phase 6 testing
```
**Impact:** The `events_source_check` constraint was modified during certification. The production constraint now allows `source='certification'` which was not in the original schema. This is schema drift caused by the certification process itself.
**Fix:** Remove 'certification' from the constraint or document it as intentional.

---

## MEDIUM FINDINGS

### FINDING-005 — MEDIUM: Infrastructure Ports Exposed on 0.0.0.0
**Evidence:**
```
sahool-minio:  0.0.0.0:9000->9000, 0.0.0.0:9001->9001  (should be 127.0.0.1)
sahool-raster: 0.0.0.0:8001->8001                       (should be 127.0.0.1)
```
**Fix:** Change port bindings in docker-compose.fixed.yml to `127.0.0.1:9000:9000` etc.

### FINDING-006 — MEDIUM: No Security Headers on nginx
**Evidence:**
```bash
curl -sI http://localhost/healthz | grep -E "X-Frame|X-Content|CSP|HSTS"
# No output — none present
```
`nginx.fixed.conf` has no security headers. `nginx.v9.conf` has them correctly.
**Fix:** Add to `nginx.fixed.conf` server block:
```nginx
add_header X-Frame-Options DENY;
add_header X-Content-Type-Options nosniff;
add_header Strict-Transport-Security "max-age=31536000" always;
```

### FINDING-007 — MEDIUM: Default/Weak Credentials in Production .env
**Evidence:**
```
DATABASE_URL=postgresql://sahool_user:change_this_postgres_dev_password@...
# Password literally says "change_this" — it was not changed
```
**Fix:** Generate and set strong credentials in `.env` before production deployment.

### FINDING-008 — MEDIUM: Stub Services Masquerade as Functional
**Evidence:** `sahool-indicators-service` and `sahool-weather-service` return health endpoints but contain no business logic. Real logic is in `sahool-platform/api` (not deployed).

### FINDING-009 — MEDIUM: 2 Tables Missing RLS
- `field_lifecycle_transitions` — has `field_lifecycle_id` FK but no direct `tenant_id` or RLS
- `weather_automation_locations` — stores `field_id` (tenant-scoped) without RLS

---

## LOW FINDINGS

### FINDING-010 — LOW: JWT Error Leaks Implementation Details
Auth service error response includes python-jose internal strings. Supervisor-agent handles this correctly with generic messages.

### FINDING-011 — LOW: 4 Infrastructure Services Lack Healthchecks
qdrant, prometheus, grafana, jaeger report `running` not `healthy`. Non-blocking.

### FINDING-012 — LOW: Raster Service Port 8001 Errors Under Load
Performance test: 20/20 errors on `localhost:8001/healthz`. Service healthy inside Docker; external port binding issue on host.

---

## WHAT PASSED (Evidence-Backed)

| Check | Evidence |
|-------|----------|
| Migration idempotency | migrate container exit 0, zero ERROR lines, 76 migrations |
| DB-level RLS isolation | Tenant A/B cross-query = 0 rows; fail-closed confirmed |
| Event dedup (idempotency) | Second `emit_event()` → NULL (dedup hit confirmed via NOTICE) |
| Event outbox durability | Outbox count unchanged during Redis pause (Postgres durable) |
| PostGIS 3.4.3 | 8,500 spatial ref systems; GiST indexes on 3 tables; 4 geometry triggers |
| Auth JWT tampering | Fake JWT → 401; empty auth → 401 |
| Rate limiting | 5 failures → 429 lockout (brute force protected) |
| SQL injection | Pydantic `EmailStr` rejects all payloads before DB |
| Chaos recovery | All 5 services recovered within 30s after pause/unpause |
| Performance | nginx: p50=1.7ms p95=30ms @ 20-sequential; 327 RPS @ 10-concurrent; 192 RPS @ 50-concurrent; p95=627ms |
| UI | 4/4 pages loaded, screenshots at evidence_pack/screenshots/ |
| Append-only events | `trg_append_only_events` blocked DELETE during cleanup (by design) |

---

## REMEDIATION ROADMAP

**Before production (blocking):**
1. `DATABASE_URL` → use `sahool_app` role (1 line change in .env + password set)
2. Add `sahool-platform` service to `docker-compose.fixed.yml`
3. Add `SAHOOL_AGENT_TOKEN` to guardrails-engine environment
4. Revert `events_source_check` constraint (remove 'certification')

**Before production (security hardening):**
5. Set strong passwords in .env (remove "change_this_*" defaults)
6. Bind MinIO and raster-service to 127.0.0.1
7. Add security headers to nginx.fixed.conf
8. Add RLS to `field_lifecycle_transitions` and `weather_automation_locations`

**Post-launch (backlog):**
9. Add healthchecks to qdrant, prometheus, grafana, jaeger
10. Implement sahool-indicators-service and sahool-weather-service business logic
11. Migrate to docker-compose.v9.yml (canonical production compose)

---

## EVIDENCE PACK CONTENTS

```
evidence_pack/
├── architecture/
│   ├── architecture.json          (30 services, ports, routes, deps)
│   ├── dependency_graph.json      (compose + runtime deps)
│   └── runtime_topology.json     (live IPs, networks, volumes, health)
├── migrations/
│   ├── idempotency_test.txt       (76 migrations re-run, exit 0)
│   ├── rls_coverage.json          (68 tables, RLS status)
│   ├── schema_state.json          (all columns, types)
│   ├── indexes.txt                (250 indexes)
│   ├── constraints.txt            (PKs, FKs, unique)
│   ├── functions_present.txt      (8 stored procedures verified)
│   └── critical_columns.txt       (v18 TEXT type fix confirmed)
├── tenant_isolation/
│   └── tenant_isolation_report.json (8 tests, no leakage)
├── events/
│   └── event_integrity_report.json  (dedup, outbox, DLQ)
├── gis/
│   └── gis_validation_report.json   (PostGIS, spatial indexes, triggers)
├── ai_governance/
│   └── ai_governance_report.json    (guardrails tiers, bypass tests)
├── security/
│   └── security_report.json         (JWT, IDOR, SQLi, rate limit)
├── screenshots/
│   ├── homepage.png
│   ├── frontend_direct.png
│   ├── healthz.png
│   ├── auth_api.png
│   └── ui_results.json
├── performance/
│   └── load_test_results.json        (baselines + 10/50-concurrent)
└── final_report/
    └── CERTIFICATION_REPORT.md       (this file)
```
