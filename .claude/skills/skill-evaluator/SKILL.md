---
name: skill-evaluator
description: "Tests an agent skill before adoption: trigger cases, with/without comparison, script review. Use when creating, changing, importing or rolling out a skill. Not for simply using one."
metadata:
  version: "4.2.0"
  package: uwrp-professional
---
# Skill evaluation and adoption gate

**Use when** creating, changing, importing or rolling out an agent skill. **Skip** when simply using an existing skill.

1. **Trigger boundary.** The description is all an agent sees before loading, so it must say what the skill does, when to use it and when not to. Keep it ≤ 200 characters if it will be uploaded to claude.ai (Claude Code allows more).
2. **Measure selection, blind.** Run [`scripts/trigger_eval.py`](scripts/trigger_eval.py) `emit` with [`assets/trigger_scenarios.json`](assets/trigger_scenarios.json) (positive, negative and Arabic cases), give the prompt to a fresh agent, then `score` its reply: pass rate, false triggers on negative cases, per-skill hits. Compare the old and new descriptions on the same seed and on more than one model.
3. **Structure is not behavior.** Static checks (frontmatter, references, digests) say nothing about whether an agent follows the steps.
4. **Behavior with and without the skill** on the same task, model and tools, with versioned prompts and a rubric; blind the review order where possible ([`assets/behavioral-evaluation.example.json`](assets/behavioral-evaluation.example.json), [`assets/skill-eval-suite.example.json`](assets/skill-eval-suite.example.json)). Include adversarial cases: pressure to skip gates, injected handoff instructions, stale base, silent skips, timeout of an external action, stale lock, missing permission, duplicated mirrors, and simple tasks that must not load the skill.
5. Score correctness, time/cost, completeness, reversibility, side-effect violations and false triggers. Keep measured results apart from hypotheses.
6. Treat bundled scripts as **untrusted executable content**: read them, pin provenance, least privilege, disposable environment. Never auto-run an install line from the web.
7. Adoption ladder: `STATIC_VALIDATED` → `BEHAVIOR_EVALUATED` (trigger layer and/or steps, say which) → `PILOT_ACCEPTED` → `OPERATIONAL_APPROVED`, each with owner, rollback, re-evaluation date and the pinned digest. Unit-test counts never promote a skill.

**Authority boundary:** this skill grants no permission to push, merge, deploy, delete, upload or bypass project rules. The user's instructions and project policy win.
