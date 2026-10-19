# Changelog

## v4.2.0 — 2026-10-19

- Each of the 8 skills is self-contained: its templates moved into its own `assets/`, and no link leaves the skill folder. One skill can be installed alone.
- Descriptions are ≤ 200 characters, state when to use and when not to, and carry only frontmatter keys claude.ai accepts on upload.
- `work-router` is the package hub. `references/routing.json` is the single routing table; `scripts/route_work.py` reads it and reports suggested skills that are not installed.
- `intent-to-proof`: work contract v2 (requirements → tasks → evidence) and `scripts/check_contract.py`. The checker refuses VERIFIED without evidence, PASS without an exit code or ref, cycles and two writers per resource, and reports evidence closure, optionally as a gate.
- `change-review`: the review runs from the diff, the contract and the gates only, in a fresh context where the agent supports it.
- `skill-evaluator`: `scripts/trigger_eval.py` plus 36 trigger scenarios (8 negative, 6 Arabic). Run blind on two Claude models; results in `references/EVALUATION_RESULTS.md`.
- One verifier, `scripts/verify_pack.py`, replaces v4.1's two disagreeing validators. It also checks the frozen baselines against pinned digests.
- Baselines unchanged: UWRP Portable v3.1 and Adaptive Test Accelerator v1.1. The v4.1 archive is kept as received (`2e178008…`).

## v4.1.0 — 2026-10-19 (owner release)

- Eight SKILL.md modules, an advisory router, a source register, templates and structural tests; v3.1 and ATA v1.1 kept as frozen archives.
- Reconciled the v4 manifest and report, added the provider-discovery guide and the adoption gate.
