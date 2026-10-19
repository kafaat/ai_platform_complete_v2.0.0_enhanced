# UWRP v3 — Universal Work Continuation & Recovery

A portable Agent Skill for resuming long-running, multi-session or multi-agent work from *verified evidence*, rather than agent memory. It provides a short trigger prompt, modular rules, data templates, and a read-only checker. This is a policy and contract toolkit—not an implementation of a durable workflow engine or global distributed lock.

## Quick use

> Resume from the last evidence-verified checkpoint. Apply `work-continuation` (UWRP v3), verify the actual sources, invalidate stale test results, preserve each completed receipt, reconcile uncertain external effects, and only back up with authorization after scanning and remote verification.

## Deployment

- Copy the **folder** to `.claude/skills/work-continuation/` in a project (via its normal PR checks), or install the zip through an eligible personal Skills UI. Other agents need their documented skill loader.
- Do not commit active work-state, raw logs, tokens, or private data into a source repository. A private durable state store is recommended when authorized.
- Repository rules and explicit user authority take precedence. The skill never grants permission to push, merge, deploy, delete, or upload.
- Consult `README_AR.md` for the full guide; `references/RESEARCH_AND_DECISIONS.md` provides primary sources.

## Validation

Run `python3 work-continuation/scripts/validate_package.py` and `python3 -m unittest discover -s work-continuation/tests -v` from the unpacked parent directory. Tests do not require GitHub or network access.
