---
name: ci-impact-preflight
description: "Advisory, SAHOOL repo only: before pushing a change (code, contract, docs, skill), find which CI gates, generated artifacts and tests it touches; run them locally. Not a gate or push approval."
metadata:
  version: "0.3.0"
  adoption: "BEHAVIOUR_COMPARED"
  status: "advisory pilot (owner decision 2026-11-09); v0.3 parity coverage, lower cost (2026-11-11 with/without run); see EVALUATION.md"
---
# SAHOOL CI Impact Preflight (advisory pilot)

**What this is:** an advisory checklist for working out *which* checks a change touches, running their real commands locally, and writing a truthful pre-push receipt.

**What this is not:**
- **Not a CI gate.** No workflow runs this skill. Its receipt is never a required check.
- **Not a prediction that CI will pass.** A local green means "what was measured passed". It does not mean GitHub CI will be green or that the change is ready for production. `preflight.sh` says the same about itself.
- **Not a permission.** It grants no authority to push, merge, deploy, edit generated artifacts by hand or bypass any approval. Those decisions belong to the user and project policy (see `safe-delivery` and `change-review`).

## 0. Read the governing sources first
- `docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md`: the authoritative pre-push protocol (its section 2 is now `scripts/ci/preflight.sh`).
- `docs/runbooks/GUARD_CATALOGUE.md` (generated): for each guard, what it enforces, which workflow and job block on it, and its test. Search it for the script name in a failure message.
- `.github/workflows/*.yml` / `*.yaml`, `scripts/ci/preflight.sh`, `docs/architecture/preflight_required.json` (the tests and scripts preflight requires to exist) and `scripts/ci/verify_all_generated.py`.
- Neighbouring skills: `adaptive-test-accelerator` for long or interrupted suites, `failure-investigation` for a failure with unknown cause, `change-review` for reviewing a diff, `safe-delivery` for the push itself.
- Check each CLI option with `--help` or the source before using it. Do not invent flags or assume a documented command still exists.

## 1. Freeze context
Record HEAD, tree, base (normally `origin/main`), merge-base, how far the branch is behind the base, changed files including untracked ones, and Python/Node versions. Refuse a strong receipt without a real Git worktree: `preflight.sh` refuses to run on an archive because generators there fall back to the signed manifest and report a false green. Generators list files with `git ls-files`, so an untracked file is invisible to them. Do not overwrite someone else's uncommitted work. Do not share one mutable worktree between agents running generators.

## 2. Build an impact matrix from source
For each changed file, record: producer, consumers, owner of truth, affected routes/contracts, workflows with their `on`/`paths` conditions, and generated outputs. Mark anything not inspected `UNKNOWN`, never `PASS`.

Read-only helpers:
- `bash scripts/ci/test_impact.sh --plan` (or `python3 scripts/ci/test_impact.py --base origin/main`; printing the plan is its default; `--json` and `--print-paths` exist). It asks the same capability-impact engine the blocking gate uses. It escalates to the **full suite** when a workflow file changes, when the engine flags a governance-wide reference, or when a changed source file maps to no capability, and it lists unresolved paths with `?`. It is a local accelerator, not a gate.
- `python3 scripts/ci/workflow_inventory.py --root .` lists every workflow's triggers, jobs, needs and commands. It does not decide which jobs apply to your change; compare `on`/`paths` with your changed files yourself.

Three searches the 2026-11-09 comparison showed are easy to skip (the agent without this skill did them, the one with v0.2 did not):
- **Consumers outside the changed service.** For each changed module, search every test tree and service, not only its own folder: `git grep -n "<module name or file path>" -- tests tests_v9 services`. Tests that import or read the file from elsewhere (for example `tests/test_gis_truth_boundaries_regression.py` for `gis-workflow-service`) must run too.
- **Workflows that are not pytest.** `git grep -ln "<service folder or file name>" -- .github/workflows` and read each match's `paths:` filter. Inventory and drift workflows (`service-inventory-drift.yml`, `diagnostic-inventory.yml`) react to service changes that no test names.
- **The report-only guard.** A change whose paths are only docs, skills, reports or generated files can be refused as "report only". Run `git diff --name-only origin/main... | python3 scripts/ci/no_report_only_change_guard.py --stdin` before pushing; exit 1 means CI will refuse it.

Known SAHOOL classes, check **only when applicable**:
- Raster field change: `services/raster-service/change_detection.py` to `services/raster-service/routers/fields.py` to consumers. No common valid pixels must stay `not_assessable`, never a made-up assessed result.
- Terrain QA (`services/raster-service/raster_topographic_qa.py`): no supported elevation pixels must give `None` risk values, not zero.
- GIS workflow: `services/gis-workflow-service/self_checks.py`; a required check that could not be evaluated (`passed=None`) must count as failed, not as success.
- Generated outputs (service inventory, capability mapping, decision lineage, execution dependency audit, release checksums) belong to their generators. Inspect generated diffs; never edit them by hand to get a green run.
- Cross-service chains (imagery identity/QA, indicators, vegetation diagnosis, decision service, execution, outcome): keep tenant/field/season, provenance and evidence readback intact.

## 3. Run checks in order of cost
1. **Quick read-only checks:** `git diff --check`; Ruff check and `ruff format --check` on changed Python files; no conflict markers; no unexpected generated changes.
2. **Targeted tests:** a negative witness (fails before, passes after), then unit and API/contract tests for producer and consumer. `pytest -m unit` is the quick local default. Record counts and skips.
3. **Fast static guards:** `bash scripts/ci/preflight.sh --fast` (about 30-60 s). It runs lint and static guards only. It does **not** run `verify_all_generated`, so it does **not** show whether generated artifacts are in sync.
4. **Generated artifacts:** `git add -A` first (generators only see tracked files), then `python3 scripts/ci/verify_all_generated.py --check` (read-only; the same as running it with no flag). Any tracked file the capability-mapping scanner reads changes its counts, including a new Markdown file under `.claude/skills/`. To check only that, run `python3 scripts/ci/capability_mapping_engine.py --check` (about 1 min). Do not exclude files from the scanner to get a green run. To regenerate, use `bash scripts/ci/preflight.sh --fix` or `verify_all_generated.py --fix`. Both write files: review the diff. When merging, resolve generated conflicts by taking `main` and regenerating, never by hand.
5. **Broader local run:** `bash scripts/ci/preflight.sh` (about 7 min: adds `verify_all_generated --check`, `pytest -m unit`, `pytest tests/` and, if the installed FastAPI matches the pin, the platform suite). Use `--full` (about 12 min) when security- or dependency-related files changed: it adds bandit, pip-audit (locally on `requirements_real.txt` only; CI audits more files) and the C-locale run. Use `--pr-body-file <file>` to run the blocking Capability-Impact gate on a PR body. Read the **skipped** count it prints: a skipped step was not measured and is not a pass. Then add the domain-specific workflow commands found in step 2. For long suites use `adaptive-test-accelerator`.
6. **Release-bound files:** if they changed, `python3 scripts/release/validate_release_package.py`. The release package is built **last** because it hashes everything before it (runbook section 3.16): any edit after it, even formatting a test file, makes the release checksums stale again. Regenerated outputs are release-bound even when the file you changed is not (a `.claude/` file is outside the release checksums, but the capability-mapping files it regenerates are inside them).
7. **PR-body gates:** the blocking Capability-Impact gate reads the PR body. Derive the line, do not guess it: `python3 scripts/ci/pr_capability_impact_gate.py --base origin/main --head HEAD --declared "<ids>"` must print `PASS`. A change to a governance-wide file (for example a capability-mapping script) needs `ALL`.
8. **Frozen paths:** if the diff touches a GATE-01 frozen path, `gate01_frozen_path_guard.py` blocks without an issued adjudication and, where policy requires, an owner-signed envelope. See `docs/runbooks/GATE01_OWNER_SIGNING.md`; never rebase or merge the base after the owner signs.

## 4. Diagnose, do not bypass
For each failure record `gate, job, command, first causal error, input SHA, owner/generator, negative witness, proposed fix`. Tell the root failure apart from cancelled or skipped dependent jobs. Check whether the failure also happens on the base before blaming the change. Never change CI to hide a real failure. For an unknown cause, switch to `failure-investigation`.

## 5. Pre-push receipt (advisory)
Report one receipt in the session: `head`, `tree`, `base`, `merge_base`, changed paths, affected services, discovered gates, each command with exit code and time, tests passed/failed/skipped, generated-diff review, unresolved dependencies, and a status:
- `READY_FOR_REMOTE_CI`: every **applicable local** check passed. This is not merge approval and not a prediction that CI will pass.
- `BLOCKED`: something applicable failed, or a mandatory check could not run.
- `NOT_RUN` for any check that lacked a runner, dependency or credential.

The receipt is input for the user's decision. It does not authorise a push.

## 6. After a push (only if the user pushed)
Read the actual GitHub Actions results for the pushed head; if the head changed, local receipts no longer apply. Read failed job logs and review threads and report them. Fixing, re-pushing and merging are the user's decisions, under `safe-delivery` and `change-review`.

## Evaluation status
See `EVALUATION.md` beside this file for what has and has not been measured. Trigger selection ran on 2026-11-09 (21/21 and 36/36). The with/without behaviour comparison ran on 2026-11-11 for P1-P3 and A1: same coverage as the current path (20/21 vs 19.5/21) at 13% fewer tokens and 31% less time, one run each. P4, N1-N3, A2 and A3 are NOT_RUN. It stays an advisory pilot; merging it is the owner's decision.
