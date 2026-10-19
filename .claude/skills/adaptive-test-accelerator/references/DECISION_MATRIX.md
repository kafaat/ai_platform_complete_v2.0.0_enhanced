# Operational decision matrix: accelerate without weakening gates

Choose strategy from actual workload and risk, never from the agent brand.

| User's goal | Data confidence | Resource shape | Recommended lane | Evidence claim |
|---|---|---|---|---|
| Fast feedback on local edit | Proven impact graph, no core config or auth changes | Any | Affected tests + critical smoke | Selected tests only |
| Fast feedback on changed shared fixtures/migrations/auth | Impact graph incomplete | Any | Broader suite/full mandatory suites | Exactly what was executed |
| 20-min suite repeatedly interrupted | Stable test collection and reports | Tight/time-limited | 2–5-minute sequential fixed-file shards, receipts and resume | Local sharded verification |
| Large CPU-bound independent unit suite | Reliable isolation, sufficient CPU/memory | High | Duration-balanced shards + small `xdist` pool | Verified union of shards only |
| High setup/DB/PGlite tests | Shared services or coupled fixtures | Low disk or limited DB | Group by fixture/DB and start one worker | Receipted batches, isolation limits |
| Browser E2E | Isolated tenants/browser contexts | CI workers | Playwright sharding and blob report merge | Test matrix covered only after every report present |
| Release/prod acceptance | Mandatory gates | Any | All required gates in policy, including required continuous preflight if specified | Release claim only from authoritative gate |

### Duration vs. throughput

- Measure: total wall time, median/p95 shard duration, setup/import time, peak RSS, disk free and inode headroom, DB contention, retry/flakiness and coverage union.
- Only compare *same collected tests and equivalent environments*. A partial impacted run should not be compared directly to a full-suite baseline as a speedup.
- Number of workers must be chosen against CPU quotas and available memory, not only `os.cpu_count()`.
- Lockstep test-count partition is different from duration balance. Preserve affinity groups for stateful fixtures.
- Selection and caching are two different decisions: Nx explicitly documents that task `inputs` affect which tasks count as affected, even without cache hits.

### Hard invalidation triggers

- HEAD/tree changes, changed local base ref/merge-base, dependency lock changes, runner flags, test inventory, test fixtures, DB schema/image, environment/toolchain, architecture and external service state.
- The local Git checker cannot establish that the remote `main` or PR state stayed unchanged. Refresh the remote authoritative state before merges/deploys or time-sensitive decisions.
- Contexts with partial declared-file inventories verify only those files. Do not claim hermeticity or automatically reuse across unrelated environments.

### Dangerous shortcuts

Never disable tests in CI to show faster green checks, lower coverage ratchets, treat skipped tests as passed without policy, run `pytest -n auto` on constrained hosts without measurement, or delete raw evidence required for auditing. The plugin/docs can optimize the organization of work; they do not grant new permissions.
