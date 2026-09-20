# Canonical v9 gateway startup and DNS acceptance

Scope: `docker-compose.v9.yml` (including its GPU overlay), `nginx/nginx.v9.conf`
and the frontend image built by `frontend/Dockerfile`. Legacy Compose variants
are not silently migrated by this change.

## Contract

The main gateway must start even when its application backends have no DNS
records yet. Its existing upstreams use nginx runtime resolution, a shared zone
per group and the same patch-pinned nginx version already used by the frontend.
There is no gateway-wide `depends_on: service_healthy` barrier. Dependencies of
the backends themselves, including database and tiler readiness, are unchanged.

This is not relaxed application readiness. HTTP `/healthz` is local gateway
liveness. Private HTTPS `/readyz` and `/runtime-identity` still forward to the
platform, retain their allow/deny rules, and never return the SPA as evidence.
Missing backends yield request failures. Missing Auth cannot authorize a protected
request. Missing or invalid TLS certificates remain configuration failures.
All route bodies, tenant/auth boundaries, TLS settings and physical-effect paths
are unchanged.

The frontend health command and timing match its canonical Compose healthcheck.
The image remains non-root; the stock IPv6 configuration-mutating hook is removed
because IPv6 listeners are already explicit. No writable/root runtime config is
introduced just to silence that hook.

## Automated evidence

```bash
python3 frontend/tests/test_nginx_runtime.py --docker
python3 nginx/tests/test_gateway_runtime.py --docker
python3 -m pytest -q tests_v9/test_compose_nginx_upstream_contract.py \
  tests_v9/test_v9_feature_transfer_20260702.py \
  tests_v9/test_service_consumer_closure_20260723.py \
  tests_v9/test_connectivity_tile_transport.py \
  tests_v9/test_gateway_operational_endpoints_contract.py
```

The runtime tests use actual nginx and DNS/HTTP fixtures; the gateway test also
uses a temporary TLS certificate. They start without backend DNS, add records,
remove Auth and an optional service, replace Auth's IP, and require the original
nginx process to survive. They check URI/query/body forwarding, fail-closed auth,
private operational ACLs, redirects and WebSocket headers. This is not a real
WebSocket conversation or a test of real service JWT implementations.

The static DNS gate must count `server host:port resolve;` as a binding and reject
unknown hosts or a zero-binding measurement. Regression tests intentionally plant
both failures. Readiness of the full v25 stack remains local acceptance work.

## Apply and verify locally

Use the existing project's actual Compose name, environment file and overlay
set; do not accidentally create a second stack. Capture the old image IDs and
rendered configuration first. Rebuild `sahool-frontend` and pull the pinned
`sahool-nginx` image, then recreate only those two services during a maintenance
window. A restart of an old frontend image does not copy the fixed configuration.
No database volumes or TiTiler containers need deletion.

Inspect `nginx -v` and `/etc/nginx/conf.d/default.conf` inside the frontend.
Inspect `nginx -T` inside the gateway. Confirm runtime `resolver`, every upstream's
`resolve` and `zone`, and that the gateway is Running rather than Created.
Record image IDs/config digests and the source SHA with the results. The frontend
`/runtime-identity` is the platform's identity, not the frontend image identity.

Do a cold-start/late-backend drill only in a disposable replica. Confirm local
liveness, truthful unavailable routes, recovery after backend recreation, and no
increase in nginx restarts during the drill. Do not stop production Auth merely
to run this check. A healthy frontend alone does not prove a healthy main gateway.

Rollback uses the previously recorded frontend image and gateway image/config
from the same prior revision. Rolling back only the gateway image below 1.27.3
while retaining `resolve` would be an incompatible partial rollback.
