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
- main = `1e125a7b9` (#1286, brain-only post-merge record for #1285): merge tree `b0514213` == tested head `d7d3aca87` tree; CI 66 pass, 2 skipped, 0 failed. Records Railway deploys of #1285 (read-only `list-deployments`): production frontend/auth-main/vegetation SUCCESS; staging soil/frontend/vegetation SUCCESS, auth-main SUCCESS 03:11Z; migrator not run. New gap PR-DEPLOY-EFFECT-CLAIM-NOT-DERIVED-FROM-WATCH-PATTERNS-01 (#1285's body claimed gateway-only; test files under deployed service folders trigger redeploys). MOBILE-FIELD-FORM-SCREEN-UNREACHABLE-FROM-NAVIGATION-01 and SERVICE-LOCAL-TESTS-UNRUN-BY-CI-01 carry merge-record lines but stay **open**: brain-only `fixed` is rejected (#1136 rule); promote them in the next PR that touches code.
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
