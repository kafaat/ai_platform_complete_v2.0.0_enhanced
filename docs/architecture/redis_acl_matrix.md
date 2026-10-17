# Redis ACL — one user per service (REDIS-SHARED-PASSWORD-NO-ACL-01)

**Defect (measured on `main@ec3927ce`):** both Redis servers in `docker-compose.v9.yml`
(`sahool-redis`, the cache; `sahool-redis-state`, the security state) started with
`--requirepass "${REDIS_PASSWORD}"` and nothing else. Thirteen clients carried that one password
(`redis://:${REDIS_PASSWORD}@…`), so every client was the `default` user with `+@all ~* &*`: the TTS
cache could `FLUSHALL` the cache server, and any client of `sahool-redis-state` could read refresh
tokens or clear account lockouts. No compose file defined an ACL.

**Owner decision (2026-09-30):** one ACL user per service. This is the second half of
`REDIS-CLIENTS-WITHOUT-PASSWORD-LIGHT-UNIFIED-01` (which put the password into every client URL).

**What the compose stack now does:**

- `default` is `off resetpass resetkeys resetchannels -@all` on both servers, so the shared
  password alone is refused (`WRONGPASS`).
- `REDIS_PASSWORD` is now only the password of the operator user `sahool-redis-admin`
  (`~* &* +@all`). The healthcheck uses it (`redis-cli --user sahool-redis-admin -a …`). No client
  carries it.
- Every Redis-consuming v9 service has a user named after its compose service, with its own
  password variable `REDIS_<…>_PASSWORD` (required with `:?`, no default), and only the commands,
  key patterns and channels its code uses.

The machine-readable source is [`redis_acl_matrix.json`](redis_acl_matrix.json). The `--user`
arguments in `docker-compose.v9.yml` must render **exactly** from it, and
`tests_v9/test_redis_acl_per_service.py` compares them. Each evidence entry in the JSON has
`path:line` (measured at `measured_at`) and a `needle` that the test re-checks in the file.

## Matrix

Every user also starts with `resetkeys resetchannels -@all`; what follows is all it is granted.
`+select` is granted only where the client URL uses a non-zero database (redis-py sends `SELECT` on
connect).

### `sahool-redis` (cache, `allkeys-lru`)

| User (= compose service) | Password var | Client env · db | Commands | Keys | Channels | Evidence (path:line) |
|---|---|---|---|---|---|---|
| `sahool-platform` | `REDIS_PLATFORM_PASSWORD` | `REDIS_URL` · 0 | ping get setex incr expire ttl exists | `sahool:ratelimit:*` `sahool:jti:revoked:*` `sahool:weather:tile:*` `sahool:weather:rate:*` | — | `services/sahool-platform/api/main.py:888-894` (rate limit INCR/EXPIRE/TTL) · `core/jwt_denylist.py:27,64,67` (SETEX/EXISTS) · `api/routers/weather.py:56,69,239,271,561-564` |
| `sahool-tts-service` | `REDIS_TTS_PASSWORD` | `REDIS_URL` · 2 | ping select get setex | `sahool:tts:*` | — | `services/tts-service/main.py:276,128` · `routers/tts.py:134,173` |
| `sahool-video-processor` | `REDIS_VIDEO_PROCESSOR_PASSWORD` | `REDIS_URL` · 3 | ping select | — | — | connection-only: `services/video-processor/main.py:112` reads the URL; no Redis client is built |
| `sahool-weather-service` | `REDIS_WEATHER_PASSWORD` | `WEATHER_REDIS_URL` · 4 | ping select get setex ttl | `sahool:weather:fresh:*` `sahool:weather:stale:*` | — | `services/weather-service/cache.py:39,43,29,74,114,59` |
| `sahool-field-management` | `REDIS_FIELD_MANAGEMENT_PASSWORD` | `FIELD_SERVICE_ASSERTION_REDIS_URL` · 5 | ping select set | `sahool:tenant-assertion:*` | — | `services/field-management-service/main.py:171` (SET NX EX) · `shared/security/service_tenant_assertion.py:33` · `shared/dependency_readiness.py:68` |
| `sahool-decision-service` | `REDIS_DECISION_PASSWORD` | operator-supplied `DECISION_WORKER_ASSERTION_REDIS_URL` | ping select set | `sahool:tenant-assertion:*` | — | `services/decision-service/main.py:237,221` · `shared/security/service_tenant_assertion.py:33` |
| `sahool-raster-service` | `REDIS_RASTER_PASSWORD` | `REDIS_URL` · 0 | ping get set del scan eval subscribe unsubscribe | `stac:*` `sahool:raster:job:*` `sahool:raster:indicator-batch:*` | `raster:layer_evict` | `services/raster-service/stac_client.py:116,134` · `job_store.py:32,88,134` · `indicator_batch_claim.py:18,88,104,105` · `layer_cache_events.py:15,75` |
| `sahool-raster-backfill-scan-worker` | `REDIS_RASTER_BACKFILL_PASSWORD` | `REDIS_URL` · 0 | ping get set del scan eval | same three key families | — | `services/raster-service/backfill_scan_worker.py:36,39` · `raster_asset_persistence.py:98` · `raster_runtime_state.py:16` |
| `sahool-actuator-service` | `REDIS_ACTUATOR_PASSWORD` | `REDIS_URL` · 0 | ping | — | — | connection-only: `services/actuator-service/actuator_runtime.py:442` |
| `sahool-ai-agronomist` | `REDIS_AI_AGRONOMIST_PASSWORD` | `SAHOOL_AGENT_REDIS_URL` · 0 | ping get set sadd srem smembers rpush lrange | `sahool:agent:approval:*` `sahool:agent:approvals:pending` `sahool:agent:audit` | — | `services/ai_agronomist/agent_stores.py:26-28,86-113,141` |
| `sahool-telegram-bot` | `REDIS_TELEGRAM_BOT_PASSWORD` | `REDIS_URL` · 0 | ping get set del | `fsm:*` | — | `bots/telegram/main.py:266,297` · aiogram 3.31.0 `RedisStorage` (`DefaultKeyBuilder(prefix="fsm")`; SET/GET/DELETE) |
| `sahool-notification-agent` | `REDIS_NOTIFICATION_PASSWORD` | `REDIS_URL` · 0 | ping | — | — | connection-only: no file under `agents/notification` or `agents/base_agent.py` mentions Redis |

### `sahool-redis-state` (security state, `noeviction` + AOF)

| User | Password var | Client env · db | Commands | Keys | Channels | Evidence |
|---|---|---|---|---|---|---|
| `sahool-auth` | `REDIS_AUTH_PASSWORD` | `REDIS_URL` · 0 | ping get getdel setex del exists expire ttl incr sadd smembers | `sahool:refresh:*` `sahool:user:refreshset:*` `sahool:user:token_floor:*` `sahool:jti:revoked:*` `sahool:lockout:*` `sahool:attempts:*` `sahool:ip_rate:*` `sahool:otp_rate:*` `sahool:otp:*` `sahool:reset:*` | — | `services/auth/main.py:375-971` · `otp.py:41` · `routers/password_reset.py:34` · `session_tokens.py:40` |
| `sahool-guardrails-engine` | `REDIS_GUARDRAILS_PASSWORD` | `REDIS_URL` · 0 | ping | — | — | connection-only: `redis>=5.0.0` in `requirements.txt:7`, no Python file imports it |

## Where precision stops (stated, not hidden)

- **`SCAN` is not key-scoped in Redis ACL.** Raster's job listing needs it, so raster can list key
  *names* of every key in its database (it cannot read them). No narrower rule exists.
- **Connection-only users** (video-processor, actuator, notification-agent, guardrails-engine):
  their compose environment carries a Redis URL, but their code builds no client. They get `PING`
  (plus `SELECT` for a non-zero db) and nothing else. The test fails if one of them starts building
  a Redis client, so its rules are derived then. Removing the URL altogether is a further step that
  is the owner's call (`scripts/ci/v9_feature_transfer_gate.py` and
  `tests_v9/test_infra_hardening_72h_static.py` still pin two of these URLs).
- **Telegram keys come from a third-party library** (aiogram's key builder), not from repo code.
  The bot's throttle middleware is built without a Redis client (`bots/telegram/main.py:272`), so
  `sahool:throttle:tg:*` stays in process memory and is not granted.
- **`sahool-auth` `MULTI`/`EXEC`** in `session_tokens.py` is a fallback for a client without
  `getdel`; redis-py has `getdel`, so the fallback is unreachable and not granted.
- **`RASTER_LAYER_EVICT_CHANNEL`** can rename the eviction channel. Compose does not set it; anyone
  who sets it must change the `&` rule too.
- **Pre-existing, outside this slice:** (1) `sahool-raster-cache-invalidation-worker` has no
  `REDIS_URL` in v9, so its eviction `PUBLISH` (`cache_invalidation_worker.py:62`) is skipped. No
  user is created for it; wiring it needs a user with `+publish &raster:layer_evict`. (2) The
  platform checks `sahool:jti:revoked:*` on the **cache** server while auth writes it on the
  **state** server. The ACL grants the platform what its code does; it does not repair that split.
- **Redis 7.2+ `CLIENT SETINFO`:** redis-py sends it on connect and ignores the error, so it is not
  granted. `+client|setinfo` would also break startup on Redis 7.0, where that subcommand is unknown.
- **Passwords sit in the server's argv** (visible to `docker inspect`), the same exposure as the
  previous `--requirepass`. An `--aclfile` rendered at start-up would avoid that, at the cost of an
  entrypoint script. Deliberately not done here.
- **`&` must be quoted in the compose `command`.** Compose splits the string with a shell-word
  parser and silently stops at a bare `&`. This was measured with `docker compose config`: 17 of
  175 arguments survived, so every user after the operator was dropped. The test enforces quoting.

## Client migration plan (for a running deployment)

The compose file holds the **final** state. A stack that is already running moves to it in three
steps, so that no client is ever without a working login:

1. **Add the users, with `default` still working.** Set every `REDIS_<…>_PASSWORD` in `.env`
   (each from `openssl rand -hex 32`, all different). Start the servers with the new `--user`
   lines, but replace the `default` line with
   `--user default on ">${REDIS_PASSWORD}" ~* "&*" +@all`, which is what `--requirepass` meant.
   Old clients (`redis://:${REDIS_PASSWORD}@…`) and new users both authenticate. Check this with
   `redis-cli --user sahool-redis-admin -a "$REDIS_PASSWORD" ACL LIST`.
2. **Switch clients one by one** to their compose URL `redis://<service>:${REDIS_<…>_PASSWORD}@…`
   and recreate each container. After each one, confirm on the server that its connections log in
   as the new user (`CLIENT LIST` shows `user=<service>`), and that `ACL LOG` has no `NOPERM`
   entries for it. A `NOPERM` means the matrix is missing a command, key or channel the code uses:
   fix the matrix and compose together (the test keeps them equal). Do not widen the user to `~*`.
3. **Disable `default`.** Restore the `--user default off …` line (the compose file as committed)
   and restart both servers. `CLIENT LIST` must show no `user=default` connection **before** this
   step. Any connection still using `default` is a client you missed.

**Rollback:** at any step, go back to step 1's `default on` line and restart the server. Clients
that are still on the shared password work again, and clients already switched keep working
(their users stay defined). The data is untouched; ACL changes do not touch keys.

**What breaks if a client is missed at step 3** (it still sends the shared password as
`default` and gets `WRONGPASS` on connect). This is derived from each client's error handling:

| Client | Production behaviour | Development behaviour |
|---|---|---|
| `sahool-auth` | refuses to start (`services/auth/main.py:382-383`) | `_redis = None`: revocation, lockout and refresh tokens silently off (`:385-386`) |
| `sahool-platform` | refuses to start (denylist, `api/main.py:1169`) | in-process denylist and rate limit (`:875`, `:1170`) |
| `sahool-field-management` | every tenant-asserted request returns 503 (`main.py:174-177`), readiness false | the same once a URL is set |
| `sahool-decision-service` | worker-asserted requests return 503 (`main.py:241-243`) when the URL is set | the same |
| `sahool-ai-agronomist` | refuses to start when `SAHOOL_AGENT_STORE_BACKEND=redis` (`agent_stores.py:145-146`) | in-memory approvals and audit (lost on restart) |
| `sahool-tts-service` | caching off, `/readyz` returns 503 degraded (`routers/health.py:34`) | the same |
| `sahool-weather-service` | memory cache per process (`cache.py:33`) | the same |
| `sahool-raster-service` / backfill worker | job store, STAC cache and batch claims fall back to process memory (`job_store.py:69-71`); jobs are not shared between processes; the eviction subscriber retries every 5 s | the same |
| `sahool-telegram-bot` | FSM storage is created lazily (`main.py:265-266`), so every stateful handler fails at use; readiness only reports `redis_ok=false` | the same |
| video-processor · actuator · notification-agent · guardrails-engine | nothing (no Redis command is issued) | nothing |

## Deploy impact

- **Compose only.** The changed files are `docker-compose.v9.yml`, `.env.example`, this document
  and its JSON, `tests_v9/`, and the needle in `scripts/ci/v9_feature_transfer_gate.py`. No service
  code changed. `docker compose -f docker-compose.v9.yml -f docker-compose.production.yml config`
  still resolves.
- **An existing compose deployment must set the 14 new `REDIS_<…>_PASSWORD` variables** (compose
  fails fast with `required` otherwise), and should follow the migration plan above if it cannot
  restart Redis and all clients together.
- **Railway is not affected and was not changed.** Railway runs `sahool-redis` and
  `sahool-redis-state` as its own services, with start commands and variables set in Railway, not
  from compose (`certification/evidence/railway_reconciliation_readonly_20261014.json`;
  `docs/runbooks/RAILWAY_DEPENDENCY_RECOVERY.md:133-139` still prescribes `--requirepass`, and
  `:125` builds `FIELD_SERVICE_ASSERTION_REDIS_URL` from the shared `REDIS_PASSWORD`). None of
  the files above is a Railway watch path, and no service image changes. **The same defect
  therefore remains on Railway.** Closing it there means applying the three-step plan to the
  Railway Redis start commands and service variables. That is an operator action, outside this
  slice.
