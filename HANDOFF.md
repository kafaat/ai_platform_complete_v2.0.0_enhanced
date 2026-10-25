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
- main = `41a8c305f` (#1282, brain post-merge record). Verified 2026-10-25 via `git fetch` + `gh`: merge tree `b633d602` == tested head `1dc57b2ac` tree; CI 66 pass, 2 skipped, 0 failed.
- #1281 (unified gap slices) merged ⇒ `ad25eba0b`; merge tree `d5722012` == tested head `f95bdda65` tree (CI 83 pass + 1 skipped). It touched Railway deploy paths (gateway, notification agent, guardrails-engine, shared/**) by explicit owner order (option ب for ROLE-DICTIONARY); post-deploy verification is read-only and awaits Railway MCP re-authorization.
- The six gap rows touched by #1281 carry their «merged ⇒ SHA» line and all stay **open**; #1278/#1279/#1280 are superseded by #1281.
- Open on the owner: `Select-String -Path .env -Pattern '^MINIO_(MC_)?IMAGE='` output, to decide whether the stale MinIO image value comes from `.env` or the shell session (MINIO-IMAGES-DELETED-FROM-DOCKER-HUB-01).
- Local workspace note (Windows, v26): local `main` carries 13 old unpushed merge commits and lags origin; left untouched.
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
