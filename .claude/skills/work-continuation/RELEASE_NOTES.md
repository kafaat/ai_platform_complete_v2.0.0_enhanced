# Release notes — UWRP v3

Release date: 2026-10-19.

Source inspiration and primary references are recorded in `references/RESEARCH_AND_DECISIONS.md`. This release adds no external service integration, no background agent, no source repository edits, and no automatic actions. It includes a read-only structural checker and synthetic data examples, not production acceptance tests.

Regression guard: `references/PROTOCOL_v2_1_ORIGINAL.md` SHA-256 must be `98b78578924584b550addc0f6bfc05e58ab3fa07c1bbbff07154a52008ddae2c`.

Usage: `prompts/RESUME_AR.md` or `prompts/RESUME_EN.md`, or invoke `/work-continuation` where installed and supported.

Security: run a real secrets/privacy scanner and repository gates before publishing this Skill. The included read-only validator is a first-pass check, **not a substitute** for repository-specific gates. There is no implicit permission to push, merge, deploy or upload a backup.
