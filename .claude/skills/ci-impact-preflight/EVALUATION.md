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

## 2. Blind trigger selection (evaluator step 2): RUN 2026-11-09

Procedure: `trigger_eval.py emit --skills-root .claude/skills` → the prompt was given verbatim to a fresh agent with no repository context and no tools (a `Plan` subagent, which does not load CLAUDE.md), its JSON reply saved, then `trigger_eval.py score`. One run per set, one model (the session model); this measures the description layer only, not stability across runs or models.

| Set | Prompt SHA-256 (prefix) | Seed | Result |
|---|---|---|---|
| This skill's 21 cases (`trigger_scenarios.json`) | `05e5b5eb68f9d523` | 11 | **21/21 pass; false triggers on negatives 0/4** |
| Evaluator baseline, 36 cases (`skill-evaluator/assets/trigger_scenarios.json`) | `c5555ba2fd1e40b9` | 5 | **36/36 pass; false triggers on negatives 0/8** — `ci-impact-preflight` was chosen for none of them |

Notable observed choices: `CIP-BND-03` (push timeout) → `safe-delivery` only; `CIP-NEG-01` (concept of a CI gate) → none; `CIP-BND-06` (evaluate this skill) → `skill-evaluator`; adversarial A1–A3 → this skill plus `safe-delivery` or `collaboration-coordination`; baseline `REVIEW-01` and `DELIV-01` unaffected. The author's predicted weak cases did not fail in this run.

## 3. Behaviour with and without the skill (evaluator steps 3-5): RUN 2026-11-09 on P1 and P3

Procedure: four fresh `general-purpose` agents (they load the repository CLAUDE.md, which is the current path), same checkout (`065ec18aa`), same read-only rules (no generators, suites or pushes), identical task text. "With" agents were told to read and follow only `SKILL.md`; "without" agents were told not to open this folder. Outputs were scored against what the case actually requires on this tree.

| Case | Required on this tree | With skill | Without skill |
|---|---|---|---|
| P1 new `.claude/skills/*.md` | stage first; `capability_mapping_engine.py --check` / `verify_all_generated`; `--fast` alone insufficient; release bundle last; the PR must not be report-only | stage first ✔; mapping `--check` ✔ named as main risk; `verify_all_generated --check` ✔; `--fast` insufficient ✔; release bundle — not named; `no_report_only_change_guard` — **missed** | stage first ✔; mapping `--check` ✔ (cited prior commit `0a6744d66`); `verify_all_generated --fix` ✔; release bundle last ✔; **ran `no_report_only_change_guard --stdin`: SKILL.md + regenerated files ⇒ rc=1** ✔; `--fast` insufficient ✔ |
| P3 `gis-workflow-service/self_checks.py` | service pytest as the workflow runs it; consumers outside the service; release checksums/SBOM drift; release bundle last; workflows beyond pytest | service pytest ✔; `passed=None` rule ✔; release checksum line + SBOM ✔; `validate_release_package` ✔; workflows ✔ (gis gates, ci, capability-governance, production gates) | service pytest ✔; **consumer tests outside the service** (`tests/test_gis_truth_boundaries_regression.py`, `tests_v9/test_a6_print_map.py`) ✔ — not named with the skill; checksums + SBOM ✔; runbook §3.16 order with `SOURCE_DATE_EPOCH` ✔; workflows ✔ plus `service-inventory-drift.yml`, `diagnostic-inventory.yml`; `Capability-Impact: NONE` derived ✔ |

Reading (measured on 2 cases, 1 run each — small sample): **no benefit of the skill over the current path was observed.** Both conditions found the core risks; the baseline found items the skill-guided agents missed (the report-only guard on P1; out-of-service consumer tests and two inventory workflows on P3), and the skill-guided agents found nothing the baseline missed except the `passed=None` invariant wording on P3. The current path (CLAUDE.md → runbook → `preflight.sh` messages) already carries this knowledge.

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

## 7. Verdict: advisory pilot, **not ready to merge** (revised 2026-11-09 after the real-agent runs)

- Trigger layer: sound — 21/21 own cases, 36/36 baseline cases, no false triggers, no interference with neighbouring skills (one run, one model).
- Behaviour: the owner's acceptance criterion — demonstrate benefit over the current path — is **not met**. On P1 and P3 the agents without the skill did as well or better.
- Commands: verified against this tree (section 4).

Options for the owner: (a) keep #1354 unmerged; (b) revise SKILL.md to add what the baseline found and the skill missed (report-only guard, out-of-service consumer discovery, inventory workflows, release-bundle order) and rerun the same four-agent comparison plus P2/P4/A1–A3 before deciding; (c) drop the skill. Adoption level per evaluator step 7: `TRIGGER_EVALUATED`, behaviour **not demonstrated**.

Rollback if ever merged: delete `.claude/skills/ci-impact-preflight/` and its test line in `capability-governance.yml`.

## 8. Re-run on v0.3 (2026-11-11): with/without on P1, P2, P3, A1

- **Tree:** `claude/ci-impact-preflight-skill-20261109` with main `ce4b05c46` merged in (`81bf36834`), plus SKILL.md v0.3. v0.3 adds what the 2026-11-09 baseline found and v0.2 missed: consumer search outside the service, non-pytest workflows, the report-only guard, release bundle last, the derived Capability-Impact line and GATE-01 frozen paths.
- **Procedure:** eight fresh `general-purpose` agents (they load CLAUDE.md). Same read-only rules (no generators, suites, preflight or push), identical task text per case. "With" agents read and followed SKILL.md; "without" agents were told not to open this folder. One run each, one model.
- **Rubric:** written before the runs. 1 = named with a concrete command or path, 0.5 = vague, 0 = missing.

| Case | Rubric items | With v0.3 | Without |
|---|---|---|---|
| P1 new `.claude/skills/example/SKILL.md` | stage first · mapping/`verify_all_generated --check` · `--fast` insufficient · release bundle last · report-only guard | 4/5: ran the guard (rc=1 with regenerated files) ✔; **missed the release order** (read the `.claude` release exclusion as "no release work") | 4.5/5: ran the guard ✔ plus remedy; release order ✔; did not say `--fast` is insufficient |
| P2 `raster-service/change_detection.py` | raster suite as CI runs it · consumers outside the service · `not_assessable` · release checksums + order · non-pytest workflows · Capability-Impact derived | 6/6 (the raster capability line measured PASS; execution-audit line drift) | 6/6 (also measured that the branch already failed `validate_release_package`) |
| P3 `gis-workflow-service/self_checks.py` | service pytest · outside consumers · release + last · inventory workflows · Capability-Impact · `passed=None` fails | 6/6 | 5.5/6 (missed `diagnostic-inventory.yml`) |
| A1 "hand-edit the mapping counts" | refuse · regenerate · downstream chain · no push approval | 4/4 | 3.5/4 |
| **Total** | | **20/21** | **19.5/21** |

- **Cost** (subagent totals): with 388.7k tokens / 455 s / 90 tool calls; without 449.1k / 655 s / 115. That is **13% fewer tokens and 31% less time** for the same coverage.
- **Reading:** v0.3 closes the coverage gap measured on 2026-11-09, where the baseline had found more. Both conditions now find the same risks. The measured benefit is efficiency, not extra coverage.
- **Fixed after the run:** the one with-skill miss (release order for a `.claude/` change). Step 6 now says regenerated outputs are release-bound even when the changed file is not. Not re-run.
- **Limits:** one run per cell, one model, four cases. P4, N1-N3, A2 and A3 not run.

## 9. Verdict (2026-11-11)
Adoption level `BEHAVIOUR_COMPARED` for P1-P3 and A1. The skill is an advisory pilot with parity coverage and lower cost; it is not a gate.
- **Merge:** the owner's decision, against the owner's own criterion of benefit over the current path.
- **Rollback:** delete `.claude/skills/ci-impact-preflight/` and its test line in `capability-governance.yml`.
- **Re-evaluation:** when `preflight.sh` or the runbook's section 2 changes.
