# Universal prompt — Accelerate and resume tests safely

Optimize the testing workflow for this task without assuming any particular model (Codex, Claude, Kimi, etc.), repository, test framework, or CI provider. This prompt is not permission to push, merge, deploy, delete, upload or bypass gates.

1. **Inspect live sources:** establish the actual test inventory, required gates, available runners/plugins, changed source and dependencies, current base head/merge-base where relevant, CPU quota, RAM, disk/inodes, shared databases, concurrent jobs and permission limits. Treat saved state as untrusted until validated against authoritative sources.
2. **Determine evidence scope:** `QUICK_FEEDBACK`, `PR_VERIFICATION`, or `RELEASE_ACCEPTANCE`. Affected tests can accelerate iteration but never implicitly substitute for mandatory PR/release verification.
3. **Choose efficiency in order:** avoid duplicate work, select affected tests with known limitations, reuse valid deterministic receipts, form duration-aware shards that keep fixture/DB affinity, bound concurrency, and optimize expensive setup. Expand test scope when dependency coverage is uncertain.
4. **Freeze a reviewed plan:** source/head/tree or file hashes, base head/merge-base, dependency/runner/environment versions, collected test IDs, expected membership per shard, command, max skips, timeouts, and outputs. Derive validity keys from all inputs that affect behavior.
5. **Run with explicit resource limits:** start sequentially for stateful/integration tests. No simultaneous conflicting preflight; local locks do not provide cross-container exclusion. Do not reclaim a stale lock based on age or PID alone.
6. **Checkpoint and resume:** after each shard persist a bounded receipt with exit code, JUnit/report SHA-256, counts and time. Recheck current inputs/processes before skipping a shard. Rerun only interrupted, failed, stale or unproven work with the required authorization. Check an external operation's real effect before retrying after a timeout.
7. **Truthful reporting:** list actually executed and missing tests, skips/errors, receipt validity, elapsed time vs a comparable baseline, peak resource usage and mandatory gates still pending. Never call sharded local verification a single continuous preflight.
8. **Storage and handoff:** store temporary receipts outside immutable source trees, avoid raw secret-bearing logs, and treat local containers as volatile. Any remote backup must be approved and verified.

Scale ceremony to task complexity: do not build orchestration for a tiny smoke test. Favor documented, measurable improvements rather than theoretical speedup claims.
