OWNER-APPROVED TASK: design and implement least-privilege NATS security in the canonical v9 compose stack of kafaat/ai_platform_complete_v2.0.0_enhanced. Read CLAUDE.md first and obey it. Your worktree is based on the coordinator's branch.

MEASURED STARTING POINT: nats/nats.conf already has `authorization { user: $NATS_USER, password: $NATS_PASSWORD }`; docker-compose.v9.yml makes the password required (`:?`), every client connects with `nats://${NATS_USER}:${NATS_PASSWORD}@sahool-nats:4222`, port 4222 is not published to the host, and there is no `no_auth_user`. What is missing: (1) every service shares ONE credential, so any service can publish/subscribe to any subject (it can impersonate another); (2) no TLS on the internal network. The physical-effect path does NOT go through NATS (actuator-service consumes a DB queue, signs HMAC, publishes via MQTT with allow_anonymous false) — keep it that way. The registry row NATS-BROKER-HAS-NO-AUTHENTICATION-SO-ACTUATOR-COMMANDS-ARE-UNGUARDED-01 describes the history.

OWNER CONSTRAINTS (binding): design and test in v9 compose only; do NOT touch Railway (staging has its own sahool-nats) — produce a written Railway rollout plan with a rollback instead; FEATURE_NATS_PUBLISHERS stays false (unchanged default); production must never run with self-signed certificates silently.

TASKS:
1. Per-service credentials + subject authorization: enumerate every service that connects to NATS (compose NATS_URL consumers and code) and, for each, the exact subjects it publishes and subscribes to, including JetStream API subjects ($JS.API.>, consumer/stream management it actually performs — note the notification agent creates the stream today, see JETSTREAM-STREAM-TOPOLOGY-OWNED-BY-A-CONSUMER-01; don't break that, just scope it) and request/reply inboxes (_INBOX.>). Use the repo's generated event contract graph if present, but verify against code. Give each service its own user with `permissions { publish { allow [...] } subscribe { allow [...] } }` (deny where needed), credentials from env with `:?` (no default secrets; keep compose_no_default_secrets / compose_env_contract / env_compose_drift guards green; add .env.example placeholders). Update each service's NATS_URL default in compose accordingly.
2. TLS: server TLS for sahool-nats and clients verifying it. Certificates must never be committed; for development, an init job may generate a local CA + server cert when absent and only when the environment is explicitly non-production (mirror the policy of the gateway certificate work: production with missing certs must fail loudly). Clients need the CA to verify (tls://…, or nats:// with TLS required) — make sure every Python client library in use (nats-py) is configured to verify, not skip verification.
3. Prove it live: download a real nats-server release binary (github.com release assets are reachable from this sandbox; no Docker) matching the image's major version, run it with your config, and show with nats-py clients: each service's credential can do exactly its allowed operations; publishing to another service's subject is rejected (permissions violation); unauthenticated and wrong-password connections are rejected; plaintext is rejected when TLS is required; the JetStream stream creation still works for the owning service. Add tests: static contract tests over nats.conf/compose (every connecting service has its own user; no user has publish `>`; every credential is `:?`-required) and, if feasible in CI, a live test that runs nats-server when the binary is available (skip otherwise, clearly labelled). Falsify.
4. Report the Railway rollout plan: which variables to add to which Railway services, order of operations, verification, and rollback — as a document in the report (do not execute).

COMMON RULES: Do NOT push or open PRs. Do NOT run scripts/ci/verify_all_generated.py or scripts/release/build_release_bundle.py (name artifacts + commands to regenerate). Do NOT edit anything under sahool-brain/. Commit messages may reference gap IDs only if they exist in the registry. No new general-purpose CI guard scripts (targeted tests fine). Never fabricate; measure and state limits. Do not touch GATE-01 frozen files (docs/architecture/gate01_policy.json frozen_paths). Other agents are concurrently editing: nginx/nginx.v9.conf + the v9 compose blocks for nginx/ollama/qdrant-seed/local-ai-rag/rag-retrieval (a gateway cert-init design — keep your cert approach consistent with it in policy, separate in files), services/raster-service, the weather/vegetation contracts, TITILER_URL/REDIS_PASSWORD wiring — keep your compose edits to NATS-related lines and hunks. Code comments are Arabic-leaning prose naming the measured failure; match surrounding style.

Run ruff check/format on changed files, the tests you touched, the compose/env guards, and `bash scripts/ci/preflight.sh --fast`. Commit in your worktree (`git -c user.name=Claude -c user.email=noreply@anthropic.com commit`), Arabic commit messages in repo style, ending with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw

Final report (concise): commit SHAs + worktree branch, the per-service permission matrix, TLS design and dev/prod policy, live measurement commands and results, tests + falsification, the Railway rollout + rollback plan, proposed brain registry text, limits.
---

## RE-RUN PROTOCOL (this overrides anything above that conflicts)

This is a **re-run**. A previous agent on this same task was killed by container restarts before it
handed back a report. Its uncommitted working tree was salvaged as ONE unverified commit:
`7fb7633b` (base `c1044010`). You may read it (`git show 7fb7633b`, `git show 7fb7633b:<path>`)
as a **lead only**. Nothing in it counts: it was never tested, reviewed or reported, and `main` has
moved since (≈10 PRs, #1099–#1107). Re-derive every claim, re-measure every defect on YOUR tree, and
never cherry-pick or copy it wholesale. If you reuse an idea from it, say so in the report.

Your worktree is based on current `main` (`bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1`). Re-read each gap row there first: some IDs may
already be closed or changed by the merged PRs. Say so and skip them; don't redo merged work.

### Durability (non-negotiable, because the previous run was lost)

1. **Report file first.** Before any other work, create `/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/nats.report.md` whose first line is
   `STATUS: RUNNING`. After **each** gap ID is finished (fixed, or classified B/C/D), append its
   section to that file immediately. Do not hold findings in memory to write at the end.
2. **Commit after each gap.** Each fixed gap gets its own commit in your worktree, as soon as its
   tests pass: `git -c user.name=Claude -c user.email=noreply@anthropic.com commit`, with a message
   that states the defect, the measurement and the falsification, ending with these two lines:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
   `Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw`
   Record the commit SHA in the report section for that gap.
3. **Do not push** (the coordinator integrates). **Do not create branches beyond your worktree's.**
4. When everything is done, change the report's first line to `STATUS: COMPLETE` and end your final
   message with the same summary. If you stop early for any reason, set `STATUS: INCOMPLETE — <why>`.
   A report still reading `RUNNING` will be treated as a failed run, not as silence.

### Scope rules for integration

- **Do not edit `sahool-brain/`.** Instead, put brain-ready text in the report: for each gap, the new
  status (`open`/`fixed`/`verified` — `verified` only for a live measurement), sources as `path:line`,
  and the evidence. The coordinator applies it centrally, citing the final commit SHAs.
- **Do not regenerate generated artifacts** (`verify_all_generated.py --fix`, `build_release_bundle`,
  inventories, catalog) and do not commit files under `*/generated/`, `release/`, or `*.generated.*`.
  The coordinator regenerates once, in a clean tree, after integration. If a test you need fails ONLY
  because an artifact is stale, note it in the report and move on.
- **Frozen/forbidden, unchanged:** `docs/architecture/db_ownership.yml`, `migrations/MANIFEST.txt`,
  `scripts_v9/run_migrations.sql`, every path in `docs/architecture/gate01_policy.json` frozen list;
  no Railway/NATS/database operation of any kind; no credential handling; no new general-purpose guards
  (targeted tests are fine). `FEATURE_NATS_PUBLISHERS` stays off.
- **Held paths:** changes under `agents/**`, `shared/**` or `migrations/**` are allowed only if a gap
  truly requires them. List every such file in the report under `HELD PATHS`: merging them redeploys
  the notification agent on Railway, which currently fails, so the coordinator will hold those commits.
  Keep them in separate commits from everything else.
- Tests: run the targeted tests for what you touch, plus `pytest -m unit` for the areas involved.
  Show each new test going **red** when its fix is reverted (falsification), and record that.
- Do not kill processes by name (`pkill`/`killall`); it has killed the coordinating shell before.
  Kill only PIDs you started.

### Report format (`/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/nats.report.md`)

```
STATUS: RUNNING | COMPLETE | INCOMPLETE — <why>
BASE: bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1
## <GAP-ID>
class: A-fixed | A-already-closed-on-main | B-GATE01 | C-owner | D-live
commit: <sha or —>
defect measured: <command + observed output, before>
fix: <what, where (path:line)>
falsification: <revert → which test red; restore → green>
brain row (proposed status + text): <…>
blocker / decision needed (B/C/D): <…>
## HELD PATHS
<files under agents/ shared/ migrations/, or "none">
## TESTS RUN
<commands + pass/fail/skip counts>
```
