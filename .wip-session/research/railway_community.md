# Railway community and technical research: operating, testing and verifying a ~20-service platform

Research date: 2026-09-30. Research only; no Railway project was touched.

## Access limits (read first)

The egress proxy **blocked** these hosts, so I could not fetch any page on them:
station.railway.com, help.railway.com, docs.railway.com, railway.com (templates, changelog), blog.railway.com, reddit.com, news.ycombinator.com, hn.algolia.com, dev.to, answeroverflow.com, velprove.com, bex.co, kyrylai.com, helpmetest.com, docs.phase.dev.

- Only **github.com** (and raw.githubusercontent.com) could be fetched. Every GitHub item below was fetched and read.
- Every Help Station, docs, changelog, blog or Reddit item below comes from a **search-result snippet only**. I did not open those pages, so I cannot confirm who wrote each statement (staff or user) or the exact date, unless the snippet showed it.
- Evidence-strength labels:
  - **official-staff-answer**: a Railway employee or official Railway doc or changelog. For snippets, this means "attributed to docs/staff by the snippet".
  - **multiple-users-confirm**: several independent reports.
  - **single-report**: one report.
- Reddit and HN produced no usable hits through search, and both hosts were blocked for fetching.

---

## (a) Pitfalls that silently break things

**a1. Uvicorn `--host ::` listens on IPv6 only, so Railway's IPv4 healthcheck is refused. `0.0.0.0` passes the healthcheck but leaves no IPv6 listener for private traffic in legacy environments.**
- Evidence: multiple-users-confirm (two Help Station threads plus three independent GitHub PRs).
- Date: 2024–2026 (GitHub PR 2026-09-20).
- Sources:
  - Fetched: https://github.com/nightasaur/nightasaur/pull/28 (2026-09-20): "a v6-only Uvicorn listener did not pass Railway's health check". Their fix is to bind "one socket with IPV6_V6ONLY=0 and pass it to Uvicorn so IPv4 health checks and IPv6 private-network requests reach the same authenticated app."
  - Snippet only: https://station.railway.com/questions/uvicorn-health-check-fails-with-i-pv6-bin-6e9f929e and https://station.railway.com/questions/fast-api-service-health-check-fails-in-ip-a0add1f5: "asyncio sets IPV6_V6ONLY on that socket. So --host :: listens on IPv6 only, and Railway's IPv4 healthcheck is refused"; "uvicorn doesn't support dual stack binding … Hypercorn is recommended".
- **Conflict:** Railway docs (snippet, https://docs.railway.com/networking/private-networking/library-configuration) recommend listening on `::`. That advice is fine for Node but not for uvicorn, because of asyncio's V6ONLY behaviour.
- Applies to us: we run FastAPI/uvicorn services with `/healthz` and `/readyz`. Check each service's `--host`:
  - `::` means healthchecks fail.
  - `0.0.0.0` means private calls fail, but only in legacy IPv6-only environments (see a2).
  - The robust option is a dual-stack socket (V6ONLY=0) passed to `uvicorn.Server`.

**a2. Private-network IP family depends on when the environment was created.** Environments created before 2025-10-16 are "legacy" and IPv6-only. Newer ones resolve `*.railway.internal` to both A and AAAA records.
- Evidence: official-staff-answer (docs and changelog snippet).
- Date: changelog 2025-10-17.
- Snippet only: https://docs.railway.com/networking/private-networking/how-it-works and https://railway.com/changelog/2025-10-17-repo-aware-settings: "Environments created before October 16th, 2025 are considered legacy environments and only support IPv6 addressing for private networking."
- Applies to us if production is older than 2025-10-16 and PR environments are newer. **A PR canary can then pass on IPv4 while production (IPv6-only) fails.** This means the canary is not representative for networking. Record each environment's creation date.

**a3. Node/ioredis-style clients look up only A records by default, which gives ENOTFOUND on IPv6-only networks. "Dualstack" flags are unreliable during reconnects.**
- Evidence: multiple-users-confirm, plus a Railway employee comment on GitHub.
- Date: 2025-02-07 and 2026-01-02.
- Fetched:
  - https://github.com/n8n-io/n8n/issues/13117 (2025-02-07): `getaddrinfo ENOTFOUND redis.railway.internal`.
  - https://github.com/n8n-io/n8n/issues/23787 (2026-01-02). Railway employee ray-chen: "QUEUE_BULL_REDIS_DUALSTACK=true is unfortunately unreliable in real deployments". A contributor: "edge cases where node/bull ends up preferring ipv4 sockets or failing during reconnects on ipv6-only networks". The workaround is `?family=6`.
- Snippet only: https://docs.railway.com/reference/errors/enotfound-redis-railway-internal (`family=0`).
- Applies to us if any service or tool (a Node-based UI, or anything else) uses ioredis, bull or similar. For our Python clients, check which address family each driver resolves. This is my inference, not sourced: redis-py, asyncpg and nats-py normally use getaddrinfo with no family restriction, so they should resolve AAAA records, but check once in a legacy environment.

**a4. `restartPolicy ON_FAILURE` never restarts a clean `exit 0`.** One team had production 502s "for hours".
- Evidence: single-report (fetched), consistent with a docs snippet.
- Date: 2026-09-18.
- Fetched: https://github.com/mobius-os/mobius/pull/1195: "Railway treats a clean stop as a successful stop and never brings the deployment back". Their fix is `ALWAYS` with `restartPolicyMaxRetries` 3.
- Applies to us: any long-running service (NATS consumer, worker, gateway) that can exit 0 on SIGTERM, on a lost upstream connection, or on "graceful shutdown" will stay down. The migrator with `NEVER` is fine, but make sure it exits **non-zero** on failure. Otherwise a failed migration looks like a success.

**a5. Volumes are mounted root-owned, so a non-root image cannot write. The failure can be silent (writes fail, the process keeps running).**
- Evidence: multiple-users-confirm (several Help Station threads) and a fetched GitHub issue quoting the docs.
- Date: 2026-09-14.
- Fetched: https://github.com/samuelisch/formula-time/issues/305. The process ran as uid 1001 and `/data` was root `drwxr-xr-x`. It was found via `railway ssh` with `mkdir` returning permission denied. The fix was `RAILWAY_RUN_UID=0` plus a boot-time writability probe that also warns when the "path not on mounted volume (ephemeral disk)". It quotes the docs: "Docker images that run as a non-root UID by default will have permissions issues when performing operations within an attached volume".
- Applies to us if the NATS image (`nats:2-alpine`) or any service writing to a volume runs non-root. Also applies to the postgis image, whose entrypoint normally handles chown, but verify. Add a write probe on `/data` at startup.

**a6. A wrong volume mount path is silently ephemeral.** Data "persists" until the next redeploy.
- Evidence: single-report (fetched).
- Date: 2026-09-17.
- Fetched: https://github.com/hookdeck/outpost/pull/1067. The Redis volume was mounted at the wrong path (`/var/lib/rabbitmq`) and was corrected to `/bitnami`. The fix was verified by checking that "a tenant plus destination survive a Redis redeploy."
- Applies to us: check that NATS `-sd`/`store_dir` points at the volume path exactly (`/data/jetstream` under the `/data` mount). Check that Redis `--dir` equals the mount path, and that postgis `PGDATA` is under the mount. Test with a write, a redeploy, then a read.

**a7. Build has no private network.** Anything that touches `*.railway.internal` at build time fails with ENOTFOUND.
- Evidence: official-staff-answer (snippet).
- Date: not visible.
- Snippet only: https://station.railway.com/questions/enotfound-mongodb-railway-internal-742e9671: "The private network is indeed not available during build due to technical limitation"; "please run the database-related commands during the pre-deploy step."
- Applies to us if any Dockerfile step or build hook contacts Postgres, Redis or NATS.

**a8. Healthchecks run only at deploy time and are never used for runtime monitoring.**
- Evidence: official-staff-answer (docs snippet), repeated by third-party monitoring blogs.
- Date: docs current.
- Snippet only: https://docs.railway.com/deployments/healthchecks: "only called at the start of the deployment … Railway does not monitor the healthcheck endpoint after the deployment has gone live."
- Applies to us: a green `/readyz` at deploy time says nothing about the service an hour later. We need external synthetic checks (see section (b)).

**a9. Railway autodeploys from GitHub only when changed files match the watch patterns. Negation rules work only if a preceding rule includes the files. Watch paths also decide which services a Focused PR environment deploys.**
- Evidence: official docs snippets and a third-party blog snippet.
- Date: 2026-08 (blog).
- Snippet only: https://bex.co/blog/2026/08/07/monorepo-path-filtered-deploys-render-railway-vercel ("negations only work if you include files in a preceding rule"), https://docs.railway.com/deployments/monorepo, and https://station.railway.com/questions/no-changed-files-matched-patterns-81a7ece6 (thread title "No changed files matched patterns").
- Applies to us: a change to shared code (a common library or a shared nginx config) that is not in every consumer's watch pattern leaves stale services running. Stale services do not show up as a failure.

**a10. Focused PR environments skip services whose files did not change,** unless the changed service references them with `${{svc.X}}`.
- Evidence: official-staff-answer (changelog and docs snippet).
- Date: 2026-01-23.
- Snippet only: https://railway.com/changelog/2026-01-23-100m-series-b and https://docs.railway.com/environments: "all other services are skipped and indicated on the canvas."
- Applies to us if focused mode is on. A canary with 20 services may be missing the gateway, migrator or NATS. Check what the PR comment lists as "skipped" before trusting a canary result.

**a11. Renaming a service may not change its private DNS name.**
- Evidence: single-report (fetched).
- Date: 2026-09-29.
- Fetched: https://github.com/eddy-guo/pools-info/pull/186: `RAILWAY_PRIVATE_DOMAIN` was "still `ledger-tip.railway.internal` 14 min later (`RAILWAY_SERVICE_NAME` now `chain-sync`)".
- **Conflict:** the docs snippet (https://docs.railway.com/private-networking) says changing the service name "updates the DNS name".
- Applies to us: avoid hardcoded `*.railway.internal` names in nginx or env files. Use `${{svc.RAILWAY_PRIVATE_DOMAIN}}` references, and re-resolve after any rename.

**a12. Default draining is 0 seconds.** The old deployment gets SIGTERM and then SIGKILL immediately.
- Evidence: official docs snippet.
- Date: docs current.
- Snippet only: https://docs.railway.com/deployments/reference: "by default is given 0 seconds to gracefully shutdown before being forcefully stopped with a SIGKILL". The settings are `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` and `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS`.
- Applies to us: in-flight uvicorn requests and un-acked JetStream messages get cut off on every deploy. Set a draining period on the API and worker services.

---

## (b) How people test and verify in live environments

**b1. PR environments as canaries (the official pattern).**
- Evidence: official docs snippet.
- Date: 2026.
- Snippet only: https://docs.railway.com/guides/ship-on-merge-pr-canaries:
  - "every PR opened by a project member gets its own temporary environment with all services, networking, and variables copied from your base environment"
  - "Whatever variables and services exist in the base at PR-open time are what the canary runs against"
  - it is deleted on merge or close
  - "PRs from outside contributors do not deploy"
  - "write one automated smoke case that proves the flow is alive end to end"
- Also: sync "copies configuration, not data, so databases, volumes, and bucket contents stay separate". Snippet only: https://docs.railway.com/environments.
- Applies to us: the canary gets an **empty Postgres/PostGIS and an empty NATS store**. So:
  - the migrator must bootstrap from zero, which is itself a good test of it;
  - smoke tests need seed data;
  - canaries cannot find data-dependent regressions.

**b2. Watch out for literal (non-reference) variables copied into PR environments.**
- Evidence: third-party snippet.
- Date: 2026.
- Snippet only: https://checkyourvibe.dev/blog/how-to/railway-env-vars and https://docs.railway.com/guides/preview-deployments-with-pr-environments: "If you inherit STRIPE_SECRET_KEY=sk_live_..., anyone with the preview URL can hit your live Stripe account"; "Sealed variables are not copied over when creating PR environments."
- **Conflict or likely error in the search summary:** it claimed that `${{Postgres.DATABASE_URL}}` would point a PR environment at the production database. Railway reference variables resolve inside their own environment. The real risk is **hardcoded literal URLs or secrets**. I could not verify this on the blocked docs page.
- Applies to us: audit variables for literal production hosts or keys. Also, **sealed secrets missing from a PR environment** may make auth fail in the canary.

**b3. Waiting for the deploy before running smoke tests.** Use GitHub `deployment_status` (state `success`) or Railway webhooks.
- Evidence: official docs snippet and a Help Station thread.
- Date: docs current.
- Snippet only:
  - https://docs.railway.com/guides/github-actions-post-deploy ("use the success state to trigger your action")
  - https://station.railway.com/questions/how-to-wait-deployment-with-health-check-c0b176d9 ("the railway up command completes too quickly … not actually waiting for health checks")
  - https://docs.railway.com/observability/webhooks
- Applies to us: our CI must gate smoke tests on deployment success, not on the CLI exiting.

**b4. Restore drills: a backup that has never been restored is not verified.** Automated nightly restore into an isolated database, followed by integrity checks.
- Evidence: multiple-users-confirm (fetched).
- Date: 2026-09-21 and later.
- Fetched:
  - https://github.com/Kjudeh/railway-postgres-backups: `pg_dump` to S3, then "Verify Service … restores them to an isolated database". The verify `DATABASE_URL` "Must be different from production".
  - https://github.com/customerservice-prog/Party-Rental-Software-Saas/issues/9 (2026-09-21): "a backup that has never been restored is unverified". Its checklist: volume backup schedule and retention, PITR status, restore to a non-production target, record restore duration and backup age. It also notes: "Repeated read-only Railway-agent backup queries timed out."
  - https://github.com/boardsesh/boardsesh/issues/4340: weekly disposable PITR restore plus monthly logical restore with "PostGIS/index/constraint/application smoke checks".
- Applies to us: a PostGIS restore drill should check that the extension versions match (`postgis_full_version()`), spatial indexes, and one geometry query.

**b5. Running one-off commands inside the private network: `railway ssh -s <svc>`, `railway run`, pre-deploy, `railway connect --tunnel-only`, and `railway private-network`.**
- Evidence: official changelog and docs snippets, plus the fetched GitHub item a5 (which used `railway ssh` to diagnose).
- Date: 2026-06-26.
- Snippet only: https://railway.com/changelog/2026-06-26-railway-over-ssh ("standard SSH connection … port forwarding, SCP, SFTP"; "forwarding is limited to the container's loopback and your project's private network"). Also https://docs.railway.com/deployments/pre-deploy-command: "execute within your private network"; "If your command fails, it will not be retried and the deployment will not proceed."
- **Important nuance:** `railway run` executes **locally** with injected variables, so `*.railway.internal` will not resolve from a laptop. Use `railway ssh` or a tunnel for private-network checks.

**b6. DNS logs for debugging service-to-service failures.**
- Evidence: official changelog snippet.
- Date: 2026-07-24.
- Snippet only: https://railway.com/changelog/2026-07-24-dns-logs: "Every deployment's Network tab now includes DNS logs … the name queried, the record type, the response code". It has filters `@qname @rcode @zone=internal`.
- Applies to us: when the gateway returns 502, look for NXDOMAIN, or an A-only lookup against a legacy environment.

**b7. Boot-time self-probes: writability, correct volume path, and dependency reachability.**
- Evidence: single-report (fetched, a5).
- Applies to us: this turns silent failures into crash-at-boot. That pairs well with `/readyz`, but only if `/readyz` really touches the dependency.

**b8. OOM kills can be invisible in Railway metrics.**
- Evidence: snippet, appears to be a staff answer.
- Snippet only: https://station.railway.com/questions/worker-process-exiting-with-code-137-ced4a258: "the metrics polling interval is relatively long, so the process exceeded its memory allocation and was killed before the metrics system could capture and display the spike."
- Applies to us: when verifying from logs or metrics, look for exit code 137 in deploy logs rather than trusting the memory graphs.

---

## (c) Postgres on Railway with custom images

**c1. Railway volumes are ext4 with `lost+found` at the root, so setting `PGDATA` to the mount point makes initdb fail.** Put `PGDATA` in a subdirectory. There is a related trap: "directory appears to contain a database; Skipping initialization".
- Evidence: multiple-users-confirm (Help Station threads plus GitHub PR titles in search).
- Snippet only:
  - https://station.railway.com/questions/postgre-sql-custom-docker-image-with-volu-aa38e53b
  - https://station.railway.com/questions/parade-db-postgre-sql-container-fails-to-i-f67643a0
  - GitHub PR titles (search): "PGDATA must be a subdirectory of the volume mount" (adammarquette/agent-forge-copilot#406) and "set PGDATA to a subdirectory for Railway's db volume" (TripAndCode/transit-app#441). The fetch returned 404, so I have titles only.
- Railway's own template uses `PGDATA=/var/lib/postgresql/data/pgdata`. Fetched: https://github.com/railwayapp-templates/postgres.
- Applies to us: with `postgis/postgis:15-3.4`, check that `PGDATA` is below the mount path (for example mount `/var/lib/postgresql/data`, `PGDATA=/var/lib/postgresql/data/pgdata`).

**c2. Railway's one-click major-version upgrade (pg_upgrade) does not support custom images.** Changing the tag across a major version gives "database files are incompatible with server".
- Evidence: official docs and changelog snippet, plus multiple users.
- Date: changelog 2026-09-11.
- Snippet only:
  - https://docs.railway.com/databases/postgresql-major-upgrade: "Official Railway image only — ghcr.io/railwayapp-templates/postgres-ssl …"; ":latest is not supported".
  - https://railway.com/changelog/2026-09-11-one-click-postgres-major-version-upgrades
  - https://station.railway.com/questions/postgres-deploy-fails-after-image-update-c6c10e90 ("PG17 data dir, PG16 won't start"; a user reports that a restore into the same service did not fix it).
- Applies to us: upgrading `postgis:15-3.4` means a manual dump and restore, or logical replication. PostGIS needs `ALTER EXTENSION postgis UPDATE` in **every** database (from the pg_upgrade/PostGIS search snippets, for example https://postgis.net/workshops/postgis-intro/upgrades.html).

**c3. Image auto-updates.** Railway can auto-update Docker-image services. With versioned tags it stages a new tag; with non-versioned tags it re-pulls the digest. The redeploy means downtime for volume services. Pro plans get an automatic volume backup first.
- Evidence: official docs snippet.
- Snippet only: https://docs.railway.com/deployments/image-auto-updates: "Automatic updates trigger a redeployment, which may cause brief downtime (typically under 2 minutes) for services with attached volumes … Railway automatically creates a backup of all volumes … named Auto Update {image}".
- Railway's own Redis-HA image had a silent **total data loss** after an image auto-patch. Fetched: https://github.com/railwayapp-templates/redis-ha/pull/67 (2026-09-16, Railway templates repo). The new image loaded a stale AOF with "0 keys" and then "Shutdown saved that empty dataset, overwriting the customer's RDB" (57,401 keys).
- Evidence strength for the incident: official repo, single incident.
- Applies to us: `postgis/postgis:15-3.4` is a **floating tag** (new patch digests get pushed under it). Check whether auto-updates are on for Postgres, Redis and NATS. I recommend pinning by digest, updating deliberately, and taking a backup first.

**c4. Collation version mismatch after an image or glibc change.** This has been reported on Railway's own PG17 template: "created using collation version 2.36, but the operating system provides version 2.41".
- Evidence: multiple-users-confirm (three or more Help Station threads).
- Snippet only:
  - https://station.railway.com/questions/postgre-sql-collation-version-mismatch-er-c8144284
  - https://station.railway.com/questions/refresh-collation-version-postgres-warni-e85b11e9
  - https://station.railway.com/questions/collation-version-issue-3ae12b79
- The fix is `REINDEX` followed by `ALTER DATABASE … REFRESH COLLATION VERSION`.
- Applies to us: any re-pull of `postgis:15-3.4` whose Debian base moved (see c3) can silently corrupt text-index ordering. Add a post-deploy check that queries `pg_database.datcollversion` against `pg_database_collation_actual_version()`.

**c5. `/dev/shm` is fixed at 64MB.** Parallel queries, VACUUM and index builds fail with "could not resize shared memory segment". Raising it reportedly needs a plan above Pro.
- Evidence: multiple-users-confirm, with staff-style answers (snippet).
- Snippet only:
  - https://station.railway.com/questions/error-could-not-resize-shared-memory-s-42091a03
  - https://station.railway.com/questions/error-when-running-vacuum-on-postgres-c-ad229e2a
  - https://station.railway.com/questions/postgres-dev-shm-too-small-pgvector-f-6ca8460e
  - https://station.railway.com/feedback/increse-shm-size-for-postgre-sql-instances-db7a57d3
- Applies to us: PostGIS spatial queries and GiST index builds with parallel workers. Consider lowering `max_parallel_workers_per_gather` and `maintenance_work_mem`.

**c6. A full volume leaves Postgres in a crash-recovery loop** ("could not write to file 'pg_wal/xlogtemp': No space left on device"). Some volume metrics were reported as wrong or misleading.
- Evidence: multiple-users-confirm.
- Snippet only:
  - https://station.railway.com/questions/postgres-stuck-in-crash-recovery-loop-n-5b551e52
  - https://station.railway.com/questions/pg-vollume-not-showing-as-full-but-pg-h-c8f30487
  - https://station.railway.com/questions/postgres-volume-shows-434mb-total-despit-8565af3f
- Volume size caps from the snippet: Hobby 5GB, Pro 50GB. An offline resize restarts the service.
- Applies to us: alert on disk usage from inside Postgres (`pg_database_size` plus WAL size), not just the Railway volume graph.

**c7. Railway's default Postgres has no PostGIS** ("could not open extension control file …postgis.control"), which is why a custom image is needed.
- Evidence: multiple-users-confirm.
- Snippet only: https://station.railway.com/questions/installing-postgis-extension-with-post-0643a575
- Applies to us: already handled by using a custom image. Remember that the managed upgrade path, and possibly other managed features, assume the official image.

**c8. Backups.** Volume backups are incremental and copy-on-write. A restore mounts a new volume, and "backups newer than that point are not copied to it but remain on the previous volume, which stays unmounted". PITR exists.
- Evidence: official docs snippet.
- Snippet only: https://docs.railway.com/volumes/backups, https://docs.railway.com/volumes/point-in-time-recovery, https://docs.railway.com/guides/postgres-backups-restores.
- Unknown, since the docs are blocked: whether PITR works with a **custom** image or only with Railway's image. Verify this before relying on it.

---

## (d) NATS and Redis on Railway

**d1. A Redis volume is needed, and so is persistence mode.** Without a volume, AOF only protects against in-deployment crashes. The community template uses `--requirepass`, `--protected-mode yes` and `requiredMountPath=/data`, and notes the volume "is not created automatically".
- Evidence: multiple (snippets plus the fetched a6).
- Snippet only:
  - https://docs.railway.com/guides/redis-cache-vs-store
  - https://station.railway.com/questions/urgent-redeploy-caused-data-loss-requ-dd39544c (thread title "Redeploy Caused Data Loss")
  - https://github.com/sahilrupani/redis-railway-template (search snippet)
- Applies to us: decide whether Redis is a cache or a store. If it is a store, use volume plus AOF and run the redeploy-survival test.

**d2. NATS templates: JetStream on a `/data` volume, an auto-generated auth token, and a TCP proxy provisioned for external access.**
- Evidence: official template listing (snippet).
- Snippet only: https://railway.com/deploy/nats-jetstream and https://railway.com/template/Iy1rFN: "protects client connections with an automatically generated authorization token, and automatically provisions a Railway TCP proxy for external NATS client access".
- Applies to us: our self-built `nats:2-alpine` has **no auth by default** unless we configured it. If a TCP proxy was ever added, NATS is publicly reachable. Check for TCP proxies on the NATS, Redis and Postgres services, and require a token or nkeys even inside the private network.
- I found no Help Station threads specifically about NATS failures. Community evidence here is thin.

**d3. Databases went private by default** (2026-07-31). New Postgres, MySQL, Mongo and Redis templates have no TCP proxy; existing services are untouched.
- Evidence: official changelog (snippet).
- Snippet only: https://railway.com/changelog/2026-07-31-railway-plugin-for-chatgpt and https://bex.co/blog/2026/09/11/railway-private-databases-connection-string-migration.
- Applies to us: our custom services predate this and are not templates, so any TCP proxy we added in the past still exists. Audit.

**d4. One volume per service. Replicas cannot use volumes. Maximum 20 volumes per project.**
- Evidence: official docs snippet plus feedback threads.
- Snippet only: https://docs.railway.com/reference/volumes, https://station.railway.com/feedback/multiple-volumes-per-service-7ce57788, https://station.railway.com/questions/volume-limit-counting-issue-162ecf47.
- Applies to us: Postgres, NATS and Redis each need their own volume and cannot be scaled horizontally on Railway. JetStream HA needs three separate services.

---

## (e) nginx and reverse proxies on Railway

**e1. The private IP changes on every redeploy, and nginx resolves literal hostnames once at startup. The result is 502s from the gateway after any backend redeploy until nginx restarts.** The fix is a `resolver` plus a variable in `proxy_pass`.
- Evidence: multiple-users-confirm (Help Station snippets plus GitHub).
- Snippet only:
  - https://station.railway.com/questions/nginx-with-private-networking-upstream-8d7ce3c3: "[fd12::10] would be the resolver you need to use, this doesn't change regardless of service or project"; "Every time you deploy the upstream service, they get a new IPv6 address. Even with a resolver [fd12::10] valid=1s;, you could still hit a stale DNS value".
  - https://station.railway.com/questions/reliability-internal-networking-7daff8bd: `resolver [fd12::10] ipv6=on valid=1s; set $proxy_pass_url http://api.railway.internal:8080; proxy_pass $proxy_pass_url;`.
- Fetched: https://github.com/FabioCarlesso/cartolaoddsfe/issues/34 (2026-09-02). It uses `set $upstream ${BACKEND_ORIGIN}; proxy_pass $upstream$request_uri;` with `resolver … valid=1s`. Its acceptance criterion: "Redeploy do backend não quebra o frontend" ("a backend redeploy does not break the frontend").
- Fetched counter-example: https://raw.githubusercontent.com/phasehq/railway-nginx/main/nginx.conf.template uses `proxy_pass ${BACKEND_HOST};`, a literal after envsubst, with `resolver [::1];`. This is the startup-only resolution pattern that goes stale.
- Applies to us, **high priority**: our gateway uses `auth_request`. The auth subrequest location **and** every API `proxy_pass` must use variables. Otherwise redeploying the auth service breaks every authenticated route. That is a silent 401/502 with a green frontend healthcheck.

**e2. Resolver address family.** The community nginx template uses `ipv4=off` for `*.railway.internal` because "Railway's private network routes over IPv6 only between services". Upstreams are "re-resolved every 10 seconds".
- Evidence: single-report (fetched).
- Fetched: https://github.com/M-Codeartisan/nginx-railway. It also has a caveat: custom domains have their own target port, and "a mismatch causes `502` errors unrelated to DNS or certificates".
- **Conflict:** this is correct for legacy environments, but new environments (after 2025-10-16) also return A records (a2). `ipv4=off` stays safe in both.
- Unverified: whether `[fd12::10]` is still the resolver in new dual-stack environments. The staff quote says it "has been the same address since private networking was first introduced", but that predates the dual-stack change. Read `/etc/resolv.conf` via `railway ssh` in each environment.

**e3. Open-source nginx ≥1.27.3 supports `server host resolve;` in `upstream` blocks** (with a `zone`). This is an alternative to the variable trick that keeps upstream keepalive.
- Evidence: official nginx blog snippet.
- Snippet only: https://blog.nginx.org/blog/dynamic-dns-resolution-open-sourced-in-nginx and https://www.getpagespeed.com/server-setup/nginx/nginx-upstream-resolve.
- Applies to us if the gateway image is nginx ≥1.27.3.

**e4. nginx must listen on `${PORT}` because the healthcheck uses `PORT`. Limit envsubst variables so `$uri` and `$host` survive templating.**
- Evidence: multiple (fetched a2 issue #34 plus docs snippet).
- Snippet only: https://docs.railway.com/guides/healthchecks: "this variable's value is also used when performing health checks".
- Listen on both families (`listen ${PORT}; listen [::]:${PORT};`) if other services call the gateway privately.

---

## (f) Healthcheck semantics and zero-downtime caveats with volumes

**f1. A service with a volume always has downtime on redeploy, even with a healthcheck.** Railway does not run two deployments against one volume.
- Evidence: official docs snippet.
- Snippet only: https://docs.railway.com/deployments/healthchecks and https://docs.railway.com/volumes/reference: "There will be a small amount of downtime when re-deploying a service that has a volume attached, even if there is a healthcheck endpoint configured"; "we prevent multiple deployments from being active and mounted to the same service."
- Applies to us: every Postgres, Redis or NATS redeploy, including image auto-updates, is an outage for every dependent service. Clients need retry and backoff at startup and at runtime. Schedule these redeploys deliberately.

**f2. Healthcheck mechanics.**
- It uses `PORT`, arrives over IPv4, and sends Host `healthcheck.railway.app`, so allow that host in TrustedHost or nginx `server_name`.
- Any 2xx passes.
- The default timeout is 300s (`RAILWAY_HEALTHCHECK_TIMEOUT_SEC`, reportedly capped at 3600). A UI value may override the variable.
- Evidence: official docs plus a Help Station snippet.
- Snippet only: https://docs.railway.com/guides/healthchecks, https://station.railway.com/questions/max-healthcheck-timeout-47061bff, https://station.railway.com/questions/different-port-for-healthcheck-public-808fa854 ("Railway's healthcheck uses the PORT variable and doesn't look at anything else").
- Applies to us: configure the Railway healthcheck to `/readyz` (a dependency-aware check) so the switch-over waits for real readiness. But if `/readyz` fails whenever Postgres is briefly down (f1), deploys of other services will fail during Postgres redeploys. Choose deliberately.

**f3. Pre-deploy commands are an alternative to a separate migrator service.** They run in the private network. A failure blocks the deploy and is not retried.
- Evidence: official docs snippet.
- Snippet only: https://docs.railway.com/deployments/pre-deploy-command.
- Applies to us: a one-shot migrator (`NEVER`) is not ordered before the API deploys unless we enforce that order. A pre-deploy migration on the API service gives real ordering.

**f4. Deploys can get stuck on volume mounting** ("Waiting for volume migration", "Creating containers"). Community workarounds include cloning the service onto a fresh node and "Redeploy source image".
- Evidence: multiple-users-confirm (snippets, six or more threads).
- Snippet only:
  - https://station.railway.com/questions/volume-cannot-be-mounted-by-any-containe-ba700ff0
  - https://station.railway.com/questions/service-deployment-stuck-in-queued-wai-7922ebe8

---

## (g) Cost and limit surprises

**g1. Egress bills.** Connecting to a database through its public URL or TCP proxy is billed egress. Private-network traffic is free.
- Evidence: multiple-users-confirm (snippets).
- Snippet only: https://station.railway.com/questions/unexpected-egress-charges-first-time-u-e0dfc695 ("$41 coming from egress alone (820GB)") and https://station.railway.com/questions/huge-network-egress-costs-e90b03c5.
- Applies to us: check that every `DATABASE_URL`, `REDIS_URL` and `NATS_URL` uses `*.railway.internal`, not `*.proxy.rlwy.net`.

**g2. PR environments bill as a full mirror of the base environment.** With about 20 services, each open PR multiplies the bill.
- Evidence: official docs snippet plus third-party estimates.
- Snippet only: https://docs.railway.com/pricing/faqs ("you are billed for those workloads running in the ephemeral environment"). Third-party estimate (unverified): "at 100 PRs a month … ~$1,000/month" (https://bex.co/blog/2026/09/11/railway-focused-pr-environments-changed-only-previews).

**g3. The hard usage limit shuts down all workloads.** Warnings arrive at 75%, 90% and 100%. The minimum hard limit is $10.
- Evidence: official docs snippet.
- Snippet only: https://docs.railway.com/reference/usage-limits.
- Applies to us: a PR-environment spike can take **production** offline if a hard cap is set.

**g4. Serverless (app sleeping) plus private networking: a sleeping service may refuse private connections** instead of waking.
- Evidence: multiple snippets, including feedback threads.
- Snippet only: https://station.railway.com/questions/sleeping-service-not-waking-in-response-ef6af90e and https://station.railway.com/feedback/connection-refused-when-service-sends-re-a0a97135.
- **Conflict:** the current docs snippet says services wake from private-network traffic.
- Applies to us if serverless is enabled on any internal service. It should not be enabled in production.

**g5. Other limits:** 64MB `/dev/shm` (c5), volume caps of 5GB Hobby and 50GB Pro (c6), one volume per service, and 20 volumes per project (d4).

**g6. Platform incidents in 2026 hit private networking and DNS:**
- 2026-03-15: private networking incident.
- 2026-03-21: DNS resolution failures (about 26 minutes).
- 2026-07-02: US-East outage, including "disrupted private networking for roughly two hours".

Evidence: official status page and blog (snippet). Snippet only: https://blog.railway.com/p/incident-report-july-2-2026-us-east-services-outage and https://status.railway.com/cmn0q6tpn0cgahvwrlv7hyubq. Applies to us: our retry and backoff on internal DNS failures should be tested, not assumed.

---

## Top 10 pitfalls to check in our deployment

1. **nginx gateway re-resolution (e1/e2).** Every `proxy_pass`, including the `auth_request` subrequest location, must use a variable with `resolver … valid=…`, or nginx ≥1.27.3 `upstream … resolve`. Test this: redeploy the auth service, then check that authenticated routes still return 200 without restarting the frontend.
2. **Uvicorn bind (a1).** `::` fails the IPv4 healthcheck. `0.0.0.0` breaks private calls in legacy IPv6-only environments. Use a dual-stack socket, and check each FastAPI service's start command.
3. **Environment age and IP family (a2).** Find out whether production predates 2025-10-16. If it does, PR canaries (dual-stack) do not reproduce production networking.
4. **`postgis:15-3.4` floating tag plus auto-updates (c3/c4).** Pin by digest. Check whether image auto-updates are enabled on Postgres, Redis and NATS. Watch for collation mismatch after any re-pull.
5. **`PGDATA` location (c1).** It must be a subdirectory of the volume mount. Check that the data really lives on the volume by writing a row, redeploying, and reading it back.
6. **Volume ownership and path for NATS and Redis (a5/a6).** Check that the JetStream store dir equals the mount path, that the process uid can write, and that streams survive a redeploy.
7. **Restart policy (a4).** Long-running services on `ON_FAILURE` never come back from exit 0. The migrator (`NEVER`) must exit non-zero on failure and must be ordered before the API services (or moved to pre-deploy, f3).
8. **Unauthenticated or public data services (d2/d3/g1).** Audit TCP proxies on Postgres, Redis and NATS, check that NATS auth is on, and check that all URLs are private.
9. **Volume-service redeploys are outages (f1), and draining defaults to 0s (a12).** Set `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` on the APIs and workers. Make sure every client retries on startup. Decide whether `/readyz`-as-healthcheck should depend on Postgres.
10. **Watch patterns and Focused PR environments (a9/a10).** Shared-code changes may not redeploy consumers. Canaries may skip services. Check the "skipped" list, and add shared paths to every consumer's watch patterns.

Honourable mentions:
- 64MB `/dev/shm` against PostGIS parallel queries (c5).
- Sealed variables are not copied to PR environments; literal production secrets are (b2).
- A hard usage cap can stop production (g3).

## Top 8 verification techniques practitioners actually use on Railway

1. **PR environment as a canary with one end-to-end smoke case per critical flow**, gated on GitHub `deployment_status == success` rather than on CLI exit (b1/b3). For us this also proves the migrator bootstraps an empty PostGIS database.
2. **Redeploy-survival tests.** Write a marker, redeploy the data service, then read it back (Redis, NATS stream, Postgres row). This is how the hookdeck and Redis-HA problems were caught (a6/c3).
3. **"Redeploy the upstream, probe through the gateway" test.** Redeploy a backend or auth service and check that the gateway serves 200 without restarting nginx (e1; the acceptance criterion in FabioCarlesso#34).
4. **Automated restore drills.** Nightly `pg_dump` to S3, then restore into an isolated database, then integrity checks (row counts, indexes, and for us PostGIS version plus a spatial query). Record restore time and backup age (b4).
5. **In-network one-off checks with `railway ssh -s <svc>`** (or the `railway private-network` and `connect --tunnel-only` tunnels). Use them for `getent ahosts svc.railway.internal`, `cat /etc/resolv.conf`, `nats stream ls`, `psql` and write probes. Remember that `railway run` runs locally (b5).
6. **Boot-time self-probes** that crash loudly: volume writable, path really on the volume, dependencies reachable (b7).
7. **DNS logs in the deployment Network tab** (`@zone=internal @rcode=NXDOMAIN`) when service-to-service calls fail (b6).
8. **External synthetic monitoring**, because Railway healthchecks stop after go-live (a8). Pair it with deploy-log checks for exit code 137, since metrics can miss OOM spikes (b8).
