# Branch consolidation audit — 2026-10-12 (read-only)

Repository `kafaat/ai_platform_complete_v2.0.0_enhanced`, `main` = `29c09d0b`. Nothing was deleted, merged, or deployed; Railway was only read.

## Result

| Classification | Count |
|---|---|
| SAFE_TO_DELETE | 387 |
| NEEDS_REVIEW | 44 |
| ACTIVE_DEPENDENCY | 17 |
| REQUIRES_INTEGRATION_REVIEW | 141 |
| PRESERVED_NO_CONTENT_LEFT | 5 |
| **total** | 594 |

## How each class was decided

- **SAFE_TO_DELETE (387):** the branch tip is an ancestor of `main`, or its PR was squash-merged with exactly this tip and replaying the tip onto the squash commit's parent yields the squash commit's tree byte-for-byte (`git merge-tree`). Every one is also reachable from `refs/pull/<N>/head` or `main`, which GitHub does not delete — so deleting the branch name loses no commit. Not a Railway source branch, not referenced by any workflow, no open PR.
- **NEEDS_REVIEW (44):** 43 PRs #504–#539 (June) whose merge commits exist but are not ancestors of today's `main` (history after them was rewritten; three merge commits are absent locally), so equivalence cannot be proven against current `main`; all still restorable via `refs/pull`. Plus `develop`, which workflow triggers still name.
- **ACTIVE_DEPENDENCY (17):** `main`, `claude/project-exploration-dtjw3p` (staging TTS source, #1122), `claude/claude-md-docs-p6qqir`, the five `deploy/*` (Railway sources: `deploy/sahool-staging-fa92a1f7` production platform+auth, `deploy/sahool-platform-db-ready-eb6da9df` staging platform), and every open-PR head.
- **REQUIRES_INTEGRATION_REVIEW (141) / PRESERVED_NO_CONTENT_LEFT (5):** the 124 no-PR and 22 closed-unmerged branches, kept for separate analysis as instructed. 5 of them add nothing to `main` today.

## Dependency checks performed

- Railway (read-only `describe-environment`, both environments): repo-sourced services build only from `main`, `claude/project-exploration-dtjw3p`, `deploy/sahool-staging-fa92a1f7`, `deploy/sahool-platform-db-ready-eb6da9df`. None is a deletion candidate.
- GitHub Actions: workflow branch filters on `main` name `main`, `release/**` and `develop`; `develop` moved to NEEDS_REVIEW.
- Open PRs: all 10 heads (and #1129's base) classed ACTIVE_DEPENDENCY.

## Backup / restoration

- `branch_audit_20261012.csv` holds every branch's full head SHA, merge-base, PR history and a ready restore command (`git push origin <sha>:refs/heads/<branch>`).
- For all 387 SAFE_TO_DELETE and the 44 NEEDS_REVIEW the head commit is held by `refs/pull/<N>/head` or `main` (verified per branch, column `restorable_via`), so the restore command works after deletion. The 146 preserved branches have no such ref for most — they are not candidates.
- Not yet done (needs your call): a durable copy of this CSV inside the repository (a PR), since this container is ephemeral.

## Unique work in the 141 preserved branches

Integration difficulty against `main@29c09d0b`: {'source_conflicts': 109, 'brain_or_generated_only': 3, 'clean_unique': 23, 'generated_only_conflicts': 6}.

- **clean_unique (23):** merge cleanly and add something. Most are one-off CI repair labs (`codex/*-repair-lab-*`, `codex/publish-*`, `ops/conflict-resolution-*`) — workflows created for a single incident; integrating them would add dead workflows. Product-relevant: `claude/wip-v25b-sam2` (SAM2 ref pin + freshness workflow), `claude/wip-v25b-tiler`, `claude/wip-v25b-erp` (compose/ERP provider), `claude/wip-agent-ratchets-jwt-held` (frontend e2e + weather static tests, 40 source files), `codex/merge-tree-preservation-20260921` (guard, closed PR #1063).
- **generated_only_conflicts (6):** source merges cleanly, only generated files conflict. `claude/wip-voice-consult-57847492` and `claude/wip-tts-review-tests` belong with #1122; `claude/wip-vegetation-rs256` is superseded by #1128 (v2).
- **source_conflicts (109):** diverged from `main` in source files; each needs a human read before anything is carried forward. Listed in the CSV with their source files.

## Proposed next steps (each needs your approval)

1. Delete the 387 SAFE_TO_DELETE branch names in batches of 50, each batch re-verified immediately before deletion.
2. Read the 6 product-relevant clean_unique branches and the 6 generated-only ones and decide which enter the two integration branches; the CI repair-lab branches look like candidates for deletion after a glance.
3. Triage the 109 source-conflict branches by area (CSV column `source_files_changed`).
