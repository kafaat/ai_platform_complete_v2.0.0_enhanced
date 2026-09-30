You are closing open gaps from the brain gap registry of kafaat/ai_platform_complete_v2.0.0_enhanced, deeply and completely where they are fixable in code. Read CLAUDE.md first and obey it. Your worktree is based on the coordinator's branch, which already contains a batch of v25-review fixes.

YOUR GAP IDs (data paths and certification): EDGE-MODEL-DIGEST-CONTRACT-UNENFORCED-01 · RECONCILIATION-CURSOR-SKIPS-ROWS-THAT-BECOME-ELIGIBLE-01 · CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01 · TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01 · CONNECTIVITY-AUDIT-20260910 · CAP-INT-004-INTEGRATION · SENSOR-TELEMETRY-INGEST-REACHES-NO-AGRONOMIC-CONSUMER-01 · PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01 · CORRELATION-ID-ABSENT-FROM-THE-THREE-TABLES-THAT-CARRY-THE-DECISION-CHAIN-01 · IRRIGATION-WATER-SUITABILITY · REPORT2-C03-DEDUP-FOLLOWS-STREAM-MESSAGE-NOT-EVENT-ID-01 · REPORT2-C04-QUEUED-PUSH-RECEIPTS-HAVE-NO-CONSUMER-01.

METHOD for each ID: read its row in sahool-brain/gaps/registry.md (and any `## ` section with the same ID), read its sources, reproduce by measurement, then classify: (A) fixable in code now; (B) blocked by GATE-01 (docs/architecture/gate01_policy.json frozen paths — note adding a migration requires migrations/MANIFEST.txt, which is frozen); (C) owner decision/policy; (D) needs a live environment. Fix every (A) at the root with tests and falsification. Specific cautions:
- TYPED-CONTRACT-FORBIDS-ABSENCE-SO-THE-EDGE-INVENTS-ZERO-01: the absent-WIND behaviour is explicitly deferred to the owner (PLATFORM-CONNECTOR-STILL-COERCES-AN-ABSENT-WIND-TO-ZERO-01) — do not change wind handling; fix only other fields the row names as still coerced, if any.
- PRODUCTION-CERTIFICATION-VERDICT-IS-FORGEABLE-AND-UNREACHABLE-01: investigate the "unreachable" half precisely. Any change must not make certification easier to pass without real evidence, and you must never set production_certification / production_certified / overall_runtime_acceptance / runtime_verified to a passing value. If the only fix is to supply live evidence, classify as D.
- CDSE-EMPTY-SCENE-HAS-NO-ATTRIBUTABLE-CAUSE-01: another agent is changing field.created imagery invalidation — do not touch that code; limit yourself to recording/attributing empty CDSE scenes.
- RECONCILIATION-CURSOR-…: check first whether the cursor code is in a GATE-01 frozen file (e.g. phase_runtime_workers.py / phase_runtime_store.py / event_bus.py); if so, report with a proposed patch only.

COMMON RULES: Do NOT push or open PRs. Do NOT run scripts/ci/verify_all_generated.py or scripts/release/build_release_bundle.py (name artifacts + commands to regenerate). Do NOT edit anything under sahool-brain/. Commit messages may reference gap IDs only if they exist in the registry. No new general-purpose CI guard scripts. Ratchets only go down. The platform route budget is full (629/629). Never fabricate; measure and state limits. No Railway operations. FEATURE_NATS_PUBLISHERS stays false. Do not touch areas other agents are working on concurrently: nginx/nginx.v9.conf, docker-compose.v9.yml ollama/qdrant-seed/local-ai-rag/rag-retrieval/nginx blocks, services/raster-service, frontend/nginx.conf, deploy/railway/, services/mcp_servers/sentinel_hub_server.py, field.created imagery invalidation, vegetation contracts, weather schema_version / canonical field state, TITILER_URL/REDIS_PASSWORD wiring, SAM2/edge readiness, the WOFOST adapter, JWT decode sites, the frontend fetch layer, scripts/ci guard internals, service startup retry logic. Code comments are Arabic-leaning prose naming the measured failure; match surrounding style.

Run ruff check/format on changed files, the tests you touched, relevant unit subsets, and `bash scripts/ci/preflight.sh --fast`. Commit in your worktree (`git -c user.name=Claude -c user.email=noreply@anthropic.com commit`), Arabic commit messages in repo style, ending with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw

Final report (concise, one block per gap ID): class, root cause with file:line, fix + tests + falsification, exact blocker/decision where not fixed, proposed brain registry state/text for the coordinator, commit SHAs + worktree branch, generated artifacts to regenerate, limits.
---

## RE-RUN PROTOCOL (this overrides anything above that conflicts)

This is a **re-run**. A previous agent on this same task was killed by container restarts before it
handed back a report. Its uncommitted working tree was salvaged as ONE unverified commit:
`3116b861` (base `c1044010`). You may read it (`git show 3116b861`, `git show 3116b861:<path>`)
as a **lead only**. Nothing in it counts: it was never tested, reviewed or reported, and `main` has
moved since (≈10 PRs, #1099–#1107). Re-derive every claim, re-measure every defect on YOUR tree, and
never cherry-pick or copy it wholesale. If you reuse an idea from it, say so in the report.

Your worktree is based on current `main` (`bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1`). Re-read each gap row there first: some IDs may
already be closed or changed by the merged PRs. Say so and skip them; don't redo merged work.

### Durability (non-negotiable, because the previous run was lost)

1. **Report file first.** Before any other work, create `/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/data_path.report.md` whose first line is
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

### Report format (`/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/data_path.report.md`)

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
