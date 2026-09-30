STATUS: COMPLETE
BASE: 1cb6cd6c2e01851bb9afa49d1fb1a4bfb35ee277 (worktree HEAD; brief said bcb7f0ed, main has moved)

## NATS-AUTHORIZATION-NOT-ENFORCED (contract gap in docs/architecture/nats_subject_ownership_contract.json; the residual of brain row NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01)
class: A-fixed
commit: 96f6a034 (worktree branch `worktree-agent-a0fac3de0e9209a7e`, on top of 1cb6cd6c)
defect measured (on 1cb6cd6c, before):
- `nats/nats.conf` had one `authorization { user: $NATS_USER, password: $NATS_PASSWORD }` and no `permissions`, `tls`, or `default_permissions`. 13 compose services carried that one credential in `NATS_URL`. Any credentialed service could therefore publish or subscribe on any subject: forge `sahool.events.*` as the platform, read `_INBOX.>` (where the notification agent's JetStream push deliveries go), or delete the `sahool` stream.
- Checked by grep: 3 of those 13 (`sahool-soil-service`, `sahool-weather-service`, `sahool-telegram-bot`) contain no NATS client at all. `soil main.py:37` reads the variable and never uses it; `bot_readiness.py:20` says so itself.
- Port 4222 was plaintext (no `tls` block).
- Found along the way, and also present on main: nats-server parses env-variable values with its config parser. A password like `3e0f9c2b7a` makes the broker refuse to start (`variable reference … could not be parsed`). `1000`, `true` and `256MB` also fail. Measured on 2.14.6 and 2.15.0 against main's own nats.conf (`probe_pw.py` in scratch). The failure is loud (named variable) and never silent.
fix:
- `nats/nats.conf`: 10 users, one per connecting service, named after the compose service. Each password comes from `$NATS_<X>_PASSWORD`. Permissions are derived from code (matrix below). `default_permissions` denies everything. There is no `no_auth_user`, and no user publishes or subscribes to `>`. Each user's reply inbox is `_INBOX_<user>.>`, except the notification agent, which keeps `_INBOX.>` because its legacy durables deliver to `_INBOX.<nuid>` and queue_v1 delivers to `_INBOX.sahool.notification.*`. A `tls {}` block with cert and key under `/etc/nats/tls` makes TLS mandatory. User blocks: nats/nats.conf:85-280. `tls`: nats/nats.conf:65. `default_permissions`: nats/nats.conf:75.
- `docker-compose.v9.yml`:
  - New `sahool-nats-tls-init` (compose :366). `sahool-nats` now requires the 10 `NATS_*_PASSWORD` values with `:?`, `depends_on` the init with `service_completed_successfully`, and mounts `./nats/tls/server:/etc/nats/tls:ro`.
  - Each of the 10 clients gets `NATS_URL: tls://<service>:${NATS_<X>_PASSWORD:?…}@sahool-nats:4222` (the shared `${NATS_URL:-…}` override is gone, because a shared URL would collapse every service into one identity), `SSL_CERT_DIR: /etc/sahool/nats-ca:/etc/ssl/certs`, and the volume `./nats/tls/ca:/etc/sahool/nats-ca:ro`.
  - `NATS_URL` removed from soil, weather-service and telegram-bot. The `depends_on: sahool-nats` of weather-service and telegram-bot is removed too.
- `scripts/nats/ensure_nats_tls.sh` (new) follows the same policy as `ensure_gateway_tls.sh`. With `SAHOOL_ENV` explicitly development/dev/local/test and no material present, it generates a dev CA and a server cert (SAN DNS:sahool-nats, localhost, 127.0.0.1; O=SAHOOL-DEV-SELF-SIGNED), then deletes the CA key. Otherwise it validates what is there: readable, key matches, not expired, chains to `ca/ca.pem`, SAN includes `DNS:sahool-nats`, and exactly one CA certificate. Outside dev it refuses dev material and self-signed server certs. It writes the `<subject_hash>.0` trust index that `SSL_CERT_DIR` needs and removes stale indexes. Named failures: NATS_TLS_MISSING, PARTIAL, EXPIRED, KEY_MISMATCH, CHAIN_INVALID, NAME_MISMATCH, CA_BUNDLE_UNSUPPORTED, DEV_MATERIAL_OUTSIDE_DEV, SELF_SIGNED_OUTSIDE_DEV, TOOLING_MISSING.
- Client code, reply-inbox prefix only (no held paths):
  - `services/sahool-platform/api/main.py:570-571`. The line budget stays at 2553/2553; a 2-line comment was merged into 1.
  - `services/vegetation-analysis-service/vegetation_runtime.py:530`
  - `services/weather-polygon-worker/src/main.py:161-164`
  - `services/sahool-platform/workers/canonical_execution_learning_worker.py:261` (INBOX_PREFIX; placed below the tenant-GUC site so the baselined :117 does not move), plus `retarget_foreign_deliveries` (:264) called from `run()` (:386); connects at :338 and :371. This one is measured, see "upgrade path" below.
- Unchanged, because they don't need it: the notification agent (keeps `_INBOX`), phase_runtime_workers.py (GATE-01 frozen; Core publish only, no inbox), and the relay (Core subscribe only).
- TLS on the client side needs no code. When INFO says `tls_required`, nats-py 2.10/2.16 upgrades with `ssl.create_default_context()`, which means CERT_REQUIRED plus a hostname check. The broker CA reaches that context through `SSL_CERT_DIR`, which is additive: the default `SSL_CERT_FILE` system bundle stays in use. Verification is therefore on, not skipped. The live test proves this: with an empty trust dir the client gets `SSLCertVerificationError`, and with the wrong `tls_hostname` it gets the same error.
- `.env.example`: the 10 placeholders, the letter-first password rule (`echo "n$(openssl rand -hex 32)"`) and the TLS instructions. `NATS_URL=` is kept for tooling outside compose. `.gitignore`: `nats/tls/`.
- `docs/architecture/nats_subject_ownership_contract.json`: `connected_services` goes from 13 to 10, and gap `NATS-AUTHORIZATION-NOT-ENFORCED` becomes CLOSED with `verified_by` and `residual`. `docs/architecture/component_registry.json`: `sahool-nats-tls-init` added as an infrastructure unit.
- `.github/workflows/notification-rollout.yml`: a new step runs `tests_v9/test_nats_least_privilege.py` with `NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1` against the job's checksum-pinned nats-server 2.15.0, using nats-py 2.16.0 (the agent's pin). This is a targeted test step, not a guard script.
- Tests updated for the new truth: `test_nats_broker_authentication.py` (per-service vars, 13 → 10), `test_nats_subject_ownership_contract.py` (the open-gap snapshot is replaced by the closure evidence), `tests/runtime/test_phase17_runtime_bootstrap_doctor.py` (safe_env gets the 10 vars), and `guard_mutation_registry.json` (4 moved anchors and 8 new mutations; the headroom cap reason is under falsification), and `test_env_compose_default_override_guard.py`. That test anchors on the historical `${NATS_URL:-…}` form, which compose no longer reads; it now asserts that compose does not read `NATS_URL`.

Permission matrix (non-`$JS` part derived from code; `test_every_non_jetstream_permission_is_what_the_code_needs` checks both directions):

| identity (compose service) | publish allow | subscribe allow | source |
|---|---|---|---|
| sahool-platform | `sahool.events.>` | `_INBOX_sahool-platform.>` | OutboxWorker → make_jetstream_publisher; subject is `'sahool.events.' \|\| p_event_type` (migrations/v18:97); only runs when FEATURE_NATS_PUBLISHERS=true (unchanged false) |
| sahool-phase-runtime-outbox-worker | `sahool.phase9.execution.plan.created`, `sahool.phase9.autonomy.cycle.completed` | deny `>` | persist_runtime_event(event_type=…) in phase9_autonomous_farm_os.py, dotted by build_outbox_action |
| sahool-plugin-runtime-worker | `sahool.plugin.execution.requested` + 9 KNOWN_HOOKS dotted (`sahool.field.updated` … `sahool.digital.twin.snapshot.created`) | deny `>` | phase_runtime_workers.py:280,301 |
| sahool-model-registry-worker | `sahool.model.promotion.requested`, `sahool.model.rollback.requested` | deny `>` | :398,:446 |
| sahool-actuator-dispatch-worker | `sahool.actuator.dispatch.requested` | deny `>` | :507 (a delivery notice with `physical_effect=False`; the physical path stays DB queue → HMAC → MQTT) |
| sahool-reservation-dispatch-relay-worker | deny `>` | `sahool.events.irrigation.reservation.dispatch_requested`, `…dispatch_failed` | irrigation_dispatch_relay.SUPPORTED_DISPATCH_EVENTS |
| sahool-canonical-execution-learning-worker | `$JS.API.INFO`, `$JS.API.STREAM.NAMES`, and for each of its 3 durables (`canonical-execution-learning-v1-{irrigation-execution-completed,season-closed,agronomy-projection-requested}`): `CONSUMER.INFO`, `CONSUMER.DURABLE.CREATE`, `$JS.ACK.sahool.<d>.>` | `_INBOX_sahool-canonical-execution-learning-worker.>` | durable_for_subject(compose default base, SUBJECTS) |
| sahool-notification-agent (stream owner) | `sahool.notification.dead_letter`, `$JS.API.STREAM.INFO.sahool`, `$JS.API.STREAM.CREATE.sahool`, `$JS.API.STREAM.NAMES`, `$JS.API.CONSUMER.INFO.sahool.*`, DURABLE.CREATE × 9 legacy names, CONSUMER.CREATE × 9 `_queue_v1` names, `$JS.ACK.sahool.<name>.>` × 18 | `_INBOX.>` | agent.py `_ensure_subscriptions`, `_dead_letter`; shared/notification_consumers.SUBSCRIPTIONS/apply_plan. No STREAM.DELETE/PURGE/UPDATE and no CONSUMER.DELETE (live-refused) |
| sahool-weather-polygon-worker | `sahool.weather.field.overlay.completed`, `$JS.API.STREAM.NAMES`, `CONSUMER.INFO`, DURABLE.CREATE, and both CREATE forms for `polygon-worker`, `$JS.ACK.sahool.polygon-worker.>` | `_INBOX_sahool-weather-polygon-worker.>` | src/main.py:165,186 (scaffold, flag OFF) |
| sahool-vegetation-analysis | `sahool.tenant.*.satellite.*.computed` | `_INBOX_sahool-vegetation-analysis.>` | vegetation_runtime.py:531 |

TLS design and dev/prod policy:
- The server requires TLS (`tls {}`, so INFO carries `tls_required=true`). Plaintext CONNECT is dropped with no reply (live).
- Clients use the default nats-py verifying context and trust the broker CA through `SSL_CERT_DIR=<ca-dir>:/etc/ssl/certs`.
- Material lives in `./nats/tls/` (gitignored):
  - `server/` holds the server pair and is mounted only into sahool-nats.
  - `ca/` holds `ca.pem` and the hash index, with no key, and is mounted read-only into the 10 clients.
- Generation happens only when `SAHOOL_ENV` is explicitly non-production. In production, missing material fails with NATS_TLS_MISSING, and leftover dev material or a self-signed server cert fails by name. The broker never starts silently on self-signed material.

Live measurement (sandbox, no Docker):
- Binaries: nats-server v2.14.6 (checksum 61c3d55f…, the version inside the pinned image digest `sha256:ad7a43eb…`, amd64 manifest label `2.14.6-alpine3.22`) and v2.15.0 (checksum 5d2c51ca…, matching the CI pin; this is the version Railway runs).
- Clients: nats-py 2.10.0 (platform pin) and 2.16.0 (agent pin).
- Command: `NATS_LEAST_PRIVILEGE_LIVE_REQUIRED=1 NATS_SERVER_BIN=<bin> [PYTHONPATH=<nats-py-2.16>] python3 -m pytest tests_v9/test_nats_least_privilege.py tests_v9/test_nats_tls_init.py`.
- Results with the final commit (live file + TLS-init file, 50 cases per pair):
  - 2.14.6+2.10.0: 49 passed, 1 skipped (named: queue_v1 needs server ≥2.15).
  - 2.14.6+2.16.0: 49 passed, 1 skipped (same reason).
  - 2.15.0+2.10.0: 49 passed, 1 skipped (named: validate_stream needs nats-py 2.16).
  - 2.15.0+2.16.0: 50/50 passed.
- CI replica: python3.12 venv with only `agents/notification/requirements.txt` + pytest + pytest-asyncio, nats-server 2.15.0: 25/25 passed, 0 skipped.
- What these runs prove:
  - Anonymous, wrong-password and cross-identity-password connections get `Authorization Violation`.
  - Plaintext CONNECT gets no reply, the socket closes and no user is authorised.
  - An untrusted CA or wrong hostname gives `SSLCertVerificationError`.
  - Each identity publishes its own subjects; for every other identity's subjects plus 3 extra subjects, it gets `Permissions Violation for Publish`.
  - Subscriptions to `>`, `sahool.>`, `sahool.events.>`, other identities' inboxes and `_INBOX.>` (for non-notification users) are refused.
  - Real code paths work: agent-style `add_stream` and 9 legacy `js.subscribe`; the platform's real `make_jetstream_publisher` gets a PubAck; the canonical worker's real `subscribe_subjects` receives and acks; vegetation gets a PubAck; the agent can publish dead letters; queue_v1 `build_plan`/`apply_plan`/`subscribe_bind` all work under the scoped identity.
  - The owner cannot delete, purge or update the stream; non-owners cannot create an `eavesdrop` consumer.
  - The frozen `phase_runtime_workers._publish_nats` stores its own subject; a forbidden subject is refused, raises nothing, and does not reach the stream (the limit below).
  - `connz` shows `tls_version` and the `authorized_user`.
- Upgrade path, measured on a persisted store (`probe_migration.py`):
  - Consumers created under main's single identity: the notification agent's 9 legacy durables re-bind with no violation.
  - The canonical worker's durables deliver to `_INBOX.<nuid>`. Under the new config, `js.subscribe` returned normally, the broker logged a `Subscription Violation`, and the worker received nothing — idle, with a green healthcheck.
  - Fix: `retarget_foreign_deliveries` updates the durable's `deliver_subject` in place through `CONSUMER.DURABLE.CREATE`. On 2.14.6 and 2.15.0 the ack floor was unchanged (2 → 2). A live test covers it.
- An open broker (no auth, which is Railway's state today) accepts a client whose URL already carries `user:password` and an inbox prefix, and it returns a PubAck (`probe_open_creds.py`, 2.15.0). That makes the Railway client-first order below safe.

falsification:
- Registered mutations: all 16 new ones plus the 4 re-anchored existing ones were planted with `scripts/ci/guard_mutation_guard.py --run --only <file>`, and each turned its named test red:
  - nats.conf: 8/8
  - compose: 7/7 (includes 1 unrelated MCP mutation already in that spec)
  - ensure_nats_tls.sh: 4/4
  - canonical worker: 1/1
- `tests_v9/test_mutation_sweep_headroom.py` caps the registry at 775 declared mutations (base was 767; 16 new would make 782). Raising the cap needs a re-measured Unit Tests job time, which I can't do from here. So **8 new ones are committed**, bringing the total to 775:
  - nats.conf: publish `>`, `_INBOX.>`, dropped frozen subject, TLS block disabled
  - compose: borrowed identity, `SAHOOL_ENV:-development`
  - ensure_nats_tls.sh: self-signed accepted in prod, generate everywhere
- The other 7 were measured red but are not registered. The coordinator can re-add them after re-measuring the headroom anchor:
  - `STREAM.CREATE.*`
  - `default_permissions` allow
  - tls-init `condition: service_started`
  - client `SSL_CERT_DIR` dropped
  - CA key leaked into `ca/`
  - stale trust index kept
  - canonical `inbox_prefix` dropped
  (`scratchpad/nats/edit_registry.py` holds their exact specs.)
- `preflight.sh --fast` re-planted every registered NATS mutation: green.
- Live falsification (`live_falsify.py`, nats-server 2.15.0 + nats-py 2.16.0, byte-exact restore): 7/7 red on the named live test:
  - removing the `tls{}` block → plaintext and monitoring tests red; clients using `tls://` then connected in plaintext, which also measures the downgrade limit
  - vegetation + `sahool.events.>` → publish-matrix test red
  - platform + `_INBOX.>` → subscription test red
  - `no_auth_user` → anonymous test red
  - notification + `STREAM.DELETE` → destroy test red
  - disabling retarget → takeover test red
  - dropping one notification DURABLE.CREATE → JetStream end-to-end test red
- One falsification caught a vacuous test, which I fixed. The first version of the live publish and subscribe tests took their "forbidden" set from nats.conf itself, so broadening nats.conf stayed green (measured 2/7 GREEN). The tests now take their expectations from code (`_expected()`).
brain row (proposed status + text):
- `NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01`: status stays **fixed**. Replace the "حدُّ صدقٍ" residual (one credential, no permissions, no TLS) with: «**تحديث 2026-09-30 — أُغلِق الحدّ الباقي في v9:** هويّةٌ لكلّ عميلٍ من العشرة في `nats/nats.conf` بصلاحيّاتٍ مُشتقّةٍ من شيفرته (لا `>`، صندوقُ ردٍّ باسمها، `default_permissions` ترفض كلّ شيء)، وTLS مُلزَمٌ بمادّةٍ يفحصها `sahool-nats-tls-init` (تطويرٌ صريحٌ فقط يولّد؛ الإنتاجُ بلا مادّةٍ أو بمادّةٍ ذاتيّة يفشل مُسمّىً). ثلاثُ خدماتٍ بلا عميلٍ نُزِع عنها الاعتماد (13→10). مُثبَتٌ حيّاً على nats-server 2.14.6 و2.15.0 مع nats-py 2.10.0 و2.16.0 (`tests_v9/test_nats_least_privilege.py`، يُشغَّل مُلزَماً في `notification-rollout.yml`). المصدر: <commit>.» Sources: nats/nats.conf:65-280 · docker-compose.v9.yml (sahool-nats-tls-init, sahool-nats) · scripts/nats/ensure_nats_tls.sh · tests_v9/test_nats_least_privilege.py · tests_v9/test_nats_tls_init.py.
- Contract gap `NATS-AUTHORIZATION-NOT-ENFORCED`: status **verified** in the sense that live positive and negative probes were measured, in the sandbox and in a CI-identical venv. It becomes CI-verified once the notification-rollout step runs on the PR.
- New row proposed: `NATS-ENV-PASSWORD-PARSED-AS-A-CONFIG-VALUE-01`, status **open** (mitigated by documentation). Text: «nats-server يُعرِب قيمةَ متغيّر البيئة المُستوفى في nats.conf بمُعرِب الإعداد: `3e0f9c2b7a` تُقرأ عدداً فيرفض الإقلاع، و`1000`/`true`/`256MB` كذلك. قائمٌ على main مع `$NATS_PASSWORD` (مقيس 2.14.6 و2.15.0). الفشلُ صاخبٌ مُسمّى. الإرشادُ في `.env.example`: حرفٌ ثمّ hex؛ وشاهدٌ حيّ `test_live_a_password_that_looks_like_a_number_stops_the_broker_loudly`.» Closure would need either password validation before start, or bcrypt/NKeys.
- New row proposed: `NATS-CORE-PUBLISH-PERMISSION-REFUSAL-IS-SILENT-IN-FROZEN-WORKERS-01`, status **open**, owner/GATE-01. Text: «`phase_runtime_workers._publish_nats` (مجمَّد GATE-01) ينشر Core NATS ثمّ `flush`؛ رفضُ الإذن لا يرفع (مقيس حيّاً) فيُوسَم الصفُّ `published`. مُحتوًى بعقدٍ ساكنٍ يُطابِق قائمةَ كلّ عاملٍ بشيفرته بالتمام؛ الإغلاقُ يحتاج تفويضَ GATE-01 لتحويله إلى `js.publish` مُقِرّ.»
blocker / decision needed:
- The Railway rollout below is the owner's decision.
- Also the owner's decision: whether path3-runtime-verification.yml (self-hosted, `staging-pg16`) should get the 10 new secrets and NATS TLS material on its runner. That workflow still passes `NATS_USER`/`NATS_PASSWORD`, which compose no longer reads. With this commit it will fail on `docker compose config` (`NATS_PLATFORM_PASSWORD … missing`) until those secrets exist, and on `sahool-nats-tls-init` unless `nats/tls/` is provisioned or SAHOOL_ENV is development. It fails loudly, and it already needed gateway TLS material after #1103. I did not edit the workflow's secret names because that is credential provisioning.

## NATS-ON-RAILWAY-STAGING-HAS-NO-AUTH-AND-A-FLOATING-TAG-01
class: C-owner (not touched: no Railway call of any kind, reads included; the plan below relies on the registry row and repo docs)
commit: —
defect measured: not re-measured, since touching Railway was forbidden. The registry row (sahool-brain/gaps/registry.md:15) says staging runs `nats:2-alpine`, floating, resolving to 2.15.0, with zero variables, no config, and no auth. `docs/evidence/railway_audit_review_20260920.md:73` says notification runs `queue_v1` on nats-py 2.16.0.
fix: none. Below is the **Railway rollout plan with rollback**, for the owner to decide and execute.

### Railway rollout plan (not executed)
Principle: clients change first, the broker last. Rollback is one broker redeploy.

**Measured facts this order depends on:**
- An open broker (Railway today) accepts clients whose URL already carries `user:password` and an inbox prefix, and returns a PubAck (`probe_open_creds.py`, nats-server 2.15.0).
- The notification agent's existing consumers (legacy `_INBOX.<nuid>` and queue_v1 `_INBOX.sahool.notification.*`) re-bind under its scoped identity with no violation (`probe_migration.py`).
- The canonical worker self-retargets its durables and keeps their ack floor.

0. **Freeze and read (owner, read-only).** Record:
   - `sahool-nats` deployment id, image digest and whether it has a **volume**. Without a volume, every broker redeploy loses the `sahool` stream and all consumers, including the operator-provisioned `*_queue_v1` ones, which then need `shared.notification_consumers --plan/--apply` again. If there is no volume, add one **before** anything else, as its own step with its own verification.
   - `nats stream info sahool` and `nats consumer ls sahool` (deliver subjects).
   - The list of services with `NATS_URL`. Each one that connects needs an identity; the v9 list is the 10 in nats.conf. On Railway, confirm which of them exist (platform, notification, vegetation are confirmed by the audit; the others are unknown to me).
1. **Pin the image** (separate change, no behaviour change): `nats:2.15.0-alpine@sha256:<digest of the running 2.15.0>`. Verify: boot log `Version: 2.15.0`, stream and consumers intact.
2. **Deploy client code** (the services/* part of 96f6a034, `inbox_prefix` plus canonical retarget) with **no env change**. Clients keep `nats://…railway.internal:4222` with no credentials, which the open broker accepts. Verify: each service is healthy; notification `/readyz` is 200; queue_v1 bound 9/9.
   - The notification agent code is unchanged, so this step does **not** redeploy it. That keeps clear of NOTIFICATION-AGENT-LEGACY-PUSH-CONSUMERS-BLOCK-ZERO-DOWNTIME-REDEPLOY-01 until step 4.
3. **Create the 10 passwords** as variables on `sahool-nats` only: `NATS_<X>_PASSWORD`, **letter-first**, e.g. `n` + `openssl rand -hex 32` — a digit-first value can stop the broker (measured).
4. **Point each client at its identity** with Railway reference variables, one service at a time, e.g. on sahool-platform: `NATS_URL=nats://sahool-platform:${{sahool-nats.NATS_PLATFORM_PASSWORD}}@${{sahool-nats.RAILWAY_PRIVATE_DOMAIN}}:4222`. Use `nats://` without TLS on Railway (see TLS note).
   - The broker still has no auth, so credentials are ignored and nothing breaks.
   - The notification agent is redeployed here. That is the held queue_v1 decision: do this step for notification only once its redeploy works.
   - Verify per service: healthy, and in the connz output (`http://sahool-nats:8222/connz?auth=1` via a private shell) the client name is present.
5. **Switch the broker config.** Railway has no config file today, so it needs a small image `FROM nats:2.15.0-alpine@sha256:…` with a Railway variant of nats.conf baked in. Railway variant = **the same `authorization` block** (users, permissions and default_permissions byte-identical to nats/nats.conf) **without the `tls {}` block**, start command `-c /etc/nats/nats.conf`. Keep one source of truth: generate the variant from nats/nats.conf by removing the tls block, with a test asserting the authorization blocks are identical. That file is not created in this commit, because Railway was out of scope.
   - Redeploy `sahool-nats`. Clients reconnect automatically (nats-py reconnects; the canonical worker restarts under `restart`).
6. **Verify** within about 10 minutes:
   - connz shows every connection with `authorized_user`, and no anonymous connection.
   - Notification `/readyz` 200, queue_v1 9/9, pending draining.
   - Platform outbox stays `record_decision_only` (FEATURE_NATS_PUBLISHERS=false, unchanged).
   - Negative probe from a private shell with the vegetation credential: publishing `sahool.events.x` gives `Permissions Violation`.
   - The broker log has zero `Authorization Violation` from real services.
   - Any `Publish Violation` in the broker log from `phase-runtime` users means a subject missing from the list. Those refusals are **silent** on the worker side, so the broker log is the only witness.
7. **Rollback** at any point after 5: redeploy the previous `sahool-nats` deployment (open broker). Clients whose URLs carry credentials keep working, because an open broker ignores them (measured), so no client change is needed. Reverting client URLs (step 4) is optional. Stream and consumers survive if a volume exists (step 0).
- **TLS on Railway:** deferred and optional. Railway's private network is already encrypted between services (WireGuard), and nats-server cannot read its cert from an env var. It would need an image build with operator certs or a volume, plus `SSL_CERT_DIR` for clients. Recommendation: auth+ACL first (steps 1–7), then decide on TLS separately.

brain row (proposed status + text): stays **open**. Add: «خطّةُ الطرح مكتوبةٌ في تقرير 96f6a034 (عملاءُ أوّلاً بعناوينَ تحمل الهويّة — مقيسٌ أنّ الوسيطَ المفتوح يقبلها — ثمّ صورةُ الوسيط بإعداد authorization المطابق لـv9 بلا tls؛ الرجوعُ إعادةُ نشرِ الوسيط السابق وحدَه). تنتظر قرارَ المالك وقرارَ queue_v1 لوكيل الإشعارات، وتأكيدَ وجود volume للوسيط قبل أيّ إعادة نشر.»
blocker / decision needed: the owner decides on execution, the notification-agent queue_v1 migration (gates step 4 for notification) and whether the broker has a volume (gates step 5).

## HELD PATHS
none. No file under `agents/`, `shared/` or `migrations/` changed in 96f6a034, and the notification agent needs no code change: it keeps `_INBOX.>`, and its TLS trust comes from env (`SSL_CERT_DIR`). Note for the coordinator: the change is still one unit on the v9 side. Merging it requires every v9 operator to set the 10 new variables and have `nats/tls/` material (generated automatically with `SAHOOL_ENV=development`).

## GENERATED ARTIFACTS LEFT STALE (regenerate centrally, not done here)
- `docs/runbooks/GUARD_CATALOGUE.md`: `python scripts/ci/guard_catalogue.py`. Stale because of the registry change (`test_guard_catalogue` red, stale-only).
- `docs/architecture/tenant_guc_scope_baseline.json` provenance: `python3 scripts/ci/tenant_guc_scope_guard.py --generate`. The input sha of main.py / canonical worker changed and the result is unchanged; `PROVENANCE_STALE` (`test_tenant_guc_scope_guard::test_the_tree_matches_the_declared_baseline` and `test_measurement_basis_freshness` ×2 red, stale-only).
- Likely also stale (not measured): capability/architecture projections that scan compose/tests. That covers `architecture/generated/architecture_graph.json` and `platform_catalog.generated.json` (the new `sahool-nats-tls-init` unit), and the capability witness inventories (2 new test files). Run `scripts/ci/verify_all_generated.py --fix` centrally.

## TESTS RUN
- `ruff check` + `ruff format --check` on all changed Python files: clean.
- Compose/env guards (`compose_env_contract_gate`, `compose_no_default_secrets_guard`, `env_compose_default_override_guard`, `env_compose_drift_guard`): all rc=0.
- `docker compose config`: with a CI-style dummy env, rc=0. With `NATS_VEGETATION_PASSWORD` missing, rc=1 naming it.
- `bash scripts/ci/preflight.sh --fast` on the final commit: 0 failures, 0 skipped. It re-plants the registered NATS mutations.
- `scripts/ci/guard_mutation_guard.py` (static): ok. `--run --only` for nats.conf, compose, ensure_nats_tls.sh and the canonical worker: every mutation red on its named test.
- `pytest tests_v9/test_nats_least_privilege.py tests_v9/test_nats_tls_init.py`:
  - Without a binary: 13 static + 25 TLS-init passed, 12 live **skipped with the "LIVE PROOF SKIPPED" label** (this is the Unit Tests job's view).
  - With binaries (matrix above): 49–50/50 per pair.
  - CI replica: 25/25.
- `pytest -m unit tests_v9` (serial, before the last two fixes): 7949 passed, 8 failed, 17 skipped. After fixes, 4 failures remain, all stale-generated (listed above), plus 1 environment artifact: `test_dockerfile_pip_mirror_guard` skips any path containing `.claude`, and my worktree lives under `.claude/worktrees/`, so it finds 0 Dockerfiles. That is unrelated to this change. The earlier real failures were fixed and re-run green: component_registry (added `sahool-nats-tls-init`), env override (historical anchor), mutation headroom (trimmed to the 775 cap), and tenant GUC line (block moved).
- Related suites green: test_nats_broker_authentication, test_nats_subject_ownership_contract, test_canonical_execution_learning_worker_subscriptions, test_outbox_requires_jetstream_ack, test_telegram_bot, test_container_command_path_guard, test_compose_services_are_declared_as_services, tests/runtime/test_phase17_runtime_bootstrap_doctor (6/6), test_text_encoding_locale, test_env_compose_default_override_guard, test_component_registry_gate, test_mutation_sweep_headroom.

## LIMITS (honest)
- **Consumer-create is scoped by name, not by filter subject.** nats-py (2.10 and 2.16) sends `CONSUMER.DURABLE.CREATE.<stream>.<name>` without the filter, so the holder of a permitted durable name could create it with a wider filter.
- **Frozen phase-runtime workers publish Core NATS without an ack.** A permission refusal there is silent (measured live), and the row is marked `published`. It is contained by the exact code↔config static match; closing it needs GATE-01 authorisation.
- **No handshake_first.** Clients upgrade only when INFO says `tls_required`. An impostor broker on the internal network with the name `sahool-nats` that advertises no TLS would receive CONNECT in plaintext. The `tls://` scheme does not force TLS in nats-py (read in its code, and measured: with the tls block removed, clients using `tls://` connected in plaintext). Fixing it needs `tls_handshake_first` on clients, including the frozen worker.
- **Passwords are plaintext in the broker env** (server warns "Plaintext passwords detected"). bcrypt or NKeys would need a second variable per service.
- **nats-server parses env values as config.** A digit-first or number-like password stops the broker. This is also present on main, is loud, and is documented.
- **Existing polygon-worker durables** (if any) would face the same `_INBOX.` retarget issue as the canonical worker. It is not handled because the worker is a disabled scaffold (`WEATHER_GRID_PIPELINE_ENABLED` off, never connects).
- **path3-runtime-verification.yml** (self-hosted) still maps `NATS_USER`/`NATS_PASSWORD` secrets. It will fail loudly until the owner adds the 10 secrets and NATS TLS material on its runner.
- **No Docker in the sandbox.** `docker compose up` of the v9 stack was not run. The compose wiring is proven by `docker compose config` plus the static contract; broker behaviour is proven on the real binaries with the same nats.conf and the same init script.
- **Salvaged commit 7fb7633b was a lead only.** Ideas it shares with this work: the per-user `_INBOX_<user>` prefix and the users named after compose services. It also had a `connect_broker` helper in shared/ and `handshake_first`; I did not take those, to avoid held paths, and did not take its `_INBOX.>` grant to the canonical worker, which would reopen eavesdropping. I replaced the latter with the measured retarget. I re-derived and re-measured everything here.
