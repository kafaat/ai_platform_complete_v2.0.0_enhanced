# ci-impact-preflight: evaluation record

- **Date:** 2026-11-09
- **Base:** `origin/main` @ `32b2237458031f4da8c7cb7c202145cf75d10160`, merged into PR #1354's head `13c03fd9e928f81c6320c300b55a34e0db0ac89a` (merge commit `ea1163b28`). Evaluated tree: that merge plus this commit.
- **Owner decision (2026-11-09):** accept as an **advisory pilot**, not a CI gate. Rebuild on main and run the skill-evaluator comparison before promotion or merge.
- **Procedure:** `.claude/skills/skill-evaluator/SKILL.md` v4.2.0, steps 1-7.
- **Evaluator:** one Claude Code agent (Claude Opus 5.5) working in a worktree. It had **no way to start a fresh, blind agent**, so every step that needs a model reply is marked `NOT_RUN` below. Nothing in this file is a measured agent result unless it says "ran".

## 1. Trigger boundary (evaluator step 1): done, static

| Check | Result |
|---|---|
| Frontmatter parses with `trigger_eval.installed_skills`; `name` matches its folder | ran: yes (11 skills installed) |
| Description length (limit 200 for claude.ai upload) | ran: 192 characters (was 164) |
| Says what, when, when not | yes: what = find which CI gates, generated artifacts and tests a change touches; when = before pushing a change in the SAHOOL repo, docs and skills included; not = not a gate, not push approval |

The old description said "not for a documentation-only question". That contradicted pilot case P1 (adding a skill Markdown file is a docs-only change that **does** make generated artifacts drift: see section 4). The new description includes docs and skill changes and keeps conceptual questions out by saying "before pushing a change".

## 2. Blind trigger selection (evaluator step 2): prompts emitted, model run NOT_RUN

`trigger_scenarios.json` (21 cases, beside this file) covers the pilot cases plus the boundary with the neighbouring skills:

- 6 positive (2 Arabic), including P5 as `any_of` with `failure-investigation`
- 3 adversarial (A1-A3)
- 6 boundary cases owned by a neighbour (`failure-investigation`, `adaptive-test-accelerator`, `safe-delivery`, `change-review`, `work-router`, `skill-evaluator`), where choosing this skill counts as a false trigger
- 5 negative (1 Arabic)
- 1 where loading it is optional (N3, no Git checkout)

Ran (deterministic): `trigger_eval.py emit --skills-root .claude/skills --seed 0` with this file and with the evaluator's own `assets/trigger_scenarios.json` (36 cases). Both prompts now list `ci-impact-preflight` among 11 skills. Prompt SHA-256 at this tree: own cases `80bfc3d3…2699595`; baseline cases `263a583a…ebef5b34c929`. The scenario file is validated: every skill it names is installed, and `score` accepts it.

**NOT_RUN:** giving either prompt to a fresh agent and running `score` on the reply. There are no pass rates, false-trigger counts or per-skill hits. The baseline 36-case set also needs a rerun, because adding a skill can change choices on cases that do not mention it (for example `REVIEW-01` "CI was green on the old base…", where this skill is not acceptable).

Author's non-blind prediction, **not a measurement**: the cases most likely to fail are `CIP-BND-03` (push timeout; the description says "before pushing"), `CIP-NEG-01` (names "CI gate"), and baseline `REVIEW-01` / `DELIV-01`. These are the first ones to check when the blind run happens.

Harness observation: `score` counts a negative case as negative only when it has an answer. With an empty reply it printed `false triggers on negatives: 0/0`, so read `negative_cases` together with `cases`.

## 3. Behaviour with and without the skill (evaluator steps 3-5): NOT_RUN

No with-skill or without-skill agent runs were made (no fresh agent, same model and tools). What follows is a **static instruction-coverage comparison**: does the text an agent would read tell it the expected behaviour? The baseline is what an agent has without this skill: `CLAUDE.md`, `scripts/ci/preflight.sh` output, the protocol runbook and the nearest existing skill. Where a command could show the mechanism, it was run.

| Case | Expected | With skill (section) | Baseline without skill | Command evidence |
|---|---|---|---|---|
| P1 new skill `.md` | detect mapping drift | §3.4 says `--fast` does not cover it and names `capability_mapping_engine.py --check` | CLAUDE.md lists generated drift and says to run preflight; `--fast` prints "do not push on this alone" | ran: mapping `--check` exit 1 (drift); `verify_all_generated --check` exit 1 (2 of 75 steps drift); `preflight --fast` exit 0 (section 5): `--fast` alone misses it |
| P2 raster change | consumer contracts; no-valid-pixel stays `not_assessable` | §2 names the chain and the rule | not in CLAUDE.md; `test_impact` gives capability-derived tests | rule present at `change_detection.py:282-296`, `routers/fields.py:1197` |
| P3 GIS self-checks | workflow and release gates, not only pytest | §2, §3.4-3.6 | preflight default tier runs the generated sweep | rule present at `self_checks.py:146-147` |
| P4 shared contract | expand to consumers; unknown is not pass | §2 `UNKNOWN` rule plus `test_impact` | `test_impact` escalates to full suite on unbound sources | ran: `test_impact.sh --plan` escalated (3 reasons) |
| P5 cancelled jobs | first causal failure | §4 | `failure-investigation` | none |
| N1 concept question | no execution | description scoped to "before pushing a change" | n/a | none |
| N2 other repository | no trigger | description says "SAHOOL repo only" | n/a | none |
| N3 no Git checkout | no strong receipt; `NOT_RUN` | §1 | preflight refuses | ran outside a worktree: `preflight.sh` exit 1, `test_impact.sh` exit 2, both say why |
| A1 hand-edit drift | stay blocked | §2, §3.4 "never by hand" | CLAUDE.md: take main and regenerate | not run (a hand edit should fail the generator's `--check`; not tested here) |
| A2 stale base or shared worktree | invalidate; isolate | §1, §6 | preflight step 0 prints "behind N" | ran: merge-base and behind count printed |
| A3 local green, CI pending | not merge-ready | §5 `READY_FOR_REMOTE_CI` is not approval | preflight header: green is not CI green | none |

Reading of the comparison (a hypothesis, not a measurement): most of the expected behaviour is already in the baseline (`CLAUDE.md`, `preflight.sh`, the existing skills). What the skill adds is (a) one English entry point that sends the agent to the right existing tool, (b) the explicit warning that `--fast` does not check generated artifacts, with a one-minute command that does, (c) a few named domain invariants, and (d) a receipt format. Whether agents behave better with it is **unmeasured**.

## 4. Command verification (on this tree)

| Command or path in SKILL.md | Exists | Behaviour as described | How checked |
|---|---|---|---|
| `scripts/ci/preflight.sh --fast` | yes | static guards only; no `verify_all_generated` | ran (section 5); source lines 598-604 |
| `preflight.sh` (default) | yes | adds `verify_all_generated --check`, `-m unit`, `tests/`, platform suite if the FastAPI pin matches | source lines 609-680; **not run** (about 7 min) |
| `preflight.sh --full` | yes | adds bandit, pip-audit (`requirements_real.txt` only), C-locale | source; **not run**. #1354 did not mention the narrower local pip-audit scope; fixed |
| `preflight.sh --fix`, `--pr-body-file` | yes | `git add -A`, `--fix`, then `--check`; blocking Capability-Impact gate on a PR body | source; not run |
| `preflight.sh --help` / unknown flag | yes | exit 0 / exit 2 | ran |
| `bash scripts/ci/test_impact.sh --plan` | yes | plan only; escalates to full suite | ran: exit 0; workflow change plus unbound test, so full suite; 3 changed paths shown as `?` |
| `python3 scripts/ci/test_impact.py --base origin/main` (`--json`, `--print-paths`) | yes | plan by default (`--plan-only` is the real flag; `--plan` works only as an argparse abbreviation) | ran: exit 0; JSON keys present; 2077 paths |
| `python3 scripts/ci/workflow_inventory.py --root .` | yes (#1362) | read-only listing | ran: exit 0; 78 workflows |
| `python3 scripts/ci/verify_all_generated.py --check` | yes | read-only; needs `git add -A` first | ran: before staging, exit 1 in 0.1 s naming the untracked file; after staging, exit 1 in 3 min 43 s, 75 steps from 78 workflows, drift only in `capability_mapping_engine.py --check` and `pr_capability_impact_gate.py --check-index` (expected: generated files are taken from main, and the lead regenerates them) |
| `python3 scripts/ci/capability_mapping_engine.py --check` | yes | about 1 min | ran: exit 1 in 57 s (drift) |
| `python3 scripts/release/validate_release_package.py` | yes | `--root` option | `--help` ran; not run (no release-bound change) |
| `docs/architecture/preflight_required.json` | yes | preflight step 0a checks its paths | source |
| `docs/runbooks/CI_GATES_AND_PRE_PUSH_PROTOCOL.md`, `docs/runbooks/GUARD_CATALOGUE.md` | yes | n/a | exists |
| Domain paths in §2 | yes | rules confirmed at the lines in section 3 | grep and read |

`tests/architecture/test_ci_impact_preflight_skill_mapping.py` now also checks that every backticked repository path in SKILL.md exists, that every flag passed to a `scripts/` command appears in that script's source, that the advisory wording stays and no workflow references the skill, and that the description fits 200 characters.

### Capability-mapping evidence after #1361
Markdown and JSON are still read raw (the comment and fixture filtering in #1361 applies only to Python). Ran `capability_mapping_engine.py --generate` in this worktree only to inspect, then restored the generated files. Result: the skill files add to `files_scanned`, `files_by_kind.other` and `files_by_reading.raw`, and they appear in **no** capability's evidence (no path match in `capability_mapping.json`). Highest per-file scores, against a link threshold of 8, are in section 5. No routes, tables or event subjects are extracted from them.

## 5. Results of this session's runs
All on the evaluated tree, with `pytest -p no:cacheprovider -q`:

- **Capability links of the skill files** (`--generate`, inspected, then restored): 4 files, 0 capability links. `files_scanned` 7086 to 7090, `other` 2152 to 2156, `raw` 3272 to 3276. No file under `docs/capability-registry/generated/` names the skill. Highest capability score per file is 3, against a link threshold of 8 (one domain word each). #1354's SKILL.md reached 6 from two terrain words; the rewrite lowered it to 3. Capability IDs are deliberately not written in this file: the scanner treats an ID in Markdown as an explicit link (+20).
- `tests/architecture/test_ci_impact_preflight_skill_mapping.py` + `tests/architecture/test_capability_mapping_engine.py`: **19 passed** with mapping and impact index regenerated temporarily; **16 passed, 3 failed** with the committed (main) generated files. The 3 failures are generated drift only: `test_skill_files_are_scanned_and_counted_without_hidden_exclusion`, `test_current_impact_index_binds_workflow_sha256`, `test_mapping_has_no_drift`.
- Existing preflight, coverage and skill tests (`tests_v9/test_local_preflight_contract.py`, `tests/architecture/test_arch_test_ci_coverage_guard.py`, `tests_v9/test_test_impact_selector.py`, `tests/architecture/test_pr_capability_impact_gate.py`, `tests_v9/test_work_continuation_checksum_strict.py`, `tests/test_workflow_inventory.py`, `tests_v9/test_capability_mapping_dependency_evidence.py`): **143 passed**.
- `tests_v9/test_text_encoding_locale.py`: 23 passed. The first `preflight --fast` caught #1354's test calling `subprocess.run(text=True)` without `encoding="utf-8"`; fixed.
- `bash scripts/ci/preflight.sh --fast --no-fetch`: **exit 0, failures 0, skipped 2.** The 2 skipped gates are the ruff gates: the installed ruff 0.16.8 differs from the 0.15.8 pin. Ruff 0.15.8 run by hand over the whole tree: `check` clean, `format --check` clean (3887 files). `--fast` did **not** report the capability-mapping drift that `verify_all_generated --check` found, which is the P1 point.

## 6. Not run, and why
- Blind trigger selection by a fresh agent, on both prompt sets and on more than one model: no agent could be started from this session.
- With-skill and without-skill behaviour runs and blind review: same reason.
- `preflight.sh` default and `--full` tiers: about 7 and 12 minutes on a disk shared with two other agents. The lead runs them on the integrated tree.
- Regenerating generated artifacts: owned by the lead, per the session rules.

## 7. Verdict: advisory pilot, **not ready to merge yet**
Ready:
- The text is advisory, correct against the current tree, and guarded by tests.
- It says it is not a gate, that a local green is not CI green, and that it grants no push or merge authority.
- The skill files add no capability evidence.

Two things block merge:
1. **The owner's precondition is not met.** The skill-evaluator comparison has not been run with a real agent. The minimum is the blind trigger run: give the two emitted prompts to a fresh agent and run `trigger_eval.py score`. Then record pass rate and false triggers here. If false triggers appear on the boundary cases, change the description and rerun before merge.
2. **Generated artifacts:** capability mapping (scanned-file counts) and the impact index (workflow SHA) must be regenerated on the final tree. Until then, 3 tests fail, all because of that drift.

Adoption level per evaluator step 7: `STATIC_VALIDATED`. Not `BEHAVIOR_EVALUATED`, so not `PILOT_ACCEPTED` on the evaluator's ladder, even though the owner accepted the advisory-pilot scope.

Owner, rollback (delete `.claude/skills/ci-impact-preflight/` and its test line in `capability-governance.yml`) and a re-evaluation date are still to be assigned.
