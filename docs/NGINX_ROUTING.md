# NGINX Production Routing — SAHOOL (`nginx/nginx.v9.conf`)

How the frontend's `/api/*` (and `/auth/*`, `/tts/*`, `/ws/*`) calls reach the
backends in production. The web app's `kongApi` uses base `/api`
(`VITE_API_URL` default `/api`); the auth client uses `VITE_AUTH_URL` → `/auth`.

## Key nginx rewrite rule

When `proxy_pass` has a **URI** (a path after the host, e.g. `.../api/v1/`),
nginx replaces the matched `location` prefix with that URI. When `proxy_pass`
has **no URI** (just the host, e.g. `.../`), the matched prefix is stripped and
the remainder is forwarded. This is the crux of every mapping below.

## Public path → upstream → backend route

| Public path (browser) | `location` | `proxy_pass` | Upstream receives | Backend route exists? |
|---|---|---|---|---|
| `/auth/*` | `/auth/` | `auth_backend` (`rewrite` to `/v1/auth/*`, no URI) | `/v1/auth/*` (rewritten, not just prefix-stripped) | auth-service `/v1/auth/login` etc. (API-VERSIONING-GUARD-IS-A-MIRROR-01) — auth client base already includes `/auth`, so e.g. `authApi.post('/auth/login')` → `/auth/auth/login` on the wire. See note 1. |
| `/api/v1/*` | `/api/v1/` | `platform_backend/api/v1/` | `/api/v1/*` (prefix preserved) | sahool-platform — all `/api/v1/...` routes ✓ |
| `/api/indicators/*` | `/api/indicators/` | `platform_backend/api/v1/indicators/` **(FIXED)** | `/api/v1/indicators/*` | platform `/api/v1/indicators/dashboard`,`/catalog` ✓ |
| `/api/weather/*` | `/api/weather/` | `platform_backend/api/v1/weather/` **(FIXED)** | `/api/v1/weather/*` | platform `/api/v1/weather/current`,`/forecast`,`/historical` ✓ |
| `/api/vegetation/*` | `/api/vegetation/` | `vegetation_backend/` | `/*` (prefix stripped) | vegetation `/v1/analyze`,`/v1/timeseries/{id}` — call as `/api/vegetation/v1/...` ✓ |
| `/api/soil/*` | `/api/soil/` | `soil_backend/` | `/*` (prefix stripped) | soil `/v1/soil/readings/{id}` — call as `/api/soil/v1/soil/...` (alias; frontend uses direct `VITE_SOIL_URL`) |
| `/api/agent/health` | `= /api/agent/health` (exact) **(FIXED)** | `supervisor_backend/health` | `/health` | supervisor `/health` ✓ (health probe) |
| `/api/agent/*` | `/api/agent/` | `supervisor_backend/agent/` **(FIXED)** | `/agent/*` (prefix preserved) | supervisor `/agent/query`,`/agent/optimize` ✓ |
| `/api/guardrails/*` | `/api/guardrails/` | `guardrails_backend/` | `/*` (prefix stripped) | guardrails `/validate` — service-to-service only; requires `X-Agent-Token`, so a direct browser call fails-closed by design (see note 2) |
| `/tts/*` | `/tts/` | `http://sahool-tts:8000` | `/tts/*` (no URI ⇒ preserved) | tts-service |
| `/ws/*` | `/ws/` | `notification_ws/ws/` | `/ws/*` (preserved) | notification-agent WebSocket |
| `/metrics` | `/metrics` | `indicators_backend/metrics` | `/metrics` | internal-only (allow 127/172.20) |
| `/*` (everything else) | `/` | `frontend_backend/` | `/*` | SPA static + `@spa_fallback` → `index.html` |

## Fixes applied in this pass

1. **`/api/agent/*` dropped the `/agent/` prefix.** The supervisor serves its
   functional routes under `/agent/` (`/agent/query`, `/agent/optimize`), but
   `proxy_pass http://supervisor_backend/;` rewrote `/api/agent/query` → `/query`
   (404). Changed to `proxy_pass http://supervisor_backend/agent/;` so
   `/api/agent/query` → `/agent/query` and `/api/agent/optimize` → `/agent/optimize`.
   The health probe (`/api/agent/health`) needs `/health` (not `/agent/health`),
   so it is broken out into an `exact-match` `location = /api/agent/health` that
   maps to `supervisor_backend/health` — placed before the prefix block so the
   probe keeps working.

2. **`/api/indicators/*` and `/api/weather/*` dropped the `/api/v1/` prefix.**
   These platform surfaces live under `/api/v1/indicators/*` and
   `/api/v1/weather/*`, but `proxy_pass http://platform_backend/;` rewrote
   `/api/weather/current` → `/current` (404) and `/api/indicators/dashboard` →
   `/dashboard` (404). Changed to
   `proxy_pass http://platform_backend/api/v1/indicators/;` and
   `.../api/v1/weather/;` so the documented platform routes resolve. (The current
   web app reaches indicators via `/api/v1/indicators/*` directly; these aliases
   are now correct rather than silently broken.)

3. **Undefined `general_limit` rate-limit zone.** The `/tts/` block referenced
   `zone=general_limit`, which was never declared — nginx fails to load with
   "unknown limit_req_zone". Declared
   `limit_req_zone ... zone=general_limit:10m rate=120r/m;` alongside the other
   zones to keep the config loadable.

## Notes

1. **Auth base path.** The frontend's `authApi` has base = `VITE_AUTH_URL` **and**
   calls paths that already begin with `/auth/` (e.g. `authApi.post('/auth/login')`).
   So with the production setting `VITE_AUTH_URL=/auth`, the browser requests
   **`/auth/auth/login`**. The auth-service itself moved its routes from bare
   `/auth/*` to `/v1/auth/*` (API-VERSIONING-GUARD-IS-A-MIRROR-01), so the nginx
   block now carries **two** `rewrite` rules instead of a single prefix-strip:
   ```
   location /auth/ {
       rewrite ^/auth/auth/(.*)$ /v1/auth/$1 break;
       rewrite ^/auth/(.*)$ /v1/auth/$1 break;
       proxy_pass http://auth_backend;
   }
   ```
   The first rule normalizes the frontend's double-prefixed convention
   (`/auth/auth/login` → `/v1/auth/login`); the second normalizes a direct
   REST client's single-prefixed convention (`/auth/login` → `/v1/auth/login`).
   Either way the auth-service — which now mounts its routes under
   `/v1/auth/*` — receives a path it recognizes. A trailing-slash
   `proxy_pass http://auth_backend/;` (no rewrite) cannot express this: it can
   only strip one literal `/auth/` layer, so it would forward
   `/auth/auth/login` → `/auth/login`, still short of `/v1/auth/login`.
   (In `VITE_API_MODE=dev`, `VITE_AUTH_BASE_URL` defaults to the auth-service
   origin directly with no nginx in between, so `frontend/src/config/endpoints.ts`
   bakes the `/v1` segment into that default base itself — `frontend/src/config/
   endpoints.ts` resolves it as `http://localhost:8120/v1`, so the frontend's
   unchanged `/auth/login` call becomes `http://localhost:8120/v1/auth/login`,
   which the service recognizes.)

2. **Guardrails is service-to-service.** `guardrails-engine`'s `/validate`
   enforces a service token (`X-Agent-Token`) and is intended to be called by the
   supervisor (which derives `tenant_id` from the verified user token), not
   directly from the browser. The nginx mapping `/api/guardrails/` →
   `guardrails_backend/` is structurally correct (`/api/guardrails/validate` →
   `/validate`); a direct browser call fails-closed by design.

3. **`nginx -t` not runnable here** (no nginx binary, `${DOMAIN}` is an envsubst
   placeholder resolved at deploy). This document is the result of a careful
   textual review; brace blocks were verified balanced.
