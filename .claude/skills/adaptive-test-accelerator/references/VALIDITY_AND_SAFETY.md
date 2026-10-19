# Validity and safety policy

## Execution validity

- Capture contextual inputs: project ID, source identity/tree, base ref **resolved head** and merge-base (for PR-dependent gates), dependency lock hashes, test collection digest, environment/tool versions, command and test flags, matrix identity, fixtures, and relevant external states.
- Differentiate **fast-changing facts** (GitHub CI status, PR mergeability, deployments) from stable input identity. Read volatile facts fresh before consequential decisions even when a prior receipt matches.
- An environment digest is a scoped hash of deterministic, non-secret configuration; never serialize tokens/DSNs/credentials. Omitted or unknown relevant inputs prevent strong reuse claims.
- For impact selection, track the coverage union and maintain full gate runs where policy requires them. Dynamic imports, subprocesses, snapshot data, and external state may evade test impact analyzers.

## Authority and locks

- This skill **does not grant permission** for push, merge, deploy, delete, credential upload or bypassing test gates.
- Project policies, safety requirements, release standards, and explicit owner approvals take precedence.
- `checkpoint_runner.py` protects only its output path **on one shared filesystem**, via an exclusive local lock. A lock created in another container/filesystem isn't visible; external writers still need remote coordination.
- Never release any stale lock just because it is old or its stored PID does not exist locally. Prove the original holder absent across relevant sessions/hosts and inspect downstream runs; if uncertain, stop.
- Atomic remote reservation example: creating a unique Git reference through the GitHub **Create reference** API fails if the name already exists. This alone is not a distributed lease or fencing mechanism; enforce lease ownership/version on every protected write.

## Interruption, reproducibility, and disk hygiene

- Every shard writes `inflight.json` before launching and a checksummed `receipt.json` only once the process completes and its evidence is parsed. `inflight` without a passing verified receipt => `INTERRUPTED_OR_UNKNOWN`.
- A verified receipt needs the same immutable approved plan digest, context digest, exact command and test definition, exit code, and a valid JUnit report with nonzero **executed** tests. A zero exit code without JUnit is not sufficient for test reuse.
- JUnit XML is not a cryptographic attestation or independent production certification; local fake data can pass syntactic checks. Treat files as evidence requiring provenance and independent trust.
- Keep output logs bounded and **local**, with full-stream digest; consider output sensitive. Scanning/authorization is required before moving anything to a remote store.
- Set explicit limits and a retention policy outside source tree; avoid accidental cache/history pollution. Never silently delete active/pending evidence.
- Test changes to caching and sharding on the same runner/environment, comparing elapsed time, passing tests, missing tests, flaky changes, peak RSS/disk and number of reruns. This skill does not assert a particular speed-up ratio.

## Local implementation v1.1 — proof boundaries

- Before `inspect`, `status`, or `run`, the optional runner verifies either a **clean local Git checkout** at HEAD/tree/base SHA/merge-base, or **only the explicitly declared local files**. For Git, the local base ref can itself be stale vs upstream: refresh from an authorized source separately before decisions that require remote truth.
- `context.verification.root` must be an absolute folder. A Git checkout with uncommitted/untracked changes is refused for HEAD-based reuse. Declared-file checking does not establish an exhaustive dependency graph.
- Every approved plan SHA is bound to the full plan; the effective context hash binds the JSON context plus resolved working directories. A modified plan or context produces a different result namespace.
- The runner requires JUnit with actual testcase records and internally consistent test/error/failure/skipped counts. Default `max_skipped=0`; exceptions require an explicit per-unit integer allowance. Optional `expected_tests` enforces exact count; neither replaces comparison with a frozen collected test-ID inventory. JUnit may represent xfail as skipped; check framework semantics.
- The runner never auto-retries failures or interrupted jobs. `--resume-interrupted` is an operator assertion that the original holder has ceased, and is not a cross-host proof. Locked executions stop until ownership is proven offline.
- Process output is hashed without saving text by default; enabling a tail can expose secrets, so handle it as sensitive. Events form a local checksum chain, **not a signature, immutable audit log, or independently certified evidence**. Do not persist sensitive JUnit files remotely without review.
- Execution inherits only a small reviewed environment allowlist by default; `pass_env` must be reviewed because its values are not persisted into the context. When those variables affect test outcomes, add **non-secret derived digests** to context identity or disable reuse.
- A sequential local runner is not a sandbox. Explicitly approved test code can still access network/files unless the execution environment itself isolates it. Use disposable credentials, network controls and external storage permissions for high-risk tests.
