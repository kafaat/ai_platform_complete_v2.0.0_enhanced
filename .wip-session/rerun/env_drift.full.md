You are investigating and fixing P2 configuration findings from a live full-stack runtime audit of kafaat/ai_platform_complete_v2.0.0_enhanced (2026-09-29, docker-compose.v9.yml brought up on a clean machine with a .env derived from .env.example). Your worktree is based on origin/main. Read CLAUDE.md first and obey it.

COMMON RULES: Do NOT push or open PRs. Do NOT run scripts/ci/verify_all_generated.py or scripts/release/build_release_bundle.py. No Railway operations. Do not touch GATE-01 frozen paths (docs/architecture/gate01_policy.json frozen list; includes services/sahool-platform/api/event_bus.py, phase_runtime_*.py, actuator runtime/commands, migrations/*, docs/architecture/db_ownership.yml, scripts_v9/run_migrations.sql). No new general-purpose CI guard scripts. An in-flight PR (branch claude/project-exploration-dtjw3p, not in main) ALREADY fixes S3_BUCKET defaults and the pg-exporter POSTGRES_EXPORTER_DSN default in docker-compose.v9.yml, adds auth OTEL env and INDICATORS_SERVICE_URL — do not redo or touch those hunks. Measure, don't assume; falsify every new test. Code comments are Arabic-leaning prose naming the measured failure; match surrounding style.

TASK 1 — .env drift for TITILER_URL and REDIS_PASSWORD. The live audit reported these values as drifted between the operator's .env and what the containers need. For each variable: compare .env.example, every compose bundle (docker-compose.v9.yml primarily; also fixed/unified/light), and each consuming service's code (defaults, required-ness, URL shape, host/port/path, name mismatches, whether redis-server's requirepass and every client URL/password agree, whether a password is embedded in a URL without encoding). Identify the exact drift with file:line evidence, then fix in the repo (compose defaults and/or .env.example and/or code) so a fresh .env copied from .env.example yields working wiring. Keep the env guards passing: env_compose_drift_guard, compose_env_contract_gate, compose_no_default_secrets, env_compose_default_override, compose_auth_sink (find them in scripts/ci/). Add targeted tests. If the drift is purely in the operator's private .env with the repo already correct, say so with evidence instead of changing things.

TASK 2 — Model artifacts. The SAM2 weights and the edge ONNX models are missing on the audited machine (artifacts, not code). Verify that when absent, the SAM2 service and edge-inference report an honest not-ready state (e.g. 503 with a named reason on readiness, no fabricated inference) rather than healthy or crash-looping — measure by running each service app in-process (FastAPI TestClient) without the artifacts if feasible. Fix only if they misreport. Also examine the audit observation that Docker showed sahool-local-ai-rag, sahool-rag-retrieval and sahool-ai-agronomist as healthy while they were failing: inspect their compose healthchecks — if they deliberately probe liveness (/healthz) rather than readiness, report that as by-design with the trade-off; change nothing unless clearly wrong (another agent is separately fixing the Ollama/qdrant-seed ordering — do not touch sahool-ollama, sahool-qdrant-seed or local-ai-rag's model pulling).

Run ruff check/format on changed files, the tests you touched, and `bash scripts/ci/preflight.sh --fast`. Commit in your worktree (`git -c user.name=Claude -c user.email=noreply@anthropic.com commit`), Arabic commit messages in repo style, ending with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw

Final report (concise): commit SHAs + worktree branch (or "no commit" with reasons), exact drift found per variable with file:line, fixes and tests, model-artifact behaviour measured per service, limits.
---

## RE-RUN PROTOCOL (this overrides anything above that conflicts)

This is a **re-run**. A previous agent on this same task was killed by container restarts before it
handed back a report. Its uncommitted working tree was salvaged as ONE unverified commit:
`3ee89ce4` (base `c1044010`). You may read it (`git show 3ee89ce4`, `git show 3ee89ce4:<path>`)
as a **lead only**. Nothing in it counts: it was never tested, reviewed or reported, and `main` has
moved since (≈10 PRs, #1099–#1107). Re-derive every claim, re-measure every defect on YOUR tree, and
never cherry-pick or copy it wholesale. If you reuse an idea from it, say so in the report.

Your worktree is based on current `main` (`bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1`). Re-read each gap row there first: some IDs may
already be closed or changed by the merged PRs. Say so and skip them; don't redo merged work.

### Durability (non-negotiable, because the previous run was lost)

1. **Report file first.** Before any other work, create `/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/env_drift.report.md` whose first line is
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

### Report format (`/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/env_drift.report.md`)

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
