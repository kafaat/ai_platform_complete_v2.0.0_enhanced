# Connectivity repairs — 2026-09-10

Base: `7407eae2ba006a4c4c07018988a0f680e176abea`; branch `fix/connectivity-audit-20260910`.

## Implemented scope

| Review finding | Change | Closure boundary |
| --- | --- | --- |
| CONN-01 | Registry TileJSON emits an authenticated, tenant-scoped platform tile route. The canonical raster tiler joins the internal network; platform and raster depend on its health. | Code and mocked transport verified; live Compose remains unmeasured. |
| CONN-02 | Raster layer TileJSON uses the gateway route; dynamic COG transport executes after tenant authorization. Field compatibility tiles reuse the authorized field route. | No internal hostname or arbitrary source URL in tile URLs. |
| CONN-05 | ERPNext requires an explicit deployment URL plus credentials; incomplete configuration selects NullProvider. | No live ERPNext request measured. |
| CONN-06 | All nginx upstreams are healthy dependencies, directly or transitively. | Startup dependency DAG checked; cold start and container replacement/DNS recovery remain unmeasured. |
| CONN-08 | Source-derived inventories and their downstream evidence are regenerated. | Source wiring is not runtime certification. |

`shared/gis/cog_tile_proxy.py` bounds coordinates, source scheme/host, backend timeout, PNG type/signature and response size. Backend redirects are refused, credentials are not forwarded, and tile responses are private/no-store. The client supplies a registered record ID, never a TiTiler source URL. The additional platform route retains the existing permission and transaction-scoped tenant lookup.

## Operator configuration

The canonical v9 backend is `TITILER_URL=http://raster-tiler-service:8088`. Set `COG_TILE_ALLOWED_HOSTS` to an explicit comma-separated list of trusted public HTTPS source hosts used by registered COG records. Empty configuration returns 503. Unapproved hosts, non-HTTPS URLs and private `s3://`/`file://` objects are refused. A host allowlist assumes trusted host content and redirect behavior; it is not an object-level ownership or DNS/egress firewall. Private object access requires a separate ownership-aware adapter before enabling it. No example host is enabled automatically.

Browser tile requests must carry existing authentication. ERPNext deployments must supply their actual reachable URL. The older `sahool-titiler` is retained only under the `legacy-tiler` profile.

## Measured validation

The following combined selection passed **74 tests**, with 5 warnings, in 2.53 seconds:

```sh
python -m pytest -q \
  tests_v9/test_connectivity_tile_transport.py \
  shared/gis/test_cloud_native_runtime.py \
  tests_v9/test_compose_nginx_upstream_contract.py \
  tests_v9/test_raster_tiler_service_contract.py \
  services/odoo-bridge/test_erp_readiness_granular.py \
  tests_v9/test_raster_field_tenant_authz.py \
  tests_v9/test_tilejson_nginx_runtime_fix_20260626.py \
  tests_v9/test_erp_bridge_alias_contract.py \
  tests_v9/test_erp_bridge_fail_closed.py
```

The new HTTP test imports the actual platform router and follows its emitted TileJSON URL. Test identity and tenant database adapters demonstrate denied anonymous/other-tenant requests before transport; HTTPX MockTransport supplies the backend PNG. This does **not** measure production JWT validation, PostgreSQL RLS, deployed TiTiler, nginx, or network reachability. Other tests cover source refusal, coordinate bounds, redirects, bad/oversized payloads, timeouts, Compose dependency cycles and ERP factory selection.

The first completed default preflight ran all three test groups. Unit: 6547 passed, 5 failed, 33 skipped; repository: 742 passed, 10 failed, 8 skipped; platform collection was blocked by missing local `defusedxml`. Failures included stale route/count expectations, generated fingerprints, missing historical Git objects in a shallow checkout and missing local SOCKS support. The two selected unit environment/history failures also reproduced on base `7407eae2`. Route/count expectations are updated for the one intentional addition (632 raw, 4 infrastructure, 628 domain; limit remains 629). Follow-up results are reported in the PR; the original full run is not represented as green. Docker and Flutter are unavailable in this environment; no live stack, mobile build, or production certification is asserted.

## Open findings

- **CONN-03 OPEN:** NATS per-service identities/subject ACLs and TLS need a coordinated producer/consumer rollout; shared credentials remain.
- **CONN-04 BLOCKED_BY_POLICY:** the producer subject mismatch remains. `docs/architecture/gate01_policy.json` freezes `services/sahool-platform/api/phase_runtime_workers.py`; no frozen file or replacement bypass was changed. An explicit repository adjudication is required before altering that boundary.
- **CONN-07 OPEN:** native Android/iOS projects and lockfile/build evidence remain outside this repair.
- End-to-end agricultural execution, AI inference and device actuation were not changed or certified by this connectivity patch.

## Follow-up verification

- 24 selected failed cases and adjacent governance checks passed after correcting gateway URL/count expectations and local dependencies.
- Both historical commit-claim cases passed after fetching their referenced history; no historical record was edited.
- The platform suite then ran: 4293 passed, one old route-count expectation failed. That expectation is updated from 631/4/627 to 632/4/628 while retaining the 629 limit; its complete budget test file is rerun separately.
- TiTiler 0.22.4 wheel source declares `/tiles/{tileMatrixSetId}/{z}/{x}/{y}.{format}`, matching the transport path shape; the deployed backend itself remains unmeasured.
- Missing `socksio` and `defusedxml` were installed only in the local test environment. Repository dependency manifests were not changed.

Final generated consistency, release validation and PR-head checks are reported in the PR. The full preflight results above remain the results of that completed run; subsequent targeted corrections are not a claim of a second full green run.
