# Product gaps: bounded acceptance, 2026-10-18

Base: `1765d73a036499318beeb6d267fdaf803e4b0a40` (merged #1213).
Implementation/test source: `de800e0` (resolve full SHA with git).
One PR per latest owner instruction; no merge authorized.

## Commands and observations

Python 3.12, pytest 9.1.1, ruff 0.15.8. HTTP proof rerun with repository FastAPI 0.136.3, Pydantic 2.13.4, PyJWT 2.15.0. Redis 7.2.6 built locally from upstream tag commit `ae6a2aa95cd094b032e7a69b8b59f64dd1ed085f` (MALLOC=libc).

```bash
REDIS_SERVER_BIN=/path/to/redis-server REDIS_ACL_LIVE_REQUIRED=1 python -m pytest tests_v9/test_raster_invalidation_redis_acl.py -q --override-ini addopts=''
REDIS_SERVER_BIN=/path/to/redis-server REDIS_ACL_LIVE_REQUIRED=1 python -m pytest tests_v9/test_raster_invalidation_redis_acl.py tests_v9/test_redis_acl_per_service.py -q --override-ini addopts=''
python -m pytest tests_v9/test_b6_real_guardrails_evaluation.py -q --override-ini addopts=''
M4_REQUIRE_PG16=1 python -m pytest tests_v9/test_m4_bootstrap_pg16.py -q --override-ini addopts=''
```

- Redis: copy the new regression test onto unmodified base source. `redis-main-red.txt`: static failure missing worker identity; live failure missing worker URL. Branch: `redis-branch-green.txt`, 142 passed, one existing parameterized test skips Lua on the state server which has no raster user. The new regression itself passes both cases without skips. Real subscriber acknowledges subscription before publishing; GET, SET, SUBSCRIBE, other channel PUBLISH and FLUSHALL return Redis NoPermissionError (NOPERM).
- B6: `b6-main.txt` and `b6-branch.txt` both pass. This adds evidence for already-landed behavior, so a red-main behavior claim would be false. The actual ASGI HTTP route uses real repository tiers; valid evaluation stays disallowed, banned/unknown chemical and excessive investment have named findings, invalid evidence returns 422, missing token is refused. DB connect/pool and approval creation entry points fail the test if called. No service lifespan, database audit, agronomic validation, chat integration or free-text enablement is claimed.
- M4: `m4-environment-blocked.txt` records fail-closed missing PG16 configuration, not a product failure. Workflow prepares a disposable PG16 with the existing processing_jobs DDL and existing tenant policy read from init_v8.sql; no migration file added or changed. Separate restricted role transactions exercise advisory lock waiting, SKIP LOCKED, cross-tenant reads/writes, stale/expired lease and persisted retry window. This suite has not run on PG16 locally; CI must execute it before any live-proof claim. No red/green claim is available.

## Acceptance levels

| Scope | Local | CI | staging | Production |
|---|---|---|---|---|
| Redis compose configuration | red/green measured, actual Pub/Sub and ACL | not measured | not measured | not measured |
| M4 | suite prepared; live PG16 BLOCKED_BY_ENVIRONMENT | not measured | not measured | not measured |
| B6 | real-rule ASGI route passed; no lifespan | not measured | not measured | not measured |
| Six owner decisions | source-reviewed documents only | not measured | not measured | not measured |
| Six RAG gaps | docker info failed; see separate raw record | not measured | not measured | not measured |
| Element84 | runbook only; no database contact | not measured | not measured | not measured |
| INT-004BC | proposed interface only; no machine evidence | not measured | not measured | not measured |

Redis scope is compose only, not Railway or full memory-cache eviction; Pub/Sub remains at-most-once. Only its configuration gap is fixed. M4/B6 flags and provider/chat wiring stay disabled. RAG retains NOT_YET_AUTHORITATIVE; no evaluation set, corpus, prefix, model or seeding changes. #1182 was merged at `9a50aac3bf71ed42f4fad91a036d49e61d151a52`; its mitigation cannot recover the historical CDSE cause.
