# Railway frontend deployment

This is an optional Railway adapter for the existing web application. Compose
continues to use `frontend/Dockerfile` and `frontend/nginx.conf`. The adapter reads
that same nginx configuration and changes only service discovery, upstream
addresses, redirect authorities and the listening port. It supports both literal
proxy targets and named upstreams used by the separate frontend DNS fix.

## Service configuration

Use the existing `sahool-frontend` service, not a duplicate service. A service with
only a Dockerfile path and no connected source cannot build.

| Setting | Value |
| --- | --- |
| Repository | `kafaat/ai_platform_complete_v2.0.0_enhanced` |
| Branch | the reviewed branch containing this adapter, then `main` after merge |
| Root Directory | `/` |
| Builder | `DOCKERFILE` |
| Dockerfile Path | `deploy/railway/Dockerfile.frontend` |
| Port / domain target port | `8080` |
| Healthcheck | `/healthz` |
| `SAHOOL_AUTH_UPSTREAM` | `${{sahool-auth-main.RAILWAY_PRIVATE_DOMAIN}}:8000` |
| `SAHOOL_PLATFORM_UPSTREAM` | `${{sahool-platform.RAILWAY_PRIVATE_DOMAIN}}:8000` |

Apply these settings directly to this service. Railway no longer permits new
services to opt into `railway.json` or `railway.toml`; leave the custom config-file
setting unset. A project-wide migration to `.railway/railway.ts` is a separate
operation because it controls the full infrastructure graph. See Railway's
[migration guidance](https://docs.railway.com/infrastructure-as-code#migrating-from-config-as-code).

The two upstream variables are mandatory, so an old auth service is never selected
silently. They contain `host:port`, without a scheme, path, credentials or token.
The browser calls relative `/auth/*` and `/api/*` routes; private addresses are
never compiled into the JavaScript bundle. Mock mode is disabled at build time.

Optional services default to the canonical service name under `.railway.internal`.
Their addresses may be overridden with `SAHOOL_<SERVICE>_UPSTREAM`, derived from
the canonical name by replacing hyphens with underscores and uppercasing it;
for example `sahool-raster-service` uses `SAHOOL_RASTER_SERVICE_UPSTREAM`.
Missing optional services return proxy failures when requested and do not prevent
the static application or local `/healthz` from starting.

Nginx reads DNS servers from the container's `/etc/resolv.conf`. It must not use
Docker Compose's `127.0.0.11` resolver on Railway. IPv4 answers are used by default
because the current auth and platform commands bind to `0.0.0.0`. For a legacy
IPv6-only Railway environment, configure the backends to listen on IPv6 and set
`SAHOOL_DNS_IPV6=on`; do not enable it against IPv4-only listeners.

## Activation and checks

1. Review the exact source revision, connect it to the existing frontend service,
   and apply the build settings above to that service.
2. Set the two private upstream references and `PORT=8080`. Preserve existing
   authentication secrets, MFA enforcement and cookie security in auth.
3. Deploy the frontend and inspect its build and runtime logs. Check `/healthz`,
   `/`, a nested SPA URL, `/readyz`, and `/runtime-identity` separately.
4. Attach a public frontend domain only when approved. The auth and platform
   services can remain private. Confirm an unauthenticated auth request is
   rejected, then test the actual login/MFA flow with an authorized test account.
   Inspect the same-origin cookies and a subsequent authenticated API request.
5. Verify JWT key compatibility between auth and platform before claiming login
   works end to end. A successful health check does not establish that contract.

On 2026-09-19, the frontend service had no source and no deployments or domain.
Auth-main's deployment metadata named commit `0af0603a`, while its image-build
arguments still declared `15c9c7f1`. Align build identity with the selected source
revision before using `/runtime-identity` as release evidence. The adapter does
not change auth, platform, database migrations, or the source branch they track.

## Raster tenant credential (RASTER-TENANT-TRUST-01) — enablement order

raster-service used to take the tenant from `X-Tenant-Id`, `?tid=` or `?tenant_id=`
without asking who was calling. The 2026-09-29 runtime audit read another tenant's
imagery that way from the internal network, and a local re-run against PostgreSQL
with the `NOBYPASSRLS` application role returned the victim's TileJSON bounds and
rendered tiles: row-level security held, but it was handed the forged tenant.

The fix has two halves that must be switched on in order:

- raster-service never reads the tenant from the query string, in any mode. It
  accepts `X-Tenant-Id` only beside a valid `X-Agent-Token` once
  `RASTER_TENANT_CREDENTIAL_ENFORCE=1`. Without that variable it runs in `observe`
  mode: old header behaviour, but every assertion is counted in `/metrics`
  (`sahool_raster_tenant_assertions_total{outcome=…}`) and shown in `/readyz`
  (`tenant_credential`).
- This frontend injects `X-Agent-Token` on `/api/raster/` behind `auth_request`.
  The renderer fills `${SAHOOL_AGENT_TOKEN}` from this service's environment. If
  the variable is unset, the header is not sent.

Compose v9 and Helm enable enforcement by default. Railway deploys from `main`, and
this service had no `SAHOOL_AGENT_TOKEN` when the change was written. Merging the
change leaves staging in `observe` mode, so tiles keep working. The hole on Railway
stays open until the operator completes these steps:

1. **Frontend first.** On `sahool-frontend`, set
   `SAHOOL_AGENT_TOKEN=${{shared.SAHOOL_AGENT_TOKEN}}`, which must be the same value
   raster-service has, and redeploy. The value may contain only URL-safe characters
   (`A–Z a–z 0–9 . _ ~ + / = : @ ! * % , -`). The renderer refuses anything else
   before nginx starts.
2. **Confirm every other caller carries the same token.** Check `sahool-platform`
   (all raster calls go through `api/raster_service_client.py`),
   `sahool-vegetation-analysis`, and indicators when it is deployed. Each must have
   the same `SAHOOL_AGENT_TOKEN` as raster-service.
3. **Measure; don't assume.** With real map traffic, check raster `/metrics`. The
   `credentialed` count should rise, and the `uncredentialed` and
   `invalid_credential` counts should stay flat. A rising `uncredentialed` count
   points to a caller from step 2. Raster's log names the path on the first
   occurrence and on every 1000th after it.
4. **Then enforce.** On `sahool-raster-service`, set
   `RASTER_TENANT_CREDENTIAL_ENFORCE=1` and redeploy. Check that `/readyz` reports
   `"tenant_credential": {"mode": "enforce", …}`. Check that
   `sahool_raster_tenant_credential_enforced` is `1`. Load a map tile and a history
   thumbnail through the frontend. From another private service, send an internal
   request with a forged `X-Tenant-Id` and no token. It should return `401`.
5. **Rollback** is `RASTER_TENANT_CREDENTIAL_ENFORCE=0` on raster-service. It does
   not bring back the `?tid=` fallback, which was removed on purpose.

If raster-service itself has no `SAHOOL_AGENT_TOKEN`, enforcement answers `503`
(`unconfigured`) to every tenant assertion. This is an operator fault, not a
caller rejection.

## Verification boundaries

```bash
python -m pytest -q tests/deploy/test_railway_frontend_config.py
```

Test the rendered configuration with real nginx 1.27.3 or newer, including startup
with unavailable DNS, URI/query preservation, login rewrites and fail-closed
`auth_request` behavior. Local DNS/HTTP fixtures prove proxy behavior, not a live
Railway login. A full container build and the hosted login/MFA flow are separate
deployment checks. Repository checks alone do not certify the hosted service.

Private networking reference: https://docs.railway.com/networking/private-networking/how-it-works
