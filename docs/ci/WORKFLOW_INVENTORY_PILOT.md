# Source-derived CI workflow inventory (pilot)

This is a **read-only inventory tool**, not a new CI approval gate. It inventories every direct `.yml`/`.yaml` file in `.github/workflows` at the checked-out Git revision, including workflow triggers, jobs, needs, reusable-workflow references, commands, explicit test paths, and SHA-256 of each workflow file.

## Usage

```bash
python scripts/ci/workflow_inventory.py --root . > /tmp/sahool-ci-workflows.json
```

Requires PyYAML. It uses `BaseLoader` to preserve the GitHub Actions `on` key and fails closed on invalid or unreadable workflow files. Output is deterministic for an unchanged source tree. Use `--output /tmp/new-inventory.json` only for a **new** path outside the repository; overwriting is deliberately refused.

## Truth and limitations

- Counts are **workflow files**, not PR-triggered runs, expanded matrix jobs, or required branch-protection checks.
- It does not execute tests, follow reusable-workflow chains, inspect dynamic shell invocations, infer missing test coverage, or derive run durations.
- Workflow SHA-256 is a content fingerprint, **not** a cryptographic signature or a CI success receipt.
- Actual test coverage needs the architecture coverage guard, test discovery, and runtime receipts. Mutation sweep and regression tests need separate measured execution.
- CI applicability requires comparing `on` events, paths filters, job conditions and reusable workflow dependencies with changed files; this first version **extracts** those facts but does not claim a sound impact selection.
- Use the existing `scripts/ci/preflight.sh` and `verify_all_generated.py` as project-owned checks. Do not make this inventory a competing source of truth.

## Acceptance status

Pilot implementation only. Test execution, whole-repository count, and cross-check against GitHub Actions are **NOT_RUN** until CI or an authorized clean worktree produces a receipt. The file is intentionally not a generated snapshot committed to the repository.
