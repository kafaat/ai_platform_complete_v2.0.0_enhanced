# Agent adapters — optional and version-sensitive (2026-10-19)

**One canonical `work-continuation/SKILL.md`.** All vendor variants are installation pointers, not different policies. Verify each agent version and the actual set of supported skill roots before copying. Never assume a capability merely because a folder was created.

| Environment | Typical discovery route | Portability note |
|---|---|---|
| Codex | `.agents/skills/work-continuation/SKILL.md` where supported; `AGENTS.md` can point to skill | AGENTS.md is project guidance, not the cross-agent protocol itself |
| Claude Code | `.claude/skills/work-continuation/SKILL.md` or corresponding supported personal skills | Cloud containers may be temporary; account installation may differ |
| Kimi Code CLI | `.agents/skills/work-continuation/SKILL.md` or its current recognized user/project directory; inspect the installed version | Kimi CLI documentation has changed between versions; no universal fixed home path |
| OpenCode | `.agents/skills/work-continuation/SKILL.md` or `.opencode/skills/...` | Verify current `skill` support and precedence |
| Generic chat/agent without Skills | Paste `prompts/UNIVERSAL_RESUME_AR.md` or EN; optionally attach state and references | No automatic persistence or execution is inferred |

Do **not** write four different copies with different content. If copying is necessary, verify all `SKILL.md` hashes are identical and revisit on updates. Store the canonical skill outside a project's mutable state; only add a repository-level reference when allowed and review/gates permit. Avoid overwriting existing `AGENTS.md`/`CLAUDE.md` instructions and never commit ephemeral state merely because the skill is installed.

References (official or primary documentation, URLs verified 2026-10-19):
- Agent Skills specification: https://agentskills.io/specification
- OpenAI Skills: https://developers.openai.com/api/docs/guides/tools-skills
- Codex workflow & AGENTS.md: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
- Claude/Codex migration: https://developers.openai.com/cookbook/examples/agents_sdk/migrate-from-claude-agent-sdk/readme
- Kimi Code CLI: https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html
- OpenCode: https://opencode.ai/docs/skills

These references support compatibility patterns, not an assertion that this package was installed or activated in any product account.
