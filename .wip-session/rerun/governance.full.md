You are closing open gaps from the brain gap registry of kafaat/ai_platform_complete_v2.0.0_enhanced, deeply and completely where they are fixable in code. Read CLAUDE.md first and obey it. Your worktree is based on the coordinator's branch, which already contains a batch of v25-review fixes.

YOUR GAP IDs (governance/CI tooling): RUNNER-CRASH-READS-AS-A-TEST-FAILURE-WHEN-ITS-MESSAGE-SAYS-FAILED-01 · SWEEP-SELF-CHECK-CANNOT-TELL-A-GUARD-WRITE-FROM-MY-OWN-COMMIT-01 · BRAIN-HISTORICAL-GAP-ID-ALIAS-01 · ADMISSION-GROUND-STATED-IN-PROSE-ENFORCED-BY-NOTHING-01 · FROZEN-PATH-LIST-NAMES-A-FILE-THAT-DOES-NOT-EXIST-01 · TEXT-GUARD-ANCHORED-IN-THE-WRONG-FILE-01 · C-LOCALE-GUARD-SWEEPS-A-NAMING-CONVENTION-NOT-A-CLASS-01 · AUDIT-FINDINGS-NAMED-BUT-NOT-YET-MEASURED-BY-ME-01 · LESSON-READ-SUMMARY-NOT-TAIL-01 · LESSON-MERGED-GENERATED-ARTIFACTS-01.

METHOD for each ID: read its row in sahool-brain/gaps/registry.md (and any `## ` section with the same ID, which may carry more history), read its sources, reproduce the defect by measurement, then classify: (A) fixable in code now; (B) blocked by GATE-01 (frozen paths in docs/architecture/gate01_policy.json); (C) owner decision/policy; (D) needs a live environment/operation. Fix every (A) at the root with tests and falsification (show the test goes red when the fix is reverted). For B/C/D change nothing and report the exact blocker and the precise decision/authorization/operation needed (with a proposed patch for B). Specific cautions: for FROZEN-PATH-LIST-NAMES-A-FILE-THAT-DOES-NOT-EXIST-01, any change to the frozen list is a governance change — only correct a provably non-existent path to its real counterpart if it strictly strengthens the freeze and the gate01 guards/tests accept it; never remove or weaken protection; if in doubt, report. For BRAIN-HISTORICAL-GAP-ID-ALIAS-01, you may change the brain guard scripts, but not the brain files — propose the exact registry data change (e.g. an alias_of field) for the coordinator to apply. For LESSON-* rows, determine whether a tooling change removes the hazard (e.g. preflight printing its failure-summary line prominently / exit code wiring); otherwise classify them as process lessons.

COMMON RULES: Do NOT push or open PRs. Do NOT run scripts/ci/verify_all_generated.py or scripts/release/build_release_bundle.py (the coordinator regenerates centrally; if your change requires a generated artifact to change, name the file and generator command). Do NOT edit anything under sahool-brain/ (the coordinator updates the brain centrally; the registry is union-merged and concurrent row edits would duplicate rows). Commit messages may reference gap IDs only if they exist in the registry. No new general-purpose CI guard scripts (changing existing guards is fine, with a test and falsification). Ratchets may only go down, never up. The platform route budget is full (629/629). Never fabricate; measure and state limits. No Railway operations. FEATURE_NATS_PUBLISHERS stays false. Do not touch areas other agents are working on concurrently: nginx/nginx.v9.conf, docker-compose.v9.yml (ollama/qdrant-seed/local-ai-rag/rag-retrieval/nginx), services/raster-service, frontend/nginx.conf, deploy/railway/, services/mcp_servers/sentinel_hub_server.py, field.created imagery handling, vegetation/weather/canonical field state, TITILER_URL/REDIS_PASSWORD wiring, SAM2/edge readiness, the WOFOST adapter, JWT decode sites, frontend fetch layer. Code comments are Arabic-leaning prose naming the measured failure; match surrounding style.

Run ruff check/format on changed files, the tests you touched, and `bash scripts/ci/preflight.sh --fast`. Commit in your worktree (`git -c user.name=Claude -c user.email=noreply@anthropic.com commit`), Arabic commit messages in repo style, ending with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Pn1Px72XNWVxDq6QR2Ztgw

Final report (concise, one block per gap ID): class (A/B/C/D), root cause with file:line, fix + tests + falsification (for A), exact blocker and needed decision (for B/C/D), proposed brain registry state/text for the coordinator, commit SHAs + worktree branch, generated artifacts that need regenerating, limits.
---

## RE-RUN PROTOCOL (this overrides anything above that conflicts)

This is a **re-run**. A previous agent on this same task was killed by container restarts before it
handed back a report. Its uncommitted working tree was salvaged as ONE unverified commit:
`fa622cbd` (base `c1044010`). You may read it (`git show fa622cbd`, `git show fa622cbd:<path>`)
as a **lead only**. Nothing in it counts: it was never tested, reviewed or reported, and `main` has
moved since (≈10 PRs, #1099–#1107). Re-derive every claim, re-measure every defect on YOUR tree, and
never cherry-pick or copy it wholesale. If you reuse an idea from it, say so in the report.

Your worktree is based on current `main` (`bcb7f0ede37ddb509a9060e624445ca7ac1fdfa1`). Re-read each gap row there first: some IDs may
already be closed or changed by the merged PRs. Say so and skip them; don't redo merged work.

### Durability (non-negotiable, because the previous run was lost)

1. **Report file first.** Before any other work, create `/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/governance.report.md` whose first line is
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

### Report format (`/tmp/claude-0/-home-user-ai-platform-complete-v2-0-0-enhanced/f31fb6e3-fb2d-56ad-95cb-c3ae66c91adb/scratchpad/rerun/governance.report.md`)

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
