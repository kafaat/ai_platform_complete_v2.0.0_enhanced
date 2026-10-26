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
- main =  (#1289, AI review: 40 fixes + 35 open gaps), merged on the owner's explicit «دمج #1289 على ba1978cc2»; merge tree  == tested  tree. Railway (read-only ): exactly the derived deploy effect — prod decision/frontend/guardrails/notification, staging the same + ai-agronomist, migrator SKIPPED.
- In flight: PR #1291  at  (15 feature agents + integration; 966 flutter tests; LRM bidi chars escaped; Deploy-Effect NONE) ⇒ merge under delegation after green CI + tree check. Brain/measurement for #1289 rides in #1291.
- Chain change (measured on ): one  (it loops internally and builds/validates the release bundle) then commit then preflight; old chain's second  +  = 3 calls/473 steps vs 1 call/265 steps, regen 1661s→990s, regen trees identical. Use  (never edit a script while a run uses it). Wait loops must not  a pattern that matches their own command line.
- main = `accbfa7f8` (#1235), tree `76eb284d`.
- #1237 is open. Its head is `8bbef1f00` (main merged in to clear gate01). It waits for CI, then for an **explicit owner merge approval on that head**.
- Waiting on owner decisions:
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
