# UWRP Portable v3.1 — one protocol, adaptive use

Use the same agent-agnostic workflow in coding, research, documents, creative and operational work. Decide capabilities at runtime; optional vendor adapters explain installation but do not alter the core rules.

Any agent can use `prompts/UNIVERSAL_RESUME_EN.md` as a standalone prompt. Where Agent Skills are supported, copy `work-continuation/` to a *version-confirmed* skills directory (see `references/PROVIDER_ADAPTERS.md`). Do not assume one product layout, Git, CI, a shell, or remote storage.

`SKILL.md` is the short, progressive entrypoint; `templates/` examples are optional, not mandatory forms. `scripts/validate_package.py` and `tests/` provide offline package lint, **not** end-to-end agent acceptance.
