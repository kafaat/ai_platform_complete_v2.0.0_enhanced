# Re-run of 6 salvaged agents (owner-approved plan step 3) — started 2026-09-30 ~09:15Z
Base: main bcb7f0ed. Briefs: rerun/<name>.full.md (original brief + PROTOCOL.md). Reports: rerun/<name>.report.md
Wave 1 (launched): governance (salvage fa622cbd) · ratchets (9657f93a) · data_path (3116b861)
Wave 2 (pending wave 1): raster_trust (5113d330) · env_drift (3ee89ce4) · nats (7fb7633b, all held paths)
Failure rule: report missing or still "STATUS: RUNNING" after the agent's completion notice (or after a
container restart) = FAILED run, explicitly. Re-launch that one from its brief; never treat as silence.
Integration per agent: cherry-pick its commits onto fresh main in genwt, review code myself, apply brain text
centrally with final SHAs, regenerate cleanly (bundle last), full preflight, one PR each, merge on green.
Commits touching agents/** shared/** migrations/** held until owner decides queue_v1.

## Owner rule (2026-09-30 ~09:25Z) — recreation vs restart
Local commit + on-disk report survives a RESTART, not a RECREATION. Accepted for now (3 restarts, 0 recreations).
If a recreation happens even ONCE in this round: runs are LOST (say so explicitly — not "undetected"), and
durability is re-evaluated → push agent commits to named remote branches (needs owner naming/permission).
Detection lives in the server-side watchdog prompt (trig_016iYtbp5zLf8ikW6rwFqgMX (hourly, recurring — replaced the one-shot chain)), since recreation erases this file.
Watchdog kill-set (owner definition 2026-09-30): only session archive or trigger delete/disable. If a recreation is found
without the watchdog reporting it ⇒ first question: "what killed the watchdog?". Rebuild after recreation = START OVER from
original task, no WIP/salvage reference (salvage SHAs are local too).

## Wave 1 results (2026-09-30 ~10:00Z)
- data_path: STATUS COMPLETE · 4 commits 10b4aaa6 7c0bb88b 82dca782 a9f813d9 · reviewed OK (41 read sites of now-Optional weather fields checked; evidence collector exclusion = catalogue's blocking predicate, published) · cherry-picked in genwt as 0ee85f68 01324584 288c134b a479020d · regen running · PR 1 of wave.
- governance: STATUS COMPLETE · 7 commits e0b80d1f 5e585916 874b0d61 9eee8d9c 9f6c3f01 39abd57e 32a275de · reviewed OK (verify_all_generated --check attribution only; preflight tail summary; reachability shrink-only list) · no overlap with data_path · PR 2 of wave (needs GUARD_CATALOGUE regen).
- ratchets: still running.
- ratchets: STATUS COMPLETE · commits 2bc313ac 428556ab 0586567b(HELD shared/security) 4df3336b(needs 0586567b ⇒ HELD) 8e0676d3 · ROUTER-SIZE = owner decision.
  Non-held PR candidate: 2bc313ac + 428556ab + 8e0676d3 (frontend/** ⇒ sahool-frontend Railway redeploy, normal).
  JWT pair: deep review before merge — stricter exp/sub/aud/iss on auth/guardrails (Railway-deployed) could reject live staging tokens; unexplained supervisor test_circuit_open_returns_graceful_degraded must be checked on base.
## Wave 2 launched ~10:05Z: raster_trust · env_drift · nats (base = main 1cb6cd6c). Watchdog trig_016iYtbp5zLf8ikW6rwFqgMX covers it.
Integration queue (one branch): data_path → governance → ratchets(non-held) → wave 2 as they finish.
- 10:30Z: supervisor test_graceful_degradation.py::test_circuit_open_returns_graceful_degraded FAILS ON MAIN 1cb6cd6c too
  ⇒ pre-existing, NOT caused by the JWT decoder (0586567b/4df3336b). Remaining JWT concern = stricter aud/iss/exp/sub on Railway-deployed auth/guardrails.
- governance slice prepared in scratchpad/genwt2 (cherry-picked 7 commits on 1cb6cd6c; regen running). data_path preflight running in genwt.
- env_drift: STATUS COMPLETE (base 1cb6cd6c) · non-held: b49c7d61 da1eaae6 00361b00 0d83fa65 5a4413c2 c86cba4a · HELD: ce67bca1 (shared/gis/cog_tile_proxy.py, independent — skip in cherry-pick).
  Reviewed: ${REDIS_PASSWORD:?} safe in CI (Validate Docker Compose writes dummy env for all :? vars). raster_security_context/tiles ⇒ raster ×2 Railway redeploy (normal).
  Owner decisions surfaced: edge /readyz partial=200 degraded · RAG/agronomist probe /healthz by design (gateway waits) · tiler in fixed/unified unbuildable · refuse URL-unsafe Redis password at start?
Integration queue: data_path (preflight #2 running) → governance (genwt2 regen) → ratchets non-held (2bc313ac 428556ab 8e0676d3) → env_drift non-held → raster_trust/nats when done.
- raster_trust: STATUS COMPLETE (base 1cb6cd6c) · 0840d46e 94f2e520 7242461a 80d0b757 · no held paths · REAL cross-tenant leak measured live (forged X-Tenant-Id / ?tid / ?tenant_id ⇒ tenant A's bounds+tile to B).
  Default code mode = observe (enforce needs RASTER_TENANT_CREDENTIAL_ENFORCE=1 + frontend SAHOOL_AGENT_TOKEN — operator steps, owner).
  OVERLAPS: env_drift (.env.example, docker-compose.v9.yml, raster_security_context.py) + data_path (platform_extraction_map.json — HAND anchors, resolve carefully).
  MUST VERIFY before merge: ?tid ignored in ALL modes ⇒ any Railway path relying on ?tid only would 404 tiles post-merge. Confirm Railway frontend (render_frontend.py) routes /api/raster/ with auth_request-derived X-Tenant-Id; thumbnails via platform send header.
  Surfaced for owner: fixed.yml /api/raster/ no auth · frontend /api/vegetation/ forwards client X-Tenant-Id (same class!) · tenant tiles Cache-Control public · MCP S1 payload vs Process API.
- nats: still running.
- nats: STATUS COMPLETE (base 1cb6cd6c) · single commit 96f6a034 · no held paths claimed — VERIFY at integration: no agents/ shared/ migrations/, no GATE-01 frozen file (phase_runtime_workers.py etc.). Touches vegetation_runtime.py (Railway vegetation redeploy), platform api/main.py, notification-rollout.yml, docker-compose.v9.yml (10 NATS pw :? — CI dummy env ok).
  Owner decisions: path3-runtime-verification.yml secrets (credential provisioning) · 2 new open rows (env-parsed password, silent refusal in frozen workers) · Railway rollout plan in report (broker volume check first!).
## ALL SIX RE-RUNS HANDED BACK (no failed run). Watchdog stays on: un-pushed integration work lives only locally.

## Owner notes 2026-09-30 ~11:35Z → go into the next brain commit (log/ledger), measured:
1. WATCHDOG STABILITY (measurement, not news): 11:27Z hourly watchdog fired · no recreation · scratchpad present · 12 worktrees · all six reports COMPLETE. First real stability signal of the session.
2. OBSERVE→ENFORCE gate (owner: "pick one") — CHOSEN: TEMPORAL with receipt exit. Targeted test fails after due date (merge+7d)
   unless certification/evidence/raster_tenant_enforce_*.json exists (readyz mode=enforce + reviewed counters). Row stays
   "open — observing" (NOT fixed) until receipt. Precedent: gate01_policy.json decision_due_on re-block. Implement in raster slice.
3. TENANT-CLAIM TRUST = ONE CLASS ("who is trusted to state the tenant?") — inventory measured on main 1cb6cd6c:
   fixed/light/unified gateways: 14+9+18 = 41 locations, none clears or sets X-Tenant-Id, none includes proxy_params ⇒ client header passes unchanged.
   frontend/nginx.conf: 23 locations, 13 set tenant, 0 include proxy_params (which clears) ⇒ up to 10 may forward client value.
   nginx.v9.conf: 41 locations, 31 include proxy_params (clears), 12 set. 18 service dirs read X-Tenant-Id.
   ⇒ rule needs per-location classification (inventory), not 4 decisions. One class row.
4. MANUAL LINE ANCHORS (record only): ≈1,345 hand-maintained anchors — platform_extraction_map 637 + capability-registry domain yamls ~670
   + threshold_authority_ledger 22 + env_compose_drift_allowlist 16 (pattern-measured; capabilities.json 683 & tenant_guc baseline are regenerated ⇒ excluded).
   Same class as M4: guard catches drift, doesn't prevent it. Measure before next batch.

## Owner research #4 (2026-09-30 ~11:45Z) — adoption decisions (measured where possible)
- Measured: guard_mutation_guard.py:203-211 requires the mutation `find` to occur EXACTLY ONCE (static) ⇒ every plant changes the file;
  :572 proves restoration by content. Owner's "prove the plant landed" precondition already holds there (stronger than hash).
  Residual: find==replace unchecked (trivial). Does NOT cover ad-hoc falsification by agents / live plants.
- Measured: set_config inside DB definitions = exactly 1 (v9_foundation.sql:140, set_tenant_context). No function has a `SET param` config clause. ⇒ DB-side GUC inventory closed at 1, already in the SECURITY-DEFINER row.
- ADOPT in raster slice: flag metadata for RASTER_TENANT_CREDENTIAL_ENFORCE (owner, safe_value, expires, runbook, health_signals) + temporal test reads `expires`, exit = receipt. + 7 pre-enforce drills as runbook checklist (esp. re-enable after rollback).
- ADOPT as rule (separate slice, not now): gateway strips every inbound x-tenant-* then sets verified value (OWASP). CAUTION nginx: proxy_set_header at server level is NOT inherited by a location that sets any proxy_set_header ⇒ must be per-location include (as v9 proxy_params). 41 locations in fixed/light/unified + frontend's unset ones.
- ADOPT in SECURITY-DEFINER row: 4th hardening item = honest volatility; PG17 expression-index/matview functions need own search_path (upgrade prep); ORDER = upgrade 15.19 first, then ownership hardening (CVE-2026-14666 stale plans).
- RECORD (future): NATS decentralized operator→account→user is the multi-tenant endgame; 10 static users in nats.conf is correct single-server step.
- NOT ADOPTED until verified: rlsgrid · testguard-cli · pgrls 57 rules/Z3 — unverified by me; any dependency needs inspection + pip-audit first.
- METRIC to start: per guard "last red on something we did not plant" — currently 0 known; accumulate, not a one-off test.

## Owner refinements (2026-09-30 ~11:55Z) — measured
- RECEIPT must bind itself (a committed file only proves it was committed). Measured: sahool-raster-service on Railway staging has NO public domain (serviceDomains []) ⇒ CI cannot fetch /readyz. So: receipt = raw /readyz JSON + raw /runtime-identity JSON (sha must be a main commit containing the enforce code, timestamp ≥ merge) + Railway deployment id; test checks internal consistency. Two-party: operator flips flag; Claude reads deploy logs read-only as second party. Limit stated: still writer-reported; binding defeats stale/copied receipts, not a malicious writer.
- TENANT INVENTORY needs a REACHABILITY column (topology, not raw counts): per bundle × service reading X-Tenant-Id → reachable without passing a clearing gateway? (published port / non-clearing location). Do in the gateway-rule slice.
- ANCHORS: capability-registry domain YAML route anchors (`METHOD path @ file:line`): 649 total · 303 exact · 273 MOVED · 73 not in route inventory ⇒ 53% wrong/orphaned, NOTHING checks them (only 2 tests read these YAMLs; no scripts/ci consumer). Fully derivable from route_inventory.generated.json (METHOD+path+file). Fix = remove, not maintain: drop the line (identity suffices) or generate it. platform_extraction_map 637 are guard-derivable too (collect_surface computed them).
- 12:59Z governance = PR #1110 (head e55b8cda). Lesson: brain commit messages must name gap IDs IN FULL (brain_commit_claim rejects "…" abbreviations). data_path = PR #1109 merged 559b177e.

## Owner research #5 (2026-09-30 ~14:50Z) — measured (Railway read-only + Docker Hub registry), adoption
- PG image on Railway: postgis/postgis:15-3.4 (custom ⇒ Railway one-click pg_upgrade N/A — docs confirm feature exists; applies to Railway images). Volume 50GB /var/lib/postgresql/data.
- Registry-measured tag contents: 15-3.4 = PG 15.8/PostGIS 3.4.3 (Debian bullseye, last pushed 2024-10-14 ⇒ why we're on 15.8);
  15-3.5 = PG **15.13** (NOT 15.19 — owner's suggested tag does not reach the fix); 15-3.5-alpine = PG 15.19/PostGIS 3.5.7 (musl ⇒ collation risk on glibc-built text indexes);
  16-3.5 = 16.9, 17-3.5 = 17.5 (Debian postgis tags stale). Official postgres:15.19-bookworm exists (2026-09-19, glibc).
  ⇒ lowest-risk path: tiny Dockerfile FROM postgres:15.19-bookworm + apt postgresql-15-postgis-3 (glibc 2.31→2.36, no 2.28-class collation break), then ALTER EXTENSION postgis UPDATE. Alternative 15-3.5-alpine requires REINDEX of every non-C-collation text index (or datcollate=C measured first).
  Pre-switch read-only SQL (needs owner/operator): datcollate/datctype/datlocprovider · pg_extension versions · pg_prepared_xacts · md5 in pg_authid · pg_replication_slots · disk free. Migrations create: postgis, pgcrypto, btree_gist (uuid-ossp only in legacy init_v8).
  Downtime: volume-backed service ⇒ Railway cannot overlap deploys ⇒ brief downtime is unavoidable (Railway docs) — owner's "no downtime window" is incorrect.
- NATS: volume /data present (50GB), start `nats-server -js -sd /data/jetstream`, 0 variables (no auth, confirmed), stock nats:2-alpine, no config file ⇒ per-service authz on Railway needs a baked config (custom image or start-command-generated). No external/browser NATS client in frontend/mobile ⇒ WS restricted-user layer not needed now.
- Migrator: ENTRYPOINT at runtime (not build) ⇒ build-phase private-network limit does not apply.
- Healthchecks: raster + platform healthcheckPath=/readyz. Railway docs: healthcheck = deploy-time gate (old deploy keeps serving if new fails); not a liveness restarter ⇒ /readyz is correct for Railway; owner's "/healthz for Railway" would let a deploy with a dead DB go live.
- Raster enforce flip: raster has a volume (/data/rasters) ⇒ no overlap; in-flight pre-cutoff requests finish or abort in the old container's graceful shutdown; no worker re-admission path (stateless reads; tile cache keyed by asserted tenant holds that tenant's own data). ADOPT disposition vocabulary in receipt: {claim_id, deadline, disposition ∈ STOPPED|DEFERRED|READ_ONLY|ESCALATED|IN_FLIGHT_UNRESOLVED, applied_at, owner, admitted_before_cutoff (from observe counters), terminal_or_unresolved} + default state if nobody acts = test RED (fail-closed).
- Anchors: correction — platform_extraction_map 637 are guard-enforced (0 drift at HEAD by construction); YAML capability anchors 346/649 wrong (measured); owner's "~900 wrong" projection not applicable. Adopt "name the symbol, derive the line"; linecite NOT adopted (unverified).
- JWT held pair: the risk is stricter claim checks (aud/iss/sub/exp), not key rotation ⇒ dual-key pattern doesn't address it; analog = observe-mode counter of tokens that would fail new checks, then enforce.
- Tenant strip: adopt "all paths incl. those skipping tenant resolution"; empty-string proxy_set_header per location or shared include.
- Self-expiring gate: pattern already exists (gate01 decision_due_on); no new general meta-gate (owner rule).

## Owner research #6 (2026-09-30 ~15:05Z) — mostly repeats #5; new items measured in repo
- Repeats already refuted by measurement (#5): 15-3.5 = PG 15.13 (not 15.19); NATS volume /data exists; no external/browser NATS client ⇒ WS layer not needed.
- 15.19 extra steps, measured: ltree = not used anywhere · btree_gist used once (v205 EXCLUDE on tenant_id, resource_node_id, range) — no float4/float8/bit ⇒ no btree_gist reindex · pgcrypto: gen_random_uuid ×193, digest ×15, hmac ×1; no raw encrypt/decrypt, no bf/cast5/cipher-algo ⇒ CVE-2026-14663 N/A · no CREATE OPERATOR ⇒ CVE-2026-2004 N/A · no CREATE EVENT TRIGGER (fn_update_calibration_evidence is a FOR EACH ROW trigger, v86:103).
- PostGIS order: pre-swap postgis_extensions_upgrade() on 15-3.4 is a no-op (image ships 3.4.3 = installed, to verify live); post-swap postgis_extensions_upgrade() required. Keep both (cheap).
- Traefik: not used anywhere in repo (0 files) ⇒ CVE-2026-54765/88004 N/A. Our gateways are nginx with default proxy_request_buffering (no `off` anywhere) ⇒ request body buffered and re-sent with Content-Length, request trailers not forwarded (code-read, not live-tested). Railway edge proxy is outside our control.
- Vacuous-in-direction guards (Orleans #2656): ADOPT for wave-2 fault planting — each guard gets ≥2 mutants: a wrong non-degenerate value AND the degenerate value (0/absent/empty) that the original defect produced. The "113 unplanted" count is not revised (it counts guards with no mutant); guards whose existing mutant misses the degenerate direction are an additional, unmeasured set.
- Anchors: YAML 346/649 wrong was MEASURED (not "~440 likely"); map 637 guard-enforced.
- NATS operator/account JWT = end-state architecture; nats.conf per-service users = today's single-server fix. No change.

## Owner research #7 (2026-09-30 ~15:20Z) — measured; candidate brain rows (to register in a brain batch, not in env_drift PR)
- Qdrant (v1.17.1 in v9; NOT on Railway): tenant isolation is server-side (production_qdrant.py:1153 `metadata.tenant_id match any [tenant, GLOBAL]` inside the search filter) ⇒ correct. GAP (perf, not isolation): no payload index at all on metadata.tenant_id (ensure_collection :1101-1128 creates vectors only; no is_tenant/keyword index). Candidate row QDRANT-TENANT-FILTER-HAS-NO-PAYLOAD-INDEX-01.
- Ollama: not on Railway. v9 = ollama 0.32.5 pinned by digest, sahool-internal only, no host port; fixed = 0.30.8 internal; unified = **0.3.0** bound 127.0.0.1 (ancient pin). CVE-2026-7482 fixed-version UNVERIFIED (OSV + NVD blocked by egress policy). Candidate row: unified ollama 0.3.0 pin. GGUF→safetensors: Ollama consumes GGUF by design — not an adoptable switch; digest-pinning of model artifacts exists for edge (EDGE digest contract), not for Ollama pulls (sahool-ollama-models) — to measure.
- Redis: no ACL anywhere (0 matches); one shared requirepass ⇒ any client can FLUSHALL. Candidate row (owner decision: per-service ACL users).
- gRPC: 0 usages (no grpcio, no insecure_channel) ⇒ N/A.
- MQTT (mosquitto 2.0.22, v9 only, NOT on Railway): allow_anonymous false + password_file, internal network, single shared user, no TLS on 1883, no ACL (comment says ACL if exposed). Low priority.
- Backups: scripts + runbook exist (docs/runbooks/POSTGRES_RECOVERY.md); runbook itself states RPO/RTO NOT_MEASURED and no live restore drill (:5-6, :81-88). Railway volume backup schedule for sahool-postgres: not visible via read-only API ⇒ UNKNOWN. Candidate row: POSTGRES-RESTORE-NEVER-DRILLED-RTO-UNMEASURED-01 (check vs SUP-11/CP997-03 overlap).
- Rate limiting: **frontend/nginx.conf (the Railway gateway) has 0 limit_req** vs nginx.v9.conf 32 ⇒ Railway public edge has no gateway rate limit (app-level limits exist in some platform routers). Candidate row RAILWAY-GATEWAY-HAS-NO-RATE-LIMIT-01. Highest-value finding of #7.
- IaC: Railway config not in code (only services/auth/railway.json) ⇒ Railway changes unreviewed/undiffable. Candidate row (owner decision).
- K8s/helm: NetworkPolicy + runAsNonRoot present in helm; not deployed ⇒ entry conditions noted, no action.

## Railway docs agent (2026-09-30 ~15:45Z) — report scratchpad/research/railway_docs.md; cross-checked in repo
- CORRECTION to research #5 note: RAILWAY_DEPLOYMENT_DRAINING_SECONDS default 0 (SIGTERM→SIGKILL immediate) and no service sets it (grep 0) ⇒ at the raster enforce flip, in-flight pre-cutoff requests are ABORTED (disposition STOPPED; client retry is evaluated under enforce), not "finished during graceful shutdown".
- railway.json: only services/auth/railway.json (build builder+dockerfilePath) ⇒ config-as-code stops being read 2026-12-01; verify auth service settings carry the same in Railway before then.
- No TrustedHostMiddleware anywhere ⇒ healthcheck.railway.app host is not a risk.
- Custom PostGIS image: PITR/HA/one-click major upgrade N/A (docs); volume backups DO work for any volume (daily 6d/weekly 27d/monthly 89d; restore = new volume, staged) — schedule state for sahool-postgres unknown via read-only MCP.
- Safest live-test vehicle: `railway sandbox create --private-network` (VM beside services, not inside); strongest read-only signals: `railway metrics --http`, `railway logs --http/--network/--dns`, tracing.
## Community agent (~15:55Z) — report scratchpad/research/railway_community.md (egress blocked most forums ⇒ mostly snippets; GitHub fetched). Cross-checked:
- nginx stale-IP pitfall: ALREADY HANDLED — nginx 1.27.5, every upstream `server … resolve` + zone; Railway renderer deploy/railway/render_frontend.py:104-164 replaces Docker resolver with /etc/resolv.conf nameservers, valid=10s (auth_request upstream frontend_auth included). ipv6=off default (SAHOOL_DNS_IPV6) — OK only in dual-stack env; live traffic works ⇒ consistent with dual-stack.
- uvicorn --host 0.0.0.0 (2 Dockerfiles; raster startCommand too) — works live ⇒ env is dual-stack (post-2025-10-16) — to confirm env creation date.
- Worth adopting: redeploy-survival test (marker write → redeploy → read) for Postgres/NATS/Redis volumes; PGDATA subdir check (PGDATA var exists on sahool-postgres — value not read); image auto-update check + digest pin for postgis (tag 15-3.4 frozen since 2024 so re-pull is same digest, but pin anyway); ON_FAILURE ignores exit 0.
## Live-map agent (~16:05Z) — scratchpad/research/railway_live_map.md. VERIFIED by me (read-only):
- PRODUCTION auto-deploys from main, checkSuites:false (frontend, raster confirmed) ⇒ every merge to main ships to production with no CI wait. My earlier PR notes said "redeploys sahool-frontend" without saying production — correct going forward.
- sahool-platform: staging branch deploy/sahool-platform-db-ready-eb6da9df (4 behind in platform paths), production deploy/sahool-staging-fa92a1f7 (24 behind); BOTH pin PyJWT==2.13.0 while main has 2.14.0 (CVE-2026-102274) ⇒ live platform runs the unpatched PyJWT.
- staging decision-service latest SUCCESS = eff473aa (#1080, 2026-09-28 redeploy) ⇒ lacks #1085 (7059d0dc) + #1086 (63727907, canonical tenant boundary across legacy RLS).
- Agent-reported (not re-verified): prod migrate-main build failed (railpack), no success in last 50; prod frontend resolver noise for 4 absent upstreams; leftover services (wc005 proof in prod, platform-db-proof, sahool-migrate europe-west4, raster-main-candidate, redis-state-0zaK, legacy prod sahool-auth); tracing off everywhere; no webhooks; images tag-pinned w/o digest.

## Owner decisions 2026-09-30 ~16:20Z (gate production first) — executed / blocked
- DONE (Railway, config-only, no redeploy; pendingWork=[] verified): prod healthcheckPath /healthz→/readyz on sahool-platform, sahool-auth-main, sahool-auth (all three have /readyz in their deployed branches). drainingSeconds=20 on platform+auth-main (prod+staging), auth (prod), frontend, raster, decision, guardrails, field, vegetation, tts, notification (all envs). Previous values: healthcheck /healthz, draining default 0 (rollback = set back).
- NOT DONE — frontend healthcheck: its /readyz proxies to platform /readyz ⇒ would couple frontend deploys to platform readiness; kept /healthz pending owner's explicit choice.
- BLOCKED (no tool): checkSuites/Wait-for-CI (source/trigger setting; connect-service-source would rebuild all envs) and volume backup (no MCP tool); railway-agent = "Agent usage limit reached". ⇒ owner does both in dashboard. Main push CI green on last 2 commits (32/32, 28/28) ⇒ Wait-for-CI won't silently block.
- Webhook: needs a destination URL from owner.
- Flag question: raster reads RASTER_TENANT_CREDENTIAL_ENFORCE per call (raster_security_context.py:70-72 os.getenv) but Railway injects vars only at container start ⇒ flip = new deployment; the cut comes from the deploy. With drain now 20s: old container finishes in-flight observe-mode requests (terminal) within 20s; volume ⇒ no overlap ⇒ brief gap where edge errors ⇒ client retry evaluated under enforce.
- RLM: registry has exactly 72 U+200F (0 override/isolate). `--generate` rewrites baseline from current counts ⇒ nothing prevents 72→74 except review (owner's point confirmed; M4 class). None of the 72 are semantically required. Candidate: targeted test that baseline per-file counts never exceed the previous committed baseline; stripping historical marks may conflict with brain_append_only — owner decision.

## Owner message ~17:00Z responds to a report NOT from this session/repo (measured: retention_runs/v_retention_last_success/intermodal/MIGRATE_ONLY = 0 files; hermes only npm hermes-parser; no db/ dir; no "8h restore" claim). Transferable, measured here:
- Railway cron services: none (all cronSchedule null) ⇒ cron-skip N/A on Railway; 2 scheduled GH workflows.
- Skipped-reads-green: REAL here — docker-build-matrix-verifier.yml:58 `docker-build` runs only on workflow_dispatch; sahool-production-gates.yml:195 `runtime-stack-e2e-chaos` only on dispatch+var ⇒ both "skipped" on every PR (seen on #1112) and read as passing; with prod checkSuites:false nothing builds the Dockerfiles before Railway builds them in production. Candidate row DOCKER-BUILD-VERIFIED-ONLY-ON-MANUAL-DISPATCH-SKIP-READS-GREEN-01.
- Exec-form env prefix: 0 in Dockerfiles.
- overlapSeconds (Railway tool doc): old deployment keeps serving N s after new is healthy; drainingSeconds: SIGTERM→SIGKILL. Only consumer service = notification-agent ⇒ overlap there = two consumers (queue_v1 problem) ⇒ not set.
- Staging public domain EXISTS: sahool-frontend-staging.up.railway.app (only way to reach staging) ⇒ owner decision, not deleted.
- PR envs on migrations/** (our path): transferable; needs dashboard + proof that migrate-main's PG*/DATABASE_URL are ${{}} references (values unreadable by rule) else PR migrator writes prod DB.

## Builder survey (~17:30Z) — research/railway_builder_survey.md (28 deployments, read-only). Spot-checked 600fa8bb (read full build log) + 90e48979 (list-deployments: FAILED redeploy 12:40Z).
- Class RAILWAY-BUILT-WITH-RAILPACK-DESPITE-DOCKERFILE-CONFIG-01: ONLY sahool-migrate-main, both envs, the 2026-09-28 12:40Z redeploys; all other services (same wave included) built with their Dockerfile. RAILWAY_DOCKERFILE_PATH name is NOT the discriminator (present on all but decision). Cause inferred not proven (effective build config at redeploy time). Prod: no live successful migrate deployment; later commits SKIPPED by watch patterns.
- Part A: regen b38f6a05 clean, 0 watched paths, preflight (clean copy — old run ended before it) running.
- Owner decisions ~17:10Z: part D falsifier (plan must cover touched Dockerfiles) ADDED (10 tests, matcher-break ⇒ 4 red); SAHOOL_DEBUG startup log line → core/prod_readiness.py (main.py at 2553/2553 ceiling), part C; webhook: declined public third-party endpoint (leak) — need owner-owned URL; Railway emails on crash exist.

## #1114 CI (~17:00Z): 2 red
- gitleaks-full-history: THIS PR — tests_v9/test_redis_password_wiring.py:33 literal hex password (generic-api-key) in commit 96bc99ac. Fixed by rewriting the chain (literal → bytes(range(0x10,0x20)).hex()); literal absent from whole PR range; 73/73 pass. New chain e3c0aa81 0bc725e6 3e842870 3671e97c fc771ad5 + brain 420d8339.
- Security Scan: NOT this PR — new advisory CVE-2026-101918 on pyjwt 2.14.0 (fix 2.15.0), red on main too. Reproduced locally with CI's flags; PyJWT==2.15.0 ⇒ "No known vulnerabilities found". Only pin: services/sahool-platform/api/requirements.txt (lock file generated). Ported into #1114 as commit e184955d — deploys nowhere (platform on deploy/* branches in both envs). Regen + clean-copy preflight bko6ftisd running.
- Also measured: decision /readyz and tts /readyz always 200 (row READYZ-RETURNS-200-WHEN-IT-REPORTS-NOT-READY-01 in slice C); main migrator has NO ledger (replays MANIFEST) ⇒ MIGRATION-STATE-IN-PRODUCTION-IS-UNREAD-01; email alerts opt-in (checklist page).

## Owner's local audit (2 rounds) — citations resolved on origin/main (~17:40Z)
SHAs 3be88ec4 / 0f6c5809 NOT in repo; audit-reports/ and docs/audits/2026-09-30/ NOT in repo ⇒ frame unverifiable; citations resolved:
- §3.6 CONFIRMED farms.py:139-160 list_farm_fields: no ownership check, SQL has no tenant_id filter (RLS only); farms.py untouched since db8a570d (#1099 did not touch it).
- §3.10 CONFIRMED live_full_e2e.py:100-102,194 area_degrees2(.get) + root: field_geometry_history.geometry JSONB (v96:5) with no jsonb codec in platform ⇒ API returns geometry as JSON string (fields.py:1524 handler returns r["geometry"] raw).
- §3.1 CONFIRMED ai_evidence_runtime.py:950-959 suppression overwrite + generation_model = gen.model even when suppressed.
- §3.9 CONFIRMED raster_pixel_processing.py:142,272,814 all raise raw_raster_no_valid_pixels (behaviour/cause needs re-measure).
- §3.4 PARTLY: erp-bridge (services/odoo-bridge) no profile, depends_on sahool-odoo required:false, odoo profile [odoo] — CONFIRMED; but "/readyz reports ready while ERP dead" is DOCUMENTED DESIGN (routers/health.py:8-12: /readyz internal DB only; /v1/readyz/capabilities reports ERP state) ⇒ issue is profile/default-run, not a lying readyz.
- §3.5 CONFIRMED VLLM_BASE_URL default sahool-vllm-jais (profile vllm) on ai-agronomist + platform; +3rd member NOT in report: field-segmentation → sahool-sam2-inference (profile gpu).
- §3.7 CONFIRMED sam2-models/ only README/.gitkeep/.gitignore; no download step (by design, operator bind mount).
- §3.8 CONFIRMED edge Dockerfile.arm64 mkdir /models (named volume edge-models) no provisioning; video-processor main.py:186-187 edge ok = /healthz 200 only.
- §3.3 no file:line ⇒ not admitted. Behavioural items (SAM2 live, RAG 0 hits, payload parity) measured on drifted local copy ⇒ need re-measure on main/prod.

## #1114 MERGED ~17:52Z squash b0c14b6d (mergeable_state clean; 0 failures). Prod list-deployments: all 8 latest = SKIPPED @ b0c14b6d (watch patterns) ⇒ "no production deploy" MEASURED.
- Slice D rebased: 6fdb4f25 code + 87ef01ec brain (genwt3); regen running.
- Slice C code in genwt2 (on 166bdebf): ec9ad34e guard · 8b734cc3 SAHOOL_DEBUG log · be317c60 evidence; brain_c.py now argv root G L.
- Audit slice in genwt4 (on 166bdebf): bdfeeff6 §3.6 farms 404 (4/4 falsified) · f961178a §3.10 ROOT CAUSE IN API (history JSONB as string; frontend toTurfFeature drops all revisions) + harness named step (2/2) · a80ab98f §3.1 attempted vs surfaced attribution (7/7). brain_audit.py: 4 rows incl. LOCAL-AUDIT-REPORT-PINNED-TO-SHAS-NOT-IN-REPOSITORY-01.

## Owner-pasted CI log (~18:10Z): Playwright install failed 17:53–17:58Z (after #1114 merge; not from its content)
- Measured from the log: attempt1 timed out (azure mirror ~100KB/s); apt-get (pid 2655) SURVIVED timeout (Get:16–20 after the timeout line) holding dpkg lock ⇒ attempts 2,3 failed in ~3s each on the lock (not retries). Mirror "switched" message printed, next update still azure: runner uses mirror+file:/etc/apt/apt-mirrors.txt; sed -i rc=0 without substitution ⇒ vacuous claim. Final message "exceeded timeout 3 times" false for 2 of 3.
- Fix genwt5 c7b96d82 (on b0c14b6d): wait_for_apt_idle (no kill) + apt-mirrors.txt first + claim only if host present + per-attempt outcomes. Old test faked sed + fake source line absent on runners. Falsified 4/4 red on main scripts; 19/19 green. Gaps: PLAYWRIGHT-RETRY-FAILS-ON-ORPHANED-APT-LOCK-01 · APT-MIRROR-SWITCH-CLAIMED-WITHOUT-SUBSTITUTION-01 (brain rows pending). Slice after D.

## Independent review of owner's audit (~18:25Z), pinned 166bdebf (resolves; cites file:line) — verified on origin/main b0c14b6d
- F02 CONFIRMED + class 3 members: v9:1398 (was 1393) · fixed:683 · services/raster-service/Dockerfile:52 (Railway-built, raster deploys from main ⇒ held to gate). Measured httpx 0.28.1: 200/503/500/404 all exit 0. urllib members fine (raise HTTPError).
- F03 CONFIRMED: production.yml:22-27 vegetation-analysis-service / sahool-raster not in base (base: sahool-vegetation-analysis:1083 · sahool-raster-service:1311). PLUS: ci.yml:596 SKIPS production.yml as overlay ⇒ merged pair never validated (skipped-reads-green).
- F05 CONFIRMED + worse: e2e_field_imagery_ai.sh asserts mode=='evidence_only' ⇒ REJECTS validated_field_facts positive path; accepts failed audit. Runs only in runtime-stack-e2e-chaos (dispatch-only ⇒ skipped on every PR).
- F08 CONFIRMED agriai-engine/main.py:67-91 readyz 200 with ready=false ⇒ member of READYZ-RETURNS-200-WHEN-IT-REPORTS-NOT-READY-01 (slice C row; decision/tts).
- F10 CONFIRMED Makefile:49 `|| true`; live_full_e2e.py:129-130 SKIPPED ⇒ 0 unless REQUIRE_LIVE_E2E=1.
- SAM2_REF=main CONFIRMED sam2-inference/Dockerfile:41.
- F09 auth half ALREADY FIXED in #1114 (b0c14b6d) after the review's ref.
- F04 consistent with a80ab98f (attribution only; suppression untouched). F06/F07/F11/F12 = acceptance/evidence (rows, not code).

## F02 production measurement (~18:45Z, read-only) — owner: "measure before deciding the Dockerfile"
- prod sahool-raster-service 475f79b4: online, active deploy 7cecbf00 SUCCESS 05:20Z, replicas 1/1, 0 crashes/0 failures/0 warnings in 24h, pendingWork=[].
- Railway readiness = healthcheckPath=/readyz (timeout 300, drain 20); docs: activation requires any 2xx at deploy time only; docs describe no role for Dockerfile HEALTHCHECK (not proven ignored, not proven used).
- /healthz code = unconditional {"status":"ok"} (routers/observability.py:33-35) ⇒ 200 whenever serving; fix can only flip on 404/5xx from a non-serving/misrouted process.
- NOT measurable directly: no service domain; gateway /api/raster/ is behind auth_request (no creds used); uvicorn access logs absent in deploy logs.
- Decision per owner rule ("if 200, push with E"): Dockerfile:52 fix ships with E. Merge ⇒ raster redeploy (watch /services/raster-service/**) with brief downtime (volume ⇒ no overlap). State in PR.
- Owner rules to record: "المراجعةُ تقرأ، والفحصُ يُعطي سببًا"; reviews are snapshots — pin SHA + time. Blind guard (F02/F03) vs inverted guard (F05, worse than absent).
- Preflight D unit: 3 failed = test_blocking_surface_freeze (railway-dockerfile-pr-build.yml::plan undeclared addition) — registration tax; fix after preflight completes.

## Independent verification of agent work (~19:40Z) — measurer ≠ actor
- F03 genwt6 (645109fe, de82fe25): MY compose v5.1.1 run: b0c14b6d pair ⇒ exit 1 `service "sahool-raster" has neither an image nor a build context`; fixed pair ⇒ exit 0. Test 13/13; restoring old production.yml ⇒ exactly 2 red. ci.yml step renders per header usage line + explicit image/build check (read the diff). Follow-ups: .ci.env gitignore; odoo-snippet stale names (out of scope).
- F05 genwt7 (050e9979): 25/25; MY mutation (persistence check short-circuited) ⇒ 13 red; reviewer fixture: OLD block "ai evidence flow ok", NEW exit 1 naming persistence. Runtime statuses cited 259-285 confirmed. Limit: still dispatch-only job (correct ≠ enforced).
- Slice D ready at bb84a594 (declaration 9cfb4610, mutations 3/3 killed); full preflight deferred until agents stop (clean machine).
- F02+F08 genwt8 (6334fddd compose · d2056e36 agriai · 40ff69d2 Dockerfile — only one touching services/raster-service/**): MY run 200 pass; reverting Dockerfile+agriai main.py ⇒ 4 red. Sweep: 25 python probes (only 3 httpx members), 94 curl all -f, 17 wget. agriai not on Railway (tree). Out of scope: titiler/edge-arm64 probes w/o timeout; fixed.yml:1103 frontend probes root.
- All agents finished ~19:55Z; machine clean ⇒ preflight D full started.

## Owner decisions (~19:40Z)
- queue_v1: HELD unchanged until the prod gate opens (needs console; nothing urgent behind it).
- Postgres: postgis/postgis:15-3.5 Debian: postgis_extensions_upgrade() on 15.8 → retag → postgis_extensions_upgrade() again → REINDEX CONCURRENTLY only if encoding/collation query shows need. Starts after gate; read-only checks NOW (pg_proc, pg_authid, pg_prepared_xacts, replication slots). I cannot run SQL (no creds by rule) ⇒ SQL handed to owner.
- §3.4: erp-bridge behind profile odoo AND /readyz reinforcement. Rule: a service that cannot work without its dependency is not run without it.
- §3.5 vllm-jais: a test decides — clean fallback to Ollama proven ⇒ document+add, don't gate; else gate behind profile.
- SAM2_REF: pin to commit + periodic-update rule (reviewed & merged) + pin weights SHA256 (model_artifact_gate expects it).
- Tiler: remove from fixed/unified.
- Dashboard priority: FIRST Wait for CI · backup · migration-state read; WITH gate (cheap): SAHOOL_DEBUG value · RAILWAY_DOCKERFILE_PATH; DEFERRED: PR environments · email · webhook.
- Scope moves: ai_evidence_runtime.py:282 (absent persisted read as recorded) joins §3.1 fix; titiler/edge-arm64 missing timeouts join F02.
- Merge order at gate window: D → Playwright → audit (§3.6, §3.10, §3.1) → C → E → env_drift B.

## F02 owner question measured (~19:45Z): does a failing Dockerfile HEALTHCHECK kill/restart?
- Local dockerd 29.3.1, image raster's own base python:3.11-slim-bookworm (mirror.gcr.io), --restart=always, health interval 2s retries 2:
  hc-new (fixed probe, server 503): health=unhealthy streak=18 running=true restarts=0 after ~35s. hc-old (old probe, 503): health=healthy (the defect). ⇒ Docker engine does NOT kill/restart unhealthy containers.
- Boot window: nothing listening ⇒ old probe exit 1, new probe exit 1 ⇒ identical; fix adds no boot-time failure mode.
- Railway docs: restart policy acts only when the process stops/exits non-zero (deployments/restart-policy); healthcheckPath (/readyz for raster) only at deploy time, any 2xx (deployments/healthchecks); docs silent on HEALTHCHECK instruction. railway-agent unavailable (usage limit). Not measured on Railway itself.
- Contamination note: this experiment ran concurrently with preflight D3 (separate dirs, light) — declare.

## Owner screenshot (~20:15Z): notification-agent "Healthcheck error" on #1102 deploy — measured read-only
- It is STAGING: 34324a40 FAILED 01:53Z (the recorded gap NOTIFICATION-AGENT-LEGACY-PUSH-CONSUMERS-BLOCK-ZERO-DOWNTIME-REDEPLOY-01); staging still serves 43af9d13 (#1091, 09-28), 1/1 running.
- NEW: PRODUCTION deployed the SAME commit at the same minute (b7b739ed, 01:53:36Z) ⇒ SUCCESS; deploy log: /readyz 200 within 1s of start. readyz (agent.py at 32da2953) is strict: requires NATS + all 9 consumers verified via consumer_info ⇒ prod really subscribed.
- Config identical by NAME in both envs (incl. NOTIFICATION_CONSUMER_MODE; value not read by rule); only diff drainingSeconds=20 in prod (set today, AFTER 01:53). Mode is not logged by the agent. ⇒ difference is either the mode value (queue_v1 allows two replicas) or prod consumers not held by the old replica. Owner can read the variable value in dashboard.
- Pending slices touching the watch paths (agents/notification/**, agents/base_agent.py, shared/**): NONE (D, PW, audit, C, E, env_drift B) ⇒ none re-triggers the staging failure.
- Railway agent report (owner-pasted ~20:30Z): staging facts match mine (34324a40, start 01:54:17, 14×503, timeout 01:58:51, log prints class name only). Q1–Q5 unanswered (its tools can't read prod logs/NATS/vars). Q5 "inferred: likely both" = guess, NOT evidence ⇒ F02 Railway part stays ASSUMPTION. Its "psql to compare NOTIFICATION_CONSUMER_MODE" is wrong (service variable, dashboard).
- MY Q4 measurement: prev prod deploy 1bb943cc (eff473aa #1080) REMOVED at 01:54:30Z ⇒ alive when b7b739ed started 01:54:17 and passed /readyz 01:54:18. Both eff473aa and 32da2953 have the mode switch (#1045, 09-20), legacy default binds named durables, strict readyz. ⇒ in legacy mode the new prod replica should have been rejected like staging. INFERENCE (unproven): prod NOTIFICATION_CONSUMER_MODE=queue_v1, staging=legacy (or unset). Owner can confirm by reading the value in the dashboard.

## ~20:45Z: #1116 merged f02aa029 (13 real image builds; prod 11/11 SKIPPED). Owner approved backup branches (no PRs) — verified via ls-remote:
claude/wip-playwright-apt a8839594 (preflight 0/0 on this head) · claude/wip-audit-3-6-3-10-3-1 a80ab98f · claude/wip-slice-c be317c60 · claude/wip-slice-e-f03 de82fe25 · claude/wip-slice-e-f05 050e9979 · claude/wip-slice-e-f02-f08 40ff69d2.
On recreation: restore from these branches (not lost). PRs still open from claude/project-exploration-dtjw3p one slice at a time.
- ~21:30Z owner scope moves applied:
  * :282 into §3.1 — genwt4 7ceb401e (absent persisted ⇒ "unconfirmed"; status written after payload). Verified all platform branches (main + both deploy/*) return persisted ⇒ no deployed effect. Falsified 4/6 red. Backup claude/wip-audit-3-6-3-10-3-1 → 7ceb401e. brain_audit.py row updated (rcpt sha).
  * timeouts into F02 — genwt8: 6334fddd compose · d2056e36 agriai · 413d8d0f timeouts (titiler v9 + edge-arm64; 2 of 25 probes lacked timeout) · 5609ca8f raster Dockerfile LAST (droppable). Every commit green alone (middle: 217 pass + 4 strict xfail on the Dockerfile member); top 221; reverting Dockerfile at top ⇒ 4 red. Backup claude/wip-slice-e-f02-f08 → 5609ca8f (force-updated, own backup branch).
