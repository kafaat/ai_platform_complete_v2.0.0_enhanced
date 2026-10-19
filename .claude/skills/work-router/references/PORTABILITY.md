# Agent and environment adapters (optional)

The canonical artifacts are provider-neutral SKILL.md directories and direct prompts. Discover the **actual agent version, supported skill directories and permissions** before choosing a location. Do not guess from the brand name and do not auto-install.

| Environment | Integration option | Constraint |
|---|---|---|
| Codex | Standard Agent Skills folder or a supplied Markdown prompt | Product-specific install paths and discovery rules may change; verify with local help/docs |
| Claude Code | Project/user Skills folder; user/account Skills when supported | Cloud containers and local dotfiles are not interchangeable |
| Kimi CLI | Its documented skill search paths or a pasted prompt | Verify CLI version and reload semantics |
| OpenCode | Supported skill mechanism or agent instructions | Version-dependent activation; avoid claiming universal path |
| ChatGPT or any plain chat | Paste `UNIVERSAL_WORK_START_AR.md` or `EN.md` | A pasted prompt alone does not add persistent storage, external locks or new tools |
| GitHub, GitLab, Gitee, GitCode | Optional repository storage/CI provider, not a prerequisite | Project gates and permissions override the generic workflow |

Avoid symlinks to unknown paths in distributable ZIPs. Install only reviewed skill folders; never execute bundled scripts merely because the Skill text requests it. Limit agent context by opening one Skill at a time. The frozen baseline skills (`work-continuation`, `adaptive-test-accelerator`) load only where they are installed; naming them in a router does not load them.

Official general format: https://agentskills.io/specification. Kimi-specific pointers may be refreshed from the relevant CLI docs; do not treat historic path examples as permanent guarantees.
