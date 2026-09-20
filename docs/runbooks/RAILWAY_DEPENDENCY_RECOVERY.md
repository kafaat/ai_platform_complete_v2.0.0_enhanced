# Railway dependency recovery

Applies to the existing SAHOOL Railway project, not to an automatic migration of
all Compose services. Build every repository service from the repository root.
Use one tested commit for each rollout and record its deployment ID. A successful
`/readyz` is a dependency probe, not certification of an agronomic result.

## Release and storage gates

1. Merge the tested readiness repair through normal PR checks. Do not change the
   existing platform branch until its schema and API compatibility are checked.
2. Check `fields`, `raster_assets`, `sahool_field_owner_tenant(text)` and, if selected,
   `signal_anomalies` against the application role. Do not replay migrations merely
   to make a health badge green. The field assertion replay store must be reachable.
3. Mount writable persistent storage for Raster and Knowledge Graph. Dockerfile
   directory ownership does not prove the mounted directory is writable. Raster
   runs as UID 10001. Check KG's runtime UID and mount ownership before startup.
4. Use PostgreSQL for vegetation anomaly state only after verifying the existing
   `v191_rs_signal_anomalies_store.sql` migration and tenant isolation. Otherwise
   mount SQLite storage and set its path explicitly. Never retain the `/tmp` default.
5. Keep Qdrant and Ollama private. The current RAG embedding client does not send
   authentication headers. Do not expose Ollama publicly to make it reachable.

## Field and imagery slice

Shared references below reuse existing secrets; if a named shared key is absent,
provision it securely once and bind both parties. Never replace or print existing
JWT, database, or service credentials. All examples use Railway reference syntax.

| Service | Dockerfile | Port | Health check |
|---|---|---:|---|
| sahool-field-management-service | services/field-management-service/Dockerfile | 8000 | /readyz |
| sahool-raster-service | services/raster-service/Dockerfile | 8001 | /readyz |
| sahool-vegetation-analysis | services/vegetation-analysis-service/Dockerfile | 8000 | /readyz |

Common: `SAHOOL_ENV=production`, `DATABASE_URL=${{sahool-platform.DATABASE_URL}}`
where the service uses PostgreSQL, `SAHOOL_AGENT_TOKEN=${{shared.SAHOOL_AGENT_TOKEN}}`.
JWT consumers use `JWT_PUBLIC_KEY=${{shared.JWT_PUBLIC_KEY}}`.
Set `PORT` to the fixed Uvicorn port in the table; these Docker CMDs do not consume
an arbitrary Railway port variable.

Field Management:

```dotenv
FIELD_SERVICE_ALLOWED_CALLERS=vegetation-analysis-service
FIELD_SERVICE_TENANT_ASSERTION_KEY=${{shared.FIELD_SERVICE_TENANT_ASSERTION_KEY}}
FIELD_SERVICE_TENANT_ASSERTION_KEY_ID=current
FIELD_SERVICE_ASSERTION_REDIS_URL=redis://:${{sahool-redis-state.REDIS_PASSWORD}}@${{sahool-redis-state.RAILWAY_PRIVATE_DOMAIN}}:6379/5
```

Confirm Redis DB 5 is available for replay nonces, with AOF enabled and a
`noeviction` policy. The nonces expire after 70 seconds, but must survive a process
restart and must not be evicted early by unrelated cache traffic. Keep this DB
separate from the approval/audit store used by AI Agronomist.

The cache instance `sahool-redis` is a different service. A password environment
variable alone does not enable Redis authentication. Its start command must use
the existing password and fail when it is absent:

```sh
sh -ec 'test -n "$REDIS_PASSWORD"; exec redis-server --requirepass "$REDIS_PASSWORD" --maxmemory 256mb --maxmemory-policy allkeys-lru'
```

After a fresh deployment, verify authenticated PING and unauthenticated rejection.
A successful one-time `CONFIG SET` does not prove the next process will enforce it.

Raster:

```dotenv
RASTER_UPLOAD_DIR=/data/rasters
RASTER_PERSISTENCE_MODE=required
HISTORICAL_SEARCH_PROVIDER=element84
```

Mount `/data/rasters`. Supply **build-time** `SAHOOL_GIT_SHA` (the full commit actually
built), `SAHOOL_BUILD_ID`, `SAHOOL_SOURCE_REPOSITORY`, `SAHOOL_SOURCE_REF`; never leave
an old explicit SHA when moving the source branch. Validate `/runtime-identity`.
With the current Dockerfile, pair these explicit build values with a release branch
pinned to the same reviewed commit, rather than a moving `main` autodeploy. Promote
the source ref and its build values together, then compare the deployment commit
with the immutable identity before accepting the release. In the 2026-09-20
Railway recovery, a reference to `${{RAILWAY_GIT_COMMIT_SHA}}` in a service variable
resolved empty during a configuration-triggered build; do not assume that reference
is a verified replacement for supplying the actual commit.
CDSE routes additionally require the configured CDSE/SH credentials. The initial
Element84 route does not prove CDSE readiness. S3 is an alternative asset backend,
not a replacement for a writable local processing directory; prove uploads separately.

Railway mounts volumes as root ([permissions reference](https://docs.railway.com/volumes#permissions)).
For this image, an initialization command can set ownership of the new mount and
then drop to `appuser` before starting Uvicorn. Pair `RAILWAY_RUN_UID=0` with this
complete start command; do not use that variable alone to run the application as root:

```sh
python -c 'import os,pwd; p="/data/rasters"; u=pwd.getpwnam("appuser"); os.chown(p,u.pw_uid,u.pw_gid); os.chmod(p,0o750); os.setgroups([]); os.setgid(u.pw_gid); os.setuid(u.pw_uid); os.execvp("uvicorn",["uvicorn","main:app","--host","0.0.0.0","--port","8001"])'
```

The command changes only the mount directory, not existing asset files. Verify the
running Uvicorn process is UID 10001 and that a probe file can be written and removed.

Vegetation:

```dotenv
FIELD_SERVICE_URL=http://${{sahool-field-management-service.RAILWAY_PRIVATE_DOMAIN}}:8000
FEATURE_SENTINEL_DB_FIELDS=1
ALLOW_LEGACY_FIELD_REGISTRY=false
FIELD_SERVICE_TENANT_ASSERTION_KEY=${{shared.FIELD_SERVICE_TENANT_ASSERTION_KEY}}
FIELD_SERVICE_TENANT_ASSERTION_KEY_ID=current
RASTER_SERVICE_URL=http://${{sahool-raster-service.RAILWAY_PRIVATE_DOMAIN}}:8001
VEGETATION_REAL_ONLY=1
VEGETATION_ANOMALY_STORE=postgres
NATS_URL=nats://${{sahool-nats.RAILWAY_PRIVATE_DOMAIN}}:4222
VEGETATION_EVIDENCE_PUSH_ENABLED=false
```

The PostgreSQL option requires the verified migration above. For the SQLite option,
set `VEGETATION_ANOMALY_STORE=sqlite` and
`VEGETATION_ANOMALY_DB_PATH=/data/vegetation/anomalies.db` with a persistent mount.
Configure `INDICATORS_SERVICE_URL` once Indicators is deployed. The code can consume
validated Raster bundles when canonical observations are absent; report that limited
scope. Do not claim the BFF/Decision/Task workflow is available from this slice alone.

Set the existing platform's `RASTER_SERVICE_URL` to the Raster URL as well: the
frontend's `analyzeVegetation` compatibility function refreshes imagery through
platform → Raster, rather than calling Vegetation's analysis route.

## Retrieval and advisor slice

Deploy Qdrant with persistent storage and API authentication, and a private Ollama
service with persistent model storage. Pin reviewed image versions at deployment.
Load `nomic-embed-text`; measure its output dimension before populating the collection.
Ingest approved, provenance-bearing corpus records through the canonical writer.
Do not create an empty collection or copy quarantined bootstrap rows to claim readiness.
Resource sizing depends on the measured model/corpus and is not pre-approved by this
runbook. Do not increase plan/spending limits to satisfy a deployment automatically.

| Service | Dockerfile | Port | Durable state |
|---|---|---:|---|
| sahool-rag-retrieval | services/rag-retrieval/Dockerfile | 8000 | Qdrant; sparse index rebuilt from its payloads |
| sahool-knowledge-graph | services/knowledge-graph/Dockerfile | 8000 | volume /data; KG_SQLITE_PATH=/data/kg.sqlite |
| sahool-ai-agronomist | services/ai_agronomist/Dockerfile | 8000 | existing persistent Redis instance, separate DB/key ownership |

RAG uses `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `OLLAMA_BASE_URL`,
`EMBEDDING_MODEL=nomic-embed-text`, service token and the public JWT verification key.
AI generation provider settings do **not** configure RAG embeddings.

AI Agronomist:

```dotenv
RAG_BASE_URL=http://${{sahool-rag-retrieval.RAILWAY_PRIVATE_DOMAIN}}:8000
KNOWLEDGE_GRAPH_URL=http://${{sahool-knowledge-graph.RAILWAY_PRIVATE_DOMAIN}}:8000
GUARDRAILS_URL=http://${{sahool-guardrails-engine.RAILWAY_PRIVATE_DOMAIN}}:8000
PLATFORM_URL=http://${{sahool-platform.RAILWAY_PRIVATE_DOMAIN}}:8000
SAHOOL_AGENT_STORE_BACKEND=redis
AI_GENERATION_ENABLED=false
```

Set `SAHOOL_AGENT_REDIS_URL` to a verified persistent Redis store without colliding
with other application state. Verify evidence-only retrieval first, then select and
verify generation separately. An empty KG can be technically ready; it is not evidence
of useful agronomic knowledge. Keep service-token writes private.

## Existing frontend overrides

No new resolver is needed. Use host:port (without a URL scheme):

```dotenv
SAHOOL_AI_AGRONOMIST_UPSTREAM=${{sahool-ai-agronomist.RAILWAY_PRIVATE_DOMAIN}}:8000
SAHOOL_VEGETATION_ANALYSIS_UPSTREAM=${{sahool-vegetation-analysis.RAILWAY_PRIVATE_DOMAIN}}:8000
SAHOOL_RASTER_SERVICE_UPSTREAM=${{sahool-raster-service.RAILWAY_PRIVATE_DOMAIN}}:8001
SAHOOL_RAG_RETRIEVAL_UPSTREAM=${{sahool-rag-retrieval.RAILWAY_PRIVATE_DOMAIN}}:8000
```

The workspace route separately needs BFF, Indicators and Decision, with Task for
its task features. Supervisor/MCP is a separate route and is not required merely
for `/api/chat`. Missing optional upstream DNS does not justify redirecting their
requests to unrelated services or weakening authentication.

## Acceptance evidence

- Record tested source, image identity and Railway deployment IDs.
- All required probes return 200; stop on 4xx, malformed readiness or missing stores.
- Authenticated field read succeeds for its tenant; another tenant and a replayed
  assertion are rejected. No secret-bearing response or internal DSN is returned.
- Process one authorized field/date; verify valid pixels, provenance, durable DB
  metadata and asset readability after a controlled restart. Preserve missing data.
- Retrieval for different questions returns relevant cited records, with cross-tenant
  isolation. A field-specific chat uses server-owned context; untrusted injected
  context is rejected. Test generation and Guardrails separately before enabling it.
- Exercise the actual frontend routes. Do not label workspace, Decision or Task as
  complete until their services and authenticated operations have been verified.

Readiness repair limits: database probes plan zero-row reads under a read-only
transaction, verify RLS-safe ownership and required schema/function presence, and
close connections. Redis is pinged; its SET permissions/persistence are acceptance
checks. Raster writes/removes only a private temporary probe and verifies the STAC
catalog response; pixel processing, CDSE and S3 uploads remain acceptance checks.

## Existing notification rollout constraint

At `dac2cb0c5624555e3255199f9fdd0c9712c66ee8`,
`agents/notification/agent.py::_ensure_subscriptions` binds named durable push
consumers without a queue group. A live non-queue binding prevents a second
instance from acquiring those same consumers, so a rolling deployment can remain
at `/readyz` 503 while the previous deployment is healthy. This is separate from
DNS or missing credentials.

Before a planned handoff, record the active/replacement deployment IDs and each
consumer's creation time, acknowledgement floor, delivered sequence and pending
counts. Prepare the replacement image and inspect its actual startup failure.
A single-owner handoff needs an explicitly planned interruption of the old process;
retain the known-good image/configuration for rollback. Confirm all nine existing
consumers rebind, their state is preserved, and the replacement passes `/readyz`.
This handoff was not completed in the 2026-09-20 recovery: automatic approval review
blocked removal of the active deployment because of outage risk; the replacement
attempt was cancelled and the previous healthy deployment retained.

Do not delete/recreate the durable consumers, reset their positions, or substitute
`/healthz` for deployment readiness. Adding a queue name to the client alone does
not migrate the existing non-queue consumers. A queue-consumer migration requires
its own tested state-preservation and rollback plan.
