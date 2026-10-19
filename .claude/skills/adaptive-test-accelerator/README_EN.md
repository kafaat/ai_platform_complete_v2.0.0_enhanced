# Adaptive Test Accelerator — portable v1.1

A vendor-neutral Skill for safely accelerating slow tests, with optional offline-capable Python 3.10+ standard-library tools. It does not require UWRP, Git, GitHub, a specific agent, or external packages.

- **SKILL.md:** primary guidance and authority limits
- **adapters/AGENT_NEUTRAL_PROMPT_EN.md** or **_AR.md:** copy/paste prompt if your agent cannot load Skills
- **scripts/resource_profile.py:** read-only conservative CPU/RAM/disk worker budget
- **scripts/duration_planner.py:** deterministic duration-aware shard assignment (groups with shared fixture affinity stay together)
- **scripts/checkpoint_runner.py:** opt-in sequential JUnit-based local runner with verified source snapshots, immutable approved plan hash, per-shard receipts, local exclusion lock, atomic state and checksum-linked transitions
- **templates/**: illustrative JSON, replace real input paths, SHA digests, expected tests and base refs before use
- **references/**: framework recipes, validity rules, decision table and authoritative upstream documentation

## Safe CLI lifecycle

From inside the Skill directory:

```sh
python scripts/resource_profile.py --path /absolute/scratch
python scripts/duration_planner.py --durations templates/durations.example.json --shards 2
python scripts/checkpoint_runner.py inspect --plan /path/to/reviewed-plan.json --context /path/to/context.json
# Only after explicit approval of the exact SHA reported by inspect:
python scripts/checkpoint_runner.py run --plan /path/to/reviewed-plan.json --context /path/to/context.json --results /outside/source --approve-plan-sha <reviewed-sha>
python scripts/checkpoint_runner.py status --plan /path/to/reviewed-plan.json --context /path/to/context.json --results /outside/source
```

`inspect` and `status` do not execute tests. The optional local runner refuses shell command plans and secret-bearing context keys. JUnit is required for PASS; nonzero exit, missing JUnit, unexpected skips or mismatched expected test count block reuse. It checks local source identity, **not the remote GitHub/CI state**. Local receipts are not cryptographic attestations or release certificates, and a declared-files inventory may omit relevant dependencies.

No remote write or repo mutation is performed by installation. Follow the repository's gates, test isolation requirements and owner's permissions before execution.
