---
name: ci-impact-preflight
description: "Inspect SAHOOL CI gates, generated artifacts, and cross-service test impact before push or PR. Use for code/contract changes; not for a documentation-only question."
metadata:
  version: "0.1.0"
  adoption: "STATIC_REVIEW_PENDING"
---
# SAHOOL CI Impact Preflight (pilot)

**Purpose:** Predict *which checks apply*, reproduce their actual commands and source-derived prerequisites, and produce a truthful pre-push receipt. Do not claim a local green run guarantees GitHub CI or production readiness.

## 0. Read the governing implementation, not only reports
- Read `.github/workflows/*.yml` / `*.yaml`, `scripts/ci/preflight.sh`, `docs/architecture/preflight_required.json`, `scripts/ci/verify_all_generated.py`, and the exact referenced generator/check scripts.
- Read `.claude/skills/adaptive-test-accelerator/SKILL.md` for long suites, `.claude/skills/failure-investigation/SKILL.md` for unknown failures, and `.claude/skills/skill-evaluator/SKILL.md` before promoting this skill.
- Verify actual CLI options with `--help` or source. Never invent flags or assume a documented command still exists.

## 1. Freeze context
Capture current HEAD, tree, base HEAD, merge-base, changed files including untracked files, Python/Node versions, lockfile hashes, available tools, CI runner versions, and running concurrent jobs. Refuse a strong receipt without an actual Git worktree. Do not overwrite someone else's uncommitted work. Do not share mutable worktrees across agents running generators.

## 2. Build an impact matrix from source
For each changed file, record: producer, consumers, owner of truth, affected routes/contracts, workflows and their `on`/paths conditions, generated outputs, and release checksums. Expand to direct and transitive consumers for shared contracts, auth/tenant, field/season identity, raster QA, decision referrals, execution receipts and UI/mobile. Mark uninspected dependencies `UNKNOWN`, never `PASS`.

Known SAHOOL classes to check, **only when applicable**:
- Raster field assessment: `services/raster-service/change_detection.py` → `routers/fields.py` → consumers. No common valid pixels must remain `not_assessable`, not a fabricated assessed result.
- DEM/topography: no valid elevations must not become slope zero.
- GIS workflow: `services/gis-workflow-service/self_checks.py` → bundle status → downstream acceptance; required unknown checks must not become success.
- Static outputs: service inventory, capability mapping, decision lineage, execution dependency audit and release checksum manifest. These are generator-owned; inspect generated diffs and do not edit to force green.
- Cross-service: imagery product identity/QA → indicators → vegetation diagnosis → decision-service → execution → outcome; preserve tenant/field/season, provenance and evidence readback.

## 3. Execute in increasing cost and risk
1. **Read-only quick checks:** `git diff --check`, syntax/compile, Ruff check and `ruff format --check` on changed Python files; check for conflicts, unexpected generated changes and dirty tree.
2. **Targeted tests:** negative witness (fails before, passes after), then unit and API/contract tests on both producer and consumer. Use temporary fixtures; record counts and skips.
3. **Generated evidence:** run `bash scripts/ci/preflight.sh --fast` in a clean isolated worktree. **Important:** `--fast` does NOT prove generated artifacts are synchronized; always discover and run the relevant `--check` generators separately, even when only a skill Markdown file changed. The capability-mapping scanner can treat `.claude/skills/*.md` as input evidence, so compare generated mapping on pinned `main` and PR head in separate clean worktrees to attribute baseline versus PR-induced drift. Do not automatically exclude skills from the scanner or edit generated JSON by hand. For changes affecting generators, run the repository's *verified* generation procedure in a disposable worktree, inspect diffs, then apply only authorized outputs. `--fix` is mutating; never run without reviewing its effects.
4. **Broader acceptance:** `bash scripts/ci/preflight.sh`, optionally `--full` if required by changed surfaces, plus all applicable domain-specific workflow commands discovered from the live workflow source. For long suites use adaptive-test-accelerator receipts and bounded resources.
5. **Final read-only checks:** `python scripts/ci/verify_all_generated.py` (read-only default; **no `--check` option**) after staging newly added files in an isolated disposable worktree, because generators use `git ls-files`; `python scripts/release/validate_release_package.py` if release-bound files changed; rerun mandatory workflow-specific gates. No skipped mandatory gate counts as pass.

## 4. Diagnose instead of bypassing
For each failure save `gate → job → command → first causal error → input SHA → owner/generator → negative witness → proposed correction → regression`. Distinguish root failure from cancelled/skipped dependent jobs. Check whether a failure is present on the base branch before attributing it to the PR. Reproduce with the pinned dependency set. Never change CI to suppress a legitimate failure.

## 5. Pre-push decision
Emit one machine-readable receipt with `head`, `tree`, `base`, `merge_base`, changed paths, affected services, discovered gates, command + exit code + elapsed time, tests passed/failed/skipped, generated-diff review, unresolved dependencies, and explicit status `READY_FOR_REMOTE_CI` or `BLOCKED`. Use `READY_FOR_REMOTE_CI` only when all **applicable local** checks passed; it is not merge approval. Treat missing runner/dependency/credentials as `NOT_RUN` and block when mandatory.

## 6. GitHub after push
Fetch PR head and actual GitHub Actions job results; if head changed, invalidate local receipts. Inspect failed job logs and review threads, fix on the same approved branch, and rerun only as appropriate. Merge only after required checks, reviews, branch protections and E2E evidence pass. This skill grants no authority to push, merge, deploy or bypass approvals.

## Skill evaluation before adoption
Run `skill-evaluator` on Arabic and English positive triggers (GIS code edit, generated drift, long CI) and negative triggers (general explanation, unrelated project, no Git checkout). Compare with the existing `preflight.sh` workflow and measure false-positive trigger rate and actual gate coverage. Promote from pilot only with an owner, rollback, evidence and re-evaluation date.
