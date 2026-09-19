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
