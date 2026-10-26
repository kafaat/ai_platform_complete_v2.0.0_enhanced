# HANDOFF — SAHOOL PR stewardship (work_id: sahool-pr-stewardship-20261019)

Location: `/home/user/.work-state/sahool-pr-stewardship-20261019/` (outside the repo tree, v2 §2). Backup: only `state.json` + `HANDOFF.md` on `claude/backup-work-state-20261019`.
Read `state.json` first, but treat it as RECORDED_UNVERIFIED until checked against git and GitHub (v2 §1). `transitions.jsonl` is the append-only history.
Do not trust chat memory, tool task IDs or old PIDs as evidence that something is running.

## Resume in 5 steps
1. `git fetch origin --prune` and compare `origin/main` with `state.json → main.head`. If main moved, find out who moved it before acting.
2. For each `in_progress` item, read its PR on GitHub, including the current head, CI on that head and mergeability. Do not rely on the saved head alone.
3. Before any heavy run, check `pgrep -af "pytest|preflight"`. Then use `bin/run_locked.sh <label> <cmd…>`, which holds a lock shared by every worktree.
4. Long suites: run `bin/sharded_tests.py --worktree <clean worktree>`. Results bind to head + tree + env + command digest, and base_head and merge_base are recorded. The script stops if free disk drops below 1 GB. Use `--status` to see which shards are done. Report the result as "sharded verification", never as a connected preflight run.
5. After every step that has an effect, run `bin/ws.py set …` or `bin/ws.py event …`. Record results with `bin/ws.py checksum <file>`. After each milestone, run `bin/backup.sh`, which fast-forwards `claude/backup-work-state-20261019` and verifies the remote ref.

## Where things stand (verify, do not assume)
- main = `5c7e1cb83` (#1292), merged on the owner's «قوم بالدمج» for head `a75ba1968`; merge tree `64a9bcf3` == tested tree. Railway (read-only): sahool-frontend prod `0d92bbe6` + staging `a4b63968` SUCCESS (owner-confirmed Online); 22 others + migrator SKIPPED. The API fix is NOT in production: `deploy/sahool-staging-fa92a1f7` (prod, 2026-09-15) is 243 commits behind main and `deploy/sahool-platform-db-ready-eb6da9df` (staging, 2026-10-17) 161 behind; neither contains it. Promoting them is the owner's decision. Owner also confirmed resourceful-commitment cause: Railpack builds the repo root without a service target.
- main = `bc764f760` (#1293, pip mirror): every compose pip build (56) forwards `PIP_INDEX_URL` defaulting to `https://mirrors.aliyun.com/pypi/simple/`; Dockerfiles keep PyPI (CI/Railway unchanged). Owner chose «Default in compose only». Merged under delegation (Deploy-Effect NONE); merge tree `97af90cf` == tested `05fdd57f7` tree; 70 pass + 2 skipped.
- In flight: PR #1292 `claude/platform-idempotency-20261026` at `a75ba1968` (tree `64a9bcf3`, on `bc764f760`): lab sample POST + task PATCH honour Idempotency-Key; brain gap RAILWAY-STRAY-PROJECT-FAILS-EVERY-MAIN-COMMIT-01. Local preflight 0/0. History rebuilt (force-with-lease) because gitleaks flagged `_KEY = "<uuid>"` test literals at old head `9f2fbc085`; constant now `_REPLAY_ID`. Deploy-Effect production+staging[sahool-frontend] (catalog counter 62→64 + fingerprint) ⇒ **merge only on the owner's explicit approval of the final head**.
- Owner action outside the repo: Railway project `resourceful-commitment` (53063514-…) fails every main commit's status (red ✗); delete it, disconnect its source, or configure a real build.
- main = `84f29f2fa` (#1291, mobile rebuild): merged under delegation (Deploy-Effect NONE); merge tree `414b362b` == tested `31da4bc6e` tree; 73 checks green. Nothing in flight.
- main = `775e63bff` (#1289, AI review: 40 fixes + 35 open gaps), merged on the owner's explicit «دمج #1289 على ba1978cc2»; merge tree `b8f49cdb` == tested `ba1978cc2` tree. Railway (read-only `list-deployments`, 16:32Z-16:35Z): exactly the derived deploy effect — prod decision/frontend/guardrails/notification, staging the same + ai-agronomist, migrator SKIPPED.
- In flight: PR #1291 `claude/mobile-overhaul-20261026` at `31da4bc6e` (15 feature agents + integration; 966 flutter tests; LRM bidi chars written as `\u200E` escapes; Deploy-Effect NONE) ⇒ merge under delegation after green CI + tree check. The #1289 deploy measurement and brain record ride in #1291.
- Chain change (measured on `aab05b3b7`): one `verify_all_generated --fix` (it loops internally and builds/validates the release bundle), then commit, then preflight. Old chain (second `--fix` + `--check`) = 3 calls / 473 steps vs 1 call / 265 steps; regen 1661s → 990s; regen trees identical `eccfd388` incl. `release/`. Use `bin/chain_bench_frozen.sh <wt> <label> new`. Never edit a script while a run uses it; wait loops must not `pgrep -f` a pattern that matches their own command line; write heredocs that contain backticks with a quoted delimiter.
- Previous backup of this file (before 2026-10-26 19:10Z) was taken from the backup branch checkout; the work-state copy was older. Rebuilt from backup `4cd7ab666` + this block.
- main = `dde126886` (#1287, deploy-effect tool): merge tree `19382d55` == tested head `3992f7fc1` tree; CI 66 pass + 2 skipped. `scripts/ci/railway_deploy_impact.py` derives the PR's `Deploy-Effect` from `docs/architecture/railway_watch_patterns.json` (read-only Railway capture 2026-10-26T09:39:58Z); five measured merges replay derived == built. Staging tts-service is pinned to `d301c136` and does not follow main. MOBILE-FIELD-FORM and SERVICE-LOCAL-TESTS rows promoted to fixed.
- In flight (not merged): `claude/ai-review-fixes-20261026` — full AI review, 40 fixes + 35 open gaps (report `sahool-brain/reports/ai_review_20261026.md`); redeploys guardrails/decision/notification (prod+staging) + ai-agronomist (staging) ⇒ held for OWNER merge approval. Mobile overhaul with 20 agents: foundation on `claude/mobile-foundation-20261026`, audits in session scratchpad.
- Before it: main = `1e125a7b9` (#1286, brain-only post-merge record for #1285): merge tree `b0514213` == tested head `d7d3aca87` tree; CI 66 pass, 2 skipped, 0 failed. Records Railway deploys of #1285 (read-only `list-deployments`): production frontend/auth-main/vegetation SUCCESS; staging soil/frontend/vegetation SUCCESS, auth-main SUCCESS 03:11Z; migrator not run. New gap PR-DEPLOY-EFFECT-CLAIM-NOT-DERIVED-FROM-WATCH-PATTERNS-01 (#1285's body claimed gateway-only; test files under deployed service folders trigger redeploys). MOBILE-FIELD-FORM-SCREEN-UNREACHABLE-FROM-NAVIGATION-01 and SERVICE-LOCAL-TESTS-UNRUN-BY-CI-01 carry merge-record lines but stay **open**: brain-only `fixed` is rejected (#1136 rule); promote them in the next PR that touches code.
- Before it: main = `73355f509` (#1285, 26-agent fix fleet in one PR): merge tree `6013f756` == tested head `00ec67d35` tree; CI 81 pass + 2 skipped; main CI Unit Tests (run 40260916782) green incl. the new service-local tests step. Owner decisions: `sahool-brain/reports/owner_decisions_20261026.md`.
- Before it: main = `ae30a0fcf` (#1284, brain: owner's MinIO `.env` measurement): merge tree `7955d406` == tested head `dafa92af5` tree; CI on that head all green (2 skipped), diff = `sahool-brain/log.md` + `hot.md` only. Records: `.env` in owner's `v26` holds the coollabsio mirror values, no `MINIO_*` in the session; decisive check still open on the owner: `docker compose -f docker-compose.v9.yml pull sahool-minio sahool-minio-init` from `v26`.
- Before it: main = `2c7637563` (#1283, log-only correction): merge tree `aa422ad6` == tested head `ccbfeb824` tree; CI on that head 66 pass, 2 skipped, 3 cancelled by superseded runs whose re-runs passed, 0 failed. It appends one `log.md` entry correcting #1282's line on the MINIO-IMAGES row: `run_all` probes `/minio/health/live` (`scripts_v9/run_all.sh:89`, `run_all.ps1:112`); `mc ready local` is the Compose healthcheck (`docker-compose.v9.yml:550`). The row itself still carries the wrong phrase; move the correction into it with the first code/evidence change for that gap.
- Before it: main = `41a8c305f` (#1282, brain post-merge record). Verified 2026-10-25 via `git fetch` + `gh`: merge tree `b633d602` == tested head `1dc57b2ac` tree; CI 66 pass, 2 skipped, 0 failed.
- #1281 (unified gap slices) merged ⇒ `ad25eba0b`; merge tree `d5722012` == tested head `f95bdda65` tree (CI 83 pass + 1 skipped). It touched Railway deploy paths (gateway, notification agent, guardrails-engine, shared/**) by explicit owner order (option ب for ROLE-DICTIONARY); post-deploy verification is read-only and awaits Railway MCP re-authorization.
- The six gap rows touched by #1281 carry their «merged ⇒ SHA» line and all stay **open**; #1278/#1279/#1280 are superseded by #1281.
- Open on the owner: `Select-String -Path .env -Pattern '^MINIO_(MC_)?IMAGE='` output, to decide whether the stale MinIO image value comes from `.env` or the shell session (MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01).
- Local workspace note (Windows, v26, owner-reported): local `main` reset to `origin/main`; the 14 local commits (incl. local-only `AGENTS.md` and `audit-reports/`) are kept on local branch `backup-local-main`; three uncommitted Dockerfile edits are in `stash@{0}` (do not drop before review).
- Everything below this entry dates from 2026-10-19 and was NOT re-verified today; treat it as RECORDED_UNVERIFIED history, not current state.
- Old 2026-10-19 entry: main = `accbfa7f8` (#1235), tree `76eb284d`.
- Old 2026-10-19 entry: #1237 was open at head `8bbef1f00`; current state unknown, re-read GitHub before acting.
- Old 2026-10-19 owner-decision list (not re-verified):
  - deleting the two `codex/*-blob-transfer-20261019` branches;
  - a PR adding the research-correction notes;
  - a read-only Railway check for `accbfa7f8`.

## Hard rules (from the owner)
See the `constraints` list in `state.json`. In short:
- No merge without explicit approval on the final head.
- No force-push on shared branches.
- Railway is read-only, and the incident freeze is in force.
- Brain files are append/prepend-only, and the U+200F counts must stay fixed.
- Never run preflights concurrently.

## Files
- `logs/`: preflight and test logs, named `<what>-<pr>-<head>.log`.
- `results/`: JSON from `run_locked.sh`; sharded results go under `results/sharded/<tree>/<marker>/`.
- `checkpoints/`: earlier state snapshots.
- `checksums.sha256`: SHA-256 of every recorded artifact.

## Resume point — 2026-10-20 14:10Z (after the owner-approved merges)
- `main` = `b7d765236` (#1248, documentation; tree `64d65713` == tested `236542aae`), on top of
  `18239b410` (#1244 S3 endpoint policy + legacy TiTiler gate; tree `2baa6549` == tested `e93f3e80a`).
- Earlier in this session: #1241 `d480c6ef0`, #1242 `3559ae024`, #1245 `11338da60`; #1243 closed unmerged (branch kept).
- Gaps: S3-ENDPOINT-SCHEME-DOWNGRADED-TO-PLAINTEXT-01 and TITILER-LEGACY-S3-BYPASSES-ENDPOINT-POLICY-01 fixed (merged);
  open: TITILER-LEGACY-USES-SHARED-ADMIN-S3-KEY-01, UWRP-V43-LEARNING-SCRIPTS-UNSAFE-01.
- Not tested, by the freeze: the season-logbook HTTP endpoint (needs `season_records`, i.e. migrations).
- Owner decision pending elsewhere: deleting the orphan `dependency_inventory.generated.json` and `.csv`
  (generator removed in `9ddde2c26`; `docs/runbooks/DOCKER_BUILD_CHECKLIST_CRITICAL_AND_EXTENDED_SERVICES_20260710.md:40` still cites the deleted guard).
- No open PR from this session. Worktrees `wt_s3tls` and `wt_hot` hold merged branches only.

## Resume point 2026-10-25T05:00Z
- main = 2890baf22.
- Merged under the owner delegation ("أنت مفوض", 2026-10-25), each with merged tree == tested tree:
  - #1268 TiTiler read-only account → c492ee12a (tree 8a3e3221; TITILER-LEGACY-USES-SHARED-ADMIN-S3-KEY-01 fixed).
  - #1270 gap sweep → 2890baf22 (tree 7f9ea4c3): triage report sahool-brain/reports/gap_triage_20261025.md; RAG-06 offline slice; GITLEAKS merge-scan gap fixed; ledger records the delegation and the deploy-effect exclusion.
- Open: #1271 frontend npm advisories, head 5111f71b2 (worktree /home/user/wt_fedeps). CI was green on 2d8358a1b. The merge deploys the frontend to production, so it waits for the owner's explicit word.
- Held local branch: claude/gap-notification-agent-legacy-push-consumers-block-z-20261025 (fdc2da5ec). Needs a tenant_guc_scope_baseline refresh and capability-mapping regeneration. Touching agents/notification/** redeploys on Railway, so it also waits for the owner.
- Gaps by triage category: 30 need an owner decision, 22 blocked by the freeze, 14 need a live environment.
- Local environment fix: the OTel family for python3.11 is aligned to 1.45.1/0.66b1. The earlier failures came from pip installing into python3.13.
- Lesson: never use `pgrep -f NAME` inside a command line that itself contains NAME (it matches itself). Run jobs sequentially instead.
