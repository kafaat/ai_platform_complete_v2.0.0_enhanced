STATUS: COMPLETE
BASE: 1cb6cd6c2e01851bb9afa49d1fb1a4bfb35ee277
WORKTREE BRANCH: worktree-agent-a1ece0f1d62d2e7f2 (not pushed)
NOTE: BASE is the worktree HEAD at start (1cb6cd6c = main incl. #1108), not the bcb7f0ed named in the brief. Salvage 5113d330 was read as a lead only. Ideas reused from it are marked "(idea from salvage)".

## RASTER-TENANT-TRUST-01 (P1): raster-service trusted a tenant named by the caller
class: A-fixed
commit: 0840d46e
defect measured:
  - Before, on the internal path, live: real uvicorn raster-service running the pre-fix tree (git archive HEAD), real PostgreSQL 16 + PostGIS, app role `sahool_app` NOSUPERUSER NOBYPASSRLS, FORCE RLS. The schema slice came from migrations/v14_imagery_storage.sql and v88_field_owner_function.sql. Two tenants A and B each had one field and one ready NDVI GeoTIFF. The harness is scratchpad/rerun/rt/live_two_identity.py.
      identity A (A + token) reads F-A        -> tilejson 200, A's bounds | tile 200, 802B rendered
      identity B (B + token) reads F-A        -> 404 / tile 403
      B forges X-Tenant-Id: A, no token       -> tilejson 200, A's bounds | tile 200, 802B   LEAK
      B forges header A, wrong token          -> 200, A's bounds | tile 200                 LEAK
      B uses ?tid=A, no header                -> 200, A's bounds | tile 200                 LEAK
      B uses ?tenant_id=A                     -> 200, A's bounds | tile 200                 LEAK
  - Mechanism, measured: the tenant is `X-Tenant-Id` or `?tid` or `?tenant_id` (services/raster-service/raster_security_context.py:30 at base; shared/security/tenant_context.py:39). raster_app_factory.py sets REQ_TENANT from it for every request. `require_field_tenant` compares the DB owner (a SECURITY DEFINER function) with that value. db_persist sets `app.current_tenant` to the same value, so RLS returns the victim's rows. RLS itself holds (the app role sees 0 rows without the GUC); it was given the forged tenant.
  - What leaked, by route: every route that reads REQ_TENANT and does not require X-Agent-Token. That covers /v1/fields/{id}/tilejson (bounds, dates, cog version), /tiles/{z}/{x}/{y}.png (rendered imagery; the tile cache is keyed by the asserted tenant), cdse-tilejson, cdse-tiles, cdse-thumbnail.png (history thumbnails, persisted source), available-dates, terrain, contours, soil summary, sampling zones and sampling plan. /v1/soil/* and terrain hillshade/slope tiles are global data gated only by "any tenant". Routes that already require X-Agent-Token (indicator-grid, observation-bundle, prescription, process-*, jobs, …) were not open to untokened callers.
  - Who could reach it: any container on the internal network (compose: sahool-internal; Railway: the private network). In Helm, the Ingress routes /api/raster straight to the service with no auth_request and no header stripping (helm/sahool/templates/ingress.yaml, values.yaml pathPrefix). The prefix is not stripped, so raster routes there 404 today.
fix:
  - services/raster-service/raster_security_context.py: `tenant_assertion_for_request` (header only; `service_token_ok` from shared/security/trusted_tenant.py is the #1069 comparator, reused rather than copied). Outcomes are counted: none / credentialed / uncredentialed / invalid_credential / unconfigured / query_hint_ignored. The warning log fires on the first occurrence and every 1000th. `require_service_token` now uses the same comparator. The import of shared/security/tenant_context.py and the local query fallback were removed.
  - services/raster-service/raster_app_factory.py: the middleware decides once for all routes. Under enforce it returns 401 (503 if the service has no token) before any router runs. (idea from salvage)
  - The routers (fields.py, cdse_tiles.py, soil_tiles.py, terrain_tiles.py) no longer emit `tid` in TileJSON tile URLs, and the unused `tid` Query params on soil and terrain tiles are gone. (idea from salvage)
  - routers/observability.py: `/metrics` exposes sahool_raster_tenant_assertions_total{outcome} and sahool_raster_tenant_credential_enforced. `/readyz` reports `tenant_credential` for information only; it is not a readiness condition.
  - Gateways inject the token only behind auth_request: nginx/nginx.v9.conf `location /api/raster/` (envsubst already existed) and frontend/nginx.conf `location ^~ /api/raster/`, using the `${SAHOOL_AGENT_TOKEN}` placeholder.
      · frontend/Dockerfile: nginx.conf is now an entrypoint template, with NGINX_ENVSUBST_FILTER=SAHOOL_AGENT_TOKEN and a default of "". The stock default.conf is removed, and conf.d is chowned to nginx so the non-root entrypoint can write to it. (idea from salvage) I checked the entrypoint logic against the nginx 1.27.5 script (20-envsubst-on-templates.sh). The image build itself was NOT run, because the docker daemon is unavailable here.
      · deploy/railway/render_frontend.py fills the placeholder from SAHOOL_AGENT_TOKEN. If the variable is unset, it renders "" and nginx does not send the header. It refuses values containing quote, $, ;, braces, backslash or whitespace, and refuses any other unfilled ${UPPER} placeholder. (idea from salvage)
  - docker-compose.v9.yml sets RASTER_TENANT_CREDENTIAL_ENFORCE=${…:-1} on raster and SAHOOL_AGENT_TOKEN on sahool-frontend. helm/sahool/values.yaml sets raster RASTER_TENANT_CREDENTIAL_ENFORCE "1"; there, only the platform calls raster. .env.example documents it. The code default is observe (Railway).
  - services/vegetation-analysis-service/post_execution_bridge.py now sends X-Agent-Token with X-Tenant-Id. The raster route it targets (/imagery-ingestion-requests) does not exist on raster; it already returned 404.
  - docs/runbooks/RAILWAY_FRONTEND_DEPLOYMENT.md gains a new section "Raster tenant credential — enablement order".
  - frontend/src (comments only) corrects the stale claim that raster reads `tid`.
callers enumerated (every one of them must send the token; status after this commit):
  - Browser MapLibre/<img>/XHR → nginx.v9 /api/raster/ (compose) and frontend /api/raster/ (compose :3003, and the Railway gateway itself): inject the token behind auth_request. Measured with real nginx, see below.
  - sahool-platform api/raster_service_client.py: every call sends X-Agent-Token (raster_service_headers). routers/compat_gateway.py was a laundering path; see the next gap.
  - vegetation-analysis vegetation_runtime.py:305,372,665: already sent the token. post_execution_bridge: fixed here.
  - indicators-service observation_runtime.py:185, observation_timeline.py:193: already sent the token.
  - sentinel-hub-mcp sentinel_hub_server.py:423,462: sent NO token. Fixed in SENTINEL-HUB-MCP-01.
  - sentinel_hub/vegetation_real.py (legacy facade, not in any compose file): sends the token only if INTERNAL_SERVICE_TOKEN is set. Not deployed; left as is.
  - raster workers (cache_invalidation_worker, backfill_scan_worker), raster-tiler and titiler: make no HTTP calls to raster-service (grep).
  - platform-emitted thumbnail URLs (routers/fields.py:877, field_workspace_imagery.py:141) still carry `&tid=`. They are loaded through the gateway, which injects the header, so the parameter is now inert. I did not remove it, to keep the platform diff small; it is a follow-up item.
rollout (exact Railway operator steps; also in the runbook):
  0. Merge: raster in observe (no env var) and frontend rendering X-Agent-Token "" (not sent). Tiles are unchanged. Only ?tid/?tenant_id stop naming a tenant, and the Railway gateway always sends the verified header.
  1. sahool-frontend: set SAHOOL_AGENT_TOKEN=${{shared.SAHOOL_AGENT_TOKEN}}, the same value raster has, and redeploy.
  2. Verify that sahool-platform, sahool-vegetation-analysis and indicators (if deployed) all hold the same SAHOOL_AGENT_TOKEN.
  3. With real map traffic, raster /metrics should show sahool_raster_tenant_assertions_total{outcome="credentialed"} rising while uncredentialed and invalid_credential stay flat.
  4. sahool-raster-service: set RASTER_TENANT_CREDENTIAL_ENFORCE=1 and redeploy. Then /readyz should show tenant_credential.mode=enforce and the gauge should read 1. Load a tile and a thumbnail through the frontend, and check that a forged internal X-Tenant-Id without a token returns 401.
  5. Rollback is RASTER_TENANT_CREDENTIAL_ENFORCE=0. This does not re-open ?tid.
falsification (each mutation applied, the named tests run, then restored; scratchpad/rerun/rt/falsify_all.py):
  M1 enforce ignored → 5 red (test_tenant_credential_boundary: forged header ×3, thumbnails/every route, unconfigured 503)
  M2 query fallback restored → 5 red (query ignored ×4 + test_tile_tenant_query::test_query_tid_never_reaches_the_db_layer)
  M3 any token accepted → 1 red (invalid_credential)
  M4 tilejson emits tid → 2 red (test_tile_tenant_query)
  G1 v9 stops injecting → 1 red (test_nginx_tenant_injection_guard)
  G2 frontend stops injecting → 4 red (guard + 3 Railway renderer tests)
  G3 frontend auth_request removed → 2 red (guard + test_e2e_findings_regressions::test_service_token_is_injected_only_behind_auth_request)
  G4 renderer stops filling → 7 red
  G5 renderer accepts any chars → 7 red
  All restored → green.
  After, live (same harness, post-fix tree): enforce → A+token 200 with A's bounds · B+token 404 · B forged header 401 (uncredentialed) · B wrong token 401 (invalid_credential) · ?tid / ?tenant_id → 404, tile 403. observe → query closed, forged header still 200 (counted: uncredentialed=2).
  Real nginx 1.24, with the two raster blocks and /_auth_verify lifted verbatim (scratchpad/rerun/rt/nginx_raster_probe.py):
    frontend with token set: unauthenticated request carrying spoofed X-Tenant-Id/X-Agent-Token → 401, raster never hit. Authenticated → raster sees x-tenant-id=verified-tenant and x-agent-token=<fixture>, and the spoofed values are replaced.
    frontend with token unset: authenticated → raster sees no x-agent-token (the spoofed one is dropped).
    v9 with token set: same result as frontend with token set.
  frontend/tests/test_nginx_runtime.py was updated to fill the placeholder and assert that raster receives the token and others do not. It needs nginx ≥1.27.3 or --docker; NOT run locally (nginx 1.24 has no `resolve`, docker daemon down).
brain row (proposed): RASTER-TENANT-TRUST-01 | P1 | status: fixed (compose v9 and helm enforce; Railway stays observe until the operator order above is executed, at which point it can be marked verified by a live forged-header 401 on staging) | sources: services/raster-service/raster_security_context.py (tenant_assertion_for_request), raster_app_factory.py (middleware), nginx/nginx.v9.conf location /api/raster/, frontend/nginx.conf location ^~ /api/raster/, deploy/railway/render_frontend.py (service_token), docker-compose.v9.yml (raster RASTER_TENANT_CREDENTIAL_ENFORCE, frontend SAHOOL_AGENT_TOKEN) | evidence: two-identity live re-proof above (local PG16 and uvicorn, not staging) + commit 0840d46e.
blocker / decision needed: the Railway operator must execute steps 1–4. The code cannot close the hole on staging by itself without breaking tiles.

## RASTER-COMPAT-PASSTHROUGH-01 (P1): the platform's /api/raster/{path} passthrough laundered any tenant claim into a credentialed one
class: A-fixed
commit: 94f2e520
defect measured:
  - services/sahool-platform/api/routers/compat_gateway.py:113-137 (at base). Unauthenticated: the route was listed in tests_v9/test_endpoint_auth_coverage.py PUBLIC_ALLOWLIST as "raster authenticates server-side". It promoted `X-Tenant-Id`, `?tid=` or `?tenant_id=` to tenant_id and called raster_get_raw, which attaches the platform's X-Agent-Token (api/raster_service_client.py:32-36,115). Once RASTER-TENANT-TRUST-01 enforces, this route turns an anonymous claim into a credentialed one.
  - Live measurement (scratchpad/rerun/rt/live_compat.py): raster-service from the worktree with enforce=1 against the PG16/RLS setup above, and the platform app in-process with RASTER_SERVICE_URL pointed at it.
      direct to raster, forged X-Tenant-Id: A, no token      -> 401
      platform /api/raster/v1/fields/F-A/tilejson, forged X-Tenant-Id: A, no JWT -> 200, A's bounds   LEAK
      platform same path with ?tid=A, no JWT                  -> 200, A's bounds                      LEAK
  - Reachability: both canonical gateways route /api/raster/ to raster, not the platform, so a caller must reach sahool-platform directly (internal network, or the platform's own public domain if one exists).
fix: compat_gateway.py now takes the tenant from the JWT through `get_current_user`. This is a module-local wrapper that calls api.main.get_current_user when a request arrives, not at import. `tid`/`tenant_id` are no longer forwarded. The route was removed from PUBLIC_ALLOWLIST. docs/architecture/RASTER_FACADE_CLEANUP_CONTRACT.md P2.4 was corrected. (idea from salvage: JWT-derived tenant + allowlist removal)
  - Where this differs from the salvage, measured: the salvage imported api.main at module level. That breaks automatic router registration whenever compat_gateway is imported before api.main (register_routers gets the half-initialised module with no `router` and skips it silently). I reproduced this: test_router_decomposition_guard failed, and the route returned 404 in the same pytest session. Hence the call-time import.
falsification: C1 (the request tenant promoted again) → 1 red (test_compat_raster_passthrough_tenant::test_authenticated_caller_asserts_its_own_tenant_not_the_requested_one). C2 (auth dependency dropped) → 3 red (both compat tests + tests_v9/test_endpoint_auth_coverage::test_every_unauthenticated_endpoint_is_in_public_allowlist). Restored → green.
  After, live, two identities with real HS256 JWTs signed with the platform's in-process secret:
      no JWT (header or ?tid)                    -> 401 / 401
      JWT(A) reads F-A via compat                -> 200, A's bounds
      JWT(B) + forged X-Tenant-Id: A via compat  -> 404
      JWT(B) + ?tid=A via compat                 -> 404
brain row (proposed): RASTER-COMPAT-PASSTHROUGH-01 | P1 | status: fixed | sources: services/sahool-platform/api/routers/compat_gateway.py (get_current_user wrapper, raster_api_passthrough) · tests_v9/test_endpoint_auth_coverage.py PUBLIC_ALLOWLIST | evidence: live laundering reproduced before (200 with A's bounds while direct raster gave 401), then 401/200/404/404 after · commit 94f2e520.
blocker / decision needed: none. Note that a browser <img> reaching this legacy route without an Authorization header now gets 401 instead of data. No canonical gateway routes /api/raster/ to the platform.
stale generated artifact: tests_v9/test_api_versioning_policy_guard.py::test_api_versioning_policy_guard_inventory_is_current fails ONLY because api_versioning_inventory.{csv,generated.json} record line numbers that moved in raster observability.py/fields.py/soil/terrain/cdse routers. The coordinator's central regeneration fixes it.
PROCESS NOTE (my error): I invoked `python scripts/ci/verify_all_generated.py --check` once, against the brief. It stopped at its index precondition (an untracked file), but api_versioning_inventory.csv and .generated.json were found rewritten in the working tree (either by it or by the inventory test). I restored both with `git checkout --`. Nothing generated was committed.

## SENTINEL-HUB-MCP-01 (P2): sentinel-hub-mcp trusted a caller-chosen tenant, used demo fields, and called commercial Sentinel Hub with CDSE credentials
class: A-fixed
commit: 7242461a
defect measured (before; the real HTTP entry point POST /v1/mcp/tools/call with a real HS256 JWT for tenant-caller, scope satellite:read; the image's merged `shared` package; only httpx transport mocked. Script: scratchpad/rerun/rt/measure_mcp.py):
  read_indicator_observation, args.tenant_id=tenant-victim -> 200; GET raster /indicator-grid with X-Tenant-Id=tenant-victim and NO X-Agent-Token
  read_indicator_observation, args.tenant_id omitted     -> 422 "field_id and tenant_id are required"
  analyze_field_change, args.tenant_id=tenant-victim     -> GET raster /timeseries with X-Tenant-Id=tenant-victim, no token
  fetch_sentinel2_l2a field_01 (demo)                    -> 200; POST https://services.sentinel-hub.com/oauth/token, then /api/v1/process with fabricated bbox [45.5,15.0,45.6,15.1]
  fetch_sentinel2_l2a fld_real_123 (a real id)           -> 404 "Field … not found"
  Sources at base: services/mcp_servers/sentinel_hub_server.py:36-38 (SH_BASE_URL hard-coded to services.sentinel-hub.com), :63-129 (FIELD_REGISTRY field_01..08), :153-164 (get_field_bbox), :415-470 (tenant taken from args and forwarded).
fix (services/mcp_servers/sentinel_hub_server.py):
  - `_caller_tenant(user, args)` uses shared.security.trusted_tenant.resolve_trusted_tenant. The tenant comes from the JWT that require_scope already verified (the same verified-context pattern market_server uses via user["tenant_id"]). The argument may only echo it; otherwise 403 tenant_mismatch, returned before any outbound request. Tool schemas now mark tenant_id optional (echo only). The supervisor client already injects the caller's own tenant (services/supervisor-agent/mcp_client.py:41-43), so legitimate calls are unaffected.
  - `_raster_headers` sends X-Tenant-Id plus X-Agent-Token plus X-Service-Name. This is the service-credential pattern that weather_server._weather_service_headers already uses. If SAHOOL_AGENT_TOKEN is missing, the result is 503, not an unauthenticated claim.
  - FIELD_REGISTRY was removed. `get_field_bbox(field_id, tenant)` reads the field from its declared owner, field-management-service (GET /internal/fields/{id}). It uses the same contract as vegetation-analysis: X-Agent-Token, X-Service-Name=sentinel-hub-mcp, and an X-Tenant-Assertion from shared.security.service_tenant_assertion bound to method, path and X-Request-Id. The bbox comes from shared.gis.phase5_runtime.geometry_bbox. Error mapping: 404 → 404 (another tenant's field looks like a missing one); 401/403 → 502; other → 503; no geometry → 424; unconfigured → 503 field_source_unconfigured. There is no fabricated fallback anywhere. (idea from salvage: resolve via field-management-service; implementation re-derived)
  - CDSE: SH_TOKEN_URL/SH_BASE_URL use the same env names and defaults as the canonical services/raster-service/cdse_client.py (_TOKEN_URL/_BASE_URL). Credentials are CDSE_* then SH_*, as in raster `_cdse_credentials`; missing credentials give 503.
  - docker-compose.v9.yml: sentinel-hub-mcp gains SH_BASE_URL, SH_TOKEN_URL, SAHOOL_AGENT_TOKEN, FIELD_SERVICE_URL, FIELD_SERVICE_TENANT_ASSERTION_KEY and _ID. field-management FIELD_SERVICE_ALLOWED_CALLERS defaults to "vegetation-analysis-service,sentinel-hub-mcp".
after (same harness): victim argument → 403 tenant_mismatch with no outbound request · no argument → raster gets X-Tenant-Id=tenant-caller with the token set · field_01 → field-service 404 → 404, no provider call · real field → owner lookup with a verifiable assertion → identity.dataspace.copernicus.eu token, then sh.dataspace.copernicus.eu/api/v1/process with the owner's bbox [44.1,15.3,44.2,15.4].
tests: tests_v9/test_mcp_sentinel_tenant_and_cdse.py (16, unit). The assertion is verified with the same verify_tenant_assertion that field-management-service runs. CDSE defaults are parity-checked against the raster source.
falsification: S1 argument tenant wins → 2 red · S2 raster call without token → 2 red · S3 fabricated bbox for an unknown field → 2 red · S4 commercial token URL → 1 red · S5 assertion not bound to the path → 1 red. The whole file reverted to base gives 15 errors + 1 fail. Restored → 16/16.
limits:
  - fetch_sentinel2_l2a and fetch_sentinel1_grd still return only data_size_bytes. The S1 payload (polarization sent as a list, no evalscript) does not match the Process API, so S1 would be rejected upstream. Both are untouched and out of scope. The supervisor blocks these tools by default (BRAIN_DIRECT_SATELLITE_FETCH_ENABLED=false, services/supervisor-agent/skills/remote_sensing_skill.py:89).
  - docker-compose.fixed.yml, light.yml and unified.yml run sentinel-hub-mcp without SAHOOL_AGENT_TOKEN or field-service config. There, the read tools now answer 503 (explicit) where they used to forward an unauthenticated tenant. light and unified have no raster-service at all. Not changed (non-canonical stacks).
  - Railway: nothing indicates sentinel-hub-mcp is deployed. If it is, set SAHOOL_AGENT_TOKEN and FIELD_SERVICE_* on it, and add sentinel-hub-mcp to FIELD_SERVICE_ALLOWED_CALLERS on field-management-service.
brain row (proposed): SENTINEL-HUB-MCP-01 | P2 | status: fixed | sources: services/mcp_servers/sentinel_hub_server.py (_caller_tenant, _raster_headers, get_field_bbox, fetch_sentinel_hub_token, SH_TOKEN_URL/SH_BASE_URL) · docker-compose.v9.yml sahool-sentinel-hub-mcp + field-management FIELD_SERVICE_ALLOWED_CALLERS | evidence: before and after request captures above (in-process through the HTTP entry point, not a live deployment) · commit 7242461a.
blocker / decision needed: none for code. Operator config applies only if the MCP is deployed outside compose v9.

## POLICY-DOC FOLLOW-UP (belongs to the two raster gaps)
commit: 80d0b757
- docs/architecture/platform_extraction_map.json: seven compat_gateway line anchors shifted +12. This is a hand-maintained policy doc that `--fix` does not regenerate. The new values are the "current" values that test_platform_extraction_map_matches_full_route_surface itself reports.
- tests/architecture/test_router_size_ratchet.py: the raster routers/fields.py frozen size was lowered from 1712 to 1708, which is what the ratchet demands after tid emission was removed.
- Both tests were red on 94f2e520 and are green now.

## HELD PATHS
none. No file under agents/, shared/ or migrations/ was changed. shared/security/tenant_context.py (which holds the query-parameter fallback) now has ZERO importers. I left it untouched because it is a held path. Suggestion: delete it in a separate held commit.

## TESTS RUN (final tree 80d0b757)
- services/raster-service, run the way CI does (cd + PYTHONPATH=. pytest test_*.py): 343 passed, 2 skipped.
- services/sahool-platform/tests (full): 4441 passed.
- pytest -m unit (tests_v9, full): 7934 passed, 3 failed, 17 skipped. None of the 3 is caused by these changes:
    · test_api_versioning_policy_guard_inventory_is_current: STALE GENERATED artifact (api_versioning_inventory line numbers). Fixed by central regeneration.
    · test_generated_artifact_contract[duplicate_definition_guard]: STALE GENERATED artifact. python_files_parsed went 1917 → 1919 because of the two new test files; finding_count stays 0 (measured with build_payload, no write).
    · test_dockerfile_pip_mirror_guard: an ENVIRONMENT artifact. The guard skips every path containing ".claude", and this worktree lives under .claude/worktrees, so it finds 0 Dockerfiles. Unrelated.
- pytest tests/architecture tests/release: 533 passed, 14 failed. All are stale generated artifacts (route budget/ownership/governance attestation, route conflicts, router reachability, gateway reachability outputs, service inventory, execution dependency audit, capability mapping/roundtrip, release checksum), except brain_commit_claim (below).
- Targeted: tests_v9 raster/nginx/compose/helm/railway/env/gateway/tile/frontend subset 635 passed; MCP/supervisor subset 309 passed; tests/deploy 29 passed; post_execution_bridge 5 passed.
- services/supervisor-agent: 65 passed, 1 failed (test_graceful_degradation::test_circuit_open_returns_graceful_degraded). It is PRE-EXISTING: it fails identically on base 1cb6cd6c (git archive), and I did not touch this service.
- ruff check + ruff format --check (0.15.8) on every changed file: clean. bandit -r services/raster-service services/vegetation-analysis-service services/mcp_servers deploy/railway services/sahool-platform/api/routers/compat_gateway.py --severity-level high: no findings.
- compose_env_contract_gate OK; raster_main_decomposition_gate OK.
- preflight --fast: failures=1, skipped=0. The single failure is brain_commit_claim: the commit messages name RASTER-TENANT-TRUST-01, RASTER-COMPAT-PASSTHROUGH-01 and SENTINEL-HUB-MCP-01, and sahool-brain/gaps/registry.md has no "## <ID>" section for them yet. The COORDINATOR's brain rows satisfy it, since I am not allowed to edit sahool-brain/.
- NOT run: frontend/tests/test_nginx_runtime.py, which needs nginx ≥1.27.3 or --docker. Local nginx is 1.24 (no `resolve`) and the docker daemon is down. The same two raster blocks were exercised verbatim on nginx 1.24 by the scratch probe (see RASTER-TENANT-TRUST-01). The frontend image build (entrypoint envsubst template) was also not built. I only reviewed it against the nginx 1.27.5 entrypoint script source.
- Scratch harnesses (not committed): scratchpad/rerun/rt/{measure.py, live_two_identity.py, live_compat.py, nginx_raster_probe.py, measure_mcp.py, falsify_all.py, schema.sql}. The private PG16 cluster "rtrust" I created was stopped and dropped at the end. No processes other than my own PIDs were touched.

## DECLINED / OUT OF SCOPE (reported, not changed)
- docker-compose.fixed.yml with nginx/nginx.fixed.conf: `location /api/raster/ { proxy_pass http://raster_backend/; }` has no auth_request and no header stripping. That makes it a public cross-tenant path while raster stays in observe there. The file is a non-canonical historical variant; enabling enforcement there would 401 all of its tiles. This is an owner decision.
- frontend/nginx.conf `^~ /api/vegetation/` (and indicators/weather/agent/guardrails/segmentation dev locations) forward the client's X-Tenant-Id as-is. vegetation-analysis trusts X-Tenant-Id on some routes. This is the same class of bug in a different service and was not audited here.
- Tenant tiles are served with `Cache-Control: public, max-age=3600` (fields.py and cdse_tiles.py). A shared cache in front of the gateway would bypass auth. There is none in the repo configs today.
- Platform-emitted thumbnail URLs still append `&tid=` (api/routers/fields.py:877, field_workspace_imagery.py:141). The parameter is inert now; removing it is left as a follow-up.
- sentinel_hub/vegetation_real.py: a legacy facade that is not deployed. It sends the token only if INTERNAL_SERVICE_TOKEN is set.
