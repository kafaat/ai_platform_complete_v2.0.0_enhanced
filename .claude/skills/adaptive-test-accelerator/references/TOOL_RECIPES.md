# Tool recipes — optional, not assumed

Choose only after detecting actual runner and ensuring the project's gates permit the change. Examples are **manual commands**, not performed by this skill.

| Ecosystem | Quick selection (local, partial) | Parallel/balanced full suite | Important limit |
|---|---|---|---|
| pytest | `pytest --testmon` after seeding testmon data; `pytest --lf` re-runs *previous failures*, **not** affected tests | `pytest -n 2 --dist=loadfile` via pytest-xdist; `pytest --store-durations`, then `pytest --splits 3 --group 1` etc using pytest-split | `-n auto` may create too many workers; session fixtures execute per worker; plugin combinations and test order need validation |
| Playwright | explicit file/project filters | `npx playwright test --shard=1/4 --workers=2` etc; use blob reports + `npx playwright merge-reports` | `fullyParallel` changes sharding granularity, and must not violate shared fixtures; shard reports must all be collected |
| Nx monorepo | `nx affected -t test --base=<SHA> --head=<SHA>` | `nx affected -t test --parallel=2`, plus existing cache or CI distribution | Affected is partial by design; base pin, graph and global dependencies matter |
| Vitest | `vitest --changed=<SHA>` | `vitest run` with configured workers; independent CI matrix with verified partition | Changed analysis is not equivalent to required full suite |
| Bazel | `bazel test //...` with correctly declared inputs and cache | remote action cache / tests in configured CI | Cache is only trustworthy for correctly declared hermetic inputs; non-determinism/undeclared inputs undermine it |

## Decision matrix

- **Untrusted, new, or altered shared config:** widen or run full suite; impact-selection-only is insufficient.
- **Heavy service/DB tests, little disk:** `workers=1`, short sequential shards and independent data stores, rather than aggressive parallelism.
- **Independent CPU-heavy tests, ample memory:** compare `-n 1`, `-n 2`, `-n 4` on **equivalent work**, stop increasing when throughput drops.
- **High setup cost per shard:** group tests by fixture/module or use workers with scope affinity; too many shards may increase total time.
- **CI distributed machines:** freeze test membership and compare union against collection; report missing/duplicate tests, skipped/xfail/xpass separately.

## Example: pytest separate receipts

```
pytest tests/unit_a.py -q --junitxml=/outside/tree/run/unit-a.xml
pytest tests/unit_b.py -q --junitxml=/outside/tree/run/unit-b.xml
```

The union of these two commands does not prove that the complete original test suite was executed. Never silently adjust required full preflight/CI gates.

## pytest-split notes

Use `--store-durations` in an environment whose baseline is reasonably representative; `--splitting-algorithm=least_duration` can improve balance but may reorder execution. Its documented `duration_based_chunks` algorithm is incompatible with test-order-randomization plugins unless coordinated, so verify before opting in.
